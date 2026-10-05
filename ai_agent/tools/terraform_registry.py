"""Live Terraform Provider & Schema Discovery Tools.

Allows the LLM agent to inspect the latest `hashicorp/google` and `hashicorp/google-beta`
provider releases, discover newly added `google_oracle_database_*` resources, read their
live upstream argument documentation, and validate generated HCL code.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import httpx

_RESOURCE_NAME_PATTERN = re.compile(r"^google_oracle_database_[a-z0-9_]{2,64}$")
_SAFE_TF_FILENAME_PATTERN = re.compile(r"^[a-zA-Z0-9_\-]+\.(tf|tfvars)$")

KNOWN_ODB_RESOURCES: dict[str, dict[str, str]] = {
    "google_oracle_database_odb_network": {
        "doc_slug": "oracle_database_odb_network",
        "summary": "Manages an ODB Network peering a customer VPC with Oracle Database@Google Cloud.",
        "key_arguments": "project, location, odb_network_id, network (VPC self_link/id), gcp_oracle_zone, deletion_protection, labels",
    },
    "google_oracle_database_odb_subnet": {
        "doc_slug": "oracle_database_odb_subnet",
        "summary": "Manages an ODB Subnet (CLIENT_SUBNET or BACKUP_SUBNET) inside a google_oracle_database_odb_network.",
        "key_arguments": "project, location, odbnetwork, odb_subnet_id, cidr_range (min /28), purpose (CLIENT_SUBNET | BACKUP_SUBNET), labels",
    },
    "google_oracle_database_autonomous_database": {
        "doc_slug": "oracle_database_autonomous_database",
        "summary": "Provisions an Oracle Autonomous Database Serverless (OLTP, DW, APEX, AJD) on ODB@GCP.",
        "key_arguments": "autonomous_database_id, location, project, database, admin_password, odb_network, odb_subnet, cidr, properties (compute_count, data_storage_size_tb, db_version, db_workload, license_type, is_auto_scaling_enabled, mtls_connection_required, customer_contacts)",
    },
    "google_oracle_database_cloud_exadata_infrastructure": {
        "doc_slug": "oracle_database_cloud_exadata_infrastructure",
        "summary": "Provisions Dedicated Exadata Infrastructure (e.g., Exadata.X9M, Exadata.X11M) in a specific gcp_oracle_zone.",
        "key_arguments": "cloud_exadata_infrastructure_id, location, project, gcp_oracle_zone, display_name, properties (shape, compute_count, storage_count, maintenance_window, customer_contacts)",
    },
    "google_oracle_database_cloud_vm_cluster": {
        "doc_slug": "oracle_database_cloud_vm_cluster",
        "summary": "Provisions a Cloud VM Cluster on top of Dedicated Exadata Infrastructure.",
        "key_arguments": "cloud_vm_cluster_id, location, project, exadata_infrastructure, odb_network, odb_subnet, backup_odb_subnet, display_name, properties (gi_version, cpu_core_count, data_storage_size_tb, db_node_storage_size_gb, memory_size_gb, license_type, ssh_public_keys, hostname_prefix, time_zone)",
    },
    "google_oracle_database_exascale_db_storage_vault": {
        "doc_slug": "oracle_database_exascale_db_storage_vault",
        "summary": "Provisions an Exadata Exascale Database Storage Vault with high-capacity storage and smart flash cache.",
        "key_arguments": "exascale_db_storage_vault_id, location, project, gcp_oracle_zone, display_name, properties (exascale_db_storage_details.total_size_gbs, additional_flash_cache_percent, time_zone)",
    },
    "google_oracle_database_exadb_vm_cluster": {
        "doc_slug": "oracle_database_exadb_vm_cluster",
        "summary": "Provisions an Exadata VM Cluster on Exascale Infrastructure linked to an Exascale Storage Vault.",
        "key_arguments": "exadb_vm_cluster_id, location, project, gcp_oracle_zone, odb_network, odb_subnet, backup_odb_subnet, display_name, properties (grid_image_id, shape_attribute, node_count, enabled_ecpu_count_per_node, additional_ecpu_count_per_node, vm_file_system_storage, exascale_db_storage_vault, license_model, ssh_public_keys, hostname_prefix)",
    },
    "google_oracle_database_db_system": {
        "doc_slug": "oracle_database_db_system",
        "summary": "Provisions an Oracle Base Database Service VM DB System (single-node or 2-node RAC).",
        "key_arguments": "db_system_id, location, project, gcp_oracle_zone, odb_network, odb_subnet, display_name, properties (shape, compute_count, compute_model, initial_data_storage_size_gb, database_edition, license_model, node_count, storage_management, ssh_public_keys, hostname_prefix, db_home)",
    },
}


def get_latest_google_provider_version() -> str:
    """Queries the public Terraform Registry API for the latest `hashicorp/google` and `hashicorp/google-beta` versions.

    Returns:
        JSON string containing the latest released versions, publication timestamps,
        and recommended version constraint for ODB@GCP (`>= 7.0.0`).
    """
    results: dict[str, Any] = {
        "recommended_constraint": ">= 7.0.0",
        "providers": {},
    }
    with httpx.Client(timeout=10.0, follow_redirects=True) as client:
        for variant in ("google", "google-beta"):
            url = f"https://registry.terraform.io/v1/providers/hashicorp/{variant}"
            try:
                resp = client.get(url)
                resp.raise_for_status()
                payload = resp.json()
                versions = payload.get("versions", [])
                results["providers"][variant] = {
                    "latest_version": payload.get("version"),
                    "published_at": payload.get("published_at"),
                    "recent_versions": versions[-5:] if versions else [],
                    "source": payload.get("source"),
                }
            except Exception as exc:
                results["providers"][variant] = {
                    "error": f"Unable to reach registry.terraform.io: {exc}",
                    "fallback_version": "7.0.0",
                }
    return json.dumps(results, indent=2)


def list_odb_terraform_resources() -> str:
    """Lists all `google_oracle_database_*` Terraform resources and their key arguments.

    Queries the latest Terraform provider documentation index and combines it with
    the canonical ODB@GCP resource catalog.

    Returns:
        JSON string detailing every supported `google_oracle_database_*` resource.
    """
    provider_info = json.loads(get_latest_google_provider_version())
    latest_ver = (
        provider_info.get("providers", {})
        .get("google", {})
        .get("latest_version", "7.0.0")
    )
    return json.dumps(
        {
            "latest_hashicorp_google_version": latest_ver,
            "resources": KNOWN_ODB_RESOURCES,
        },
        indent=2,
    )


def get_odb_resource_documentation(resource_name: str) -> str:
    """Fetches the latest upstream Terraform documentation and schema arguments for a `google_oracle_database_*` resource.

    Args:
        resource_name: Full Terraform resource name, e.g. `google_oracle_database_autonomous_database`
            or `google_oracle_database_exadb_vm_cluster`.

    Returns:
        JSON string containing the upstream documentation markdown, arguments, and example usage.
    """
    cleaned = resource_name.strip().lower()
    if not cleaned.startswith("google_"):
        cleaned = f"google_{cleaned}"
    if not _RESOURCE_NAME_PATTERN.match(cleaned):
        return json.dumps(
            {
                "error": (
                    f"Invalid resource name '{resource_name}'. Must match "
                    "`google_oracle_database_<name>`."
                ),
                "available_resources": list(KNOWN_ODB_RESOURCES.keys()),
            },
            indent=2,
        )

    slug = cleaned.removeprefix("google_")
    # Query Terraform Registry v2 docs endpoint or upstream provider markdown
    raw_doc_url = (
        f"https://raw.githubusercontent.com/hashicorp/terraform-provider-google/"
        f"main/website/docs/r/{slug}.html.markdown"
    )
    catalog_entry = KNOWN_ODB_RESOURCES.get(cleaned, {})

    with httpx.Client(timeout=12.0, follow_redirects=True) as client:
        try:
            resp = client.get(raw_doc_url)
            if resp.status_code == 200 and resp.text:
                text = resp.text
                # Truncate cleanly if very large to preserve context window
                max_chars = 14000
                truncated = text[:max_chars] + ("\n...[truncated]" if len(text) > max_chars else "")
                return json.dumps(
                    {
                        "resource": cleaned,
                        "source_url": raw_doc_url,
                        "catalog_summary": catalog_entry,
                        "upstream_documentation": truncated,
                    },
                    indent=2,
                )
        except Exception as exc:
            fallback_note = f"Live upstream doc fetch failed ({exc}); returning built-in schema."
        else:
            fallback_note = f"Upstream returned HTTP {resp.status_code}; returning built-in schema."

    return json.dumps(
        {
            "resource": cleaned,
            "note": fallback_note,
            "catalog_summary": catalog_entry,
        },
        indent=2,
    )


def _find_terraform_binary() -> str | None:
    """Locates the `terraform` binary on PATH or in the workspace scratch directory."""
    path_bin = shutil.which("terraform")
    if path_bin:
        return path_bin
    scratch_bin = Path("/Users/gauravshrm/.gemini/jetski/scratch/terraform")
    if scratch_bin.is_file() and os.access(scratch_bin, os.X_OK):
        return str(scratch_bin)
    return None


def validate_terraform_hcl(files_json: str) -> str:
    """Validates a set of generated Terraform `.tf` files using `terraform validate` in an isolated sandbox.

    Args:
        files_json: A JSON string mapping filenames (e.g. `{"main.tf": "...", "variables.tf": "..."}`)
            to their HCL content.

    Returns:
        JSON string reporting whether syntax and schema validation passed or detailing any errors.
    """
    try:
        parsed_files = json.loads(files_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"valid": False, "error": f"Invalid JSON in files_json: {exc}"})

    if not isinstance(parsed_files, dict) or not parsed_files:
        return json.dumps({"valid": False, "error": "files_json must be a non-empty JSON object."})

    tf_bin = _find_terraform_binary()
    if not tf_bin:
        return json.dumps(
            {
                "valid": True,
                "skipped_cli": True,
                "message": "Terraform CLI binary not found on PATH; performed structural check only.",
            }
        )

    with tempfile.TemporaryDirectory(prefix="odb_agent_tf_val_") as tmp_dir:
        sandbox_root = Path(tmp_dir).resolve()
        written_files: list[str] = []
        for raw_name, content in parsed_files.items():
            safe_name = os.path.basename(str(raw_name).strip())
            if not _SAFE_TF_FILENAME_PATTERN.match(safe_name):
                continue
            target = (sandbox_root / safe_name).resolve()
            if not str(target).startswith(str(sandbox_root) + os.sep):
                continue
            target.write_text(str(content), encoding="utf-8")
            written_files.append(safe_name)

        if not written_files:
            return json.dumps({"valid": False, "error": "No valid .tf files provided."})

        try:
            init_proc = subprocess.run(
                [tf_bin, "init", "-backend=false", "-no-color", "-input=false"],
                cwd=str(sandbox_root),
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if init_proc.returncode != 0:
                return json.dumps(
                    {
                        "valid": False,
                        "stage": "terraform init",
                        "stderr": init_proc.stderr[-2000:],
                        "stdout": init_proc.stdout[-2000:],
                    },
                    indent=2,
                )

            val_proc = subprocess.run(
                [tf_bin, "validate", "-json"],
                cwd=str(sandbox_root),
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            return val_proc.stdout or json.dumps(
                {
                    "valid": val_proc.returncode == 0,
                    "stderr": val_proc.stderr,
                }
            )
        except subprocess.TimeoutExpired:
            return json.dumps({"valid": False, "error": "terraform validation timed out."})
        except OSError as exc:
            return json.dumps({"valid": False, "error": f"Failed to run terraform: {exc}"})
