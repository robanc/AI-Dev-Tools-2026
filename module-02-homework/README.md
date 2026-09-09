# TaskLane

TaskLane is a small full-stack Mini Kanban Board for Homework 2 of the AI Dev Tools Zoomcamp. It helps one person manage tasks across **To Do**, **In Progress**, and **Done**, with a required title and optional description.

The approved stack is React with Vite and JavaScript for the frontend, Python with FastAPI and uv for the backend, and SQLAlchemy with SQLite for persistence. The application will run locally and include backend and frontend tests.

The interactive frontend is in `frontend/`. Create, view, edit, move, and delete tasks on a responsive three-column board. It connects to the FastAPI backend in `backend/`, using SQLAlchemy and a persistent SQLite database by default.

All frontend HTTP operations are centralized in `frontend/src/services/taskService.js`. The frontend loads tasks from the backend on page load. Tasks, edits, status changes, and deletions persist across browser refreshes and backend restarts.

## Run the frontend

Prerequisite: Node.js 22.12 or newer (Node.js 24 recommended), including npm.

From the `module-02-homework` directory:

```powershell
cd frontend
npm ci
npm run dev
```

Open `http://127.0.0.1:5173`. Start the backend in a second terminal using the commands below. Stop either server with Ctrl+C. Vite uses strict ports so it cannot silently select a port outside the backend's CORS allowlist.

The frontend's default API base URL is **`http://127.0.0.1:8000`**. Task requests go to **`http://127.0.0.1:8000/api/tasks`** and `/api/tasks/{id}`. No proxy is used.

To change the backend origin, copy `frontend/.env.example` to `frontend/.env.local` and set `VITE_API_BASE_URL` to the desired origin (without `/api/tasks`). Restart Vite after changing it; production builds embed the value at build time. The default needs no environment file.

## Tests and production build

From `module-02-homework/frontend`:

```powershell
npm test
npm run build
```

For interactive test reruns, use `npm run test:watch`. To serve the production build locally after building, use `npm run preview`.

Tests use Vitest and React Testing Library. UI tests exercise the real HTTP service with an isolated fetch fixture; service tests check request URLs, methods, payloads, 204 responses, and HTTP/network errors. They cover the main task workflows, validation, loading and failure recovery, and duplicate submission prevention. Native dialog methods are shimmed in jsdom; browser focus trapping and responsive layout require browser verification.

With the backend running, verify real communication from `frontend/`:

```powershell
node scripts/check-api.mjs
```

This uses the production frontend service for CRUD, all status changes, and reloading server state, and checks the CORS preflight response. It deletes its own temporary task. Set `TASKLANE_API_URL` for this Node-only check if the backend is on another origin; the browser uses `VITE_API_BASE_URL`.

## Run the backend

Prerequisites: Python 3.12 or newer and uv installed. From `module-02-homework`, in a separate terminal:

```powershell
cd backend
uv sync --locked
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

The API is at `http://127.0.0.1:8000/api/tasks`. Interactive API documentation is at `http://127.0.0.1:8000/docs`, and generated OpenAPI JSON is at `/openapi.json`. Stop the server with Ctrl+C. No environment activation is needed; uv uses `backend/.venv`.

The design-first API contract is [openapi.yaml](openapi.yaml). The backend supports listing tasks (200), creating tasks in To Do (201), partial updates (200), and deletion (204 with no body). Invalid input returns 422; missing tasks return 404. PATCH preserves omitted fields, allows an empty object as a no-op, and rejects explicit nulls and unknown fields. Titles are trimmed before validation; description whitespace is preserved.

CORS permits `http://localhost:5173`, `http://127.0.0.1:5173`, and the equivalent Vite preview origins on port 4173. Use those frontend ports, or explicitly update the allowed origins.

## Database setup and persistence

No separate database installation or initialization command is needed for SQLite. `uv sync --locked` installs SQLAlchemy; the backend creates the `tasks` table on startup. The default database is `backend/tasklane.db`, resolved relative to the backend source directory so changing the working directory does not select a different database. The file is ignored by Git.

Keep that file to retain tasks across restarts. A new database starts empty. Schema creation does not erase existing rows; automatic schema migrations are outside this homework scope.

Set `DATABASE_URL` in the backend terminal to use another database. For example, from `backend/`:

```powershell
$env:DATABASE_URL = "sqlite:///./custom-tasklane.db"
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Custom relative SQLite paths are relative to the process working directory; their parent directories must exist. Remove the override with `Remove-Item Env:DATABASE_URL` to return to the default. The backend reads environment variables directly; it does not automatically load a `.env` file.

The store uses SQLAlchemy ORM queries and a separate transactional session per operation. Other SQLAlchemy database URLs can be configured by installing the matching synchronous driver and provisioning that database. SQLite is the database tested for this homework; other database servers have not been verified.

## Backend tests

From `module-02-homework/backend`:

```powershell
uv run pytest -q
```

Every backend test uses an isolated temporary SQLite database, never `backend/tasklane.db`. Tests cover CRUD, validation, missing tasks, CORS, OpenAPI, database isolation, configuration, persistence through fresh app/engine lifecycles, and persistence across separate Python processes.

To run all homework tests from `module-02-homework` after installing dependencies:

```powershell
uv run --project backend pytest backend/tests -q
npm --prefix frontend test
```

To also verify the frontend production build:

```powershell
npm --prefix frontend run build
```

## Project guidance

- [Approved product specification](_docs/specs.md)
- [Coding agent instructions](AGENTS.md)
