"""Unit tests for the ODBArchitectAgent orchestrator and tool-call tracing."""

from __future__ import annotations

from typing import Any

import pytest

from ai_agent.llm_client import LLMConnectionConfig
from ai_agent.orchestrator import ODBArchitectAgent


class _DummyResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _DummyChat:
    def __init__(self, tools: list[Any]) -> None:
        self.tools = {fn.__name__: fn for fn in tools}
        self.turn_count = 0

    def send_message(self, user_message: str) -> _DummyResponse:
        self.turn_count += 1
        # Simulate Gemini invoking a live tool during the turn
        if "cidr" in user_message.lower():
            self.tools["validate_odb_network_cidrs"](
                vpc_cidr="10.10.0.0/16",
                client_subnet_cidr="10.20.1.0/24",
            )
            return _DummyResponse("Validated CIDRs and prepared ODB@GCP architecture.")

        if "hallucinate" in user_message.lower() and self.turn_count == 1:
            return _DummyResponse(
                'Here is your code:\n```hcl\nresource "oci_database_autonomous_database" "bad" {}\n```'
            )
        if "[GUARDRAIL AUTO-REPAIR]" in user_message:
            return _DummyResponse(
                'Fixed code:\n```hcl\nresource "google_oracle_database_autonomous_database" "good" {\n'
                '  autonomous_database_id = "adb1"\n  location = "us-east4"\n  odb_network = "net"\n'
                '  odb_subnet = "sub"\n  cidr = "10.20.1.0/24"\n  properties {\n    compute_count = 2\n'
                '    data_storage_size_tb = 1\n    db_workload = "OLTP"\n  }\n}\n```'
            )
        return _DummyResponse("OK")


class _DummyChatsNamespace:
    def create(self, model: str, config: Any) -> _DummyChat:
        return _DummyChat(config.tools)


class _DummyGenAIClient:
    def __init__(self) -> None:
        self.chats = _DummyChatsNamespace()


def test_orchestrator_records_live_tool_call_traces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "ai_agent.orchestrator.create_genai_client",
        lambda cfg: _DummyGenAIClient(),
    )
    cfg = LLMConnectionConfig(
        auth_mode="vertex",
        model="gemini-3.8-flash",
        project_id="my-odb-project-01",
        location="global",
    )
    agent = ODBArchitectAgent(cfg)
    turn = agent.send_message("Please validate CIDR 10.10.0.0/16 and 10.20.1.0/24")

    assert "Validated CIDRs" in turn.text
    assert turn.model == "gemini-3.8-flash"
    assert len(turn.tool_traces) == 1
    assert turn.tool_traces[0].tool_name == "validate_odb_network_cidrs"
    assert turn.tool_traces[0].arguments["vpc_cidr"] == "10.10.0.0/16"
    assert '"valid": true' in turn.tool_traces[0].result_preview.lower()


def test_orchestrator_triggers_auto_repair_on_hallucinated_hcl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "ai_agent.orchestrator.create_genai_client",
        lambda cfg: _DummyGenAIClient(),
    )
    cfg = LLMConnectionConfig(
        auth_mode="vertex",
        model="gemini-3.8-flash",
        project_id="my-odb-project-01",
        location="global",
    )
    agent = ODBArchitectAgent(cfg)
    turn = agent.send_message("Please hallucinate an OCI resource first")

    assert "google_oracle_database_autonomous_database" in turn.text
    assert "oci_database_autonomous_database" not in turn.text
    assert any(
        t.tool_name == "post_generation_hcl_guardrail" for t in turn.tool_traces
    )

