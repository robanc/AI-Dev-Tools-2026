import os

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from . import realtime, routers
from .errors import APIError, error_response
from .store import MemoryStore


def create_app(*, auth_timeout: float = 5, heartbeat_timeout: float = 25) -> FastAPI:
    app = FastAPI(title="Pairroom Interview Session API", version="0.1.0")
    app.state.store = MemoryStore()
    app.state.auth_timeout = auth_timeout
    app.state.heartbeat_timeout = heartbeat_timeout
    app.state.frontend_origins = [value.strip() for value in os.getenv(
        "FRONTEND_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",") if value.strip()]
    app.add_middleware(CORSMiddleware, allow_origins=app.state.frontend_origins,
                       allow_methods=["GET", "POST", "PUT"], allow_headers=["Authorization", "Content-Type"])

    @app.middleware("http")
    async def no_cache(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(APIError)
    async def api_error(request, exc):
        return error_response(exc.status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return error_response(400, "invalid_request", "Provide the required text field as a string.")

    @app.exception_handler(Exception)
    async def internal_error(request, exc):
        return error_response(500, "internal_error", "Could not complete the request. Please try again.")

    app.include_router(routers.router)
    app.include_router(realtime.router)
    return app


app = create_app()
