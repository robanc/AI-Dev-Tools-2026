# PairRoom read-only incident responder

The model receives only the sanitized JSON packet produced by
`collect-evidence.sh`. It has no shell, AWS, Docker, GitHub, deployment, or
general filesystem tool. Do not add credentials or raw request/session data to
the prompt. The model may explain likely causes and propose one of
`investigate`, `rollback`, or `escalate`; it must return JSON conforming to
`response.schema.json`.

Before any result is recorded, run:

```sh
python3 module-02/incident-response/responder.py validate-response response.json
```

The validator recomputes the policy decision. Model-supplied confidence or
policy fields do not grant permission. Evidence gathering and analysis are
allowed. Rollback always requires a human operator to authorize and perform the
change through the approved release process; the responder cannot run it.
Unknown actions are denied. Missing telemetry must be reported and escalated,
not filled in with guesses.

Use an incident ID of `INC-YYYY-NNN` and record the immutable deployed image
digest (or an explicitly local `unreleased` version). Review the sanitized
evidence, verify recovery with `runbooks/verify-recovery.sh`, and record any
operator action and human disposition in the incident record.
