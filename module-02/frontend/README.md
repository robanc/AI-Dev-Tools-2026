# Pairroom frontend

React, Vite and JavaScript, managed with npm. Use Node.js 22.12+.

## Run with the real backend

For a single-terminal startup, install dependencies as described in the
[root README](../README.md), then run `npm run dev` from `module-02`.
It starts both services and sets real-backend mode automatically. Ctrl+C stops
both. The separate-terminal commands below remain available.

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

The backend persists sessions and role grants in SQLite; confirmed saves survive
restarts while that database is retained. See the backend README for configuration.

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
on refresh. Changing language does not save, synchronize, or execute anything.

## Browser-only execution

Either role can click **Run** beside the language selector. The runner uses the
current editor text (including pending local edits) and selected language at click
time. Receiving shared code never automatically runs it. Run does not save or send
an execution request to FastAPI; ordinary collaboration saves still work as before.

- JavaScript executes in a new dedicated browser worker, not in React. Console
  log/info/warn/error/debug output is captured; top-level `await` is supported.
  There is no `eval` or `Function` execution in the UI thread and no DOM access
  from the worker. Unawaited background work is discarded when the run completes.
- Python executes with the pinned official `pyodide` npm package (314.0.6), using
  CPython compiled to WebAssembly inside a new worker. Python stdout and stderr
  are captured, including `print()`. Standard-library code is supported; package
  installation and interactive stdin are not part of this MVP (`input()` gets EOF).
- Output and errors appear as plain text in **Output**, labeled with the run
  language. They are local, not synchronized or persisted, and clear on the next
  run or when leaving the room. Expressions alone are not automatically printed;
  use `console.log(...)` or `print(...)`.
- Run is disabled during startup/execution. **Stop** terminates the worker.
  The page starts a **five-second execution deadline** after the worker is ready,
  and terminates it even if code loops forever. Python startup has a separate
  **30-second deadline**. Startup/runtime errors and timeouts re-enable Run.
  Navigating away also cancels execution; each new run starts with fresh globals.
- Output is buffered until completion, capped at 20,000 characters and marked if
  truncated. Stopping or timing out loses the unfinished run's buffered output.
  Browser background-tab throttling can delay the page's timeout callback.

`npm run dev` and `npm run build` copy the runtime assets from the installed
package into ignored `public/pyodide/`; Vite includes them in `dist/pyodide/`.
Deploy the complete `dist` directory, including these roughly 14 MB of assets.
No runtime CDN is required. The first Python run may take longer to load/compile
WASM. See [Pyodide usage](https://pyodide.org/en/stable/usage/index.html).

Workers isolate computation from React and the DOM; they are **not a hardened
sandbox for malicious code**, a network firewall, or a strict memory quota.
Only run code you trust. No session credentials are passed to the runner, but
normal worker APIs (including networking and origin storage) remain available.
A deployment CSP must permit the worker, runtime modules, WASM and dynamic
JavaScript compilation within the worker; the React page itself does not need
dynamic compilation permission.

## Checks

```powershell
npm test
npm run build
npm run preview
```

Set the real-mode environment **before building** a production bundle to test it
against the backend. `npm run test:watch` runs tests interactively. Unit tests
cover both adapters, HTTP headers/bodies, save ordering, WebSocket events,
reconnection, cleanup, async UI errors, role controls, local highlighting, Run/Stop
states, output/error rendering, timeouts, and cleanup. Worker tests execute real
JavaScript and Pyodide/WASM in Node worker threads through a small browser-message
adapter; browser tests additionally verify the actual production worker/assets.
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

Browser execution tests run the production frontend in mock mode with no backend:

```powershell
npm run build
$env:PLAYWRIGHT_CHANNEL = 'msedge' # Optional, if Edge is installed
npm run test:execution
```

These check JavaScript/Python output, errors, infinite-loop termination and a
responsive page, fresh runs, and output remaining local between the two roles.
No lint script is configured; the production build checks JSX/import resolution.
