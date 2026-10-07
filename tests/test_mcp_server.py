"""Unit tests for the Model Context Protocol (MCP) stdio server (`ai_agent.mcp_server`)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_agent.mcp_server import MCP_TOOL_DEFINITIONS, handle_jsonrpc_message


def test_mcp_server_never_exposes_apply_or_destroy() -> None:
    tool_names = {tool["name"] for tool in MCP_TOOL_DEFINITIONS}
    for name in tool_names:
        assert "apply" not in name.lower()
        assert "destroy" not in name.lower()

    # Attempting to invoke a non-existent or destructive tool returns an explicit safety error
    for forbidden_tool in ("terraform_apply", "terraform_destroy", "apply", "destroy"):
        resp = handle_jsonrpc_message(
            {
                "jsonrpc": "2.0",
                "id": 99,
                "method": "tools/call",
                "params": {"name": forbidden_tool, "arguments": {}},
            }
        )
        assert resp is not None
        assert resp["result"]["isError"] is True
        text = resp["result"]["content"][0]["text"]
        assert "never exposed" in text.lower()


def test_mcp_server_initialize_and_tools_list() -> None:
    init_resp = handle_jsonrpc_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05"},
        }
    )
    assert init_resp is not None
    assert init_resp["result"]["serverInfo"]["name"] == "oracle-google-onboarding-agent"

    list_resp = handle_jsonrpc_message(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    )
    assert list_resp is not None
    tools = list_resp["result"]["tools"]
    assert len(tools) == len(MCP_TOOL_DEFINITIONS)
    assert len(tools) >= 8


def test_mcp_generate_golden_returns_concise_summary_and_enforces_workspace_containment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ODB_WORKSPACE_ROOT", str(tmp_path))

    call_resp = handle_jsonrpc_message(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "generate_golden_terraform",
                "arguments": {
                    "project_id": "my-odb-project-01",
                    "workload_type": "adb",
                    "output_dir": "./output",
                    "bundle_name": "mcp-adb-bundle",
                },
            },
        }
    )
    assert call_resp is not None
    assert call_resp["result"]["isError"] is False
    payload = json.loads(call_resp["result"]["content"][0]["text"])
    assert payload["valid"] is True
    assert payload["validation_Summary"]["fast_mode"] is True
    assert "workload.tf" in payload["written_files"]
    assert "networking.tf" in payload["written_files"]
    # Ensure full multi-kilobyte HCL files are NOT dumped in the MCP payload (timeout prevention)
    assert "files" not in payload
    assert (tmp_path / "output" / "mcp-adb-bundle" / "workload.tf").is_file()

    # Path escape attempt via MCP must fail safely
    escape_resp = handle_jsonrpc_message(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "generate_golden_terraform",
                "arguments": {
                    "project_id": "my-odb-project-01",
                    "workload_type": "adb",
                    "output_dir": "../../etc",
                    "bundle_name": "escape-bundle",
                },
            },
        }
    )
    assert escape_resp is not None
    escape_payload = json.loads(escape_resp["result"]["content"][0]["text"])
    assert escape_payload["saved"] is False
    assert "Path traversal blocked" in escape_payload["error"]
