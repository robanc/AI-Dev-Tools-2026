# Collaborative Coding Interview — Product Specification

Version: 0.1  
Status: Approved MVP scope; language support and browser-side execution remain implementation decisions.  
Context: AI Dev Tools Zoomcamp, Module 2

## 1. Product overview

The application lets an interviewer create a coding interview session and share a candidate link. The interviewer provides a problem statement, and the candidate writes a solution in a browser-based code editor.

Both participants see the same problem and code, with changes synchronized in real time. The interviewer edits the problem and observes the code; the candidate reads the problem and edits the code. Participants use an external call service to talk during the interview.

This specification defines a small course-project MVP. It does not prescribe an implementation stack.

## 2. Goals

- Let an interviewer create and share a session without account setup.
- Provide a shared view of the problem statement and candidate's code.
- Synchronize edits without requiring page refreshes.
- Preserve saved session content across refreshes and temporary disconnections.
- Keep the initial implementation small and testable.

## 3. Target users

| User | Needs |
| --- | --- |
| Interviewer | Create a session, describe a problem, and observe the candidate's solution as it develops. |
| Candidate | Open an invitation link, read the problem, and write code without installing software. |

## 4. User stories

- **US-01:** As an interviewer, I want to create a session so that I can conduct an interview.
- **US-02:** As an interviewer, I want to copy a candidate invitation link so that the candidate can join my session.
- **US-03:** As an interviewer, I want to write and update the problem statement so that the candidate knows what to solve.
- **US-04:** As a candidate, I want to open the invitation link and see the current problem and code.
- **US-05:** As a candidate, I want to write code while the interviewer sees my changes in real time.
- **US-06:** As either participant, I want to see whether the other participant is connected.
- **US-07:** As either participant, I want to refresh or reconnect without losing changes already saved by the server.

## 5. Functional requirements

### Session creation and access

- **FR-01:** The interviewer can create a session from the home screen.
- **FR-02:** A new session starts with an empty problem statement and empty code.
- **FR-03:** Creation opens the interviewer's session view and provides a copyable candidate invitation link.
- **FR-04:** Separate, unguessable links grant interviewer or candidate access. Accounts are not required.
- **FR-05:** Opening a valid link loads the session's latest saved content.
- **FR-06:** An invalid session link displays a clear error.

### Problem statement and code editor

- **FR-07:** The interviewer can edit a plain-text problem statement. The candidate can read it.
- **FR-08:** The candidate can edit the code. The interviewer sees a read-only copy.
- **FR-09:** The editor supports multiline text, indentation, line numbers, and syntax highlighting. Supported programming languages and any language-selection controls are implementation decisions to refine against the Module 2 homework requirements.
- **FR-10:** The application stores and displays code as text. Whether to provide browser-side code execution, and its supported language/runtime and behavior, remains an implementation decision to refine against the Module 2 homework requirements. Execution is neither required by this baseline nor permanently excluded.

### Real-time synchronization

- **FR-11:** Problem changes appear in the candidate's view without refreshing.
- **FR-12:** Code changes appear in the interviewer's view without refreshing.
- **FR-13:** Each participant sees their connection state and whether the other role is connected.
- **FR-14:** The interface distinguishes changes awaiting server confirmation from changes confirmed as saved.
- **FR-15:** The backend enforces each role's editing permissions.

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
| AC-04 | Candidate types or deletes code. | The interviewer sees the update within one second without refreshing. |
| AC-05 | Candidate attempts to change the problem, or interviewer attempts to change the code. | The interface prevents editing, and the backend rejects unauthorized changes. |
| AC-06 | Either participant refreshes after changes are confirmed as saved. | The problem and code are restored. |
| AC-07 | A participant disconnects. | Their interface indicates the disconnection and disables editing; the other participant's presence indicator updates after connection loss is detected. |
| AC-08 | A participant reconnects. | The latest saved state loads, presence updates, and authorized editing becomes available. |
| AC-09 | A participant opens an invalid link. | A clear "Session not found or link invalid" message appears. |
| AC-10 | Candidate enters code as editor text. | The application displays, saves, and synchronizes the text independently of whether browser-side execution is included. |
| AC-11 | Candidate uses the editor with a language selected for implementation. | Multiline editing, indentation, line numbers, and syntax highlighting are available. |

