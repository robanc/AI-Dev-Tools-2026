from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictStr

Role = Literal["interviewer", "candidate"]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SessionState(Model):
    id: str
    problem: str = ""
    code: str = ""
    createdAt: datetime
    updatedAt: datetime
    revision: int = 0


class CreatedSession(Model):
    interviewerLink: str


class SessionAccess(Model):
    role: Role
    candidateLink: str | None
    session: SessionState


class ProblemUpdate(Model):
    problem: StrictStr


class CodeUpdate(Model):
    code: StrictStr
