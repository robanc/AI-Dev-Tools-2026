# Pairroom backend

To start both services together, follow the [root README](../README.md) dependency
setup and run `npm run dev` from `module-02`. It runs the same backend command
from this directory, preserving the default SQLite path. Ctrl+C stops both
services. For backend-only development, use the commands below.

Python 3.12+ and uv are required. From this repository:

```powershell
cd backend
uv sync
# Optional: defaults to sqlite:///./pairroom.db (relative to working directory).
$env:DATABASE_URL = "sqlite:///./pairroom.db"
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

Startup creates the SQLite file and missing tables automatically. The parent
directory must already exist. Sessions, role access grants, problem text, code,
timestamps and revisions survive backend restarts. Writes commit before HTTP
success or WebSocket broadcast. Keep the database file to keep existing links.
There is no import of sessions from the previous in-memory backend.

Run a single worker: WebSocket subscriptions, presence and ordering locks remain
process-local. Synchronous, short database transactions suit this small course
MVP; multi-worker broadcasting and production-scale traffic are not supported.

`DATABASE_URL` accepts SQLAlchemy connection URLs. SQLite is the default;
models and transactions use portable SQLAlchemy operations. PostgreSQL can be
configured later, for example with `postgresql+psycopg://user:password@localhost/pairroom`,
after installing its driver and creating the database. PostgreSQL has not been
verified in this step. No Alembic is needed for the initial schema: `create_all`
creates missing tables but does not migrate existing tables after schema changes.

The connected frontend uses the four HTTP operations in [openapi.yaml](../openapi.yaml)
and the WebSocket protocol in [realtime.md](../docs/realtime.md). FastAPI docs are
at `http://127.0.0.1:8000/docs`; the root contract is authoritative for errors.

`FRONTEND_ORIGINS` is a comma-separated CORS and WebSocket Origin allowlist,
defaulting to `http://localhost:5173,http://127.0.0.1:5173`. WebSocket clients must
send an allowed Origin, authenticate within five seconds, and ping every ten
seconds. The server closes connections after 25 seconds without a ping.
A second socket for the same role is rejected without replacing the first.

Use HTTPS/WSS outside local development. Keep role links and database files/backups
private: grants store opaque tokens, including the retrievable candidate token
needed to return the invitation link to the interviewer. Tokens belong in HTTP
Authorization headers or the first WebSocket message, never URL query parameters.
The application does not log credentials or payloads. SQLAlchemy SQL echo is off
and bound parameters are hidden in SQL logs/errors. Keep transport debug/trace
logging disabled because third-party loggers can log frames. Local `.db` files
and SQLite sidecars are git-ignored.

Structure:

- `app/database.py`: engine, database session factory, schema initialization and disposal.
- `app/models.py`: session and role-grant tables.
- `app/repository.py`: persisted creation, authorization, reads and atomic field updates.
- `app/store.py`: per-session locks and ordered WebSocket subscription queues.
- `app/routers.py`, `auth.py`, `schemas.py`: HTTP handlers, permissions and JSON models.
- `app/realtime.py`: sockets; `app/main.py`: lifespan, errors and CORS.

Checks, from `backend/`:

```powershell
uv run pytest -q
uv run python -m compileall -q app tests
uv run python -c "from app.main import app; print(app.title); print(sorted(app.openapi()['paths']))"
uv run openapi-spec-validator ../openapi.yaml
```

Tests override `DATABASE_URL` with a fresh temporary SQLite file for every test;
they do not touch the development database. Coverage includes HTTP contracts,
permissions, validation, concurrent field saves, restart durability of content
and grants, failed-commit rollback without broadcasts, and WebSocket snapshots,
ordered broadcasts, presence, reconnection, authentication, Origin and timeouts.
In-process two-client timing checks do not replace the specification's two-browser
acceptance check against a live backend.
