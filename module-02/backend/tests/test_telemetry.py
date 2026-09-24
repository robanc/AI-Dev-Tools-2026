from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest
from fastapi.testclient import TestClient
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy.exc import OperationalError

from app import telemetry
from app.main import create_app


ATTRIBUTES = {"service.name": "pairroom-backend", "deployment.environment.name": "local",
              "service.version": "test-release"}


@pytest.fixture
def signals(monkeypatch):
    spans, metrics, logs = InMemorySpanExporter(), InMemoryMetricReader(), InMemoryLogRecordExporter()
    runtime = telemetry.Telemetry(ATTRIBUTES, spans, metrics, logs)
    monkeypatch.setattr(telemetry, "configure", lambda: runtime)
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        yield client, runtime, spans, metrics, logs


def snapshot(runtime, spans, metrics, logs):
    assert runtime.traces.force_flush(2000)
    assert runtime.logs.force_flush(2000)
    return (spans.get_finished_spans(), metrics.get_metrics_data(), logs.get_finished_logs())


def test_request_and_session_signals_are_correlated(signals):
    client, runtime, spans, metrics, logs = signals
    assert client.post('/sessions').status_code == 201
    assert client.get('/health').json() == {'status': 'ok'}
    traces, data, records = snapshot(runtime, spans, metrics, logs)
    creation = next(span for span in traces if span.name == 'pairroom.session.create')
    request = next(span for span in traces if span.name == 'POST /sessions')
    assert creation.parent.span_id == request.context.span_id
    assert creation.context.trace_id == request.context.trace_id
    record = next(item for item in records if item.log_record.body == 'session.created')
    assert record.log_record.trace_id == creation.context.trace_id
    assert record.log_record.span_id == creation.context.span_id
    for span in traces:
        assert dict(span.resource.attributes) == ATTRIBUTES
    for record in records:
        assert dict(record.resource.attributes) == ATTRIBUTES
    for resource in data.resource_metrics:
        assert dict(resource.resource.attributes) == ATTRIBUTES
    collected = {metric.name: metric for resource in data.resource_metrics
                 for scope in resource.scope_metrics for metric in scope.metrics}
    assert sum(p.value for p in collected['pairroom.sessions.created'].data.data_points) == 1
    assert sum(p.value for p in collected['pairroom.http.requests'].data.data_points) == 2
    assert sum(p.count for p in collected['http.server.request.duration'].data.data_points) == 2


def test_secrets_paths_payloads_and_exception_details_are_not_exported(signals, monkeypatch):
    client, runtime, spans, metrics, logs = signals
    link = client.post('/sessions').json()['interviewerLink']
    session_id, token = link.split('/')[2:]
    path = '/sessions/' + session_id
    headers = {'Authorization': 'Bearer ' + token, 'Cookie': 'private-cookie',
               'X-Private': 'private-header'}
    assert client.put(path + '/code?secret=private-query', headers=headers,
                      json={'code': 'private-code'}).status_code == 200
    assert client.put(path + '/problem', headers=headers,
                      json={'problem': 'private-problem'}).status_code == 200
    assert client.get('/private-unknown-path?token=private-query').status_code == 404

    def fail():
        raise OperationalError('private-sql', {}, Exception('private-password'))

    monkeypatch.setattr(client.app.state.store, 'create', fail)
    assert client.post('/sessions').status_code == 500
    monkeypatch.setattr(client.app.state.database.engine, 'connect', fail)
    response = client.get('/health')
    assert response.status_code == 503
    assert response.json() == {'status': 'unavailable'}
    traces, data, records = snapshot(runtime, spans, metrics, logs)
    serialized = '\n'.join([*(span.to_json() for span in traces), data.to_json(),
                            *(record.to_json() for record in records)])
    for secret in [session_id, token, link, 'private-cookie', 'private-header', 'private-query',
                   'private-code', 'private-problem', 'private-unknown-path', 'private-sql',
                   'private-password']:
        assert secret not in serialized
    assert any(span.status.status_code.name == 'ERROR' for span in traces)
    assert all(not span.events for span in traces)
    assert any(record.log_record.body == 'session.creation.failed' for record in records)


