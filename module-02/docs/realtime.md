# Planned real-time protocol

This is a contract for the future backend, not an implemented or verified protocol.
It complements [openapi.yaml](../openapi.yaml) and implements FR-11 through FR-20
and the synchronization/reconnection acceptance criteria in [spec.md](spec.md).
All HTTP and WebSocket traffic stays inside the frontend service layer.

## Service mapping

| Existing service operation | Planned transport |
| --- | --- |
| `createSession()` | `POST /sessions`, returning `{ interviewerLink }` |
| `joinSession(id, token, onChange)` | `GET /sessions/{sessionId}` to validate access and read state, then authenticated WebSocket |
| `updateProblem(value)` | `PUT /sessions/{sessionId}/problem` with `{ problem: value }` |
| `updateCode(value)` | `PUT /sessions/{sessionId}/code` with `{ code: value }` |
| `disconnect()` | Pause editing, stop reconnect attempts, close WebSocket |
| `reconnect()` | Revalidate through GET, reopen/authenticate WebSocket, await fresh snapshot |
| `close()` | Close WebSocket, cancel timers/listeners and requests where possible, suppress later callbacks |

No HTTP join mutation, presence polling, heartbeat, leave, or reconnect endpoint
is necessary. GET does not mark a role connected. Copying the candidate link is
local UI behavior. Language selection remains local and is never transmitted.
Writes use HTTP only; WebSockets deliver snapshots and presence, avoiding two
competing write protocols.

## Connection and authentication

Connect to `/sessions/{sessionId}/ws` on the configured backend origin using
`wss` outside local development (`ws` locally). The browser WebSocket API cannot
set an arbitrary Authorization header, so the first client JSON message is:

```json
{ "type": "authenticate", "token": "role-specific-link-token" }
```

Use the same opaque token as HTTP. Do not put it in the WebSocket URL, log it,
or broadcast it. The server validates the session and token before sending any
session data or counting presence. Require authentication within five seconds;
on timeout or invalid credentials, send the error below and close with code
`1008`. An unknown session and an incorrect token produce the same error.

```json
{ "type": "error", "code": "invalid_link", "message": "Session not found or link invalid" }
```

No client-selected role is accepted. Validate browser Origin against the configured
frontend origin. Each role has one active tab as assumed by the spec; duplicate-tab
editing and extra participant roles are unsupported.

## Messages

Messages are UTF-8 JSON objects. Server messages are sent in order on each socket.
Neither snapshots nor presence events contain access credentials.

| Direction | Type | Required fields and behavior |
| --- | --- | --- |
| Client to server | `authenticate` | `token`: nonempty string; first message only |
| Server to client | `snapshot` | `session`: OpenAPI `SessionState`; `otherConnected`: boolean; first authenticated event |
| Server to client | `session.updated` | `session`: OpenAPI `SessionState`; sent to both roles after each committed HTTP PUT |
| Server to client | `presence.updated` | `otherConnected`: boolean relative to the receiving role; sent when the other role connects or disconnects |
| Client to server | `ping` | No additional fields; sent every 10 seconds after authentication |
| Server to client | `pong` | No additional fields; reply immediately to each `ping` |
| Server to client | `error` | `code`: `invalid_link`, `invalid_message`, or `internal_error`; `message`: safe human-readable string |

Malformed JSON, unknown types/fields, repeated authentication, and attempted
WebSocket writes produce `invalid_message` and close `1008` without changing
content. Unexpected server failures use `internal_error` and close `1011`.
Normal client close uses `1000`. Error messages never count as save confirmation.

Example initial event (timestamps and text are illustrative):

```json
{
  "type": "snapshot",
  "session": {
    "id": "example-session",
    "problem": "",
    "code": "",
    "createdAt": "2026-09-07T12:00:00Z",
    "updatedAt": "2026-09-07T12:00:00Z",
    "revision": 0
  },
  "otherConnected": false
}
```

An update has the form `{ "type": "session.updated", "session": ... }`, using
the complete committed `SessionState`, not a text patch. Presence events never
increment the content revision. The server must subscribe the connection and
capture its initial snapshot without a gap: send that snapshot first, then any
commits after its revision in increasing order. This closes the race between
the initial HTTP GET and WebSocket connection.

## Save confirmation and ordering

