# Incident responder capability and provenance table

This table describes the current Step 1 implementation in
`module-02/incident-response/`. The evidence collector and response evaluator
are local Python code. The optional headless Codex wrapper invokes one
non-interactive CLI process and accepts only schema-validated JSON; the
deterministic policy is recomputed locally.

| Area | Permitted | Prohibited / boundary | Evidence and provenance |
|---|---|---|---|
| Operations | Fixed evidence collection; analysis of the normalized, sanitized packet; preparing an escalation record | Agent shell commands, AWS, Docker, GitHub, deployment, rollback, restart, arbitrary commands, external notifications, incident-evidence mutation, security-finding approval | `agent_adapter.py` starts only fixed `codex exec`; shell and web-search tools are disabled; `responder.py` owns policy evaluation |
| Agent integrations | One Codex model request through the CLI's provider connection | MCP servers, shared Codex daemon, web-search tool, shell tool, additional action executors | `--no-daemon`; `--ignore-user-config`; CLI override `mcp_servers={}`; `--disable shell_tool` and `--disable web_search`; exact installed CLI checked as `codex-cli 0.156.1` |
| Evidence network | Collector HTTP GET to configured plain-HTTP loopback base URLs for fixed Prometheus, Loki, and Tempo API paths; redirects rejected | Agent has no arbitrary network tool; collector rejects non-loopback hosts, credentials, query overrides, redirects, and non-GET requests. Provider network access remains necessary for an actual model response | `responder.py` `_loopback_base`, fixed `PROM_QUERY`/`LOKI_QUERY`, `_get_json`, `DenyRedirect`; provider transport is performed by Codex CLI |
| Filesystem | Collector reads its schema and caller-selected response JSON; evidence writes to stdout; adapter uses a temporary working directory/profile and temporary response file | Agent is not given filesystem tools. CLI is still a host process under the invoking OS account; the Codex read-only sandbox is not an OS-level process/container boundary | `responder.py`; `agent_adapter.py`; CLI `--sandbox read-only`, `--ephemeral`, temporary `HOME`, `USERPROFILE`, `APPDATA`, `LOCALAPPDATA`, and `CODEX_HOME` |
| Credentials | Adapter inherits only `PATH`, OS/runtime path variables (`SYSTEMROOT`, `WINDIR`, `PATHEXT`, `COMSPEC`), and temp-directory variables; profile/config locations point into the per-run temporary directory | No AWS, GitHub, cloud, deployment, API-key, or application credential environment variables are inherited. The normal user Codex profile/auth is not reused. System/organization-managed auth or policy outside these paths is not independently verified; without usable isolated Codex authentication, the CLI must fail safely | `_CLI_ENV_ALLOWLIST` and the environment built by `CodexHeadlessAdapter`; `--ignore-user-config` help explicitly says authentication still uses `CODEX_HOME`, which is redirected to an empty temporary location |
| Telemetry data | Aggregated HTTP request counts; service/environment/version/route/status labels; three fixed event names; validated trace IDs and availability status | Raw logs, trace bodies, request/session IDs, query strings, cookies, headers, bodies, arbitrary exception details | `SAFE_EVENTS`, `_safe_labels`, `_safe_logs`; `response.schema.json` rejects extra evidence keys |
| Output and policy | JSON validated using `jsonschema`; trusted incident/evidence fields restored; policy recomputed outside model output; read-only evidence/investigate/escalate allowed; unknown actions denied | Model-supplied policy decisions, shell commands, autonomous rollback | `agent_adapter.py:run_responder`, `responder.py:validate_response`, `policy_decision`, `autonomy-policy.yaml` |
| Rollback | Human operator types the incident-specific authorization phrase; operator then uses the approved release process | `rollback.sh` executes no deployment; model cannot invoke it or gain deployment access | `runbooks/rollback.sh`; currently no signed approval artifact or integration |
| Recovery | GET `http://127.0.0.1:<configured-port>/health` and compare exact JSON response | No restart, deployment, mutation, AWS/remote health query | `verify_recovery`, `runbooks/verify-recovery.sh`; only local health is checked |
| Provenance | Record tool, model/config reference, policy path, source state, and reviewer in each audit run | Treating user-supplied model metadata as cryptographic provenance or claiming the actual serving model build is attested | `response.schema.json`, `audit-brief.md`, and run schema; adapter tests fake the CLI and no provider invocation metadata is available in the incident fixture |

## Isolation limits

The adapter supplies the options supported by the installed Codex CLI and
overrides user profile paths with per-run temporary locations. The CLI process
still runs as the invoking OS user; this is not an OS account, container, or
network sandbox. A real model response necessarily uses the provider network,
and organization-managed machine policy or authentication outside the supplied
environment/profile is not independently inspected. The adapter does not pass
the ordinary Codex profile or application credentials, and any CLI/auth/config
failure is returned as a generic safe failure without taking an action. No real
model call has been made for this implementation.

Prometheus, Loki, and Tempo are not published to host ports in the current
Compose file. The collector therefore needs operator-managed loopback access
(for example, safe local forwards) before a live evidence collection can work.
Its base URL environment overrides are loopback-limited but do not restrict the
port. The `decide rollback --operator-authorized` CLI flag can produce an
authorization-labeled decision without proof; the response validator refuses
that claim from model output, and the rollback script separately prompts a
human, but the CLI label itself should be tightened in a future reviewed change.