@pytest.mark.parametrize('environment', ['local', 'development', 'production'])
def test_resource_configuration(environment):
    version = 'sha256:' + 'a' * 64
    result = telemetry.resource_attributes({
        'OTEL_SERVICE_NAME': 'custom-service',
        'OTEL_RESOURCE_ATTRIBUTES': f'deployment.environment.name={environment},service.version={version},secret=excluded',
    })
    assert result == {'service.name': 'custom-service', 'deployment.environment.name': environment,
                      'service.version': version}


def test_disabled_by_default_and_sdk_disable(monkeypatch):
    monkeypatch.delenv('PAIRROOM_TELEMETRY_ENABLED', raising=False)
    monkeypatch.setattr(telemetry, 'Telemetry', lambda *a: pytest.fail('SDK must not initialize'))
    assert telemetry.configure() is None
    monkeypatch.setenv('PAIRROOM_TELEMETRY_ENABLED', 'true')
    monkeypatch.setenv('OTEL_SDK_DISABLED', 'true')
    assert telemetry.configure() is None


@pytest.mark.parametrize('attributes,endpoint', [
    ('', 'http://localhost:4318'),
    ('deployment.environment.name=production', 'http://localhost:4318'),
    ('deployment.environment.name=local,service.version=test', 'http://user:private-password@localhost:4318'),
])
def test_invalid_configuration_preserves_health(monkeypatch, caplog, attributes, endpoint):
    monkeypatch.setenv('PAIRROOM_TELEMETRY_ENABLED', 'true')
    monkeypatch.delenv('OTEL_SDK_DISABLED', raising=False)
    monkeypatch.setenv('OTEL_RESOURCE_ATTRIBUTES', attributes)
    monkeypatch.setenv('OTEL_EXPORTER_OTLP_ENDPOINT', endpoint)
    with TestClient(create_app()) as client:
        assert client.app.state.telemetry is None
        assert client.get('/health').json() == {'status': 'ok'}
    assert 'private-password' not in caplog.text


def test_exporter_failures_do_not_change_requests(signals, monkeypatch):
    client, runtime, spans, metrics, logs = signals
    def fail(*args, **kwargs):
        raise ConnectionError('Collector unavailable')
    monkeypatch.setattr(spans, 'export', fail)
    monkeypatch.setattr(logs, 'export', fail)
    assert client.post('/sessions').status_code == 201
    runtime.traces.force_flush(2000)
    runtime.logs.force_flush(2000)
    assert client.get('/health').json() == {'status': 'ok'}
    monkeypatch.setattr(runtime.requests, 'add', fail)
    assert client.post('/sessions').status_code == 201


def test_repeated_app_lifecycles_do_not_duplicate_signals(monkeypatch):
    runtimes = []
    def configure():
        spans = InMemorySpanExporter()
        runtime = telemetry.Telemetry(ATTRIBUTES, spans, InMemoryMetricReader(), InMemoryLogRecordExporter())
        runtimes.append((runtime, spans))
        return runtime
    monkeypatch.setattr(telemetry, 'configure', configure)
    for _ in range(2):
        with TestClient(create_app()) as client:
            assert client.get('/health').status_code == 200
            runtime = client.app.state.telemetry
            assert runtime.traces.force_flush(2000)
            assert len(runtimes[-1][1].get_finished_spans()) == 1
        assert runtime.metrics._shutdown
    assert runtimes[0][0] is not runtimes[1][0]


def test_otlp_configuration_uses_three_signal_paths(monkeypatch):
    monkeypatch.setenv('PAIRROOM_TELEMETRY_ENABLED', 'true')
    monkeypatch.delenv('OTEL_SDK_DISABLED', raising=False)
    monkeypatch.setenv('OTEL_RESOURCE_ATTRIBUTES', 'deployment.environment.name=local,service.version=unreleased')
    monkeypatch.setenv('OTEL_EXPORTER_OTLP_ENDPOINT', 'http://localhost:4318/')
    calls = []
    def exporter(**kwargs):
        calls.append(kwargs)
        return object()
    for name in ['OTLPSpanExporter', 'OTLPMetricExporter', 'OTLPLogExporter']:
        monkeypatch.setattr(telemetry, name, exporter)
    monkeypatch.setattr(telemetry, 'PeriodicExportingMetricReader', lambda *a, **kw: object())
    monkeypatch.setattr(telemetry, 'Telemetry', lambda *a: a)
    result = telemetry.configure()
    assert result[0]['service.name'] == 'pairroom-backend'
    assert {call['endpoint'] for call in calls} == {
        'http://localhost:4318/v1/' + signal for signal in ['traces', 'metrics', 'logs']}
    assert all(call['timeout'] == 2 for call in calls)


