"""Opt-in OTLP telemetry. Only fixed event names and allowlisted fields leave the app."""
import logging
import os
import time
from contextlib import contextmanager
from urllib.parse import urlsplit

from opentelemetry import trace
from opentelemetry._logs import SeverityNumber
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import SpanKind, StatusCode


logger = logging.getLogger(__name__)
ROUTES = frozenset({"/health", "/sessions", "/sessions/{sessionId}",
                    "/sessions/{sessionId}/problem", "/sessions/{sessionId}/code"})
METHODS = frozenset({"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"})


def resource_attributes(environ):
    supplied = dict(item.strip().split("=", 1) for item in
                    environ.get("OTEL_RESOURCE_ATTRIBUTES", "").split(",") if "=" in item)
    # Do not auto-detect host/process data or forward arbitrary resource attributes.
    attributes = {
        "service.name": environ.get("OTEL_SERVICE_NAME") or "pairroom-backend",
        "deployment.environment.name": supplied.get("deployment.environment.name", ""),
        "service.version": supplied.get("service.version", ""),
    }
    if attributes["deployment.environment.name"] not in {"local", "development", "production"}:
        raise ValueError("An explicit telemetry environment is required")
    if not attributes["service.version"].strip():
        raise ValueError("An explicit telemetry version is required")
    return attributes


def safely(action):
    """Telemetry failures must not change a request's result or expose error details."""
    try:
        return action()
    except Exception:
        logger.warning("Telemetry operation failed; application behavior is unchanged.")
        return None


class Telemetry:
    def __init__(self, attributes, span_exporter, metric_reader, log_exporter):
        resource = Resource(attributes)
        self.traces = TracerProvider(resource=resource, shutdown_on_exit=False)
        self.traces.add_span_processor(BatchSpanProcessor(
            span_exporter, max_queue_size=512, max_export_batch_size=128,
            schedule_delay_millis=1000, export_timeout_millis=2000))
        self.metrics = MeterProvider(resource=resource, metric_readers=[metric_reader],
                                     shutdown_on_exit=False)
        self.logs = LoggerProvider(resource=resource, shutdown_on_exit=False)
        self.logs.add_log_record_processor(BatchLogRecordProcessor(
            log_exporter, max_queue_size=512, max_export_batch_size=128,
            schedule_delay_millis=1000, export_timeout_millis=2000))
        self.tracer = self.traces.get_tracer("pairroom.backend")
        self.log = self.logs.get_logger("pairroom.backend")
        meter = self.metrics.get_meter("pairroom.backend")
        self.requests = meter.create_counter("pairroom.http.requests", unit="{request}")
        self.duration = meter.create_histogram("http.server.request.duration", unit="s")
        self.sessions = meter.create_counter("pairroom.sessions.created", unit="{session}")
        self.failures = meter.create_counter("pairroom.sessions.creation.failures", unit="{error}")

    def event(self, name, attributes):
        # No root logging handler: third-party logs and exception text are never bridged.
        safely(lambda: self.log.emit(body=name, severity_number=SeverityNumber.INFO,
                                     attributes=attributes))

    @contextmanager
    def session_creation(self):
        span = safely(lambda: self.tracer.start_span("pairroom.session.create"))
        with trace.use_span(span or trace.INVALID_SPAN, end_on_exit=False,
                            record_exception=False, set_status_on_exception=False):
            try:
                yield
            except BaseException:
                if span:
                    safely(lambda: span.set_status(StatusCode.ERROR))
                safely(lambda: self.failures.add(1))
                self.event("session.creation.failed", {"outcome": "error"})
                raise
            else:
                safely(lambda: self.sessions.add(1))
                self.event("session.created", {"outcome": "success"})
            finally:
                if span:
                    safely(span.end)

    def shutdown(self):
        safely(lambda: self.traces.force_flush(timeout_millis=2000))
        safely(lambda: self.logs.force_flush(timeout_millis=2000))
        safely(self.traces.shutdown)
        safely(lambda: self.metrics.shutdown(timeout_millis=2000))
        safely(self.logs.shutdown)


def configure():
    if (os.getenv("PAIRROOM_TELEMETRY_ENABLED", "false").lower() != "true"
            or os.getenv("OTEL_SDK_DISABLED", "false").lower() == "true"):
        return None

    def build():
        attributes = resource_attributes(os.environ)
        endpoint = os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"].rstrip("/")
        url = urlsplit(endpoint)
        if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError("Invalid OTLP base endpoint")
        # Explicit timeouts avoid default retries delaying application shutdown indefinitely.
        return Telemetry(
            attributes,
            OTLPSpanExporter(endpoint=endpoint + "/v1/traces", timeout=2),
            PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=endpoint + "/v1/metrics", timeout=2),
                export_interval_millis=30000, export_timeout_millis=2000),
            OTLPLogExporter(endpoint=endpoint + "/v1/logs", timeout=2),
        )

    return safely(build)


class TelemetryMiddleware:
    """HTTP-only ASGI wrapper: never read bodies, headers, URLs or WebSocket frames."""
    def __init__(self, app, owner):
        self.app, self.owner = app, owner

    async def __call__(self, scope, receive, send):
        telemetry = getattr(self.owner.state, "telemetry", None)
        if scope["type"] != "http" or telemetry is None:
            await self.app(scope, receive, send)
            return
        method = scope.get("method")
        method = method if method in METHODS else "_OTHER"
        span = safely(lambda: telemetry.tracer.start_span("HTTP request", kind=SpanKind.SERVER))
        started, status = time.perf_counter(), 500

        async def observed_send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        with trace.use_span(span or trace.INVALID_SPAN, end_on_exit=False,
                            record_exception=False, set_status_on_exception=False):
            try:
                await self.app(scope, receive, observed_send)
            finally:
                route = getattr(scope.get("route"), "path", None)
                route = route if route in ROUTES else "unmatched"
                attributes = {"http.request.method": method, "http.route": route,
                              "http.response.status_code": status}
                if span:
                    safely(lambda: span.update_name(f"{method} {route}"))
                    safely(lambda: span.set_attributes(attributes))
                    if status >= 500:
                        safely(lambda: span.set_status(StatusCode.ERROR))
                safely(lambda: telemetry.requests.add(1, attributes))
                safely(lambda: telemetry.duration.record(time.perf_counter() - started, attributes))
                telemetry.event("http.request.completed", attributes)
                if span:
                    safely(span.end)
