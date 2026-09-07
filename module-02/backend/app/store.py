import asyncio
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from .errors import APIError, INVALID_LINK
from .schemas import Role, SessionState


@dataclass(repr=False)
class Session:
    state: SessionState
    tokens: dict[Role, str]
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    subscribers: dict[Role, asyncio.Queue] = field(default_factory=dict)

    def link(self, role: Role) -> str:
        return f"#/session/{self.state.id}/{self.tokens[role]}"

    def broadcast(self, event: dict) -> None:
        # Called under lock; queueing never waits on a remote socket.
        for queue in self.subscribers.values():
            queue.put_nowait(event)

    async def update(self, target: str, value: str) -> SessionState:
        async with self.lock:
            self.state = self.state.model_copy(update={
                target: value,
                "revision": self.state.revision + 1,
                "updatedAt": datetime.now(timezone.utc),
            })
            self.broadcast({"type": "session.updated", "session": self.state.model_dump(mode="json")})
            return self.state

    async def subscribe(self, role: Role) -> asyncio.Queue:
        async with self.lock:
            if role in self.subscribers:
                raise APIError(400, "invalid_message", "This role already has an active connection.")
            queue = asyncio.Queue()
            queue.put_nowait({"type": "snapshot", "session": self.state.model_dump(mode="json"),
                              "otherConnected": bool(self.subscribers)})
            self.broadcast({"type": "presence.updated", "otherConnected": True})
            self.subscribers[role] = queue
            return queue

    async def unsubscribe(self, role: Role, queue: asyncio.Queue) -> None:
        async with self.lock:
            if self.subscribers.get(role) is queue:
                del self.subscribers[role]
                self.broadcast({"type": "presence.updated", "otherConnected": False})


class MemoryStore:
    """One application/process owns this store; no restart durability."""

    def __init__(self):
        self.sessions: dict[str, Session] = {}

    def create(self) -> Session:
        now = datetime.now(timezone.utc)
        state = SessionState(id=str(uuid4()), createdAt=now, updatedAt=now)
        session = Session(state, {role: secrets.token_urlsafe(32) for role in ("interviewer", "candidate")})
        self.sessions[state.id] = session
        return session

    def authorize(self, session_id: str, token: str) -> tuple[Session, Role]:
        session = self.sessions.get(session_id)
        if session:
            for role, secret in session.tokens.items():
                if secrets.compare_digest(secret.encode(), token.encode()):
                    return session, role
        raise APIError(404, "invalid_link", INVALID_LINK)
