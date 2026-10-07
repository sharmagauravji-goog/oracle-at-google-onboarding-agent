"""Unit tests for live discovery, onboarding knowledge, diagrams, and deterministic guardrail tools."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_agent.tools.day2_maintenance import (
    analyze_day2_terraform_diff,
    inspect_existing_terraform_workspace,
)
from ai_agent.tools.diagram_generator import (
    SUPPORTED_DIAGRAM_TYPES,
    generate_odb_architecture_diagram,
)
from ai_agent.tools.docs_fetcher import (
    fetch_official_odb_documentation,
    validate_documentation_url,
)
from ai_agent.tools.golden_templates import generate_golden_odb_terraform
from ai_agent.tools.network_validator import (
    resolve_safe_workspace_path,
    save_generated_terraform_bundle,
    validate_odb_network_cidrs,
)
from ai_agent.tools.odb_live_discovery import (
    check_live_vpc_subnet_overlaps,
    discover_live_odb_regions_and_zones,
    discover_live_odb_shapes_and_versions,
)
from ai_agent.tools.onboarding_knowledge import (
    SUPPORTED_ONBOARDING_TOPICS,
    check_onboarding_response_for_hallucinations,
    evaluate_customer_onboarding_readiness,
    get_odb_onboarding_and_architecture_guide,
)
from ai_agent.tools.terraform_registry import (
    check_hcl_for_provider_hallucinations,
    get_odb_resource_documentation,
    list_odb_terraform_resources,
    validate_terraform_hcl,
)


def test_validate_odb_network_cidrs_enforces_slash28_and_overlap() -> None:
    valid_res = json.loads(
        validate_odb_network_cidrs(
            vpc_cidr="10.10.0.0/16",
            client_subnet_cidr="10.20.1.0/24",
            backup_subnet_cidr="10.20.2.0/28",
        )
    )
    assert valid_res["valid"] is True
    assert valid_res["errors"] == []

    small_prefix_res = json.loads(
        validate_odb_network_cidrs(
            vpc_cidr="10.10.0.0/16",
            client_subnet_cidr="10.20.1.0/29",
        )
    )
    assert small_prefix_res["valid"] is False
    assert any("minimum /28" in err for err in small_prefix_res["errors"])

    overlap_res = json.loads(
        validate_odb_network_cidrs(
            vpc_cidr="10.10.0.0/16",
            client_subnet_cidr="10.10.1.0/24",
        )
    )
    assert overlap_res["valid"] is False
    assert any("overlap" in err.lower() for err in overlap_res["errors"])


def test_workspace_path_containment_blocks_outside_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ODB_WORKSPACE_ROOT", str(tmp_path))

    # Inside workspace is allowed
    safe_dir = resolve_safe_workspace_path("./output/adb")
    assert safe_dir == (tmp_path / "output" / "adb").resolve()

    # Path traversal outside workspace is rejected
    with pytest.raises(ValueError, match="Path traversal blocked"):
        resolve_safe_workspace_path("../../etc/passwd")

    with pytest.raises(ValueError, match="Path traversal blocked"):
        resolve_safe_workspace_path("/etc")


def test_save_generated_terraform_bundle_prevents_traversal_and_secret_leaks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ODB_WORKSPACE_ROOT", str(tmp_path))
    files_payload = json.dumps(
        {
            "main.tf": 'resource "google_oracle_database_odb_network" "net" {}',
            "modules/adb/main.tf": 'resource "google_oracle_database_autonomous_database" "adb" {}',
            "../../etc/passwd.tf": "malicious traversal",
            "evil.exe": "disallowed extension",
            "terraform.tfvars": 'admin_password = "SuperSecretPassword123!"',
        }
    )
    result = json.loads(
        save_generated_terraform_bundle(
            files_json=files_payload,
            bundle_name="test-bundle",
            base_output_dir=str(tmp_path),
        )
    )
    assert result["saved"] is True
    assert "main.tf" in result["written_files"]
    assert "modules/adb/main.tf" in result["written_files"]
    assert len(result["skipped_files"]) == 3
    assert (tmp_path / "test-bundle" / "main.tf").is_file()
    assert not (tmp_path / "test-bundle" / "terraform.tfvars").exists()

    # Attempt to write outside the open workspace must be rejected
    outside_res = json.loads(
        save_generated_terraform_bundle(
            files_json=files_payload,
            output_dir="/etc/evil-dir",
            bundle_name="test-bundle",
        )
    )
    assert outside_res["saved"] is False
    assert "Path traversal blocked" in outside_res["error"]


def test_docs_fetcher_blocks_ssrf_and_non_https() -> None:
    assert (
        validate_documentation_url("https://cloud.google.com/oracle/database/docs/overview")
        == "https://cloud.google.com/oracle/database/docs/overview"
    )
    with pytest.raises(ValueError, match="Only HTTPS"):
        validate_documentation_url("http://cloud.google.com/oracle/database/docs/overview")
    with pytest.raises(ValueError, match="not in the allow-listed"):
        validate_documentation_url("https://169.254.169.254/latest/meta-data/")
    with pytest.raises(ValueError, match="not in the allow-listed"):
        validate_documentation_url("https://evil.example.com/docs")

    blocked = json.loads(fetch_official_odb_documentation("https://localhost:8080/admin"))
    assert "error" in blocked


def test_terraform_registry_catalog_and_fast_validation() -> None:
    catalog = json.loads(list_odb_terraform_resources())
    assert "google_oracle_database_autonomous_database" in catalog["resources"]
    assert "google_oracle_database_exadb_vm_cluster" in catalog["resources"]

    invalid = json.loads(get_odb_resource_documentation("aws_s3_bucket"))
    assert "error" in invalid

    golden = json.loads(
        generate_golden_odb_terraform(
            project_id="my-odb-project-01",
            region="us-east4",
            workload_type="adb",
        )
    )
    fast_val = json.loads(
        validate_terraform_hcl(json.dumps(golden["files"]), fast_mode=True)
    )
    assert fast_val["valid"] is True
    assert fast_val["fast_mode"] is True


def test_odb_live_discovery_validates_inputs_and_returns_capabilities() -> None:
    bad_proj = json.loads(discover_live_odb_regions_and_zones("INVALID_PROJECT!!"))
    assert "error" in bad_proj

    shapes = json.loads(
        discover_live_odb_shapes_and_versions("my-odb-project-01", "us-east4")
    )
    assert shapes.get("region") == "us-east4"
    assert "capabilities" in shapes or "live_capabilities" in shapes

    bad_overlap = json.loads(
        check_live_vpc_subnet_overlaps(
            project_id="my-odb-project-01",
            client_subnet_cidr="999.999.1.0/24",
            vpc_name="default",
        )
    )
    assert "error" in bad_overlap


def test_guardrail_1_golden_template_generator_passes_hallucination_checks() -> None:
    for workload in ("adb", "exadata_dedicated", "exascale", "basedb"):
        res = json.loads(
            generate_golden_odb_terraform(
                project_id="my-odb-project-01",
                region="us-east4",
                workload_type=workload,
                environment_prefix="prod-odb",
            )
        )
        assert res["valid"] is True
        assert res["workload_type"] == workload
        assert res["guardrail_checks"]["cidr_slash28_and_overlap"] == "PASSED"
        files = res["files"]
        assert "versions.tf" in files
        assert "networking.tf" in files
        assert "workload.tf" in files

        for filename, hcl_content in files.items():
            if filename.endswith(".tf"):
                issues = check_hcl_for_provider_hallucinations(hcl_content)
                assert issues == [], f"Golden {workload}/{filename} failed: {issues}"


def test_guardrail_2_detects_oci_and_attribute_hallucinations() -> None:
    hallucinated_hcl = '''
resource "oci_database_autonomous_database" "bad_oci" {
  compartment_id = "ocid1.compartment.oc1..example"
}

resource "google_oracle_database_odb_subnet" "bad_subnet" {
  odb_network = "projects/p/locations/us-east4/odbNetworks/net"
  cidr        = "10.20.1.0/24"
}

resource "google_oracle_database_autonomous_database" "bad_adb" {
  autonomous_database_id = "adb1"
  compute_count          = 4
  data_storage_size_tb   = 1
}
'''
    issues = check_hcl_for_provider_hallucinations(hallucinated_hcl)
    assert len(issues) >= 3
    joined_issues = " ".join(issues)
    assert "oci_database_autonomous_database" in joined_issues
    assert "odbnetwork" in joined_issues
    assert "properties { ... }" in joined_issues


def test_guardrail_5_day2_workspace_inspector_and_forcenew_diff_analyzer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ODB_WORKSPACE_ROOT", str(tmp_path))
    golden = json.loads(
        generate_golden_odb_terraform(
            project_id="my-odb-project-01",
            region="us-east4",
            workload_type="adb",
        )
    )
    save_generated_terraform_bundle(
        files_json=json.dumps(golden["files"]),
        bundle_name="day2-ws",
        base_output_dir=str(tmp_path),
    )
    ws_dir = tmp_path / "day2-ws"

    inspection = json.loads(inspect_existing_terraform_workspace(str(ws_dir)))
    assert inspection["exists"] is True
    assert len(inspection["tf_files"]) >= 5
    discovered = inspection["discovered_odb_resources"]
    resource_types = {meta["resource_type"] for meta in discovered.values()}
    assert "google_oracle_database_autonomous_database" in resource_types

    # Inspecting outside workspace must be blocked
    blocked_inspect = json.loads(inspect_existing_terraform_workspace("/etc"))
    assert blocked_inspect["valid"] is False
    assert "Path traversal blocked" in blocked_inspect["error"]

    orig_workload = golden["files"]["workload.tf"]
    safe_modified = orig_workload.replace(
        "compute_count        = 4",
        "compute_count        = 8",
    )
    safe_diff = json.loads(
        analyze_day2_terraform_diff(
            existing_hcl=orig_workload,
            proposed_hcl=safe_modified,
        )
    )
    assert safe_diff["safe_day2_change"] is True
    assert safe_diff["destructive_replacement_warnings"] == []

    destructive_modified = orig_workload.replace(
        'autonomous_database_id = "${var.environment_prefix}-adb"',
        'autonomous_database_id = "brand-new-adb-id"',
    )
    destructive_diff = json.loads(
        analyze_day2_terraform_diff(
            existing_hcl=orig_workload,
            proposed_hcl=destructive_modified,
        )
    )
    assert destructive_diff["safe_day2_change"] is False
    assert len(destructive_diff["destructive_replacement_warnings"]) >= 1
    assert (
        destructive_diff["destructive_replacement_warnings"][0]["attribute"]
        == "autonomous_database_id"
    )


def test_onboarding_knowledge_base_and_readiness_evaluator() -> None:
    for topic in SUPPORTED_ONBOARDING_TOPICS:
        payload = json.loads(get_odb_onboarding_and_architecture_guide(topic))
        assert payload["valid"] is True
        assert payload["topic"] == topic

    readiness = json.loads(
        evaluate_customer_onboarding_readiness(
            has_gcp_billing_and_org_admin=True,
            has_enabled_oracledatabase_api=True,
            marketplace_procurement_mode="private_offer",
            has_linked_oci_tenancy=True,
            has_mos_account_and_csi=False,
            networking_topology="hub_and_spoke_ncc",
            encryption_mode="gcp_cmek",
            workload_type="exadata_dedicated",
        )
    )
    assert readiness["valid"] is True
    assert readiness["readiness_score_pct"] == 80
    assert any("CSI" in blocker for blocker in readiness["blocking_items"])

    bad_text = (
        "Grant roles/cloudkms.cryptoKeyEncrypterDecrypter to "
        "service-12345@gcp-sa-oracle.iam.gserviceaccount.com"
    )
    issues = check_onboarding_response_for_hallucinations(bad_text)
    assert len(issues) >= 1
    assert "gcp-sa-oracledatabase" in issues[0]


def test_diagram_generator_all_types_and_workspace_sandbox(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ODB_WORKSPACE_ROOT", str(tmp_path))
    for dtype in SUPPORTED_DIAGRAM_TYPES:
        res = json.loads(
            generate_odb_architecture_diagram(
                diagram_type=dtype,
                output_format="both",
                save_to_file=f"./output/diagrams/{dtype}.md",
            )
        )
        assert res["valid"] is True
        assert "```mermaid" in res["mermaid_markdown"]
        assert res["ascii_diagram"]
        assert (tmp_path / "output" / "diagrams" / f"{dtype}.md").is_file()

    # Saving outside workspace must be blocked
    escape_res = json.loads(
        generate_odb_architecture_diagram(
            diagram_type="end_to_end_onboarding",
            save_to_file="../../etc/evil_diagram.md",
        )
    )
    assert escape_res["valid"] is False
    assert "Path traversal blocked" in escape_res["error"]
