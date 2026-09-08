# Collaborative Coding Interview — Product Specification

Version: 0.3

Status: Module 2 MVP with JavaScript/Python highlighting and explicit browser-only execution.

Context: AI Dev Tools Zoomcamp, Module 2

## 1. Product overview

The application lets an interviewer create a coding interview session and share a candidate link. The interviewer provides a problem statement, and both participants may edit the solution in a shared browser-based code editor.

Both participants see the same problem and code, with changes synchronized in real time. Only the interviewer edits the problem statement; the candidate reads it. Both roles may edit the shared code. Participants use an external call service to talk during the interview.

This specification defines a small course-project MVP. It does not prescribe an implementation stack.

The frontend supports the real FastAPI backend with SQLite persistence and an optional browser-local mock service. The mock shares saved text between tabs on the same origin and browser profile; its saved status means local browser persistence, not server confirmation. Browser-only execution is independent of the selected collaboration service.

## 2. Goals

- Let an interviewer create and share a session without account setup.
- Provide a shared problem statement and allow either participant to edit the shared code.
- Synchronize edits without requiring page refreshes.
- Preserve saved session content across refreshes and temporary disconnections.
- Keep the initial implementation small and testable.

## 3. Target users

| User | Needs |
| --- | --- |
| Interviewer | Create a session, describe a problem, and read and edit the shared solution as it develops. |
| Candidate | Open an invitation link, read the problem, and write code without installing software. |

## 4. User stories

- **US-01:** As an interviewer, I want to create a session so that I can conduct an interview.
- **US-02:** As an interviewer, I want to copy a candidate invitation link so that the candidate can join my session.
- **US-03:** As an interviewer, I want to write and update the problem statement so that the candidate knows what to solve.
- **US-04:** As a candidate, I want to open the invitation link and see the current problem and code.
- **US-05:** As either participant, I want to edit shared code while the other participant sees my changes in real time.
- **US-06:** As either participant, I want to see whether the other participant is connected.
- **US-07:** As either participant, I want to refresh or reconnect without losing changes already saved by the server.

- **US-08:** As either participant, I want to select JavaScript or Python highlighting without changing the shared code.

## 5. Functional requirements

### Session creation and access

- **FR-01:** The interviewer can create a session from the home screen.
- **FR-02:** A new session starts with an empty problem statement and empty code.
- **FR-03:** Creation opens the interviewer's session view and provides a copyable candidate invitation link.
- **FR-04:** Separate, unguessable links grant interviewer or candidate access. Accounts are not required.
- **FR-05:** Opening a valid link loads the session's latest saved content.
- **FR-06:** An invalid session link displays a clear error.

### Problem statement and code editor

- **FR-07:** Only the interviewer can edit the plain-text problem statement. The candidate has read-only access to it.
- **FR-08:** Both interviewer and candidate can edit the shared code while connected. Overlapping edits use the last saved full text; automatic conflict merging is not required.
- **FR-09:** The editor supports multiline text, indentation, line numbers, and syntax highlighting for JavaScript and Python. Both roles have a small language selector offering only these two languages, defaulting to JavaScript. Selection changes highlighting without replacing code or cursor selection. It is local to each workspace view, is not synchronized or persisted, and resets on refresh.
- **FR-10:** Either role may explicitly Run the current editor text locally as JavaScript in a dedicated worker or Python using Pyodide/WebAssembly in a dedicated worker. Never execute on typing, receipt of shared edits, refresh, or language change. Execution sends no code to the backend for execution and receives no session credentials. Output and language remain local. Server-side execution remains out of scope.
- **FR-21:** Show local stdout/console output, stderr and runtime errors as plain text in a labeled output panel. Each run starts fresh, replaces previous output and uses a snapshot of code/language at click time. Cap captured output at 20,000 characters.
- **FR-22:** Disable Run while loading/running; allow Stop. Terminate the worker after five seconds of execution, with a separate 30-second startup deadline. Stop, timeout and leaving the room release worker resources. Runtime errors and infinite loops must not freeze React or interrupt collaboration. Interactive stdin, package installation and background tasks after completion are unsupported.

### Real-time synchronization

