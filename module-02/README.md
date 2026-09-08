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
