import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import agent_adapter


INCIDENT = ROOT / "incidents/INC-2026-001.json"


class FakeAgent:
    def __init__(self, output=None, error=None):
        self.output = output
        self.error = error
        self.prompt = None
        self.schema_path = None

    def complete(self, prompt, schema_path):
        self.prompt, self.schema_path = prompt, schema_path
        if self.error:
            raise self.error
        return self.output


def _valid_output():
    return json.loads(INCIDENT.read_text(encoding="utf-8"))


def _evidence():
    return json.loads(INCIDENT.read_text(encoding="utf-8"))


def test_valid_structured_output_is_accepted_with_task_and_evidence():
    agent = FakeAgent(json.dumps(_valid_output()))
    result = agent_adapter.run_responder(_evidence(), agent)
    assert result["incident_id"] == "INC-2026-001"
    assert result["evidence"]["metrics"][0]["http_response_status_code"] == "500"
    assert "PairRoom read-only incident responder" in agent.prompt
    assert "Sanitized evidence packet" in agent.prompt
    assert agent.schema_path == agent_adapter.SCHEMA_FILE
    assert result["policy_decision"]["decision"] == "allow"


@pytest.mark.parametrize("output", ["not json", "", "{} trailing"])
def test_malformed_or_non_json_agent_output_fails_safely(output):
    with pytest.raises(agent_adapter.AdapterError, match="no action was taken"):
        agent_adapter.run_responder(_evidence(), FakeAgent(output))


def test_schema_invalid_agent_output_is_rejected():
    output = _valid_output()
    del output["evidence"]
    with pytest.raises(agent_adapter.AdapterError, match="response schema"):
        agent_adapter.run_responder(_evidence(), FakeAgent(json.dumps(output)))


def test_prohibited_action_cannot_bypass_schema_or_policy():
    output = _valid_output()
    output["proposed_action"]["type"] = "deploy"
    with pytest.raises(agent_adapter.AdapterError, match="response schema"):
        agent_adapter.run_responder(_evidence(), FakeAgent(json.dumps(output)))


def test_rollback_is_always_human_gated_and_agent_cannot_self_authorize():
    output = _valid_output()
    output["proposed_action"]["type"] = "rollback"
    output["policy_decision"] = {"decision": "operator_authorized", "reason": "agent claim"}
    output["escalation"] = {"required": False, "status": "none", "reason": "agent claim"}
    result = agent_adapter.run_responder(_evidence(), FakeAgent(json.dumps(output)))
    assert result["policy_decision"]["decision"] == "require_operator"
    assert result["escalation"]["required"] is True
    assert result["escalation"]["status"] == "pending"
    assert result["recovery_verification"]["status"] == "not_attempted"


def test_codex_wrapper_has_no_shell_web_or_mutation_tool_and_no_rollback_executor(monkeypatch):
    sensitive_env = {
        "AWS_ACCESS_KEY_ID": "must-not-pass",
        "AWS_SECRET_ACCESS_KEY": "must-not-pass",
        "GITHUB_TOKEN": "must-not-pass",
        "GH_TOKEN": "must-not-pass",
        "OPENAI_API_KEY": "must-not-pass",
        "ANTHROPIC_API_KEY": "must-not-pass",
        "CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE": "must-not-pass",
        "PAIRROOM_DEPLOY_TOKEN": "must-not-pass",
        "APPLICATION_PASSWORD": "must-not-pass",
    }
    original_profiles = {
        "HOME": "private-home",
        "USERPROFILE": "private-profile",
        "APPDATA": "private-appdata",
        "LOCALAPPDATA": "private-local-appdata",
        "CODEX_HOME": "private-codex-home",
    }
    for name, value in {**sensitive_env, **original_profiles}.items():
        monkeypatch.setenv(name, value)
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        result_path = Path(command[command.index("--output-last-message") + 1])
        result_path.write_text("{}", encoding="utf-8")
        return type("Completed", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    output = agent_adapter.CodexHeadlessAdapter(runner=fake_run).complete("safe prompt", agent_adapter.SCHEMA_FILE)
    assert output == "{}"
    command = captured["command"]
    assert "exec" in command
    assert "--no-daemon" in command
    assert "--sandbox" in command and command[command.index("--sandbox") + 1] == "read-only"
    assert "--ask-for-approval" in command and command[command.index("--ask-for-approval") + 1] == "never"
    assert command.count("--disable") == 2
    assert "shell_tool" in command and "web_search" in command
    assert "--search" not in command
    assert command[command.index("-c") + 1] == "mcp_servers={}"
    assert "--output-schema" in command
    assert "--ephemeral" in command and "--ignore-user-config" in command
    assert "aws" not in " ".join(command).lower()
    assert "docker" not in " ".join(command).lower()
    assert "github" not in " ".join(command).lower()
    assert "rollback.sh" not in " ".join(command).lower()
    assert captured["input"] == "safe prompt"
    assert captured["cwd"] != str(ROOT)
    env = captured["env"]
    assert not (set(sensitive_env) & set(env))
    for name, private_value in original_profiles.items():
        assert env[name] != private_value
        assert str(Path(env[name])).startswith(captured["cwd"])
    assert set(env) <= {
        "PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR", "PATHEXT",
        "COMSPEC", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "CODEX_HOME",
    }


def test_codex_wrapper_uses_isolated_empty_profile_and_blocks_external_integrations(monkeypatch):
    monkeypatch.setenv("MCP_SERVER_URL", "must-not-pass")
    monkeypatch.setenv("CODEX_HOME", "user-profile-with-mcp-config-and-auth")
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        result_path = Path(command[command.index("--output-last-message") + 1])
        result_path.write_text("{}", encoding="utf-8")
        return type("Completed", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    agent_adapter.CodexHeadlessAdapter(runner=fake_run).complete("safe", agent_adapter.SCHEMA_FILE)
    command = captured["command"]
    env = captured["env"]
    assert "--ignore-user-config" in command
    assert "--no-daemon" in command
    assert "--search" not in command
    assert command[command.index("-c") + 1] == "mcp_servers={}"
    assert "MCP_SERVER_URL" not in env
    assert env["CODEX_HOME"] != "user-profile-with-mcp-config-and-auth"
    assert Path(env["CODEX_HOME"]).is_relative_to(Path(captured["cwd"]))


def test_codex_nonzero_exit_is_generic_safe_failure():
    def failed_run(_command, **_kwargs):
        return type("Completed", (), {"returncode": 1, "stdout": "sensitive", "stderr": "secret"})()

    with pytest.raises(agent_adapter.AdapterError) as error:
        agent_adapter.CodexHeadlessAdapter(runner=failed_run).complete("safe", agent_adapter.SCHEMA_FILE)
    assert "sensitive" not in str(error.value)
    assert "secret" not in str(error.value)


@pytest.mark.parametrize("failure", [RuntimeError("fake failure"), OSError("missing CLI")])
def test_agent_cli_failure_is_safe_and_cannot_trigger_action(failure):
    agent = FakeAgent(error=failure)
    with pytest.raises(agent_adapter.AdapterError, match="no action was taken"):
        agent_adapter.run_responder(_evidence(), agent)
