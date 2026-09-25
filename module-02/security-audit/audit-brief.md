# PairRoom responder security audit brief

## Purpose and boundary

This recurring audit reviews the Module 4 incident responder in
`module-02/incident-response/`. It evaluates capability boundaries and the
handling of sanitized evidence; it does not certify the application, AWS, or
production. It performs no network access, deployment, or mutation. Do not put
credentials, tokens, raw session/request data, or private runtime evidence in
audit records.

## Required review stages

1. **Deterministic scanner:** run `python module-02/security-audit/scan_responder.py`.
   The repository-owned scanner uses fixed local rules and secret-pattern checks;
   it reports rule IDs, paths, and line numbers without printing matched values.
   Record its output verbatim in the scanner section. This is a narrow baseline
   check, not a replacement for Semgrep. If Semgrep is installed in the future,
   record its version, exact rules, command, and raw findings as a separate
   deterministic result.
2. **Model review:** analyze the responder implementation, policy, schemas,
   runbooks, and scanner findings. Record provider/model identity and relevant
   configuration provenance when known. Separate new analysis from scanner
   results; do not convert model suspicion into a scanner finding.
3. **Human validation:** a named human must explicitly disposition every
   scanner or model finding as `accepted`, `rejected`, `deferred`, or
   `not_applicable`, with a rationale. Until a person does this, mark the
   disposition `pending` and the audit incomplete. Never describe a pending
   record as a completed approval.

Validate a stored run and rerun the audit tests with:

```sh
uv run --project module-02/backend pytest module-02/security-audit/tests -q
uv run --project module-02/backend python module-02/security-audit/scan_responder.py
uv run --project module-02/backend python module-02/security-audit/scan_responder.py --validate-run module-02/security-audit/runs/BASELINE-20260924-001.json
```

Store one sanitized JSON record per run in `runs/`. Include scope, timestamps,
tool/model/config provenance, each stage's status and results, and human
dispositions. Keep full matching text and runtime evidence out of the record.

## Review questions

- Can the responder reach shell, AWS, Docker, GitHub, deployment, or unrestricted
  filesystem operations?
- Are credentials absent from responder context and evidence collection?
- Are metrics, events, routes, versions, and trace IDs allowlisted and sanitized?
- Are evidence URLs loopback-only, queries fixed, methods read-only, and redirects
  blocked?
- Is structured output schema-validated, and is policy recomputed outside the
  model?
- Does rollback require human authorization and remain non-executable by the
  model?
- Does recovery verification test the required user-visible behavior?
- Can the tool, model, policy, and configuration provenance be reconstructed?

The baseline run currently contains a confirmed gap: the general `decide` CLI
accepts `--operator-authorized`, so its output can say `operator_authorized`
without evidence of the interactive rollback confirmation. This does not give
the responder deployment authority, and the rollback script still executes no
change, but it weakens the reliability of the recorded policy decision. The
baseline also notes that model invocation is not integrated and recovery checks
only local `/health`. Human dispositions are pending review.
