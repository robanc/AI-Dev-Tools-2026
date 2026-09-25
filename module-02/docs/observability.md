# PairRoom backend observability

This implements the backend instrumentation and Collector pipeline steps of
[Module 4](https://github.com/DataTalksClub/ai-dev-tools-zoomcamp/blob/main/cohorts/2026/04-devops/lesson.md).
The complete five-service stack is validated locally. Normal CI deployments to
the AWS development `t3.small` currently use the image-only path because safe
capacity for that stack has not been demonstrated. Production promotion remains
unchanged and telemetry-disabled.

## Configuration

Telemetry is disabled by default. Set all of the following to enable OTLP/HTTP
export; the endpoint must be a reachable Collector base URL:

```powershell
$env:PAIRROOM_TELEMETRY_ENABLED = 'true'
$env:OTEL_SERVICE_NAME = 'pairroom-backend'
$env:OTEL_RESOURCE_ATTRIBUTES = 'deployment.environment.name=local,service.version=unreleased'
$env:OTEL_EXPORTER_OTLP_ENDPOINT = 'http://127.0.0.1:4318'
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

Run from `module-02/backend`. The loopback address above is a local example, not a
deployed Collector. `OTEL_SDK_DISABLED=true` overrides the enable switch.
Missing/invalid configuration disables telemetry with a generic warning and leaves
the application running. No resource values or exception details enter that warning.

| Resource attribute | Source |
| --- | --- |
| `service.name` | `OTEL_SERVICE_NAME`, default `pairroom-backend` |
| `deployment.environment.name` | Required in `OTEL_RESOURCE_ATTRIBUTES`: `local`, `development`, or `production` |
| `service.version` | Required in `OTEL_RESOURCE_ATTRIBUTES`; `unreleased` is a local example only |

The same resource is attached to traces, metrics, and logs. Only these three
resource keys are accepted; automatic host/process resource detection is not used.
Operators must supply non-sensitive labels. The backend cannot infer a container's
image digest and does not substitute the static package/API version `0.1.0`.

The development deploy helper passes the selected immutable `sha256:...` image
digest as `service.version`, with `deployment.environment.name=development` and
`OTEL_SERVICE_NAME=pairroom-backend`. The Collector base endpoint is
`http://otel-collector:4318`. This configuration is generated at deployment time;
the image does not bake in a development or production environment. Production
promotion does not set the development opt-in and remains telemetry-disabled.

## Signals and privacy

Explicit ASGI instrumentation records an HTTP server span, request counter
(`pairroom.http.requests`), latency histogram (`http.server.request.duration`, in
seconds), and a structured `http.request.completed` log event. Safe attributes are
HTTP method, allowlisted route template, and response status. Unknown routes use
`unmatched`, and unknown methods use `_OTHER`, keeping metric cardinality bounded.
`/health` is included, with its existing 200/503 response behavior unchanged.

`POST /sessions` also produces a child `pairroom.session.create` span, a success
counter (`pairroom.sessions.created`) or failure counter
(`pairroom.sessions.creation.failures`), and a fixed structured completion/failure
event. Logs carry the active trace/span IDs. A 5xx or failed session creation marks
the corresponding span as an error without recording exception text or stack traces.

Instrumentation does not read headers, bodies, query strings, raw request URLs,
WebSocket frames, or database connection details. Session IDs, invitation links,
authorization tokens, cookies, submitted code/problem text, SQL, and exception
messages are not exported. There is no automatic SQL instrumentation or root log
handler forwarding arbitrary application/third-party logs. WebSocket traffic and
its authentication protocol pass through unchanged. Incoming trace headers are
not propagated in this first step; correlation covers the backend request and its
child operation.

## Export lifecycle and later Collector

Each app lifespan owns its SDK providers; no global providers are replaced.
HTTP protobuf exporters append `/v1/traces`, `/v1/metrics`, and `/v1/logs` to
`OTEL_EXPORTER_OTLP_ENDPOINT`. This implementation selects HTTP/protobuf explicitly;
gRPC and signal-specific endpoint/protocol overrides are not configured by it.
The standard HTTP exporter supports `OTEL_EXPORTER_OTLP_HEADERS` if a future
authenticated Collector requires them; never commit or print those values.

Traces and logs use background batches (512-item queues, batches up to 128, a
one-second schedule). Metrics export every 30 seconds. Export calls have two-second
timeouts, and shutdown flushes/closes providers. This is best-effort telemetry:
outages can lose data but must not fail API requests or database health checks.
No network export occurs when disabled. SDK exporter diagnostics may report a
Collector outage; request payloads are never supplied to the exporters.

## Local observability stack

`module-02/observability/` is a separate Compose project. It runs the Collector,
Prometheus, Loki, Tempo, and Grafana. The Collector receives OTLP/HTTP, sends
metrics to its Prometheus scrape endpoint, logs to Loki OTLP ingestion, and traces
to Tempo. Grafana provisions all three query sources and links log trace IDs to
Tempo. Prometheus retains at most three days/1 GB; Loki and Tempo use local storage
with 24-hour retention. Grafana, metrics, logs, and traces use named volumes.
Ordinary `stop`, `restart`, and `down` preserve those volumes.

Images are pinned to Collector `0.161.0`, Prometheus `3.14.0`, Loki `3.7.8`,
Tempo `2.10.8`, and Grafana `13.2.2`. Only Collector OTLP/HTTP (`127.0.0.1:4318`)
and authenticated Grafana (`127.0.0.1:3000`) are published to the host. Prometheus,
Loki and Tempo stay on the internal Compose network. Collector health is available
inside Docker on port `13133`. The local Grafana password belongs in the ignored
`observability/.secrets/grafana-admin-password` file; it is not stored in Git.

To create that password file without displaying the generated password and start
the stack (from the repository root):

```powershell
@'
from pathlib import Path
import secrets
path = Path('module-02/observability/.secrets/grafana-admin-password')
path.parent.mkdir(parents=True, exist_ok=True)
if not path.exists():
    path.write_text(secrets.token_urlsafe(32), encoding='utf-8')
'@ | python -
docker compose -f module-02/observability/compose.yaml config --quiet
docker compose -f module-02/observability/compose.yaml up -d
```

For local PairRoom telemetry, use a dedicated application project and the optional
override. Its PostgreSQL volume is separate from the regular local app database.
Run the following from `module-02`:

```powershell
docker compose -p pairroom-observability-test -f docker-compose.yaml -f observability/compose.pairroom.yaml config --quiet
docker compose -p pairroom-observability-test -f docker-compose.yaml -f observability/compose.pairroom.yaml up --build -d --wait
```

The override connects only the app to `pairroom-telemetry`, changes its local
test port to `18100`, and sends OTLP to `http://otel-collector:4318`. It labels
telemetry with service `pairroom-backend`, environment `local`, and version
`observability-local`. `localhost` inside the app container is the app itself;
the Collector address uses its Docker network name. The regular
`docker-compose.yaml` and its port/database behavior remain unchanged.

Browse PairRoom at `http://127.0.0.1:18100` and Grafana at `http://127.0.0.1:3000`.
In Grafana Explore, query Prometheus for
`pairroom_sessions_created_total{service_name="pairroom-backend"}`; query Loki with
`{service_name="pairroom-backend",deployment_environment_name="local"}`; use a
log entry's `trace_id` to open its Tempo trace. Prometheus labels and Loki resource
labels include the service, environment and version. Grafana's provisioned
datasources link Loki log trace IDs to Tempo.

### User-impact alert

Prometheus loads `alerts.yaml` and evaluates `PairRoomElevatedServerErrorRate`
every 15 seconds. It fires per service, environment, deployed version, and route
when more than 5% of non-`/health` HTTP requests return 5xx over five minutes,
with at least three 5xx responses in that window, and the condition stays true
for two minutes. This uses the existing `pairroom_http_requests_total` counter;
it does not alert on host utilization or health probes.

The alert labels include `service_name`, `deployment_environment_name`,
`service_version`, `http_route`, and `severity=warning`. Its summary and
description identify the affected route and release and direct the responder to
inspect the matching Loki logs, follow their `trace_id` values into Tempo, verify
the deployed version, and check PairRoom service health. Alert state and its
annotations are available through Prometheus; no external notification service
or Alertmanager is configured.

Validate and test the rule locally from the repository root:

```powershell
docker compose -f module-02/observability/compose.yaml exec -T prometheus promtool check rules /etc/prometheus/alerts.yaml
docker compose -f module-02/observability/compose.yaml run --rm --no-deps `
  -v "${PWD}/module-02/observability/alerts.test.yaml:/tmp/alerts.test.yaml:ro" `
  --entrypoint promtool prometheus test rules /tmp/alerts.test.yaml
```

The synthetic rule tests prove ordinary session traffic plus failing `/health`
probes do not fire the alert, while sustained 5xx failures on a user route do.
They also check the alert's route, service, environment, version, severity, and
actionable annotations. These checks use the pinned local Prometheus image and do
not enable or deploy observability to AWS.

`verify.py` runs the end-to-end checks against only this dedicated test project,
including a normal observability project restart. Run it from the repository root:

```powershell
uv run --project module-02/backend python module-02/observability/verify.py
```

It confirms Collector/backend connectivity, all three signal pipelines and their
resource labels, health/frontend/WebSocket behavior, and scans exported test
telemetry for generated tokens, session IDs, and private fixture content. It also
checks stored metrics, logs, traces and Grafana state after restart. Results are
written to the ignored `observability/.validation/results.json`. The script never
deletes volumes. To stop containers while preserving state, use Compose `stop` or
`down` on each project without the `--volumes` option.

The local Docker telemetry network exists only on the local host. The full
Collector, Prometheus, Loki, Tempo, and Grafana stack is currently validated and
run locally with the dedicated PairRoom test project. AWS development CI does
not install this stack or enable application telemetry on its 2 GiB `t3.small`;
no representative measurements demonstrate safe capacity for both PairRoom,
PostgreSQL, and all five observability services. Production does not install this
stack or enable telemetry through the production promotion workflow.

## AWS development deployment

Normal development CI does not set `PAIRROOM_DEPLOY_ENVIRONMENT`, so it takes the
existing immutable-image-only deployment path and leaves OpenTelemetry disabled.
The helper retains an explicit future opt-in: setting
`PAIRROOM_DEPLOY_ENVIRONMENT=development` enables stack installation and app
telemetry, but only after capacity has been established. That path still requires
at least 3,500,000 KiB of host memory; the guard is unchanged. The current
development `t3.small` has 2 GiB, and its ability to run PairRoom, PostgreSQL, and
the complete stack together has not been demonstrated. Do not enable the remote
stack on that host based on lowered limits alone.

When the explicit future opt-in is used on a sufficiently sized host, the CI
deploy helper copies only the pinned Compose and Collector/Prometheus/Loki/Tempo/
Grafana datasource configuration into `/opt/pairroom-observability` through SSM
Run Command. It does not copy `.env`, `.secrets`, `.validation`, local test
overrides, or generated validation data. The host creates the Grafana admin
password with `openssl rand`, sets it to mode 0600, and never prints it. Store or
retrieve that password only through a private operator session; it is never sent
from GitHub Actions.

The observability Compose project has its own Prometheus, Loki, Tempo, and Grafana
named volumes. The Collector's OTLP/HTTP port 4318 and Grafana's UI port 3000 are
bound to the EC2 host's loopback address. Prometheus, Loki, and Tempo have no
published ports. No security-group ingress is needed for these services; leave
the existing HTTP and SSH rules unchanged. PairRoom reaches the Collector as
`http://otel-collector:4318` over `pairroom-telemetry`; Prometheus, Loki, Tempo,
and Grafana use their Compose network.

To use Grafana, start an SSM port forward from the operator machine, replacing
`INSTANCE_ID` with the development EC2 instance ID:

```powershell
aws ssm start-session --region us-east-1 --target INSTANCE_ID `
  --document-name AWS-StartPortForwardingSession `
  --parameters '{"portNumber":["3000"],"localPortNumber":["3000"]}'
```

Then browse to `http://127.0.0.1:3000` and authenticate with the Grafana admin
account. Do not expose port 3000 or 4318 through a security group or public
interface. The operator identity needs permission to start and end an SSM session;
the GitHub deployment role does not need that permission.

With the explicit development opt-in, the helper passes the deployed image digest
as `service.version`, sets `deployment.environment.name=development` and service
name `pairroom-backend`, then starts the observability project before updating
only the PairRoom app. The app override joins `pairroom-telemetry` and sets
`OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318`. If stack startup fails,
the app update does not run. If the app update or verification fails, the helper
restores the previous app override and attempts an app-only rollback. It leaves
the observability containers and volumes available for diagnosis. This remote
path is not used by normal CI on the current `t3.small`.

PostgreSQL remains in the existing `pairroom` Compose project on its unchanged
`pairroom_postgres-data` volume. The deployment does not run database commands,
`docker compose down`, or any volume deletion. To roll back application telemetry,
run the deployment helper for the previous immutable digest with
`PAIRROOM_DEPLOY_ENVIRONMENT` unset; this restores an image-only PairRoom override.
Then stop or remove only the `pairroom-observability` Compose project. Use `down`
without `--volumes` to keep its telemetry data; deleting telemetry volumes is a
separate cleanup decision. Never run `docker compose down --volumes` on the
PairRoom project.

If remote observability is later enabled on a host that passes the memory guard,
validation should check each container, confirm no new public listeners or
security-group rules, and verify the app image digest and resource labels.
Harmless `/health` requests should exercise Prometheus metrics, Loki structured
logs, and Tempo traces without creating database records. Grafana should show all
three sources and trace/log correlation. Check PostgreSQL container identity,
health, and named volume before and after deployment; test persistence across a
normal observability restart without deleting volumes.

## Validation

From `module-02`, run:

```powershell
uv run --project backend pytest backend/tests -q
```

Telemetry tests use in-memory exporters and an ephemeral loopback HTTP receiver.
They verify correlation, resource labels, all three real OTLP protobuf export paths,
privacy, failed exporters, unchanged health and WebSocket behavior, and provider
cleanup across app lifespans. The tests use temporary databases and do not contact
AWS, GitHub, or a deployed Collector.

The local end-to-end run also passed against the pinned Collector/Prometheus/Loki/
Tempo/Grafana stack: three signals arrived with their resource labels; PairRoom
health, frontend, two-client WebSocket updates and heartbeat passed; the sensitive
fixture scan was clear; Prometheus, Loki, Tempo and a user-created Grafana folder
persisted across a normal observability restart. Seven correlated traces were
retrievable before and after restart. No AWS or GitHub services were used.
