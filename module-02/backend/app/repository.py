import secrets
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select, update

from .database import Database
from .errors import APIError, INVALID_LINK
from .models import AccessGrant, InterviewSession
from .schemas import Role, SessionState


def snapshot(row: InterviewSession) -> SessionState:
    # SQLite returns naive datetimes; all stored timestamps are UTC.
    def utc(value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

    return SessionState(id=row.id, problem=row.problem, code=row.code,
                        createdAt=utc(row.created_at), updatedAt=utc(row.updated_at), revision=row.revision)


class SessionRepository:
    def __init__(self, database: Database):
        self.database = database

    def create(self) -> str:
        session_id, now = str(uuid4()), datetime.now(timezone.utc)
        with self.database.sessions.begin() as db:
            db.add(InterviewSession(id=session_id, problem="", code="", revision=0,
                                    created_at=now, updated_at=now))
            db.flush()
            db.add_all([AccessGrant(session_id=session_id, role=role, token=secrets.token_urlsafe(32))
                        for role in ("interviewer", "candidate")])
        return session_id

    def authorize(self, session_id: str, token: str) -> Role:
        with self.database.sessions() as db:
            grants = db.scalars(select(AccessGrant).where(AccessGrant.session_id == session_id))
            for grant in grants:
                if secrets.compare_digest(grant.token.encode(), token.encode()):
                    return grant.role
        raise APIError(404, "invalid_link", INVALID_LINK)

    def link(self, session_id: str, role: Role) -> str:
        with self.database.sessions() as db:
            grant = db.get(AccessGrant, (session_id, role))
            return f"#/session/{session_id}/{grant.token}"

    def read(self, session_id: str) -> SessionState:
        with self.database.sessions() as db:
            return snapshot(db.get(InterviewSession, session_id))

    def update(self, session_id: str, target: str, value: str) -> SessionState:
        if target not in ("problem", "code"):
            raise ValueError("Unknown content field")
        with self.database.sessions.begin() as db:
            db.execute(update(InterviewSession).where(InterviewSession.id == session_id).values({
                target: value, "revision": InterviewSession.revision + 1,
                "updated_at": datetime.now(timezone.utc),
            }))
            state = snapshot(db.get(InterviewSession, session_id))
        # Return only after commit; failures roll back and never reach broadcasts.
        return state