def test_websocket_behavior_and_payload_exclusion(signals):
    client, runtime, spans, metrics, logs = signals
    link = client.post('/sessions').json()['interviewerLink']
    session_id, token = link.split('/')[2:]
    with client.websocket_connect('/sessions/' + session_id + '/ws',
                                  headers={'Origin': 'http://localhost:5173'}) as socket:
        socket.send_json({'type': 'authenticate', 'token': token})
        assert socket.receive_json()['type'] == 'snapshot'
        socket.send_json({'type': 'ping'})
        assert socket.receive_json() == {'type': 'pong'}
    traces, _, records = snapshot(runtime, spans, metrics, logs)
    assert len(traces) == 2  # HTTP creation and its child operation; no frame spans.
    assert token not in str(records)


def test_real_otlp_exporters_send_all_signals_to_local_receiver(monkeypatch):
    received = []
    class Receiver(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append((self.path, self.headers['Content-Type'],
                             self.rfile.read(int(self.headers['Content-Length']))))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Receiver)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv('PAIRROOM_TELEMETRY_ENABLED', 'true')
    monkeypatch.delenv('OTEL_SDK_DISABLED', raising=False)
    monkeypatch.setenv('OTEL_RESOURCE_ATTRIBUTES', 'deployment.environment.name=local,service.version=wire-test')
    monkeypatch.setenv('OTEL_EXPORTER_OTLP_ENDPOINT', f'http://127.0.0.1:{server.server_port}')
    try:
        with TestClient(create_app()) as client:
            link = client.post('/sessions').json()['interviewerLink']
            assert client.get('/health?secret=wire-private').status_code == 200
            runtime = client.app.state.telemetry
            assert runtime.traces.force_flush(2000)
            assert runtime.logs.force_flush(2000)
            assert runtime.metrics.force_flush(2000)
        assert {path for path, _, _ in received} == {'/v1/traces', '/v1/metrics', '/v1/logs'}
        for _, content_type, body in received:
            assert content_type == 'application/x-protobuf'
            assert b'wire-test' in body
            assert b'wire-private' not in body
            assert link.encode() not in body
            assert link.split('/')[-1].encode() not in body
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_metric_export_failure_does_not_change_health(monkeypatch):
    from opentelemetry.sdk.metrics.export import MetricExporter, MetricExportResult, PeriodicExportingMetricReader

    class FailingExporter(MetricExporter):
        def export(self, metrics_data, timeout_millis=10000, **kwargs):
            return MetricExportResult.FAILURE

        def force_flush(self, timeout_millis=10000):
            return False

        def shutdown(self, timeout_millis=30000, **kwargs):
            pass

    runtime = telemetry.Telemetry(ATTRIBUTES, InMemorySpanExporter(),
                                  PeriodicExportingMetricReader(FailingExporter()), InMemoryLogRecordExporter())
    monkeypatch.setattr(telemetry, 'configure', lambda: runtime)
    with TestClient(create_app()) as client:
        assert client.post('/sessions').status_code == 201
        runtime.metrics.force_flush(2000)
        assert client.get('/health').json() == {'status': 'ok'}


def test_database_startup_failure_shuts_down_telemetry(monkeypatch):
    runtime = telemetry.Telemetry(ATTRIBUTES, InMemorySpanExporter(), InMemoryMetricReader(),
                                  InMemoryLogRecordExporter())
    monkeypatch.setattr(telemetry, 'configure', lambda: runtime)
    with pytest.raises(Exception):
        with TestClient(create_app(database_url='not-a-database-url')):
            pass
    assert runtime.metrics._shutdown
