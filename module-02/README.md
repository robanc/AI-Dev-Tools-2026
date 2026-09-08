# Pairroom — Module 2

Start the FastAPI backend and React/Vite frontend together from `module-02`.
Requirements: Node.js 22.12+, npm, Python 3.12+, and uv on your PATH.

Install dependencies once (and after dependency changes):

```sh
npm ci
npm --prefix frontend ci
uv sync --project backend
```

Then start the full application:

```sh
npm run dev
```

- Frontend: http://127.0.0.1:5173
- Backend API/docs: http://127.0.0.1:8000/docs

Press **Ctrl+C** in the same terminal to stop both processes. Output is prefixed
with `backend` or `frontend`; if either command exits, concurrently stops the
other. Ports 8000 and 5173 must be available; Vite uses `--strictPort` so it
cannot silently switch to an origin the backend does not allow.

The frontend command uses `cross-env` to set `VITE_INTERVIEW_SERVICE=real` and
`VITE_API_BASE_URL=http://127.0.0.1:8000` on Windows/PowerShell and Unix. These
settings apply to this command, overriding frontend `.env` values without editing
them. It calls the existing frontend `dev` script, including its Pyodide asset
preparation hook. To run the frontend in mock mode, use its separate instructions.

The backend uses the existing `uv run uvicorn` command from `backend/`, preserving
the default database at `backend/pairroom.db`. An existing `DATABASE_URL` or
`FRONTEND_ORIGINS` environment variable is inherited unchanged; custom origin
allowlists should include `http://127.0.0.1:5173`. No database settings, API
contracts, or browser-execution behavior are changed by this launcher.

The exact root `dev` script (homework Question 3) is:

```json
"dev": "concurrently --kill-others --names backend,frontend \"npm run dev:backend\" \"npm run dev:frontend\""
```

Individual services can also be started from here using `npm run dev:backend`
or `npm run dev:frontend`. See [frontend/README.md](frontend/README.md) and
[backend/README.md](backend/README.md) for configuration, tests, and the original
separate-terminal commands.

## Docker: one container for frontend and backend

From `module-02`, with Docker running in Linux-container mode:

```sh
docker build -t pairroom:module-02 .
docker run --name pairroom -p 8000:8000 --mount source=pairroom-data,target=/data pairroom:module-02
```

Open http://localhost:8000 for the frontend or http://localhost:8000/docs for
the API. The single Uvicorn process serves HTTP, WebSockets, the built React
frontend, and local Pyodide runtime assets. There is no Vite dev server,
concurrently, or Node runtime in the final image.

The multi-stage build uses `node:22-bookworm-slim` to run `npm ci` and the existing
frontend build (including the Pyodide preparation hook). A Python dependency
stage uses uv 0.12.10 and `backend/uv.lock`, excluding development dependencies.
**The final runtime base image is `python:3.12-slim-bookworm` (Homework Question 6).**
The server runs as non-root UID/GID 10001, with one worker to preserve the
existing process-local WebSocket ordering and presence behavior.

The image defaults to `DATABASE_URL=sqlite:////data/pairroom.db`. The named volume
keeps sessions and role grants across container replacement; do not remove it
if you want to retain links and content. `DATABASE_URL` remains configurable
with `-e DATABASE_URL=...`. A bind-mounted data directory must be writable by
UID 10001; a newly created Docker named volume gets the image directory's owner.

The Docker frontend is built in real mode with `VITE_API_BASE_URL=same-origin`,
so HTTP and WebSocket URLs follow the browser's host/port and HTTP(S) scheme.
Vite settings are build-time settings, not container-runtime settings. The
container's default WebSocket Origin allowlist contains `http://localhost:8000`
and `http://127.0.0.1:8000`. For another port or public hostname, set the exact
browser origin explicitly, for example:

```sh
docker run --name pairroom -p 8080:8000 --mount source=pairroom-data,target=/data -e FRONTEND_ORIGINS=http://localhost:8080 pairroom:module-02
```

Use HTTPS/WSS and a WebSocket-capable TLS proxy for a public deployment. FastAPI
serves the build configured by `FRONTEND_DIST=/app/frontend`. Existing hash-based
session links load at `/`; unmatched HTML navigation paths also receive the
React shell. API/docs paths, WebSockets, and missing asset paths keep their normal
responses rather than being replaced with HTML. Local development remains unchanged
when `FRONTEND_DIST` is unset. `.dockerignore` excludes local databases, secrets,
dependency directories, and old builds from the build context.

Stop and remove the container (the named volume remains):

```sh
docker stop pairroom
docker rm pairroom
```

With the container running, browser verification reuses the two-window collaboration
test and also executes JavaScript and Python using the packaged assets:

```sh
npm --prefix frontend run test:container
```

Install Playwright Chromium first (`cd frontend` then `npx playwright install chromium`),
or set `PLAYWRIGHT_CHANNEL=msedge` to use installed Edge. `CONTAINER_URL` defaults
to `http://127.0.0.1:8000`; set it when using another published port. These are
normal shell environment variables (PowerShell: `$env:CONTAINER_URL = 'http://127.0.0.1:8080'`).
The tests create sessions, so use a disposable test container/volume rather than
a database containing interviews you want to keep.
