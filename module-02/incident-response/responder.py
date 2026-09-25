"""Local, read-only PairRoom incident evidence and policy helpers."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
INCIDENT_ID = re.compile(r"INC-[0-9]{4}-[0-9]{3}\Z")
TRACE_ID = re.compile(r"[0-9a-fA-F]{32}\Z")
SAFE_VERSION = re.compile(r"(?:sha256:[0-9a-f]{64}|[0-9a-f]{7,40}|unreleased)\Z")
SAFE_ROUTE = re.compile(r"/[A-Za-z0-9_{}./-]{0,120}\Z")
SAFE_EVENTS = {"http.request.completed", "session.created", "session.creation.failed"}
PROM_QUERY = (
    'sum by (service_name,deployment_environment_name,service_version,http_route,'
    'http_response_status_code) (increase(pairroom_http_requests_total{'
    'service_name="pairroom-backend",http_route!="/health"}[5m]))'
)
LOKI_QUERY = '{service_name="pairroom-backend"} |~ "http.request.completed|session.created|session.creation.failed"'


def _check_incident(value: str) -> str:
    if not INCIDENT_ID.fullmatch(value):
        raise ValueError("incident ID must match INC-YYYY-NNN")
    return value


def _loopback_base(name: str, default: str) -> str:
    value = os.getenv(name, default).rstrip("/")
    parsed = urllib.parse.urlsplit(value)
    if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username or parsed.password or parsed.path not in {"", "/"}
            or parsed.query or parsed.fragment):
        raise ValueError(f"{name} must be a plain HTTP loopback base URL")
    return value


def _get_json(url: str, timeout: float = 3.0):
    request = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
    class DenyRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, new_url):
            return None

    opener = urllib.request.build_opener(DenyRedirect)
    with opener.open(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError("read-only evidence query did not return HTTP 200")
        return json.load(response)


def _safe_route(value):
    if isinstance(value, str) and SAFE_ROUTE.fullmatch(value) and ".." not in value:
        return value
    return "unmatched"


def _safe_labels(labels):
    labels = labels if isinstance(labels, dict) else {}
    service = labels.get("service_name", labels.get("service.name", "pairroom-backend"))
    env = labels.get("deployment_environment_name", labels.get("deployment.environment.name", "unknown"))
    version = labels.get("service_version", labels.get("service.version", "unknown"))
    status = labels.get("http_response_status_code", labels.get("http.response.status_code", ""))
    return {
        "service_name": service if service == "pairroom-backend" else "pairroom-backend",
        "deployment_environment_name": env if env in {"local", "development", "production"} else "unknown",
        "service_version": version if SAFE_VERSION.fullmatch(str(version)) else "unknown",
        "http_route": _safe_route(labels.get("http_route", labels.get("http.route"))),
        "http_response_status_code": str(status) if str(status).isdigit() and 100 <= int(status) <= 599 else "",
    }


def _field(obj, names):
    """Find a known attribute key recursively without retaining other input fields."""
    if isinstance(obj, dict):
        for key in names:
            if key in obj:
                return obj[key]
        for value in obj.values():
            found = _field(value, names)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = _field(value, names)
            if found is not None:
                return found
    return None


def _safe_logs(payload):
    results = payload.get("data", {}).get("result", []) if isinstance(payload, dict) else []
    records, trace_ids = [], set()
    for stream in results[:100]:
        labels = _safe_labels(stream.get("stream", {}))
        for entry in stream.get("values", [])[:100]:
            if not isinstance(entry, list) or len(entry) < 2:
                continue
            message = entry[1]
            metadata = entry[2] if len(entry) > 2 and isinstance(entry[2], dict) else {}
            event = message
            if isinstance(message, str):
                try:
                    parsed = json.loads(message)
                    event = _field(parsed, ["body", "event", "message"]) or message
                    metadata = {**parsed, **metadata}
                except (ValueError, TypeError):
                    pass
            if event not in SAFE_EVENTS:
                continue
            record = {
                "event": event,
                "service_name": labels["service_name"],
                "deployment_environment_name": labels["deployment_environment_name"],
                "service_version": labels["service_version"],
                "http_route": _safe_route(_field(metadata, ["http.route", "http_route"])),
                "http_response_status_code": str(_field(metadata, ["http.response.status_code", "http_response_status_code"]) or ""),
            }
            trace_id = _field(metadata, ["trace_id", "traceId"])
            if isinstance(trace_id, str) and TRACE_ID.fullmatch(trace_id):
                record["trace_id"] = trace_id.lower()
                trace_ids.add(trace_id.lower())
            records.append(record)
    return records[:100], sorted(trace_ids)[:20]


def collect(incident_id: str, version: str):
    _check_incident(incident_id)
    if not SAFE_VERSION.fullmatch(version):
        raise ValueError("deployed version must be an immutable digest, commit ID, or unreleased")
    prom = _loopback_base("PAIRROOM_PROMETHEUS_URL", "http://127.0.0.1:9090")
    loki = _loopback_base("PAIRROOM_LOKI_URL", "http://127.0.0.1:3100")
    tempo = _loopback_base("PAIRROOM_TEMPO_URL", "http://127.0.0.1:3200")
    end = datetime.now(timezone.utc).timestamp()
    start = end - 300
    metrics, logs, traces, errors = [], [], [], []
    try:
        query = urllib.parse.urlencode({"query": PROM_QUERY, "time": str(end)})
        result = _get_json(f"{prom}/api/v1/query?{query}")
        for item in result.get("data", {}).get("result", [])[:100]:
            labels = _safe_labels(item.get("metric", {}))
            raw_value = item.get("value", [None, ""])[1]
            try:
                value = float(raw_value)
                if value >= 0:
                    metrics.append({**labels, "request_count_5m": value})
            except (ValueError, TypeError, IndexError):
                continue
    except (OSError, ValueError, RuntimeError, urllib.error.URLError):
        errors.append("prometheus_unavailable")
    try:
        params = urllib.parse.urlencode({"query": LOKI_QUERY, "start": str(int(start * 1e9)),
                                        "end": str(int(end * 1e9)), "limit": "100"})
        log_payload = _get_json(f"{loki}/loki/api/v1/query_range?{params}")
        logs, trace_ids = _safe_logs(log_payload)
    except (OSError, ValueError, RuntimeError, urllib.error.URLError):
        errors.append("loki_unavailable")
        trace_ids = []
    for trace_id in trace_ids:
        try:
            _get_json(f"{tempo}/api/traces/{trace_id}")
            traces.append({"trace_id": trace_id, "status": "retrieved"})
        except (OSError, ValueError, RuntimeError, urllib.error.URLError):
            traces.append({"trace_id": trace_id, "status": "unavailable"})
            errors.append("tempo_trace_unavailable")
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    failing = sum(row["request_count_5m"] for row in metrics
                  if row["http_response_status_code"].startswith("5"))
    total = sum(row["request_count_5m"] for row in metrics)
    return {
        "incident_id": incident_id,
        "collected_at": now,
        "deployed_version": version,
        "user_impact": {"window": "5m", "http_5xx_count": failing,
                        "request_count": total, "health_route_excluded": True},
        "metrics": metrics,
        "logs": logs,
        "traces": traces,
        "collection_status": "partial" if errors else "complete",
        "collection_errors": sorted(set(errors)),
    }


def policy_decision(action: str, operator_authorized: bool = False):
    if action in {"collect_evidence", "investigate", "escalate"}:
        return {"decision": "allow", "reason": "read-only evidence or analysis action"}
    if action == "rollback":
        if operator_authorized:
            return {"decision": "operator_authorized", "reason": "explicit operator authorization recorded"}
        return {"decision": "require_operator", "reason": "rollback requires an operator; model execution is prohibited"}
    return {"decision": "deny", "reason": "action is outside the responder allowlist"}


def validate_response(value):
    try:
        import jsonschema
    except ImportError as exc:  # pragma: no cover - clearer CLI error when optional test dep is absent
        raise RuntimeError("jsonschema is required to validate responder output") from exc
    schema = json.loads((ROOT / "response.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(value, schema)
    # Model output can never carry operator authorization. The interactive runbook
    # records human approval separately and this validator keeps the model result
    # at the policy-required boundary.
    actual = policy_decision(value["proposed_action"]["type"], False)
    if value["policy_decision"] != actual:
        raise ValueError("policy decision does not match the deterministic policy")
    return True


def verify_recovery(incident_id: str):
    _check_incident(incident_id)
    port = os.getenv("PAIRROOM_LOCAL_PORT", "8000")
    if not port.isdigit() or not 1 <= int(port) <= 65535:
        raise ValueError("PAIRROOM_LOCAL_PORT must be a TCP port number")
    try:
        result = _get_json(f"http://127.0.0.1:{port}/health")
        healthy = result == {"status": "ok"}
    except (OSError, ValueError, RuntimeError, urllib.error.URLError):
        healthy = False
    return {"incident_id": incident_id, "status": "verified" if healthy else "not_verified",
            "checks": [{"name": "local_pairroom_health", "passed": healthy}],
            "checked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    evidence = sub.add_parser("collect", help="query fixed local read-only telemetry endpoints")
    evidence.add_argument("--incident-id", required=True)
    evidence.add_argument("--deployed-version", required=True)
    validation = sub.add_parser("validate-response", help="validate structured responder output")
    validation.add_argument("response_file", type=Path)
    authorization = sub.add_parser("decide", help="apply deterministic action policy")
    authorization.add_argument("action")
    authorization.add_argument("--operator-authorized", action="store_true")
    recovery = sub.add_parser("verify-recovery", help="GET local PairRoom /health only")
    recovery.add_argument("--incident-id", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "collect":
            output = collect(args.incident_id, args.deployed_version)
        elif args.command == "validate-response":
            value = json.loads(args.response_file.read_text(encoding="utf-8"))
            validate_response(value)
            output = {"valid": True, "incident_id": value["incident_id"]}
        elif args.command == "decide":
            output = policy_decision(args.action, args.operator_authorized)
        else:
            output = verify_recovery(args.incident_id)
        print(json.dumps(output, sort_keys=True))
        return 0 if output.get("status") != "not_verified" else 2
    except (ValueError, OSError, RuntimeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
