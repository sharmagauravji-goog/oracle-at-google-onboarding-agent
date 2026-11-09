"""Unit, integration, and security tests for Part 1 Interactive Topology Explorer, Overlays & Blueprint Sync."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_agent.mcp_server import execute_mcp_tool
from ai_agent.tools.day2_maintenance import analyze_day2_terraform_diff
from ai_agent.tools.diagram_generator import (
    SUPPORTED_DIAGRAM_TYPES,
    generate_odb_architecture_diagram,
)
from ai_agent.tools.interactive_diagram import (
    INTERACTIVE_DIAGRAM_JS,
    build_day2_blast_radius_overlays,
    build_interactive_diagram_spec,
    build_readiness_node_overlays,
    compute_cidr_ip_math,
    render_standalone_interactive_html,
    validate_blueprint_cidrs,
)
from ai_agent.tools.onboarding_knowledge import evaluate_customer_onboarding_readiness


@pytest.mark.parametrize("diagram_type", SUPPORTED_DIAGRAM_TYPES)
def test_build_interactive_diagram_spec_all_seven_topologies(diagram_type: str) -> None:
    """Every supported diagram type must produce valid SVG nodes, edges, HCL snippets, and layer metadata."""
    spec = build_interactive_diagram_spec(
        diagram_type=diagram_type,
        project_id="demo-odb-proj-01",
        region="us-east4",
        gcp_oracle_zone="us-east4-b-r1",
        vpc_cidr="10.10.0.0/16",
        client_subnet_cidr="10.20.1.0/24",
        backup_subnet_cidr="10.20.2.0/24",
        workload_type="exadata_dedicated",
        deployment_layer="full_stack",
        compute_count=8,
        storage_size_tb=4,
    )
    assert spec["diagram_type"] == diagram_type
    assert len(spec["nodes"]) >= 3
    assert len(spec["edges"]) >= 2
    assert spec["blueprint"]["project_id"] == "demo-odb-proj-01"
    assert spec["cidr_validation"]["valid"] is True

    node_ids = {n["id"] for n in spec["nodes"]}
    for edge in spec["edges"]:
        assert edge["from"] in node_ids
        assert edge["to"] in node_ids

    # Every node must carry Separation-of-Duties ownership and HCL/resource metadata
    for node in spec["nodes"]:
        assert node["team_owner"] in {"procurement", "network", "infrastructure", "database", "platform"}
        assert isinstance(node["iam_roles"], list)
        assert node["hcl_snippet"]


def test_cidr_ip_math_and_blueprint_overlap_validation() -> None:
    """Client/Backup subnets smaller than /28, non-RFC1918, or overlapping ranges must be flagged."""
    ok_math = compute_cidr_ip_math("10.20.1.0/24", is_odb_subnet=True)
    assert ok_math["valid"] is True
    assert ok_math["meets_min_28"] is True
    assert ok_math["usable_ips"] == 251

    too_small = compute_cidr_ip_math("10.20.1.0/29", is_odb_subnet=True)
    assert too_small["valid"] is False
    assert too_small["meets_min_28"] is False

    public_range = compute_cidr_ip_math("8.8.8.0/24", is_odb_subnet=True)
    assert public_range["valid"] is False
    assert public_range["is_private_rfc1918"] is False

    overlap_report = validate_blueprint_cidrs(
        vpc_cidr="10.20.0.0/16",
        client_subnet_cidr="10.20.1.0/24",
        backup_subnet_cidr="10.20.1.128/25",
    )
    assert overlap_report["valid"] is False
    assert "client_subnet" in overlap_report["node_flags"]
    assert "backup_subnet" in overlap_report["node_flags"]
    assert "vpc" in overlap_report["node_flags"]


def test_readiness_digital_twin_overlays_blocker_and_verified() -> None:
    """Live IAM/API checks, checklist evaluations, and live VPC collision checks map onto diagram nodes."""
    live_blocker_json = json.dumps(
        {
            "valid": True,
            "project_id": "prod-odb-01",
            "team_role": "network",
            "api_readiness": {
                "status": "missing_apis",
                "missing_apis": ["oracledatabase.googleapis.com"],
            },
            "iam_readiness": {
                "iam_policy_inspected": True,
                "missing_odb_roles": ["roles/oracledatabase.networkAdmin"],
                "remediation_commands": [
                    "gcloud projects add-iam-policy-binding prod-odb-01 --member='user:net@example.com' --role='roles/oracledatabase.networkAdmin'"
                ],
            },
        }
    )
    chk_json = evaluate_customer_onboarding_readiness(
        project_id="prod-odb-01",
        has_gcp_billing_and_org_admin=True,
        has_enabled_oracledatabase_api=True,
        marketplace_procurement_mode="private_offer",
        has_linked_oci_tenancy=True,
        has_mos_account_and_csi=False,
    )
    subnet_collision_json = json.dumps(
        {
            "live_vpc_checked": True,
            "collision_free": False,
            "collisions": [{"colliding_gcp_subnet": "app-sub-1", "colliding_gcp_cidr": "10.20.1.0/24"}],
            "existing_gcp_subnets_count": 4,
        }
    )

    overlays = build_readiness_node_overlays(
        live_readiness_json=live_blocker_json,
        checklist_readiness_json=chk_json,
        live_subnet_overlap_json=subnet_collision_json,
    )
    assert overlays["phase1_iam"]["state"] == "blocker"
    assert "gcloud services enable oracledatabase.googleapis.com" in overlays["phase1_iam"]["remediation_cmd"]
    assert overlays["phase4_mos"]["state"] == "blocker"
    assert overlays["phase3_oci"]["state"] == "verified"
    assert overlays["client_subnet"]["state"] == "blocker"


def test_day2_blast_radius_overlays_safe_vs_forcenew() -> None:
    """Safe online scaling produces `scaling_safe`, while immutable changes produce `forcenew_hazard`."""
    before_hcl = (
        'resource "google_oracle_database_autonomous_database" "adb" {\n'
        '  autonomous_database_id = "odb-prod-adb"\n'
        '  database               = "ODBPROD1"\n'
        '  location               = "us-east4"\n'
        '  compute_count          = 4\n'
        '}\n'
        'resource "google_oracle_database_odb_subnet" "client" {\n'
        '  odb_subnet_id = "odb-client"\n'
        '  cidr_range    = "10.20.1.0/24"\n'
        '}'
    )
    safe_after_hcl = before_hcl.replace("compute_count          = 4", "compute_count          = 8")
    safe_diff = analyze_day2_terraform_diff(before_hcl, safe_after_hcl)
    safe_overlays = build_day2_blast_radius_overlays(safe_diff)
    assert safe_overlays["workload_db"]["state"] == "scaling_safe"

    hazard_after_hcl = before_hcl.replace('cidr_range    = "10.20.1.0/24"', 'cidr_range    = "10.20.99.0/24"')
    hazard_diff = analyze_day2_terraform_diff(before_hcl, hazard_after_hcl)
    hazard_overlays = build_day2_blast_radius_overlays(hazard_diff)
    assert hazard_overlays["client_subnet"]["state"] == "forcenew_hazard"
    assert "FORCENEW RISK" in hazard_overlays["client_subnet"]["badge_text"]


def test_standalone_html_csp_nonce_and_dom_xss_guardrails() -> None:
    """Standalone HTML5 export must enforce nonce CSP, escape script breakouts, and forbid innerHTML/eval/alert."""
    for forbidden_sink in (
        ".innerHTML",
        ".outerHTML",
        "insertAdjacentHTML",
        "document.write",
        "eval(",
        "alert(",
        "confirm(",
        "prompt(",
        "localStorage",
    ):
        assert forbidden_sink not in INTERACTIVE_DIAGRAM_JS

    spec = build_interactive_diagram_spec("encryption_cmek")
    spec["title"] = 'CMEK </script><script>evil()</script> & "Test"'
    html_doc = render_standalone_interactive_html(spec)

    assert "Content-Security-Policy" in html_doc
    assert "default-src 'none'" in html_doc
    assert "nonce-" in html_doc
    assert "</script><script>evil()" not in html_doc
    assert "&lt;/script&gt;" in html_doc or "<\\/script>" in html_doc


def test_generate_diagram_html_export_and_mcp_tool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Diagram generator and MCP tool support standalone HTML export while enforcing workspace path containment."""
    monkeypatch.setenv("ODB_WORKSPACE_ROOT", str(tmp_path))

    out_html = tmp_path / "diagrams" / "hub.html"
    res = json.loads(
        generate_odb_architecture_diagram(
            diagram_type="networking_hub_and_spoke_ha_dr",
            output_format="interactive_html",
            save_to_file=str(out_html),
        )
    )
    assert res["valid"] is True
    assert out_html.exists()
    assert "<!DOCTYPE html>" in out_html.read_text(encoding="utf-8")
    assert "interactive_spec" in res
    assert "interactive_html" in res

    # Path traversal outside workspace must be blocked
    blocked = json.loads(
        generate_odb_architecture_diagram(
            diagram_type="end_to_end_onboarding",
            save_to_file="../escaped.html",
        )
    )
    assert blocked["valid"] is False
    assert "outside the active workspace" in blocked["error"]

    # MCP tool integration
    mcp_res = execute_mcp_tool(
        "generate_odb_diagram",
        {
            "diagram_type": "backup_and_recovery",
            "save_to_workspace": True,
            "save_interactive_html": True,
            "output_dir": "./output/diagrams",
        },
    )
    assert mcp_res["isError"] is False
    mcp_payload = json.loads(mcp_res["content"][0]["text"])
    assert mcp_payload["valid"] is True
    assert (tmp_path / "output" / "diagrams" / "backup_and_recovery.md").exists()
    assert (tmp_path / "output" / "diagrams" / "backup_and_recovery.html").exists()


