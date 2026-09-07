# Pairroom backend

Python 3.12+ and uv are required. From this repository:

```powershell
cd backend
uv sync
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

Run a single worker. Sessions, opaque role tokens, and content live only in this
process; stopping/reloading it loses everything. Successful writes are confirmed
in memory, **not durable across restarts**. This is the explicitly requested
intermediate storage implementation; the restart guarantees in the root contract
and specification remain unimplemented until persistent storage is added.

The frontend still uses its mock service. Nothing in this step connects it to
the backend. The API implements the four operations in [openapi.yaml](../openapi.yaml)
and the server portion of [realtime.md](../docs/realtime.md). Interactive FastAPI
docs are at `http://127.0.0.1:8000/docs`; the root contract remains authoritative
for error responses (including validation errors mapped to 400).

`FRONTEND_ORIGINS` is a comma-separated allowlist for CORS and WebSocket Origin
validation, defaulting to `http://localhost:5173,http://127.0.0.1:5173`. WebSocket
clients, including test/native clients, must send an allowed Origin header.
Authenticate in the first JSON message within five seconds; send `ping` every
10 seconds. The server closes connections after 25 seconds without a ping.
A second socket for the same role is rejected without replacing the first.

Use HTTPS/WSS outside local development. Keep role links private. Tokens belong
in HTTP Authorization headers or the initial WebSocket message, never query
parameters. The application does not log payloads or credentials; keep protocol
debug/trace logging disabled, since third-party transport loggers can log frames.

Structure: `app/routers.py` handles HTTP; `schemas.py` defines JSON models;
`auth.py` validates bearer headers; `store.py` owns sessions, atomic writes and
ordered subscription queues; `realtime.py` handles sockets; `main.py` wires
errors, CORS and application state. Each app instance owns an isolated store.
Queues and storage are intended for this small single-process course MVP, not
production-scale traffic.

Checks, from `backend/`:

```powershell
uv run pytest -q
uv run python -m compileall -q app
uv run python -c "from app.main import app; print(app.title); print(sorted(app.openapi()['paths']))"
uv run openapi-spec-validator ../openapi.yaml
```

Tests exercise HTTP permissions, validation, process-lifetime storage, concurrent
field saves, authenticated WebSocket snapshots/broadcasts, presence, reconnection,
Origin validation, malformed messages and timeouts. In-process two-client timing
checks do not replace the spec's two-browser, live-backend acceptance test; that
full UI verification remains pending frontend integration. Restart durability is
deliberately not claimed.
