# Pairroom frontend

React, Vite and JavaScript, managed with npm. Use Node.js 22.12+.

## Run with the real backend

In one terminal, start the backend (Python 3.12+ and uv required):

```powershell
cd backend
uv sync
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

In another terminal:

```powershell
cd frontend
npm ci
$env:VITE_INTERVIEW_SERVICE = 'real'
$env:VITE_API_BASE_URL = 'http://127.0.0.1:8000'
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Alternatively, copy `.env.example` to `.env.local`; restart Vite after changing
environment variables. `VITE_INTERVIEW_SERVICE` accepts `mock` (the default) or
`real`. `VITE_API_BASE_URL` defaults to `http://127.0.0.1:8000` and must be an HTTP(S)
base URL without query parameters, fragments, or credentials. Vite embeds these
public settings at build time ([Vite environment documentation](https://vite.dev/guide/env-and-mode)). Never put role tokens in environment files.

The backend allows frontend origins `http://localhost:5173` and
`http://127.0.0.1:5173` by default. For another frontend origin, set the backend's
`FRONTEND_ORIGINS` allowlist before starting it. For production preview on port
4173, add that exact origin too. Use HTTPS/WSS outside local development.

## Try both roles

1. Open `http://127.0.0.1:5173`, create a session, and keep the interviewer URL.
2. Copy the candidate link into a second browser window. One active window/tab
   per role is supported; duplicate role connections are rejected.
3. Edit the problem as interviewer and code from both roles, taking turns.
   The candidate's problem is read-only. Check presence and updates without refresh.
4. Wait for "Saved on server," then refresh. The latest confirmed text reloads.
5. Disconnect the network: editing pauses after failure detection. Reconnection
   reloads saved state before editing resumes. Unconfirmed edits produce a warning
   and are not replayed automatically. "Reconnect" allows a manual retry.
6. Alter the session/token in a link to check the invalid-link error.

The backend currently stores sessions **in memory only**. Restarting it loses all
sessions, tokens and saved text. "Saved on server" confirms an in-memory write,
not restart durability. No SQLite or execution support is added here.

## Mock mode

Leave `VITE_INTERVIEW_SERVICE` unset or set it to `mock` to run without a backend.
The original mock service is preserved. Its links only work on the same origin
and browser profile; its saved status means localStorage persistence. Prototype
connection controls remain available in mock mode. Mock and real sessions are
separate; switching mode does not migrate links or content.

## Service boundary

Components import only `src/services/index.js`. Both adapters expose
`createSession()` and `joinSession(id, token, onChange, onError)`; the optional
error callback reports asynchronous terminal failures in real mode. Joining
returns `updateProblem`, `updateCode`, `disconnect`, `reconnect`, and `close`
immediately. The mock still reports invalid links synchronously.

The real adapter implements [openapi.yaml](../openapi.yaml) and
[realtime.md](../docs/realtime.md). Tokens from the URL hash go into HTTP bearer
headers and the initial WebSocket authentication message, never query strings.
GET supplies role/access; only an authenticated WebSocket snapshot enables
editing. HTTP updates confirm saves; WebSocket events update text and presence.
Per-field pending text, serialized writes and revision ordering prevent old
responses from overwriting newer input. Writes flush within 150 ms when no prior
same-field request is in flight. Network failures retry after 1, 2, 4, then at
most 5 seconds; invalid links and protocol/permission failures stop automatic
retries. HTTP and WebSocket setup time out after 10 seconds. Pings run every
10 seconds, with five seconds allowed for pong. Cleanup aborts requests, closes
sockets and removes timers/listeners.

JavaScript/Python highlighting stays local, defaults to JavaScript and resets
on refresh. It is not saved or synchronized and never executes code.

## Checks

```powershell
npm test
npm run build
npm run preview
```

Set the real-mode environment **before building** a production bundle to test it
against the backend. `npm run test:watch` runs tests interactively. Unit tests
cover both adapters, HTTP headers/bodies, save ordering, WebSocket events,
reconnection, cleanup, async UI errors, role controls, and local highlighting.
Mock UI tests explicitly choose the mock regardless of development environment.

The live two-window browser check starts isolated frontend/backend servers on
ports 5174/8001 and stops them afterward:

```powershell
npx playwright install chromium
npm run test:e2e
```

If Microsoft Edge is already installed, skip the browser download and instead
set `$env:PLAYWRIGHT_CHANNEL = 'msedge'` before `npm run test:e2e`. The test uses
two independent browser contexts, checks propagation within one second in both
directions, presence, refresh, offline/reconnect behavior, and invalid links.
Generated results and screenshots in `test-results/` are ignored by git.