- **FR-11:** Problem changes appear in the candidate's view without refreshing.
- **FR-12:** Code changes from either role appear in the other participant's view without refreshing.
- **FR-13:** Each participant sees their connection state and whether the other role is connected.
- **FR-14:** The interface distinguishes changes awaiting server confirmation from changes confirmed as saved.
- **FR-15:** The interface and service layer allow both roles to edit code and only the interviewer to edit the problem statement. The backend must enforce the same permissions when implemented; the current mock enforces them through its public methods.

### Persistence and reconnection

- **FR-16:** The backend persists the latest problem statement and code.
- **FR-17:** Refreshing either view restores the latest server-confirmed content.
- **FR-18:** When disconnected, the application shows a notice and disables editing once it detects the disconnection.
- **FR-19:** After reconnecting, the application loads the latest saved content before enabling editing.
- **FR-20:** If a pending edit cannot be confirmed after a disconnection, the interface warns that it may not have been saved.

## 6. Acceptance criteria

"Real time" means within one second under normal network conditions during testing with two browser windows connected to the same running backend. This is a course-project target, not a production service guarantee.

| ID | Scenario | Expected result |
| --- | --- | --- |
| AC-01 | Interviewer selects "Create session." | A new session opens with empty problem and code fields and a candidate invitation link. |
| AC-02 | Candidate opens that link in another browser. | The candidate sees the same session and its latest saved content. |
| AC-03 | Interviewer edits the problem statement. | The candidate sees the update within one second without refreshing. |
| AC-04 | Either interviewer or candidate types or deletes code while connected; verify both directions. | Editing is allowed, and the other participant sees the update within one second without refreshing. |
| AC-05 | Candidate attempts to change the problem statement. | The interface prevents editing, the mock service rejects the change, and the backend must reject it when implemented. Interviewer problem edits and code edits by either role are authorized while connected. |
| AC-06 | Either participant refreshes after changes are confirmed as saved. | The problem and code are restored. |
| AC-07 | A participant disconnects. | Their interface indicates the disconnection and disables editing; the other participant's presence indicator updates after connection loss is detected. |
| AC-08 | A participant reconnects. | The latest saved state loads, presence updates, and authorized editing becomes available. |
| AC-09 | A participant opens an invalid link. | A clear "Session not found or link invalid" message appears. |
| AC-10 | Either participant enters or receives code as editor text. | The application displays, saves, and synchronizes text without automatically executing it; only an explicit Run starts execution. |
| AC-11 | Either role uses the editor with JavaScript or Python selected; verify both languages. | Multiline editing, indentation, line numbers, and highlighting for the selected language are available. |
| AC-12 | Either role switches the language selector between JavaScript and Python. | Only these two options are offered. Highlighting changes while code and cursor selection are preserved; the other participant's selection is unaffected. A new view or refresh defaults to JavaScript. |
| AC-13 | Interviewer edits both problem and code before pending changes save. | Both fields are saved and synchronized without one pending field discarding the other; saved content is restored on reopening. |
| AC-14 | Either role runs JavaScript or Python. | Execute the current editor snapshot in a worker; console.log/print output appears locally. Python uses Pyodide/WASM; no backend execution request occurs. |
| AC-15 | Code throws or Python raises an exception. | Show the error and preceding output as plain text; the application remains usable and another run succeeds. |
| AC-16 | Code loops forever, or runtime startup stalls. | Main UI stays responsive; terminate execution after five seconds or startup after 30 seconds, show a clear message and re-enable Run. Stop also terminates; leaving the room cleans up. |
| AC-17 | Code is running while edits or language changes occur. | Disable duplicate runs; execute the captured snapshot without modifying shared code or save state. Output is labeled with the run language and stays in this view only. |

## 7. Non-goals / out-of-scope features

- User accounts, profiles, and account-based authentication.
- Server-side code execution or compilation infrastructure, automated tests of candidate solutions, and grading.
- Automatic merging or conflict resolution for overlapping code edits. Both roles may edit code; the last saved full text wins, so participants should take turns.
- Multiple candidates, additional interviewers, or spectators.
- Audio, video, chat, and screen sharing.
- Multiple files, terminals, package installation, or project workspaces.
- Advanced IDE features.
- Interview recording, playback, revision history, or analytics.
- Scheduling, email invitations, problem libraries, or hiring integrations.
- Offline editing and merging conflicting edits.
- Session dashboards, formal completion workflows, and production-scale guarantees.