def test_bidirectional_blueprint_to_terraform_sync(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Bidirectional blueprint sync generates, validates, and saves Golden Terraform inside `./output`."""
    monkeypatch.setenv("ODB_WORKSPACE_ROOT", str(tmp_path))
    from ai_agent.web import _sync_blueprint_to_golden_terraform

    synced = _sync_blueprint_to_golden_terraform(
        {
            "project_id": "my-odb-project-01",
            "region": "us-east4",
            "gcp_oracle_zone": "us-east4-b-r1",
            "vpc_cidr": "10.10.0.0/16",
            "client_subnet_cidr": "10.20.1.0/24",
            "backup_subnet_cidr": "10.20.2.0/24",
            "workload_type": "adb",
            "deployment_layer": "full_stack",
            "compute_count": 8,
            "storage_size_tb": 2,
        }
    )
    assert synced["valid"] is True
    assert "networking.tf" in synced["files"]
    assert (tmp_path / "output" / "blueprint-adb-full-stack" / "networking.tf").exists()

    # Invalid /29 subnet must be blocked by server-side CIDR guardrail
    bad_sync = _sync_blueprint_to_golden_terraform(
        {
            "project_id": "my-odb-project-01",
            "vpc_cidr": "10.10.0.0/16",
            "client_subnet_cidr": "10.20.1.0/29",
            "backup_subnet_cidr": "10.20.2.0/24",
        }
    )
    assert bad_sync["valid"] is False


def test_streamlit_web_app_renders_cleanly() -> None:
    """Streamlit Web Studio mounts the CCv2 interactive topology component without runtime exceptions."""
    from streamlit.testing.v1 import AppTest

    web_script = Path(__file__).resolve().parents[1] / "ai_agent" / "web.py"
    at = AppTest.from_file(web_script, default_timeout=15)
    at.run()
    assert not at.exception
    assert len(at.title) >= 1
    assert "Oracle@Google Onboarding Agent" in at.title[0].value


def test_cli_diagram_interactive_html_and_studio_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CLI `diagram --save-html` exports standalone HTML and `studio --help` exposes Cloud Shell options."""
    from typer.testing import CliRunner

    from ai_agent.cli import app

    monkeypatch.setenv("ODB_WORKSPACE_ROOT", str(tmp_path))
    runner = CliRunner()

    res_diag = runner.invoke(
        app,
        [
            "diagram",
            "--type",
            "end_to_end_onboarding",
            "--format",
            "interactive_html",
            "--save-html",
            "--save-to",
            str(tmp_path / "output" / "cli-diagrams"),
        ],
    )
    assert res_diag.exit_code == 0, res_diag.output
    assert (tmp_path / "output" / "cli-diagrams" / "end_to_end_onboarding.html").exists()

    res_studio = runner.invoke(app, ["studio", "--help"])
    assert res_studio.exit_code == 0, res_studio.output
    assert "--cloud-shell" in res_studio.output

