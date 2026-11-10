"""Tests for Part 2 Interactive Workflows (Items 4-7):
- Item 4: Guided Architecture Discovery & Sizing Wizard
- Item 5: Stateful 6-Phase Onboarding Progress Tracker
- Item 6: Interactive Day-2 What-If Scaling & ForceNew Simulator
- Item 7: Live 5-Layer Guardrail Telemetry & Scorecard
- Multi-surface verification across CLI, MCP Server, and Orchestrator.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from ai_agent.cli import app as cli_main
from ai_agent.mcp_server import MCP_TOOLS_CATALOG, execute_mcp_tool, handle_jsonrpc_message
from ai_agent.orchestrator import ODBArchitectAgent
from ai_agent.tools.interactive_workflows import (
    audit_workspace_and_hcl_guardrails,
    build_guardrail_telemetry_summary,
    manage_onboarding_progress_tracker,
    recommend_odb_architecture_wizard,
    simulate_day2_scaling_what_if,
)


# ---------------------------------------------------------------------------
# Item 4: Guided Architecture Discovery & Sizing Wizard
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "workload_profile,expected_workload_type",
    [
        ("autonomous_ai_lakehouse", "adb"),
        ("oltp_mission_critical", "exascale"),
        ("consolidated_erp_rac", "exadata_dedicated"),
        ("elastic_rac_cloud_native", "exascale"),
        ("single_instance_dev_test", "basedb"),
    ],
)
def test_architecture_wizard_recommends_expected_workload(
    workload_profile: str,
    expected_workload_type: str,
) -> None:
    raw = recommend_odb_architecture_wizard(
        workload_profile=workload_profile,
        ha_dr_tier="regional_ha",
        cpu_cores_needed=16,
        storage_tb_needed=4,
        network_governance="shared_vpc",
        encryption_compliance="gcp_cmek",
        separation_of_duties_mode="enterprise_layered",
        project_id="my-odb-wizard-proj",
        region="us-east4",
        gcp_oracle_zone="us-east4-b-r1",
        generate_artifacts=False,
    )
    data = json.loads(raw)
    assert data["valid"] is True
    summary = data["wizard_summary"]
    assert summary["recommended_workload_type"] == expected_workload_type
    assert summary["recommended_diagram_type"] == "networking_shared_vpc"
    assert len(summary["separation_of_duties_layers"]) >= 2
    assert data["cidr_validation"]["valid"] is True
    assert "interactive_spec" in data
    assert len(data["interactive_spec"]["nodes"]) >= 3


def test_architecture_wizard_generates_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ODB_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("ODB_FAST_VALIDATION", "1")
    out_dir = tmp_path / "output"

    raw = recommend_odb_architecture_wizard(
        workload_profile="autonomous_ai_lakehouse",
        ha_dr_tier="multi_zone_or_cross_region_dr",
        cpu_cores_needed=8,
        storage_tb_needed=2,
        network_governance="hub_and_spoke",
        encryption_compliance="gcp_cmek",
        separation_of_duties_mode="full_stack",
        project_id="my-odb-wizard-prod",
        region="us-east4",
        gcp_oracle_zone="us-east4-b-r1",
        generate_artifacts=True,
        base_output_dir=str(out_dir),
    )
    data = json.loads(raw)
    assert data["valid"] is True
    assert data["generated_bundle"] is not None
    assert data["generated_bundle"]["saved"] is True
    bundle_dir = Path(data["generated_bundle"]["output_directory"])
    assert (bundle_dir / "networking.tf").exists()
    assert (bundle_dir / "workload.tf").exists()


# ---------------------------------------------------------------------------
# Item 5: Stateful 6-Phase Onboarding Progress Tracker
# ---------------------------------------------------------------------------


def test_onboarding_progress_tracker_lifecycle_and_digital_twin_overlays(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ODB_WORKSPACE_ROOT", str(tmp_path))
    tracker_path = tmp_path / "output" / "onboarding_progress.json"

    # 1. Initial status
    res_init = json.loads(
        manage_onboarding_progress_tracker(
            action="status",
            project_id="odb-tracker-proj",
            region="us-east4",
            tracker_file=str(tracker_path),
        )
    )
    assert res_init["valid"] is True
    assert res_init["completion_pct"] == 0
    assert len(res_init["phases"]) == 6
    assert "digital_twin_node_overlays" in res_init

    # 2. Update Phase 1 and Phase 2 to completed
    manage_onboarding_progress_tracker(
        action="update_phase",
        phase_id="phase_1",
        status="completed",
        notes="APIs and IAM enabled",
        tracker_file=str(tracker_path),
    )
    res_upd = json.loads(
        manage_onboarding_progress_tracker(
            action="update_phase",
            phase_id="2",
            status="completed",
            notes="Private Offer accepted",
            tracker_file=str(tracker_path),
        )
    )
    assert res_upd["completed_phases"] == 2
    assert res_upd["completion_pct"] == 33
    overlays = res_upd["digital_twin_node_overlays"]
    assert overlays["phase1_iam"]["status"] == "verified"
    assert overlays["phase2_mkt"]["status"] == "verified"

    # 3. Auto-verify with mocked live GCP readiness
    with patch(
        "ai_agent.tools.interactive_workflows.verify_live_onboarding_and_iam_readiness"
    ) as mock_live, patch(
        "ai_agent.tools.interactive_workflows.check_live_vpc_subnet_overlaps"
    ) as mock_vpc:
        mock_live.return_value = json.dumps(
            {
                "overall_status": "READY",
                "missing_apis": [],
                "missing_iam_roles": [],
            }
        )
        mock_vpc.return_value = json.dumps({"collision_free": True})

        res_auto = json.loads(
            manage_onboarding_progress_tracker(
                action="auto_verify",
                project_id="odb-tracker-proj",
                region="us-east4",
                tracker_file=str(tracker_path),
            )
        )
        assert res_auto["valid"] is True
        assert res_auto["auto_verify_summary"] is not None
        assert res_auto["auto_verify_summary"]["live_readiness_status"] == "READY"

    # 4. Reset tracker
    res_reset = json.loads(
        manage_onboarding_progress_tracker(
            action="reset",
            project_id="odb-tracker-proj",
            tracker_file=str(tracker_path),
        )
    )
    assert res_reset["completion_pct"] == 0


def test_onboarding_progress_tracker_blocks_path_traversal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ODB_WORKSPACE_ROOT", str(tmp_path))
    res = json.loads(
        manage_onboarding_progress_tracker(
            action="status",
            tracker_file="../outside_workspace_tracker.json",
        )
    )
    assert res["valid"] is False
    assert "outside the active workspace" in res["error"] or "Path" in res["error"]


# ---------------------------------------------------------------------------
# Item 6: Interactive Day-2 What-If Scaling & ForceNew Simulator
# ---------------------------------------------------------------------------


def test_day2_simulator_allows_safe_online_scaling_and_writes_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ODB_WORKSPACE_ROOT", str(tmp_path))
    bundle_dir = tmp_path / "output" / "adb-sim"

    res = json.loads(
        simulate_day2_scaling_what_if(
            workload_type="adb",
            current_compute_count=4,
            proposed_compute_count=12,
            current_storage_size_tb=1,
            proposed_storage_size_tb=4,
            current_auto_scaling=False,
            proposed_auto_scaling=True,
            current_deletion_protection=True,
            proposed_deletion_protection=True,
            apply_to_bundle_dir=str(bundle_dir),
        )
    )
    assert res["valid"] is True
    assert res["safe_day2_change"] is True
    assert res["delta_summary"]["destructive_forcenew_warnings_count"] == 0
    assert res["delta_summary"]["safe_in_place_updates_count"] >= 2
    assert res["saved_file"] is not None
    assert Path(res["saved_file"]).exists()
    assert "interactive_spec" in res


def test_day2_simulator_blocks_forcenew_cidr_and_zone_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ODB_WORKSPACE_ROOT", str(tmp_path))
    bundle_dir = tmp_path / "output" / "adb-unsafe"

    res = json.loads(
        simulate_day2_scaling_what_if(
            workload_type="adb",
            current_compute_count=4,
            proposed_compute_count=8,
            current_client_subnet_cidr="10.20.1.0/24",
            proposed_client_subnet_cidr="10.20.99.0/24",
            current_gcp_oracle_zone="us-east4-b-r1",
            proposed_gcp_oracle_zone="us-east4-a-r1",
            apply_to_bundle_dir=str(bundle_dir),
        )
    )
    assert res["safe_day2_change"] is False
    assert res["delta_summary"]["destructive_forcenew_warnings_count"] >= 1
    assert res["saved_file"] is None
    assert res["save_blocked_reason"] is not None


def test_day2_simulator_blocks_save_when_deletion_protection_disabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ODB_WORKSPACE_ROOT", str(tmp_path))
    bundle_dir = tmp_path / "output" / "adb-no-dp"

    res = json.loads(
        simulate_day2_scaling_what_if(
            workload_type="adb",
            current_compute_count=4,
            proposed_compute_count=8,
            current_deletion_protection=True,
            proposed_deletion_protection=False,
            apply_to_bundle_dir=str(bundle_dir),
        )
    )
    assert "deletion_protection" in res["deletion_protection_warning"]
    assert res["saved_file"] is None
    assert "deletion_protection" in (res["save_blocked_reason"] or "")


# ---------------------------------------------------------------------------
# Item 7: Live 5-Layer Guardrail Telemetry & Scorecard
# ---------------------------------------------------------------------------


def test_build_guardrail_telemetry_summary_and_workspace_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ODB_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("ODB_FAST_VALIDATION", "1")

    traces = [
        {
            "tool_name": "validate_odb_network_cidrs",
            "duration_ms": 4.2,
        },
        {
            "tool_name": "validate_terraform_hcl",
            "duration_ms": 11.5,
        },
    ]
    scorecard = build_guardrail_telemetry_summary(traces)
    assert scorecard["overall_status"] == "VERIFIED"
    assert scorecard["total_tool_invocations"] == 2
    assert len(scorecard["layers"]) == 5

    # Audit a valid HCL snippet
    audit_res = json.loads(
        audit_workspace_and_hcl_guardrails(
            workspace_dir=str(tmp_path),
            hcl_content=(
                'resource "google_oracle_database_odb_network" "main" {\n'
                '  project = "my-proj"\n'
                '  location = "us-east4"\n'
                '  odb_network_id = "odb-net"\n'
                '  network = "projects/my-proj/global/networks/default"\n'
                '}\n'
            ),
        )
    )
    assert audit_res["valid"] is True
    assert "scorecard" in audit_res


def test_orchestrator_streams_on_event_and_populates_guardrail_scorecard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_agent.llm_client import LLMConnectionConfig

    class _DummyResp:
        def __init__(self, text: str) -> None:
            self.text = text

    class _DummyChat:
        def __init__(self, tools: list) -> None:
            self.tools = {fn.__name__: fn for fn in tools}

        def send_message(self, user_message: str) -> _DummyResp:
            self.tools["validate_odb_network_cidrs"](
                vpc_cidr="10.10.0.0/16",
                client_subnet_cidr="10.20.1.0/24",
            )
            return _DummyResp("Validated CIDRs and prepared ODB@GCP architecture.")

    class _DummyChats:
        def create(self, model: str, config: object) -> _DummyChat:
            return _DummyChat(getattr(config, "tools", []))

    class _DummyClient:
        def __init__(self) -> None:
            self.chats = _DummyChats()

    monkeypatch.setattr(
        "ai_agent.orchestrator.create_genai_client",
        lambda cfg: _DummyClient(),
    )
    cfg = LLMConnectionConfig(
        auth_mode="vertex",
        model="gemini-3.8-flash",
        project_id="my-odb-project-01",
        location="global",
    )
    agent = ODBArchitectAgent(cfg)
    events: list[dict] = []

    turn = agent.send_message(
        "Please validate CIDR 10.10.0.0/16 and 10.20.1.0/24",
        on_event=lambda evt: events.append(evt),
    )

    assert "Validated CIDRs" in turn.text
    assert len(turn.tool_traces) == 1
    assert "Layer 4" in turn.tool_traces[0].guardrail_layer
    assert turn.guardrail_scorecard["overall_status"] == "VERIFIED"
    event_types = [e["event_type"] for e in events]
    assert "tool_start" in event_types
    assert "tool_complete" in event_types
    assert "guardrail_verify" in event_types


# ---------------------------------------------------------------------------
# Multi-Surface Verification: MCP Server (14 Tools) & CLI Commands
# ---------------------------------------------------------------------------


def test_mcp_server_exposes_all_14_tools_and_executes_part2_tools(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ODB_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("ODB_FAST_VALIDATION", "1")

    assert len(MCP_TOOLS_CATALOG) == 14
    tool_names = {t["name"] for t in MCP_TOOLS_CATALOG}
    assert "run_odb_architecture_wizard" in tool_names
    assert "manage_onboarding_progress_tracker" in tool_names
    assert "simulate_day2_scaling_what_if" in tool_names
    assert "get_guardrail_telemetry_report" in tool_names

    # JSON-RPC tools/list
    list_resp = handle_jsonrpc_message(
        {"jsonrpc": "2.0", "id": 10, "method": "tools/list", "params": {}}
    )
    assert list_resp is not None
    assert len(list_resp["result"]["tools"]) == 14

    # Execute each Part 2 MCP tool
    wiz_mcp = execute_mcp_tool(
        "run_odb_architecture_wizard",
        {"workload_profile": "elastic_rac_cloud_native", "generate_artifacts": False},
    )
    assert wiz_mcp["isError"] is False
    wiz_out = json.loads(wiz_mcp["content"][0]["text"])
    assert wiz_out["wizard_summary"]["recommended_workload_type"] == "exascale"

    trk_mcp = execute_mcp_tool(
        "manage_onboarding_progress_tracker",
        {"action": "status", "project_id": "mcp-proj"},
    )
    assert trk_mcp["isError"] is False
    trk_out = json.loads(trk_mcp["content"][0]["text"])
    assert trk_out["valid"] is True

    sim_mcp = execute_mcp_tool(
        "simulate_day2_scaling_what_if",
        {
            "workload_type": "adb",
            "current_compute_count": 4,
            "proposed_compute_count": 8,
        },
    )
    assert sim_mcp["isError"] is False
    sim_out = json.loads(sim_mcp["content"][0]["text"])
    assert sim_out["safe_day2_change"] is True

    grd_mcp = execute_mcp_tool(
        "get_guardrail_telemetry_report",
        {"workspace_dir": str(tmp_path)},
    )
    assert grd_mcp["isError"] is False
    grd_out = json.loads(grd_mcp["content"][0]["text"])
    assert "scorecard" in grd_out


def test_cli_wizard_tracker_and_simulate_day2_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ODB_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("ODB_FAST_VALIDATION", "1")
    runner = CliRunner()

    # 1. CLI wizard
    res_wiz = runner.invoke(
        cli_main,
        [
            "wizard",
            "--workload-profile",
            "autonomous_ai_lakehouse",
            "--ha-dr-tier",
            "regional_ha",
            "--network-governance",
            "shared_vpc",
            "--encryption",
            "gcp_cmek",
            "--save-html",
        ],
    )
    assert res_wiz.exit_code == 0
    assert "Recommended ODB Service" in res_wiz.stdout

    # 2. CLI tracker
    res_trk = runner.invoke(
        cli_main,
        [
            "tracker",
            "--action",
            "update_phase",
            "--phase",
            "1",
            "--status",
            "completed",
            "--notes",
            "CLI test note",
        ],
    )
    assert res_trk.exit_code == 0
    assert "6-Phase Onboarding Progress Tracker" in res_trk.stdout

    # 3. CLI simulate-day2
    res_sim = runner.invoke(
        cli_main,
        [
            "simulate-day2",
            "--workload",
            "adb",
            "--current-compute",
            "4",
            "--proposed-compute",
            "16",
            "--save-html",
        ],
    )
    assert res_sim.exit_code == 0
    assert "SAFE ONLINE SCALING" in res_sim.stdout