Persist each HTTP field replacement and revision increment atomically before
returning `200` or broadcasting it. Preserve the other field, including when
problem and code requests overlap (AC-13). Concurrent writes to the same field
are resolved by commit order; there is no merge, revision precondition, or history.
Broadcast each commit to both authenticated roles, including the writer.

The adapter tracks the latest server revision and ignores older/equal content
snapshots. HTTP responses and WebSocket events can arrive in either order.
A successful response still acknowledges its own request even if its snapshot
is older than one already received. A broadcast alone must not clear a pending
request: another participant could have committed it.

Keep pending text independently for problem and code. At most one PUT per field
is in flight from a client; coalesce subsequent edits to that field and send them
after the preceding request succeeds. Overlay newer pending text on saved
snapshots so an acknowledgement or remote update cannot erase unsent input.
Use a bounded debounce/flush interval (for example, 150 ms) so continuous typing
does not defer writes indefinitely. `saveState` is `saving` while any local field
is awaiting confirmation, `saved` only when all local writes are confirmed, and
`unsaved` when a write fails or its outcome is uncertain. A successful HTTP write
is durable confirmation; browser storage is no longer the authority.

## Presence, failure, and reconnect

After authentication, count the socket as present and notify the other role.
Remove presence on close or detected connection loss. If no `pong` arrives within
five seconds of a ping, the client closes the connection and pauses editing.
The server closes a socket after 25 seconds without a client ping. These deadlines
bound silent connection-loss detection; the one-second content target does not
mean silent failures must be detected within one second.

On close, heartbeat timeout, browser offline event, or transport failure, the
adapter emits `connected: false` and `otherConnected: false`, disables editing,
and stops sending writes. Both roles may edit code only while the adapter is
connected; the backend independently validates token and field permissions on
every HTTP request. HTTP authorization does not depend on a socket being open,
so a write already in flight may commit after the socket disconnects.

If any pending write cannot be confirmed, emit `saveState: 'unsaved'` with
`Your pending edit may not have been saved. Reconnecting restores the last saved version.`
Do not automatically replay those writes: they might have committed or could
overwrite newer remote text. Aborting a request does not undo a server commit.
Discard pending overlays and ignore callbacks from the old connection generation.

For an unexpected loss, retry while online with delays of 1, 2, 4, then at most
5 seconds. Manual disconnect and close cancel retries. On each attempt, GET the
latest state and role using the original token, authenticate a new socket, and
apply its fresh snapshot before setting `connected: true` and enabling edits.
Keep the uncertainty warning visible until a new intentional edit begins; a
reload cannot prove which unacknowledged edit was saved. A 401/404 or WebSocket
`invalid_link` stops retries and surfaces the invalid-link view. Permission and
validation errors are not retried automatically.

## Frontend integration differences

The current mock uses localStorage, 200 ms polling, local presence timestamps,
and `navigator.onLine`. The real adapter must detect actual backend reachability
and use durable server state. Flatten `SessionAccess.session` into the existing
callback's `problem` and `code`, retain `role` and `candidateLink` from GET, and
derive `connected`, `otherConnected`, `saveState`, and `warning` as above.
Only interviewers receive `candidateLink`; candidates receive null. The
interviewer credential is never returned to the candidate or in broadcasts.

The mock synchronously validates `joinSession` and emits its first callback.
`Session.jsx` currently catches only synchronous errors and has no asynchronous
join-error callback. Integration must add an asynchronous error path (for example,
an optional error callback while still returning the connection handle immediately),
and update its consumers/tests then. Local method permission checks may remain
synchronous, but HTTP failures must reach the adapter's callback/error path.
The storage-specific creation error, saved label, and prototype connection text
also need updating when the backend adapter is introduced. No frontend change
is required to define this contract.

## Future backend verification

Verify with two browser windows on the same running backend: creation and valid
role links; identical invalid-link errors; candidate problem-write rejection;
problem and bidirectional code propagation within one second under normal network
conditions; overlapping problem/code persistence; presence loss after detection;
refresh and backend restart durability; and reconnect loading the latest snapshot
before editing. Exercise out-of-order HTTP/event delivery, disconnect during a
pending write, and an update between GET and WebSocket authentication. Existing
mock tests do not establish these backend guarantees.
