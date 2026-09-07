# Pairroom frontend prototype

React + Vite + JavaScript, managed with npm. Run these commands from `frontend/` using Node.js 22.12+ (verified with Node 24):

```sh
npm install
npm run dev
npm test
npm run build
npm run preview
```

`npm run test:watch` runs tests interactively. Commit `package-lock.json`; use `npm ci` for repeatable installation.

## Try the interview flow

1. Open the development URL and create a session. Both fields start empty.
2. Copy the candidate invitation and open it in a second tab of the same browser profile, using the exact same origin. Keep the interviewer URL to return later.
3. Edit the problem as interviewer; candidates can only read the problem. Both roles can edit the shared code. Observe updates and presence in the other tab. Use the Language selector for JavaScript or Python highlighting, with line numbers and Tab indentation (Escape then Tab exits).
4. Wait for “Saved in this browser,” then refresh either tab to check restoration.
5. Expand prototype connection controls to simulate disconnection. Editing pauses, the other tab updates presence, and reconnect restores saved content. Disconnect immediately after typing to see the unconfirmed-edit warning.
6. Alter a credential in a link to check the invalid-session view.

## Architecture and scope

`src/services/index.js` is the single service entry point. Components never access persistence or networking directly. Its mock adapter exposes `createSession()` and `joinSession(id, token, onChange)`. Joining returns `updateProblem`, `updateCode`, `disconnect`, `reconnect`, and `close`. Snapshots contain content, role, connection/presence, save state, warnings, and the interviewer-only invitation link. Cleanup releases timers and event listeners.

The mock uses localStorage, separate keys for each editable field, a 150 ms save debounce buffering problem and code independently, 200 ms synchronization polling, and one-second presence heartbeats with a three-second timeout. It validates role credentials and rejects unauthorized editing through its public methods. Only interviewers may update the problem; both roles may update code. One active tab per role is supported. Overlapping code edits use the last saved full text; there is no conflict merging, so take turns editing.

This is a browser-local simulation: different browsers, profiles, or devices cannot join the same session. Clearing browser storage removes sessions. Credentials in localStorage are inspectable; mock permissions are not a security boundary. Saved status means browser persistence, not server confirmation. A future backend must enforce authorization and provide durable storage, real-time transport, and an OpenAPI-aligned adapter. Backend restart durability and real backend timing criteria cannot be verified at this stage.

This frontend refinement supersedes the baseline specification's read-only interviewer code behavior: both roles edit code, while only the interviewer edits the problem. The root specification is unchanged for this frontend-only task.

Highlighting uses `@codemirror/lang-javascript` and `@codemirror/lang-python`. The selector defaults to JavaScript and applies locally to each workspace view; it is not synchronized or persisted and resets on refresh. Switching languages preserves code and cursor selection and does not translate or execute code. No code execution is implemented; browser-side WASM execution is deferred to a later homework step. No backend, database, OpenAPI, Docker, or deployment files are included.

Tests cover mock authorization, persistence, independent synchronized edits, bidirectional code updates, language selection and highlighting changes, presence, pending-save loss, reconnection, creation, clipboard behavior, role-based UI controls, storage failure, and invalid links. CodeMirror provides multiline editing, indentation, and syntax highlighting; editor behavior is also tested directly.
