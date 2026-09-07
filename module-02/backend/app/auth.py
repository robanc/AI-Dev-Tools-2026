import re

from fastapi import Request

from .errors import APIError, INVALID_LINK
from .schemas import Role
from .store import Session


async def access(request: Request, sessionId: str) -> tuple[Session, Role]:
    header = request.headers.get("authorization", "")
    match = re.fullmatch(r"Bearer ([A-Za-z0-9._~+/-]+=*)", header, re.IGNORECASE)
    if not match:
        raise APIError(401, "unauthorized", INVALID_LINK)
    return request.app.state.store.authorize(sessionId, match[1])


async def require_json(request: Request):
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        raise APIError(415, "unsupported_media_type", "Use application/json.")
