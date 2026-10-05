"""Unit tests for live discovery, documentation, and deterministic guardrail tools."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_agent.tools.docs_fetcher import (
    fetch_official_odb_documentation,
    validate_documentation_url,
)
from ai_agent.tools.network_validator import (
    save_generated_terraform_bundle,
    validate_odb_network_cidrs,
)
from ai_agent.tools.odb_live_discovery import (
    discover_live_odb_regions_and_zones,
    discover_live_odb_shapes_and_versions,
)
from ai_agent.tools.terraform_registry import (
    get_odb_resource_documentation,
    list_odb_terraform_resources,
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


def test_save_generated_terraform_bundle_prevents_traversal_and_secret_leaks(
    tmp_path: Path,
) -> None:
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


def test_terraform_registry_catalog_and_resource_validation() -> None:
    catalog = json.loads(list_odb_terraform_resources())
    assert "google_oracle_database_autonomous_database" in catalog["resources"]
    assert "google_oracle_database_exadb_vm_cluster" in catalog["resources"]

    invalid = json.loads(get_odb_resource_documentation("aws_s3_bucket"))
    assert "error" in invalid


def test_odb_live_discovery_validates_inputs_and_returns_capabilities() -> None:
    bad_proj = json.loads(discover_live_odb_regions_and_zones("INVALID_PROJECT!!"))
    assert "error" in bad_proj

    shapes = json.loads(
        discover_live_odb_shapes_and_versions("my-odb-project-01", "us-east4")
    )
    assert shapes.get("region") == "us-east4"
    assert "capabilities" in shapes or "live_capabilities" in shapes
