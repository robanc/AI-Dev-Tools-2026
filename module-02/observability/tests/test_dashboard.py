import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_json_datasources_and_provisioning_are_consistent():
    dashboard = json.loads((ROOT / "dashboard.json").read_text(encoding="utf-8"))
    provider = (ROOT / "grafana/provisioning/dashboards/dashboards.yaml").read_text(encoding="utf-8")
    datasources = (ROOT / "grafana/provisioning/datasources/datasources.yaml").read_text(encoding="utf-8")
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    provisioned_dashboard = ROOT / "grafana/provisioning/dashboards/pairroom-incident.json"
    assert dashboard["uid"] == "pairroom-incident"
    assert "path: /etc/grafana/provisioning/dashboards" in provider
    assert "uid: prometheus" in datasources and "uid: loki" in datasources and "uid: tempo" in datasources
    assert "./grafana/provisioning:/etc/grafana/provisioning:ro" in compose
    assert provisioned_dashboard.read_bytes() == (ROOT / "dashboard.json").read_bytes()
    assert "GF_SECURITY_ADMIN_PASSWORD" in compose
    assert not re.search(r"(?i)(password|token|secret|AKIA[0-9A-Z]{16})\s*[:=]\s*\S+", (ROOT / "dashboard.json").read_text())


def test_panels_use_metrics_and_labels_produced_by_pairroom():
    dashboard = json.loads((ROOT / "dashboard.json").read_text(encoding="utf-8"))
    telemetry = (ROOT.parent / "backend/app/telemetry.py").read_text(encoding="utf-8")
    prometheus = (ROOT / "prometheus.yaml").read_text(encoding="utf-8")
    panel_queries = [target.get("expr", "") for panel in dashboard["panels"]
                     for target in panel.get("targets", [])]
    queries = "\n".join(panel_queries)
    for actual in ["pairroom.http.requests", "http.server.request.duration"]:
        assert actual in telemetry
    for expected in ["pairroom_http_requests_total", "http_server_request_duration_seconds_bucket",
                     "ALERTS{", "service_name", "deployment_environment_name", "service_version",
                     "http_route", "http_response_status_code"]:
        assert expected in queries
    assert "http_route!=\"/health\"" in queries
    assert 'http_route=\"/health\"' in queries
    assert "pairroom-collector" in prometheus
    assert "unmatched" in telemetry


def test_dashboard_includes_incident_logs_and_correlated_tempo_traces():
    dashboard = json.loads((ROOT / "dashboard.json").read_text(encoding="utf-8"))
    by_type = {panel["type"]: panel for panel in dashboard["panels"]}
    logs = by_type["logs"]["targets"][0]["expr"]
    traces = by_type["traces"]["targets"][0]
    datasource = (ROOT / "grafana/provisioning/datasources/datasources.yaml").read_text(encoding="utf-8")
    for event in ["http.request.completed", "session.created", "session.creation.failed"]:
        assert event in logs
    assert traces["datasource"]["uid"] == "tempo"
    assert "resource.service.name" in traces["query"]
    assert "resource.deployment.environment.name" in traces["query"]
    assert "matcherRegex: trace_id" in datasource and "datasourceUid: tempo" in datasource


def test_dashboard_has_no_external_urls_and_health_claim_is_limited():
    dashboard = json.loads((ROOT / "dashboard.json").read_text(encoding="utf-8"))
    serialized = json.dumps(dashboard)
    assert not re.search(r"https?://(?!prometheus:|loki:|tempo:|grafana:)[^\s\"]+", serialized)
    health = next(panel for panel in dashboard["panels"] if panel["title"].startswith("Observed /health"))
    assert "unknown" in health["description"]
    assert "pairroom_http_requests_total" in health["targets"][0]["expr"]
