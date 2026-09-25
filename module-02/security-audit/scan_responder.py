"""Small deterministic local checks for the PairRoom responder boundary.

This is a focused repository rule scanner, not a general-purpose SAST product.
It intentionally reports no matching source text, only safe paths and lines.
"""
from __future__ import annotations

import json
import argparse
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT_ROOT = Path(__file__).resolve().parent
TARGETS = [
    ROOT / "incident-response/responder.py",
    ROOT / "incident-response/autonomy-policy.yaml",
    ROOT / "incident-response/response.schema.json",
    ROOT / "incident-response/collect-evidence.sh",
    ROOT / "incident-response/responder-task.md",
    ROOT / "incident-response/runbooks/rollback.sh",
    ROOT / "incident-response/runbooks/verify-recovery.sh",
    ROOT / "incident-response/incidents/INC-2026-001.json",
]
SECRET_PATTERNS = {
    "AUDIT-SECRET-AWS": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "AUDIT-SECRET-GITHUB": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    "AUDIT-SECRET-PRIVATE-KEY": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "AUDIT-SECRET-BEARER": re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{16,}"),
    "AUDIT-SECRET-PASSWORD": re.compile(r"(?i)\b(?:password|client_secret|access_token)\s*[:=]\s*[^\s,]{8,}"),
}


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def scan():
    texts = {path: path.read_text(encoding="utf-8") for path in TARGETS}
    responder = texts[ROOT / "incident-response/responder.py"]
    checks = [
        {"rule_id": "RESP-NO-SHELL", "result": "pass" if not any(token in responder for token in
          ("subprocess", "os.system", "Popen(", "shell=True", "eval(")) else "fail",
         "summary": "Responder implementation contains no shell/process execution primitive."},
        {"rule_id": "RESP-LOOPBACK-ONLY", "result": "pass" if 'parsed.hostname not in {"127.0.0.1", "localhost", "::1"}' in responder else "fail",
         "summary": "Evidence base URLs are restricted to loopback hosts."},
        {"rule_id": "RESP-NO-REDIRECTS", "result": "pass" if "class DenyRedirect" in responder else "fail",
         "summary": "Evidence HTTP redirects are rejected."},
        {"rule_id": "RESP-OUTPUT-SCHEMA", "result": "pass" if "jsonschema.validate(value, schema)" in responder else "fail",
         "summary": "Responder output is checked against the JSON schema."},
        {"rule_id": "RESP-ROLLBACK-NO-EXEC", "result": "pass" if "No rollback command was executed" in texts[ROOT / "incident-response/runbooks/rollback.sh"] else "fail",
         "summary": "Rollback helper records authorization but executes no deployment."},
    ]
    findings = []
    # This check intentionally highlights a policy-evidence gap for review.
    for number, line in enumerate(responder.splitlines(), 1):
        if 'authorization.add_argument("--operator-authorized"' in line:
            findings.append({
                "finding_id": "AUD-RESP-001", "severity": "medium",
                "title": "CLI operator-authorization flag is not proof of approval",
                "description": "The policy CLI can label rollback as operator_authorized from a boolean argument; it does not validate an approval record. This CLI does not itself deploy, and model output validation rejects the claim, but the label can be misleading.",
                "recommendation": "Remove the flag or require a verifiable operator approval artifact before emitting operator_authorized.",
                "source_rule": "RESP-OPERATOR-AUTH-EVIDENCE", "path": _relative(ROOT / "incident-response/responder.py"), "line": number,
            })
            break
    for path, body in texts.items():
        for rule_id, pattern in SECRET_PATTERNS.items():
            for number, line in enumerate(body.splitlines(), 1):
                if pattern.search(line):
                    findings.append({
                        "finding_id": f"AUD-RESP-{len(findings) + 1:03d}", "severity": "high",
                        "title": "Possible credential material in responder artifact",
                        "description": f"Rule {rule_id} matched a credential-like pattern. Matching text is deliberately omitted.",
                        "recommendation": "Inspect the local source privately, remove the material, rotate it if genuine, and do not copy it into audit output.",
                        "source_rule": rule_id, "path": _relative(path), "line": number,
                    })
    return {
        "stage": "deterministic_scanner", "tool": "pairroom-responder-rule-scanner", "version": "1.0.0",
        "command": "python module-02/security-audit/scan_responder.py", "status": "completed",
        "checks": checks, "findings": findings,
    }


def validate_run(run):
    """Validate structure plus cross-stage human disposition and secret checks."""
    import jsonschema

    schema = json.loads((AUDIT_ROOT / "findings.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(run, schema)
    findings = [finding for stage in (run["deterministic_scanner"], run["model_review"])
                for finding in stage["findings"]]
    finding_ids = [finding["finding_id"] for finding in findings]
    disposition_ids = [item["finding_id"] for item in run["human_validation"]["dispositions"]]
    if len(finding_ids) != len(set(finding_ids)):
        raise ValueError("finding IDs must be unique across stages")
    if set(finding_ids) != set(disposition_ids):
        raise ValueError("every finding must have exactly one human disposition")
    if run["human_validation"]["status"] == "completed":
        if run["human_validation"]["reviewer"] is None or any(
                item["reviewer"] is None or item["disposition"] == "pending"
                for item in run["human_validation"]["dispositions"]):
            raise ValueError("completed human validation requires named dispositions for every finding")
    serialized = json.dumps(run)
    if any(pattern.search(serialized) for pattern in SECRET_PATTERNS.values()):
        raise ValueError("audit run contains material matching a credential pattern")
    if run["overall_status"] == "complete" and run["human_validation"]["status"] != "completed":
        raise ValueError("overall complete status requires completed human validation")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-run", type=Path,
                        help="validate an audit JSON run, including cross-stage dispositions")
    args = parser.parse_args()
    if args.validate_run:
        run = json.loads(args.validate_run.read_text(encoding="utf-8"))
        validate_run(run)
        print(json.dumps({"valid": True, "run_id": run["run_id"]}, sort_keys=True))
    else:
        print(json.dumps(scan(), indent=2, sort_keys=True))
