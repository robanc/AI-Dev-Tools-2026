from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class InterviewSession(Base):
    __tablename__ = "interview_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    problem: Mapped[str] = mapped_column(Text)
    code: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revision: Mapped[int] = mapped_column(BigInteger)


class AccessGrant(Base):
    __tablename__ = "access_grants"
    __table_args__ = (CheckConstraint("role IN ('interviewer', 'candidate')"),)

    session_id: Mapped[str] = mapped_column(ForeignKey("interview_sessions.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(11), primary_key=True)
    token: Mapped[str] = mapped_column(String(43), unique=True)
