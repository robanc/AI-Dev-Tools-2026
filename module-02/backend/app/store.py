import asyncio
from dataclasses import dataclass, field

from .errors import APIError
from .repository import SessionRepository
from .schemas import Role, SessionState


@dataclass(repr=False)
class Session:
    id: str
    repository: SessionRepository
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    subscribers: dict[Role, asyncio.Queue] = field(default_factory=dict)

    def link(self, role: Role) -> str:
        return self.repository.link(self.id, role)

    @property
    def state(self) -> SessionState:
        return self.repository.read(self.id)

    def broadcast(self, event: dict) -> None:
        # Called under lock; queueing never waits on a remote socket.
        for queue in self.subscribers.values():
            queue.put_nowait(event)

    async def update(self, target: str, value: str) -> SessionState:
        async with self.lock:
            state = self.repository.update(self.id, target, value)
            self.broadcast({"type": "session.updated", "session": state.model_dump(mode="json")})
            return state

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


class PersistentStore:
    """Database content with process-local locks and ordered subscriptions."""

    def __init__(self, repository: SessionRepository):
        self.repository = repository
        self.sessions: dict[str, Session] = {}

    def create(self) -> Session:
        return self._session(self.repository.create())

    def _session(self, session_id: str) -> Session:
        if session_id not in self.sessions:
            self.sessions[session_id] = Session(session_id, self.repository)
        return self.sessions[session_id]

    def authorize(self, session_id: str, token: str) -> tuple[Session, Role]:
        role = self.repository.authorize(session_id, token)
        return self._session(session_id), role
