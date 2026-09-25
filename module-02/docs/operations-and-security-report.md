# PairRoom Operations and Security Report - Module 4

## Scope and evidence status

This report maps the Module 4 operations/security deliverable to the PairRoom
implementation and reconstructs the sanitized incident `INC-2026-001`. The
incident record is an illustrative fixture, not a live production incident. Its
digest (`sha256:` followed by 64 `a` characters), request counts, log event, trace
ID, model fields, and proposed action are sanitized example values. They do not
identify a real deployed image or prove that an alert fired or an action occurred.

The labels below distinguish the evidence types used here:

| Status | Meaning |
| --- | --- |
| Implemented and tested | Repository code/configuration exists and the corresponding local automated tests pass. |
| Runtime-verified locally | A saved local verification run exercised the isolated observability and PairRoom test stacks. This is not an AWS deployment claim. |
| Illustrative/sanitized | A fixture demonstrates the report shape without representing private or live runtime data. |
| Requires human action | A permitted operation or audit disposition still needs an operator/reviewer. |
| Not deployed to AWS | The complete observability stack and application telemetry are not enabled by normal AWS development CI and have not been deployed to production. |

## Incident trail: INC-2026-001

### Version and user impact

The example record names `sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`
as its deployed version. This is a sanitized sentinel, not a verified registry
digest. Its impact summary says a short burst affected session creation while
`/health` remained available. The example reports 4 HTTP 5xx responses among 52
requests in a 5-minute window (about 7.7%). No event timestamp or live request
history is included, so the duration and actual occurrence cannot be
independently established from this record.

### Alert and evidence inspected

The configured alert is `PairRoomElevatedServerErrorRate`. It evaluates the
existing `pairroom_http_requests_total` counter, excludes `/health`, and retains
service, environment, version, and route labels. It requires more than 5% 5xx
responses and at least three 5xx responses over five minutes, continuously for
two minutes. The example's 4/52 ratio and count satisfy the numeric portions of
that expression, but the fixture does not contain the time series needed to
prove that the condition remained true for two minutes. Therefore this report
does not claim that the alert fired for `INC-2026-001`.

The fixture's sanitized evidence packet contains:

| Signal | Example evidence | Interpretation limit |
| --- | --- | --- |
| Metrics | One `/sessions` series, HTTP 500, count 4, service `pairroom-backend`, environment `development`, and the sentinel version | Example series only; no Prometheus response or alert event is attached. |
| Structured logs | One `session.creation.failed` event for `/sessions`, status 500, with the same service/environment/version labels | The log is a sanitized example; no raw message, request, session, or credential data is present. |
| Trace | Trace ID `0123456789abcdef0123456789abcdef`, fixture status `retrieved` | The ID and status are illustrative; no trace body is included. |

The live evidence collector uses fixed Prometheus and Loki queries, retrieves
only validated trace IDs from Tempo, rejects redirects, and permits only
loopback HTTP endpoints. Its output allowlists labels and event names and omits
raw trace bodies and arbitrary log content. The model input is therefore a
bounded evidence packet, not unrestricted observability access.

### Responder analysis, action, and policy

The incident fixture records provider `not-run-example`, model ID
`sanitized-fixture`, and configuration reference
`incident-response/responder-task.md`. This is not evidence of a model/API call.
The record's illustrative analysis recommends comparing the failures with the
version and inspecting the correlated trace. Its proposed action is
`investigate`, and the recorded deterministic policy decision is `allow` because
that action is read-only.

No command was executed for this example incident: no deployment, rollback,
restart, health-check, or external notification command is recorded. The
sanitized responder result itself is not a command execution record. The new
headless adapter is implemented and tested with a fake process, but it has not
been used to call an external model for this incident.

Human approval is not required for the allowed `investigate` analysis. Rollback
is a separate action and remains `require_operator`; the model cannot authorize
or execute it. The rollback runbook prompts a human for an incident-specific
confirmation and then provides a manual release-process handoff; it executes no
rollback command. The existing `responder.py decide` convenience CLI can still
label a rollback `operator_authorized` when passed a boolean flag without a
verifiable approval record. That limitation is captured by `AUD-RESP-001` below;
the headless adapter ignores model-supplied policy and recomputes it locally.

### Recovery, escalation, and related security findings

For this incident, `recovery_verification.status` is `not_attempted`, with no
checks or verification time. The fixture records complete evidence and no
escalation requirement; no escalation packet was sent or recorded. The recovery
helper, when explicitly run by an operator, checks only the local `/health`
response. It does not prove that the deployed digest or the user-impact alert
has recovered.

The related sanitized baseline audit is
`security-audit/runs/BASELINE-20260924-001.json`. It is a local baseline, not a
live production audit. It lists these findings:

| Finding | Relevance | Human disposition |
| --- | --- | --- |
| `AUD-RESP-001` — an authorization flag is not proof of approval | Rollback policy record | Pending; no human disposition is recorded. |
| `AUD-RESP-002` — free-text output is not content-scanned | Responder summaries and reasoning | Pending; no human disposition is recorded. |
| `AUD-RESP-003` — loopback overrides can target arbitrary local ports | Evidence query boundary | Pending; no human disposition is recorded. |
| `AUD-RESP-004` — recovery verification checks only local health | Recovery state in this incident | Pending; no human disposition is recorded. |
| `AUD-RESP-005` — model/tool provenance is not runtime-attested | The example is not a live model run | Pending; no human disposition is recorded. |

All five dispositions remain pending in the baseline. That audit run predates
the current headless adapter; its statements that no adapter was integrated and
that no runtime tool configuration existed are historical, not current-state
claims. The current wrapper uses an isolated temporary profile, ignores user
configuration, sets an empty MCP-server override, disables shell and web-search
tools, and avoids the shared daemon. It records only wrapper/configuration
provenance, not an attested serving model build. System- or organization-managed
policy outside those profile paths is not independently verified, and the
provider network remains necessary for a real model response. `AUD-RESP-005`
therefore needs a fresh deterministic/model review before a human disposition.
This report does not change any finding or disposition.

## Operating model

### Release separation and immutable promotion

Development CI tests the application, builds and deploys the tested image, and
records a promotion artifact only after deployment health validation succeeds.
The image is addressed by its immutable GHCR digest. Production promotion is a
separate manual workflow from `main`: it resolves the selected successful
development run and its promotion artifact, verifies the immutable digest is
still available, then deploys that same digest using the production GitHub
environment and separate OIDC role. Development and production use separate
stacks, instances, and databases; promotion transfers an application image, not
database contents. Deployment helper behavior keeps production image-only and
telemetry-disabled unless a future explicit configuration changes it.

### Observability architecture and deployment boundary

The local observability project contains the OpenTelemetry Collector,
Prometheus, Loki, Tempo, and Grafana. PairRoom connects through the dedicated
Docker telemetry network; OTLP/HTTP ingestion and Grafana are host-loopback
published locally, while Prometheus, Loki, and Tempo have no published host
ports. Prometheus, Loki, Tempo, and Grafana use persistent named volumes. The
optional local PairRoom Compose override sends traces, metrics, and structured
logs to the Collector without changing the ordinary application Compose file.

The local saved verification result records `PASS`, seven correlated traces,
persistence checks for Prometheus/Loki/Tempo/Grafana across a normal stack
restart, and a clean sensitive-fixture scan. The verifier also checks Collector
and datasource readiness, PairRoom health/frontend/WebSocket behavior, and
service/environment/version attributes. This is local runtime evidence only;
the current runtime was not rechecked while preparing this report.

AWS development observability remains disabled by default. Normal CI does not
set `PAIRROOM_DEPLOY_ENVIRONMENT=development`, so the AWS `t3.small` follows the
immutable-image-only path. The full five-service stack has not been demonstrated
to fit safely beside PairRoom and PostgreSQL on that host. The explicit future
development opt-in remains guarded by the existing 3,500,000 KiB memory check in
`deploy.py`; the guard was not lowered. Production promotion does not enable the
development opt-in. No observability stack is deployed to AWS, and no production
telemetry is enabled by this work.

### Detection and investigation flow

The actionable alert uses user-facing HTTP failures rather than host utilization.
It excludes `/health`, requires a rate above 5% and at least three 5xx responses
over five minutes, and uses a two-minute pending period. Its labels and
annotations carry service, environment, deployed version, and route context and
direct investigation to matching Loki events, trace IDs in Tempo, the deployed
version, and service health. Prometheus rule tests cover healthy traffic,
failing health probes, insufficient failures, and sustained user-route errors.
There is no Alertmanager or external notification service.

The provisioned `PairRoom Incident Investigation` Grafana dashboard follows
that path: request rate, 5xx rate and
ratio, latency, observed health responses, active alert state/context, observed
versions, safe structured events, and correlated Tempo traces. Its health panel
explicitly treats missing telemetry as unknown. The dashboard is configuration
as code and is covered by JSON/provisioning/query consistency tests.

### Bounded response and recovery

The evidence collector performs only fixed read-only queries and applies the
allowlist and redaction rules in `responder.py`. The headless adapter supplies
the task and normalized sanitized packet to Codex in non-interactive mode with
the existing JSON schema. It passes only process and OS temporary-directory
variables, redirects user-profile and Codex state paths to a per-run temporary
directory, ignores user Codex configuration, overrides MCP servers with an
empty table, disables shell/web-search tools, and avoids the shared daemon. It
uses a read-only sandbox, validates output locally, and recomputes policy
outside the model. It does not inherit AWS, GitHub, cloud, deployment, API-key,
or application credentials. The provider network remains necessary for
inference; the process is not isolated from machine- or organization-managed
policy and authentication outside those paths. The agent has no
adapter-provided execution interface for deployment, rollback, restart,
evidence mutation, external notification, or security-finding approval. The
capability table records the boundary and its limits. Adapter tests use a fake
process; no external model call is claimed here.

Rollback remains an operator-only release action. An operator must review the
target digest, provide explicit authorization through the runbook, perform the
release action using the approved deployment process, and record what happened.
The responder does not execute that command. Recovery verification is a separate
read-only check; its current implementation verifies local `/health` only and
must not be described as complete recovery evidence by itself.

