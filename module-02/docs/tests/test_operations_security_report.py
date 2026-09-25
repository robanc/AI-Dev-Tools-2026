import json
import re
from pathlib import Path


DOCS = Path(__file__).resolve().parents[1]
MODULE = DOCS.parent
REPORT = DOCS / "operations-and-security-report.md"
INCIDENT = MODULE / "incident-response/incidents/INC-2026-001.json"
AUDIT = MODULE / "security-audit/runs/BASELINE-20260924-001.json"


def test_report_reconstructs_incident_facts_and_does_not_claim_unperformed_actions():
    report = re.sub(r"\s+", " ", REPORT.read_text(encoding="utf-8").lower())
    incident = json.loads(INCIDENT.read_text(encoding="utf-8"))
    digest = incident["deployed_version"]
    assert incident["incident_id"].lower() in report
    assert digest in report
    assert "4 http 5xx responses among 52 requests" in report
    assert "session.creation.failed" in report
    assert incident["evidence"]["traces"][0]["trace_id"] in report
    assert incident["proposed_action"]["type"] in report
    assert incident["policy_decision"]["decision"] in report
    assert incident["recovery_verification"]["status"] in report
    assert "illustrative fixture, not a live production incident" in report
    assert "does not claim that the alert fired" in report
    assert "no command was executed for this example incident" in report
    assert "no external model call is claimed" in report


def test_report_keeps_every_baseline_finding_pending():
    report = REPORT.read_text(encoding="utf-8")
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    findings = {
        finding["finding_id"]
        for stage in (audit["deterministic_scanner"], audit["model_review"])
        for finding in stage["findings"]
    }
    dispositions = audit["human_validation"]["dispositions"]
    assert {item["finding_id"] for item in dispositions} == findings
    assert all(item["disposition"] == "pending" for item in dispositions)

    report_rows = {}
    for line in report.splitlines():
        match = re.match(r"\| `(AUD-RESP-[0-9]{3})`[^|]*\|[^|]*\|\s*([^|]+)\|", line)
        if match:
            report_rows[match.group(1)] = match.group(2).strip().lower()
    assert set(report_rows) == findings
    assert all("pending" in disposition and "no human disposition" in disposition
               for disposition in report_rows.values())


def test_report_covers_official_deliverable_artifacts_and_operating_controls():
    report = REPORT.read_text(encoding="utf-8")
    required_artifacts = [
        "observability/collector.yaml", "observability/compose.yaml",
        "observability/dashboard.json", "observability/alerts.yaml",
        "incident-response/collect-evidence.sh", "incident-response/responder-task.md",
        "incident-response/response.schema.json", "incident-response/autonomy-policy.yaml",
        "incident-response/runbooks/rollback.sh", "incident-response/runbooks/verify-recovery.sh",
        "security-audit/audit-brief.md", "security-audit/findings.schema.json",
        "security-audit/capability-table.md", "security-audit/runs/BASELINE-20260924-001.json",
    ]
    assert all(path in report for path in required_artifacts)
    assert "3,500,000 kib" in report.lower()
    assert "PairRoomElevatedServerErrorRate" in report
    assert "PairRoom Incident Investigation" in report
    assert "not deployed to aws" in report.lower()
