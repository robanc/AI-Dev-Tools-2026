from pathlib import Path

import yaml
from openapi_schema_validator import OAS30Validator

from conftest import headers


def test_responses_match_root_contract(client, room):
    contract = yaml.safe_load((Path(__file__).resolve().parents[2] / "openapi.yaml").read_text())

    def expand(value):
        if isinstance(value, dict):
            if "$ref" in value:
                target = contract
                for part in value["$ref"].split("/")[1:]:
                    target = target[part]
                return expand(target)
            return {key: expand(item) for key, item in value.items()}
        if isinstance(value, list):
            return [expand(item) for item in value]
        return value

    path, tokens = room
    cases = [("/sessions", "post", client.post("/sessions"))]
    for role, token in tokens.items():
        cases.append(("/sessions/{sessionId}", "get", client.get(path, headers=headers(token))))
        for field in ["problem", "code"]:
            cases.append(("/sessions/{sessionId}/" + field, "put", client.put(
                path + "/" + field, json={field: role}, headers=headers(token))))
    cases.extend([
        ("/sessions/{sessionId}", "get", client.get(path)),
        ("/sessions/{sessionId}", "get", client.get(path, headers=headers("wrong"))),
        ("/sessions/{sessionId}/code", "put", client.put(path + "/code", json={}, headers=headers(tokens["candidate"]))),
        ("/sessions/{sessionId}/code", "put", client.put(path + "/code", content="x", headers=headers(tokens["candidate"]))),
    ])
    for route, method, response in cases:
        definition = expand(contract["paths"][route][method]["responses"][str(response.status_code)])
        OAS30Validator(definition["content"]["application/json"]["schema"]).validate(response.json())
