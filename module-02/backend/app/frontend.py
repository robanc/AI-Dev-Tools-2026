from pathlib import Path, PurePosixPath

from fastapi import FastAPI
from starlette.exceptions import HTTPException
from starlette.responses import FileResponse
from starlette.staticfiles import StaticFiles


def serve_frontend(app: FastAPI, directory: str) -> None:
    """Serve the build only after normal API/WebSocket/method routing is exhausted."""
    root = Path(directory).resolve()
    if not (root / "index.html").is_file():
        raise RuntimeError("FRONTEND_DIST must contain a built frontend index.html")
    files = StaticFiles(directory=root, html=True)
    original_default = app.router.default
    reserved = {"sessions", "docs", "redoc", "openapi.json"}

    async def frontend(scope, receive, send):
        path = scope.get("path", "").lstrip("/")
        parts = PurePosixPath(path).parts
        if (scope["type"] != "http" or scope["method"] not in {"GET", "HEAD"}
                or (parts and parts[0] in reserved) or ".." in parts):
            await original_default(scope, receive, send)
            return
        try:
            await files(scope, receive, send)
        except HTTPException as exc:
            accept = dict(scope["headers"]).get(b"accept", b"").decode("latin-1")
            # Missing assets must be 404, never index.html with a JS/WASM URL.
            if (exc.status_code != 404 or "text/html" not in accept
                    or PurePosixPath(path).suffix or (parts and parts[0] in {"assets", "pyodide"})):
                raise
            await FileResponse(root / "index.html")(scope, receive, send)

    # Unlike mounting '/' or a catch-all route, the default runs after 405 and
    # slash-redirect handling and cannot swallow an existing API or WebSocket.
    app.router.default = frontend
