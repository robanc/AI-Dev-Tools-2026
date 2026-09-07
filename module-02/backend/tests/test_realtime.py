import json
import time

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import create_app
from conftest import authenticate, connect, headers


def test_snapshots_updates_presence_reconnect(client, room):
    path, tokens = room
    with connect(client, path) as owner:
        snapshot = authenticate(owner, tokens["interviewer"])
        assert snapshot["type"] == "snapshot" and snapshot["otherConnected"] is False
        with connect(client, path) as candidate:
            snapshot = authenticate(candidate, tokens["candidate"])
            assert snapshot["otherConnected"] is True
            assert owner.receive_json() == {"type": "presence.updated", "otherConnected": True}
            for role, field in [("interviewer", "problem"), ("interviewer", "code"), ("candidate", "code")]:
                start = time.monotonic()
                result = client.put(path + "/" + field, json={field: role}, headers=headers(tokens[role]))
                for socket in [owner, candidate]:
                    event = socket.receive_json()
                    assert event == {"type": "session.updated", "session": result.json()}
                    assert all(token not in json.dumps(event) for token in tokens.values())
                assert time.monotonic() - start < 1
            candidate.send_json({"type": "ping"})
            assert candidate.receive_json() == {"type": "pong"}
        assert owner.receive_json() == {"type": "presence.updated", "otherConnected": False}
        client.put(path + "/code", json={"code": "while away"}, headers=headers(tokens["interviewer"]))
        assert owner.receive_json()["session"]["code"] == "while away"
        with connect(client, path) as candidate:
            snapshot = authenticate(candidate, tokens["candidate"])
            assert snapshot["session"]["code"] == "while away"
            assert snapshot["session"]["revision"] == 4


@pytest.mark.parametrize("unknown_session", [False, True])
def test_invalid_auth(client, room, unknown_session):
    path, tokens = room
    with connect(client, "/sessions/missing" if unknown_session else path) as socket:
        event = authenticate(socket, tokens["candidate"] if unknown_session else "wrong")
        assert event == {"type": "error", "code": "invalid_link", "message": "Session not found or link invalid"}
        with pytest.raises(WebSocketDisconnect) as closed:
            socket.receive_json()
        assert closed.value.code == 1008


@pytest.mark.parametrize("payload", ['{', '[]', '{"type":"ping"}',
    '{"type":"authenticate","token":"x","role":"interviewer"}'])
def test_invalid_first_message(client, room, payload):
    path, _ = room
    with connect(client, path) as socket:
        socket.send_text(payload)
        assert socket.receive_json()["code"] == "invalid_message"
        with pytest.raises(WebSocketDisconnect) as closed:
            socket.receive_json()
        assert closed.value.code == 1008


@pytest.mark.parametrize("payload", [{"type": "authenticate", "token": "x"},
    {"type": "updateCode", "code": "bad"}, {"type": "ping", "extra": True}])
def test_invalid_authenticated_message(client, room, payload):
    path, tokens = room
    with connect(client, path) as socket:
        authenticate(socket, tokens["candidate"])
        socket.send_json(payload)
        assert socket.receive_json()["code"] == "invalid_message"
        with pytest.raises(WebSocketDisconnect) as closed:
            socket.receive_json()
        assert closed.value.code == 1008
    assert client.get(path, headers=headers(tokens["candidate"])).json()["session"]["revision"] == 0


def test_origin_rejected(client, room):
    path, _ = room
    for origin in [None, "https://untrusted.example"]:
        with pytest.raises(WebSocketDisconnect) as closed:
            with client.websocket_connect(path + "/ws", headers={} if origin is None else {"Origin": origin}):
                pass
        assert closed.value.code == 1008


def test_timeouts():
    with TestClient(create_app(auth_timeout=0.05, heartbeat_timeout=0.05)) as client:
        link = client.post("/sessions").json()["interviewerLink"]
        session_id, token = link.split("/")[2:]
        path = "/sessions/" + session_id
        with connect(client, path) as socket:
            assert socket.receive_json()["code"] == "invalid_link"
            with pytest.raises(WebSocketDisconnect):
                socket.receive_json()
        with connect(client, path) as socket:
            assert authenticate(socket, token)["type"] == "snapshot"
            assert socket.receive_json()["message"] == "Heartbeat timed out."
            with pytest.raises(WebSocketDisconnect):
                socket.receive_json()


def test_update_between_get_and_subscribe(client, room):
    path, tokens = room
    assert client.get(path, headers=headers(tokens["candidate"])).json()["session"]["revision"] == 0
    client.put(path + "/code", json={"code": "new"}, headers=headers(tokens["interviewer"]))
    with connect(client, path) as socket:
        assert authenticate(socket, tokens["candidate"])["session"]["revision"] == 1


def test_duplicate_role_preserves_original_presence(client, room):
    path, tokens = room
    with connect(client, path) as owner:
        authenticate(owner, tokens["interviewer"])
        with connect(client, path) as duplicate:
            assert authenticate(duplicate, tokens["interviewer"])["code"] == "invalid_message"
        with connect(client, path) as candidate:
            assert authenticate(candidate, tokens["candidate"])["otherConnected"] is True


def test_queued_updates_keep_commit_order(client, room):
    path, tokens = room
    with connect(client, path) as socket:
        assert authenticate(socket, tokens["candidate"])["session"]["revision"] == 0
        for number in range(1, 6):
            client.put(path + "/code", json={"code": str(number)}, headers=headers(tokens["interviewer"]))
        for number in range(1, 6):
            event = socket.receive_json()
            assert event["session"]["revision"] == number
            assert event["session"]["code"] == str(number)
