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

    def send_message(self, user_message: str) -> _DummyResponse:
        # Simulate Gemini invoking a live tool during the turn
        if "cidr" in user_message.lower():
            self.tools["validate_odb_network_cidrs"](
                vpc_cidr="10.10.0.0/16",
                client_subnet_cidr="10.20.1.0/24",
            )
        return _DummyResponse("Validated CIDRs and prepared ODB@GCP architecture.")


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
        location="us-central1",
    )
    agent = ODBArchitectAgent(cfg)
    turn = agent.send_message("Please validate CIDR 10.10.0.0/16 and 10.20.1.0/24")

    assert "Validated CIDRs" in turn.text
    assert turn.model == "gemini-3.8-flash"
    assert len(turn.tool_traces) == 1
    assert turn.tool_traces[0].tool_name == "validate_odb_network_cidrs"
    assert turn.tool_traces[0].arguments["vpc_cidr"] == "10.10.0.0/16"
    assert '"valid": true' in turn.tool_traces[0].result_preview.lower()
