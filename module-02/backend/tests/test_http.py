from concurrent.futures import ThreadPoolExecutor

import pytest

from conftest import headers


def test_creation_and_access(client, room):
    response = client.post("/sessions")
    assert response.status_code == 201
    assert response.headers["cache-control"] == "no-store"
    assert set(response.json()) == {"interviewerLink"}
    path, tokens = room
    assert tokens["candidate"] != tokens["interviewer"]
    for role, token in tokens.items():
        response = client.get(path, headers=headers(token))
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        access = response.json()
        assert access["role"] == role
        assert (access["candidateLink"] is None) == (role == "candidate")
        state = access["session"]
        assert state["problem"] == state["code"] == ""
        assert state["revision"] == 0
        assert state["createdAt"] == state["updatedAt"]
        assert tokens["interviewer"] not in response.text


def test_invalid_access(client, room):
    path, tokens = room
    wrong = client.get(path, headers=headers("wrong"))
    missing = client.get("/sessions/missing", headers=headers(tokens["interviewer"]))
    assert wrong.status_code == missing.status_code == 404
    assert wrong.json() == missing.json() == {
        "code": "invalid_link", "message": "Session not found or link invalid"}
    for auth in [None, "Basic secret", "Bearer", "Bearer two tokens"]:
        result = client.get(path, headers={} if auth is None else {"Authorization": auth})
        assert result.status_code == 401
        assert result.headers["www-authenticate"] == "Bearer"
    other_link = client.post("/sessions").json()["interviewerLink"]
    other_token = other_link.split("/")[-1]
    assert client.get(path, headers=headers(other_token)).status_code == 404
    for field in ["problem", "code"]:
        assert client.put(path + "/" + field, json={field: "x"}, headers=headers("wrong")).status_code == 404


def test_permissions_and_memory_persistence(client, room):
    path, tokens = room
    owner, candidate = (headers(tokens[role]) for role in ["interviewer", "candidate"])
    rejected = client.put(path + "/problem", json={"problem": "bad"}, headers=candidate)
    assert rejected.status_code == 403
    assert rejected.json()["code"] == "forbidden"
    revision = 0
    for field, value, auth in [("problem", "Sum two numbers", owner),
                                ("code", "return a + b", owner),
                                ("code", "print(a + b)", candidate),
                                ("code", "print(a + b)", candidate)]:
        result = client.put(path + "/" + field, json={field: value}, headers=auth)
        assert result.status_code == 200
        revision += 1
        assert result.json()["revision"] == revision
    restored = client.get(path, headers=candidate).json()["session"]
    assert restored["problem"] == "Sum two numbers"
    assert restored["code"] == "print(a + b)"
    assert restored["revision"] == 4
    assert restored["updatedAt"] >= restored["createdAt"]
    for field in ["problem", "code"]:
        assert client.put(path + "/" + field, json={field: ""}, headers=owner).json()[field] == ""


@pytest.mark.parametrize("body", [{}, {"code": None}, {"code": 12}, {"code": "x", "language": "python"}])
def test_invalid_body(client, room, body):
    path, tokens = room
    result = client.put(path + "/code", json=body, headers=headers(tokens["candidate"]))
    assert result.status_code == 400
    assert result.json()["code"] == "invalid_request"
    assert client.get(path, headers=headers(tokens["candidate"])).json()["session"]["revision"] == 0


def test_json_errors(client, room):
    path, tokens = room
    auth = headers(tokens["interviewer"])
    assert client.put(path + "/problem", content="broken", headers={**auth, "Content-Type": "application/json"}).status_code == 400
    assert client.put(path + "/problem", content="text", headers={**auth, "Content-Type": "text/plain"}).status_code == 415


def test_overlapping_fields(client, room):
    path, tokens = room
    def put(field):
        return client.put(path + "/" + field, json={field: field}, headers=headers(tokens["interviewer"]))
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(put, ["problem", "code"]))
    assert sorted(result.json()["revision"] for result in results) == [1, 2]
    state = client.get(path, headers=headers(tokens["interviewer"])).json()["session"]
    assert state["problem"] == "problem" and state["code"] == "code"
