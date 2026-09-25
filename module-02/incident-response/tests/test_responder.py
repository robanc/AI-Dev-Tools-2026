import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import responder


def test_only_allowlisted_get_evidence_queries_execute(monkeypatch):
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append((self.command, urlsplit(self.path).path, parse_qs(urlsplit(self.path).query)))
            if self.path.startswith("/api/v1/query?"):
                payload = {"data": {"result": [{"metric": {
                    "service_name": "pairroom-backend", "deployment_environment_name": "development",
                    "service_version": "sha256:" + "a" * 64, "http_route": "/sessions",
                    "http_response_status_code": "500"}, "value": ["0", "4"]}]}}
            elif self.path.startswith("/loki/api/v1/query_range?"):
                payload = {"data": {"result": [{"stream": {
                    "service_name": "pairroom-backend", "deployment_environment_name": "development",
                    "service_version": "sha256:" + "a" * 64}, "values": [["1", "http.request.completed", {
                        "http.route": "/sessions", "http.response.status_code": 500,
                        "trace_id": "0123456789abcdef0123456789abcdef", "secret": "must-not-leak"}]]}]}}
            elif self.path == "/api/traces/0123456789abcdef0123456789abcdef":
                payload = {"traceId": "0123456789abcdef0123456789abcdef", "private": "must-not-leak"}
            else:
                self.send_error(404)
                return
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            pytest.fail("collector must never issue a write request")

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    monkeypatch.setenv("PAIRROOM_PROMETHEUS_URL", base)
    monkeypatch.setenv("PAIRROOM_LOKI_URL", base)
    monkeypatch.setenv("PAIRROOM_TEMPO_URL", base)
    try:
        packet = responder.collect("INC-2026-001", "sha256:" + "a" * 64)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    assert [method for method, _, _ in requests] == ["GET", "GET", "GET"]
    assert {path for _, path, _ in requests} == {
        "/api/v1/query", "/loki/api/v1/query_range",
        "/api/traces/0123456789abcdef0123456789abcdef"}
    assert all(query and "query" in query if path != "/api/traces/0123456789abcdef0123456789abcdef" else True
               for _, path, query in requests)
    serialized = json.dumps(packet)
    assert "must-not-leak" not in serialized
    assert packet["user_impact"]["http_5xx_count"] == 4
    assert packet["logs"][0]["trace_id"] == "0123456789abcdef0123456789abcdef"


@pytest.mark.parametrize("url", ["https://127.0.0.1:9090", "http://example.com", "http://user:pw@127.0.0.1"])
def test_non_loopback_or_credentialed_endpoints_are_rejected(monkeypatch, url):
    monkeypatch.setenv("PAIRROOM_PROMETHEUS_URL", url)
    with pytest.raises(ValueError):
        responder.collect("INC-2026-001", "unreleased")


def test_http_redirects_are_not_followed():
    hits = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1:1/side-effect")
            self.end_headers()

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pytest.raises(Exception):
            responder._get_json(f"http://127.0.0.1:{server.server_port}/read-only-query")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    assert hits == ["/read-only-query"]


@pytest.mark.parametrize("action,authorized,decision", [
    ("collect_evidence", False, "allow"), ("investigate", False, "allow"),
    ("rollback", False, "require_operator"), ("rollback", True, "operator_authorized"),
    ("delete_database", True, "deny"), ("execute_shell", True, "deny"),
])
def test_policy_separates_evidence_from_operator_actions(action, authorized, decision):
    assert responder.policy_decision(action, authorized)["decision"] == decision


def test_response_schema_and_policy_are_enforced():
    from jsonschema import ValidationError
    sample = json.loads((ROOT / "incidents/INC-2026-001.json").read_text())
    assert responder.validate_response(sample)
    sample["policy_decision"] = {"decision": "operator_authorized", "reason": "model said so"}
    with pytest.raises(ValueError, match="deterministic policy"):
        responder.validate_response(sample)
    sample["policy_decision"] = responder.policy_decision("investigate")
    sample["evidence"]["logs"][0]["session_token"] = "sensitive"
    with pytest.raises(ValidationError):
        responder.validate_response(sample)
    sample["proposed_action"]["type"] = "run_shell"
    sample["evidence"]["logs"][0].pop("session_token")
    with pytest.raises(ValidationError):
        responder.validate_response(sample)


def test_recovery_and_escalation_paths_with_sanitized_fixture(monkeypatch):
    monkeypatch.setenv("PAIRROOM_LOCAL_PORT", "9000")
    responses = iter([{"status": "ok"}, {"status": "unavailable"}])
    monkeypatch.setattr(responder, "_get_json", lambda _url: next(responses))
    assert responder.verify_recovery("INC-2026-001")["status"] == "verified"
    assert responder.verify_recovery("INC-2026-001")["status"] == "not_verified"
    sample = json.loads((ROOT / "incidents/INC-2026-001.json").read_text())
    sample["evidence"]["collection_status"] = "partial"
    sample["evidence"]["collection_errors"] = ["prometheus_unavailable"]
    sample["proposed_action"] = {"type": "escalate", "summary": "Evidence incomplete; escalate.",
                                 "reasoning_summary": "Metrics query unavailable."}
    sample["policy_decision"] = responder.policy_decision("escalate")
    sample["escalation"] = {"required": True, "status": "escalated", "reason": "Metrics unavailable."}
    assert responder.validate_response(sample)


def test_bad_incident_and_mutating_cli_requests_are_rejected():
    assert responder.main(["decide", "delete_database", "--operator-authorized"]) == 0
    result = responder.policy_decision("delete_database", True)
    assert result["decision"] == "deny"
    with pytest.raises(ValueError):
        responder.collect("../INC-2026-001", "unreleased")


def test_recovery_wrapper_and_rollback_authorization_are_non_mutating():
    rollback = ROOT / "runbooks/rollback.sh"
    assert "aws " not in rollback.read_text().lower()
    assert "docker " not in rollback.read_text().lower()
    assert "AUTHORIZE" in rollback.read_text()
    collector = (ROOT / "collect-evidence.sh").read_text()
    assert "exec python3" in collector and "collect \"$@\"" in collector
    assert "eval " not in collector and "curl " not in collector