JavaScript and Python highlighting and explicit browser-only execution are in scope. Server-side execution remains out of scope.

## 8. Main application screens

### Home screen

- Brief description of the application.
- "Create session" button.

### Interviewer session screen

- Editable problem statement.
- Editable shared code editor with a JavaScript/Python language selector.
- "Copy candidate link" button.
- Connection, candidate presence, and save status.

### Candidate session screen

- Read-only problem statement.
- Editable shared code editor with a JavaScript/Python language selector.
- Connection, interviewer presence, and save status.

The two session screens can share one layout with role-based controls. Invalid links use a simple error view. The language selector is available to both roles. Both roles have Run/Stop controls and a local output panel.

## 9. Main data/entities

| Entity | Main data | Persistence |
| --- | --- | --- |
| Interview session | Session ID, problem text, code text, creation time, last update time, content revision | Persisted |
| Session access grant | Session reference, role, secret link credential | Persisted securely |
| Participant connection | Session reference, role, connection status, last activity | Temporary |

The session is the central record. Separate user, question, and code-file entities are unnecessary for this version. The selected highlighting language is local view state, not persisted session data. Execution output and status are transient local view state, never persisted or synchronized.

## 10. High-level frontend/backend interactions

1. **Create:** The frontend requests a new session. The backend creates the session and role-specific access links.
2. **Join:** The frontend submits its link credential. The backend validates access and returns the role and current session content.
3. **Connect:** The frontend establishes a real-time connection. The backend updates participant presence.
4. **Edit:** The authorized frontend sends a problem or code update.
5. **Save and broadcast:** The backend validates the role, persists the update, confirms it to the sender, and broadcasts it to the other participant.
6. **Reconnect:** The frontend reconnects and retrieves the latest server state before resuming edits.

The backend is the authoritative source of saved content. The exact framework, database, and real-time transport remain implementation decisions. Browser execution is independent of backend interactions; execution output is never synchronized.

## 11. Assumptions and constraints

- Each session has one interviewer and one candidate.
- Each role uses one active browser tab; duplicate-tab editing is unsupported in this version.
- Participants use modern desktop browsers and normally have an internet connection.
- Possession of a role-specific link grants that role's access. Links must be treated as private.
- The interviewer keeps their own link to return later; account-based recovery is unavailable.
- Only the latest problem and code are retained, without revision history.
- Sessions remain available while their records exist; automatic expiration is deferred.
- Participants communicate through an external service.
- Unsaved edits may be lost during a connection failure; confirmed saved edits must survive refreshes and backend restarts.
- Highlighting and local execution support JavaScript and Python. Workers protect UI responsiveness and DOM access, but are not a hardened sandbox for malicious code or a strict memory quota. Only run code you trust; runtime assets are served by the frontend.

## 12. Scope decisions and remaining questions

| Topic | Decision or current assumption | Scope implication |
| --- | --- | --- |
| Editing responsibilities | Only the interviewer edits the problem; both roles may edit shared code. | Last saved full text wins for overlapping edits; no conflict-resolution system is required. |
| Programming languages | JavaScript and Python syntax highlighting. | Local selector defaults to JavaScript; selection is not synchronized or persisted. |
| Browser-side execution | Explicit Run; JavaScript worker and Python Pyodide/WASM worker. | Local output/errors, five-second execution timeout, 30-second startup timeout; no backend execution or output synchronization. |
| Server-side execution | Out of scope. | No server execution or compilation infrastructure. |
| Participant identity | Private role-specific links without accounts. | Links establish access rather than verified identity. |
| Synchronized state | Problem text, code text, and presence. | Shared cursors, selections, and scroll positions are unnecessary for the MVP. |
| Offline behavior | Editing pauses; reconnect reloads saved state. | Offline recovery and merging are outside the MVP. |
| Current session view | Problem, code, and connection status. | Timers, scoring, and interview stages are unnecessary for the core workflow. |

The baseline requirements and acceptance criteria guide implementation and verification. Update this specification with any homework-driven refinements before implementing the affected features.
