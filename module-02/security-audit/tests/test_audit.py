import importlib.util
import json
import re
from pathlib import Path

import jsonschema
import pytest


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
SPEC = importlib.util.spec_from_file_location("scan_responder", ROOT / "scan_responder.py")
scanner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scanner)


def read_run():
    return json.loads((ROOT / "runs/BASELINE-20260924-001.json").read_text(encoding="utf-8"))


def test_schema_and_sanitized_baseline_are_valid():
    schema = json.loads((ROOT / "findings.schema.json").read_text(encoding="utf-8"))
    run = read_run()
    jsonschema.validate(run, schema)
    assert run["live_audit"] is False
    assert run["run_kind"] == "sanitized_baseline"


def test_every_scanner_and_model_finding_has_human_disposition():
    run = read_run()
    finding_ids = {finding["finding_id"]
                   for stage in [run["deterministic_scanner"], run["model_review"]]
                   for finding in stage["findings"]}
    dispositions = {item["finding_id"]: item for item in run["human_validation"]["dispositions"]}
    assert finding_ids == set(dispositions)
    assert all(item["disposition"] in {"pending", "accepted", "rejected", "deferred", "not_applicable"}
               and item["rationale"].strip() for item in dispositions.values())
    assert run["overall_status"] == "pending_human_validation"


def test_scanner_and_model_stages_are_separate_and_scanner_is_reproducible():
    run = read_run()
    fresh = scanner.scan()
    assert run["deterministic_scanner"] == fresh
    assert run["deterministic_scanner"]["stage"] == "deterministic_scanner"
    assert run["model_review"]["stage"] == "model_review"
    assert run["model_review"]["status"] == "completed"
    assert "scan_responder.py" in run["provenance"]["scanner_source"]
    assert "autonomy-policy.yaml" in run["provenance"]["policy_source"]
    assert run["provenance"]["model_provenance"]


def test_capability_table_covers_required_boundaries():
    table = (ROOT / "capability-table.md").read_text(encoding="utf-8").lower()
    for expected in ["shell", "aws", "docker", "github", "deployment", "filesystem",
                     "credential", "telemetry", "loopback", "redirect", "schema",
                     "policy", "rollback", "recovery", "provenance"]:
        assert expected in table


def test_audit_artifacts_have_no_obvious_secrets_or_credentials():
    paths = [ROOT / "audit-brief.md", ROOT / "findings.schema.json", ROOT / "capability-table.md",
             ROOT / "runs/BASELINE-20260924-001.json"]
    suspicious = re.compile(r"\bAKIA[0-9A-Z]{16}\b|\bgh[pousr]_[A-Za-z0-9]{20,}\b|"
                            r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
                            r"(?i:bearer\s+[A-Za-z0-9._~+/=-]{16,})")
    for path in paths:
        assert not suspicious.search(path.read_text(encoding="utf-8")), path.name


def test_schema_requires_human_disposition_for_each_finding():
    run = read_run()
    run["human_validation"]["dispositions"] = []
    with pytest.raises(ValueError, match="every finding"):
        scanner.validate_run(run)


def test_cross_stage_validator_rejects_secret_patterns():
    run = read_run()
    run["model_review"]["analysis"].append("Example leaked credential: password=supersecret12345")
    with pytest.raises(ValueError, match="credential pattern"):
        scanner.validate_run(run)