If browser-side execution is included after reviewing the homework requirements, define its acceptance criteria before implementing that feature.

## 7. Non-goals / out-of-scope features

- User accounts, profiles, and account-based authentication.
- Server-side code execution or compilation infrastructure, automated tests of candidate solutions, and grading.
- Simultaneous editing of the same document by both participants.
- Multiple candidates, additional interviewers, or spectators.
- Audio, video, chat, and screen sharing.
- Multiple files, terminals, package installation, or project workspaces.
- Advanced IDE features.
- Interview recording, playback, revision history, or analytics.
- Scheduling, email invitations, problem libraries, or hiring integrations.
- Offline editing and merging conflicting edits.
- Session dashboards, formal completion workflows, and production-scale guarantees.

Programming-language support and browser-side code execution are pending implementation decisions, not permanent exclusions.

## 8. Main application screens

### Home screen

- Brief description of the application.
- "Create session" button.

### Interviewer session screen

- Editable problem statement.
- Read-only code editor.
- "Copy candidate link" button.
- Connection, candidate presence, and save status.

### Candidate session screen

- Read-only problem statement.
- Editable code editor.
- Connection, interviewer presence, and save status.

The two session screens can share one layout with role-based controls. Invalid links use a simple error view. Any language-selection or browser-execution controls will be specified if selected for implementation.

## 9. Main data/entities

| Entity | Main data | Persistence |
| --- | --- | --- |
| Interview session | Session ID, problem text, code text, creation time, last update time, content revision | Persisted |
| Session access grant | Session reference, role, secret link credential | Persisted securely |
| Participant connection | Session reference, role, connection status, last activity | Temporary |

The session is the central record. Separate user, question, and code-file entities are unnecessary for this version. Language or execution-related data will be defined only if needed by the chosen implementation.

## 10. High-level frontend/backend interactions

1. **Create:** The frontend requests a new session. The backend creates the session and role-specific access links.
2. **Join:** The frontend submits its link credential. The backend validates access and returns the role and current session content.
3. **Connect:** The frontend establishes a real-time connection. The backend updates participant presence.
4. **Edit:** The authorized frontend sends a problem or code update.
5. **Save and broadcast:** The backend validates the role, persists the update, confirms it to the sender, and broadcasts it to the other participant.
6. **Reconnect:** The frontend reconnects and retrieves the latest server state before resuming edits.

The backend is the authoritative source of saved content. The exact framework, database, and real-time transport remain implementation decisions. If browser-side execution is included, its output and any synchronization requirements must be specified before implementation; shared execution output is not assumed by this baseline.

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
- Implementation decisions about languages and browser-side execution will be refined against the Module 2 homework requirements while keeping the MVP small.

## 12. Scope decisions and remaining questions

| Topic | Decision or current assumption | Scope implication |
| --- | --- | --- |
| Editing responsibilities | Confirmed: interviewer edits the problem; candidate edits the code. | No simultaneous code editing or conflict-resolution system is required. |
| Programming languages | Pending implementation decision based on homework requirements. | No JavaScript-only restriction; select a small, sufficient scope. |
| Browser-side execution | Pending implementation decision based on homework requirements. | Define supported runtime, trigger, result/error display, and acceptance criteria if included. |
| Participant identity | Private role-specific links without accounts. | Links establish access rather than verified identity. |
| Synchronized state | Problem text, code text, and presence. | Shared cursors, selections, and scroll positions are unnecessary for the MVP. |
| Offline behavior | Editing pauses; reconnect reloads saved state. | Offline recovery and merging are outside the MVP. |
| Current session view | Problem, code, and connection status. | Timers, scoring, and interview stages are unnecessary for the core workflow. |

The baseline requirements and acceptance criteria guide implementation and verification. Update this specification with any homework-driven refinements before implementing the affected features.
