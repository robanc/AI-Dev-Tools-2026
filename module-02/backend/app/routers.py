from typing import Annotated

from fastapi import APIRouter, Depends, Request

from .auth import access, require_json
from .errors import APIError
from .schemas import CodeUpdate, CreatedSession, ProblemUpdate, Role, SessionAccess, SessionState
from .store import Session

router = APIRouter()
Access = Annotated[tuple[Session, Role], Depends(access)]


@router.post("/sessions", status_code=201, response_model=CreatedSession, operation_id="createSession")
async def create_session(request: Request):
    return CreatedSession(interviewerLink=request.app.state.store.create().link("interviewer"))


@router.get("/sessions/{sessionId}", response_model=SessionAccess, operation_id="getSession")
async def get_session(grant: Access):
    session, role = grant
    async with session.lock:
        return SessionAccess(role=role, candidateLink=session.link("candidate") if role == "interviewer" else None,
                             session=session.state)


@router.put("/sessions/{sessionId}/problem", response_model=SessionState,
            dependencies=[Depends(require_json)], operation_id="updateProblem")
async def update_problem(body: ProblemUpdate, grant: Access):
    session, role = grant
    if role != "interviewer":
        raise APIError(403, "forbidden", "This role cannot edit that field.")
    return await session.update("problem", body.problem)


@router.put("/sessions/{sessionId}/code", response_model=SessionState,
            dependencies=[Depends(require_json)], operation_id="updateCode")
async def update_code(body: CodeUpdate, grant: Access):
    session, _ = grant
    return await session.update("code", body.code)