### Security-audit responsibilities

The audit brief separates three stages: (1) deterministic local scanner output,
(2) model analysis recorded separately from scanner results, and (3) named human
validation/disposition for every finding. The repository-owned scanner is
available and tested. Semgrep was not installed or run for this baseline, so a
Semgrep-specific result is not demonstrated. The sanitized baseline records
model provenance and limitations and leaves every human disposition pending.
The capability/provenance inventory is summarized above; the full boundary
matrix is in `security-audit/capability-table.md`. No Snyk Agent Scan result is
claimed.

## Module 4 deliverable and validation map

The official deliverable asks for the observability, incident-response, and
security-audit artifacts below, plus this report. Tests and runtime checks are
kept distinct from the illustrative incident record.

| Course requirement/artifact | PairRoom artifact(s) | Validation/evidence | Status and limitation |
| --- | --- | --- | --- |
| OpenTelemetry metrics, logs, traces without sensitive data | `backend/app/telemetry.py`; `backend/tests/test_telemetry.py` | Backend telemetry tests; local end-to-end verifier and privacy scan | Implemented and tested; runtime-verified locally. |
| Collector pipeline; `collector.yaml`, `compose.yaml` | `observability/collector.yaml`, `observability/compose.yaml`, `prometheus.yaml`, `loki.yaml`, `tempo.yaml` | Compose/config validation; saved local `verify.py` result | Implemented; all five services runtime-verified locally. Not deployed to AWS. |
| `dashboard.json` | `observability/dashboard.json`; Grafana dashboard and datasource provisioning | Dashboard JSON/provisioning/query tests; saved local verifier result | Implemented and provisioned; runtime-verified locally. |
| Actionable `alerts.yaml` | `observability/alerts.yaml`, `alerts.test.yaml` | `promtool check rules` and synthetic rule tests recorded in observability validation | Implemented and tested; no external notification path. |
| Bounded repeatable read-only evidence packet | `incident-response/collect-evidence.sh`, `responder.py`; `tests/test_responder.py` | Fixed-query, loopback, redirect, redaction, policy, and recovery tests | Implemented and tested. Live remote evidence collection is not claimed. |
| Headless read-only agent behind vendor-neutral structured adapter | `incident-response/responder-task.md`, `incident-response/agent_adapter.py`, `incident-response/response.schema.json`; `tests/test_agent_adapter.py` | Fake-process tests for structured output, failures, tools, credentials, schema, and policy; installed Codex CLI options and empty-MCP override checked locally | Implemented and tested with a fake CLI. No real model/API call or model provenance is asserted for this example. Profile isolation is CLI-level, not an OS security boundary; provider network is required for inference. |
| Allowlist/autonomy levels and operator-gated action | `incident-response/autonomy-policy.yaml`, `responder.py`, `incident-response/runbooks/rollback.sh` | Incident-response and adapter policy tests | Implemented and tested; the boolean `decide --operator-authorized` caveat remains under pending `AUD-RESP-001`. No rollback has run. |
| Recovery verification or escalation packet | `incident-response/runbooks/verify-recovery.sh`, `responder.py`; incident schema/record | Sanitized recovery/escalation tests | Implemented and tested; verifier checks local `/health` only. This fixture says recovery not attempted. |
| `incidents/` incident trail | `incident-response/incidents/INC-2026-001.json` | Schema/policy test and report consistency test | Illustrative/sanitized; not a live incident or command record. |
| Deterministic scanner, model review, human validation | `security-audit/scan_responder.py`, `security-audit/audit-brief.md`, `security-audit/findings.schema.json`, `security-audit/runs/BASELINE-20260924-001.json`; `tests/test_audit.py` | Scanner reproducibility, schema, provenance, secret-pattern, and disposition tests | Local scanner and baseline implemented/tested. Semgrep was unavailable; human dispositions remain pending. |
| Responder capability, credential, data, and provenance inventory | `security-audit/capability-table.md` | Capability coverage test and audit-run validation | Implemented and tested; no Snyk scan was run. |
| Operations and security report | `docs/operations-and-security-report.md` | `docs/tests/test_operations_security_report.py` plus full affected suite | This report reconstructs the sanitized incident and explicitly records unperformed actions. |

## Remaining gaps and limits

- The report and sanitized trail do not establish a real incident, an alert firing,
  a real model invocation, a rollback command, or recovery for `INC-2026-001`.
- Human review is still required for all five baseline findings. The baseline
  predates the current adapter and should be rerun/reviewed before any human
  disposition is made.
- Semgrep and Snyk Agent Scan were not run; no results from those products are
  claimed. The local deterministic scanner and capability table are the evidence
  actually present.
- Local observability runtime validation is recorded, but this report did not
  re-run the containers. AWS development observability remains opt-in and blocked
  by the unchanged memory guard on the current `t3.small`; production remains
  telemetry-disabled.
- Recovery verification currently proves only the local health response, not
  deployment-version or alert recovery.
