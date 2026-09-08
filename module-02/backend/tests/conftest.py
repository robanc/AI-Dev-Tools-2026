import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def database_url(tmp_path, monkeypatch):
    url = "sqlite:///" + (tmp_path / "test.db").as_posix()
    monkeypatch.setenv("DATABASE_URL", url)
    return url


@pytest.fixture(autouse=True)
def isolated_database(database_url):
    pass


@pytest.fixture
def client():
    with TestClient(create_app()) as client:
        yield client


@pytest.fixture
def room(client):
    created = client.post("/sessions")
    session_id, interviewer = created.json()["interviewerLink"].split("/")[2:]
    path = f"/sessions/{session_id}"
    owner = {"Authorization": f"Bearer {interviewer}"}
    candidate = client.get(path, headers=owner).json()["candidateLink"].split("/")[-1]
    return path, {"interviewer": interviewer, "candidate": candidate}


def headers(token):
    return {"Authorization": f"Bearer {token}"}


def connect(client, path):
    return client.websocket_connect(path + "/ws", headers={"Origin": "http://localhost:5173"})


def authenticate(socket, token):
    socket.send_json({"type": "authenticate", "token": token})
    return socket.receive_json()
