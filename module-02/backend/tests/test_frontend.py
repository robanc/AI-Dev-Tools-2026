import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import create_app
from conftest import authenticate, connect, headers


@pytest.fixture
def built_frontend(tmp_path, monkeypatch):
    root = tmp_path / "dist"
    root.mkdir()
    (root / "index.html").write_text("<html>Pairroom app</html>")
    (root / "assets").mkdir()
    (root / "assets" / "app.js").write_text("console.log('app')")
    (root / "pyodide").mkdir()
    (root / "pyodide" / "pyodide.asm.wasm").write_bytes(b"\x00asm")
    monkeypatch.setenv("FRONTEND_DIST", str(root))
    return root


def test_frontend_files_and_navigation(built_frontend):
    with TestClient(create_app()) as client:
        assert "Pairroom app" in client.get("/").text
        assert "Pairroom app" in client.get("/room/example", headers={"Accept": "text/html"}).text
        assert client.get("/assets/app.js").text == "console.log('app')"
        wasm = client.get("/pyodide/pyodide.asm.wasm")
        assert wasm.content == b"\x00asm"
        assert wasm.headers["content-type"] == "application/wasm"
        assert client.head("/").status_code == 200
        for path in ["/assets/missing.js", "/pyodide/missing.wasm", "/assets/missing", "/unknown.json"]:
            assert client.get(path, headers={"Accept": "text/html"}).status_code == 404
        assert client.get("/unknown", headers={"Accept": "application/json"}).status_code == 404


def test_api_and_websockets_take_priority(built_frontend):
    with TestClient(create_app()) as client:
        assert client.get("/docs").status_code == 200
        assert "/sessions" in client.get("/openapi.json").json()["paths"]
        assert client.get("/sessions", headers={"Accept": "text/html"}).status_code == 405
        assert client.get("/sessions/unknown", headers={"Accept": "text/html"}).status_code == 401
        assert client.get("/sessions/unknown/invalid", headers={"Accept": "text/html"}).status_code == 404
        created = client.post("/sessions")
        assert created.status_code == 201
        session_id, token = created.json()["interviewerLink"].split("/")[2:]
        path = "/sessions/" + session_id
        with connect(client, path) as socket:
            assert authenticate(socket, token)["type"] == "snapshot"
            saved = client.put(path + "/code", headers=headers(token), json={"code": "saved"})
            assert saved.status_code == 200
            assert socket.receive_json()["session"] == saved.json()
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/unknown"):
                pass


def test_invalid_frontend_directory_fails_clearly(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTEND_DIST", str(tmp_path))
    with pytest.raises(RuntimeError, match="FRONTEND_DIST"):
        create_app()
