"""Guardrail 5: Day-2 Maintenance Workspace Inspector & Destructive Change Guard.

Helps customers safely maintain and evolve existing Oracle Database@Google Cloud
Terraform environments by:
1. Reading existing `.tf` and `.tfvars` files in a workspace directory
2. Detecting any proposed modifications to `ForceNew` (immutable) attributes that
   would trigger a destructive `-/+ destroy and recreate` on live databases
3. Detecting missing `deletion_protection = true` on stateful resources
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

# Attributes in `hashicorp/google` (`google_oracle_database_*`) marked `ForceNew: true`
# Changing any of these on an existing resource forces Terraform to DESTROY and RECREATE it!
IMMUTABLE_FORCE_NEW_ATTRIBUTES: dict[str, list[str]] = {
    "google_oracle_database_odb_network": [
        "odb_network_id",
        "network",
        "location",
        "gcp_oracle_zone",
        "project",
    ],
    "google_oracle_database_odb_subnet": [
        "odb_subnet_id",
        "odbnetwork",
        "cidr_range",
        "purpose",
        "location",
        "project",
    ],
    "google_oracle_database_autonomous_database": [
        "autonomous_database_id",
        "database",
        "odb_network",
        "odb_subnet",
        "cidr",
        "location",
        "project",
    ],
    "google_oracle_database_cloud_exadata_infrastructure": [
        "cloud_exadata_infrastructure_id",
        "gcp_oracle_zone",
        "location",
        "project",
        "shape",
    ],
    "google_oracle_database_cloud_vm_cluster": [
        "cloud_vm_cluster_id",
        "exadata_infrastructure",
        "odb_network",
        "odb_subnet",
        "backup_odb_subnet",
        "gi_version",
        "hostname_prefix",
        "location",
        "project",
    ],
    "google_oracle_database_exascale_db_storage_vault": [
        "exascale_db_storage_vault_id",
        "gcp_oracle_zone",
        "location",
        "project",
    ],
    "google_oracle_database_exadb_vm_cluster": [
        "exadb_vm_cluster_id",
        "gcp_oracle_zone",
        "odb_network",
        "odb_subnet",
        "backup_odb_subnet",
        "exascale_db_storage_vault",
        "grid_image_id",
        "shape_attribute",
        "hostname_prefix",
        "location",
        "project",
    ],
    "google_oracle_database_db_system": [
        "db_system_id",
        "gcp_oracle_zone",
        "odb_network",
        "odb_subnet",
        "shape",
        "database_edition",
        "storage_management",
        "hostname_prefix",
        "location",
        "project",
    ],
}

SAFE_IN_PLACE_DAY2_ATTRIBUTES: dict[str, list[str]] = {
    "google_oracle_database_autonomous_database": [
        "compute_count (scale ECPUs in-place)",
        "data_storage_size_tb (scale storage in-place)",
        "is_auto_scaling_enabled",
        "license_type",
        "deletion_protection",
        "labels",
    ],
    "google_oracle_database_cloud_vm_cluster": [
        "cpu_core_count (scale OCPU/ECPU cores in-place)",
        "data_storage_size_tb",
        "db_node_storage_size_gb",
        "memory_size_gb",
        "ssh_public_keys",
        "deletion_protection",
        "labels",
    ],
    "google_oracle_database_exadb_vm_cluster": [
        "node_count (add/remove nodes in-place)",
        "enabled_ecpu_count_per_node",
        "additional_ecpu_count_per_node",
        "ssh_public_keys",
        "deletion_protection",
        "labels",
    ],
}

_RESOURCE_BLOCK_REGEX = re.compile(
    r'resource\s+"(google_oracle_database_[a-z0-9_]+)"\s+"([a-zA-Z0-9_\-]+)"\s*\{(.*?)\n\}',
    re.DOTALL,
)
_KV_ATTR_REGEX = re.compile(r"^\s*([a-z_]+)\s*=\s*(.+?)\s*$", re.MULTILINE)


def _extract_resources_from_hcl(hcl_text: str) -> dict[str, dict[str, Any]]:
    """Parses resource blocks and top/nested key=value pairs from HCL content."""
    extracted: dict[str, dict[str, Any]] = {}
    for match in _RESOURCE_BLOCK_REGEX.finditer(hcl_text):
        r_type, r_name, body = match.group(1), match.group(2), match.group(3)
        addr = f"{r_type}.{r_name}"
        attrs: dict[str, str] = {}
        for kv in _KV_ATTR_REGEX.finditer(body):
            key, raw_val = kv.group(1).strip(), kv.group(2).strip()
            if not raw_val.startswith("{"):
                attrs[key] = raw_val
        extracted[addr] = {
            "resource_type": r_type,
            "resource_name": r_name,
            "attributes": attrs,
            "deletion_protection": attrs.get("deletion_protection", "not_set"),
        }
    return extracted


def inspect_existing_terraform_workspace(workspace_dir: str = "./output") -> str:
    """Inspects an existing Terraform directory to inventory ODB@GCP resources for Day-2 maintenance.

    Args:
        workspace_dir: Path to the directory containing existing `.tf` files.

    Returns:
        JSON string listing discovered `.tf` files, ODB resources, current attributes,
        `deletion_protection` posture, and safe in-place Day-2 scaling options.
    """
    target_dir = Path(workspace_dir).resolve()
    if not target_dir.exists() or not target_dir.is_dir():
        return json.dumps(
            {
                "exists": False,
                "workspace_dir": str(target_dir),
                "message": "Directory does not exist yet. Use generate_golden_odb_terraform for Day-1 creation.",
            },
            indent=2,
        )

    tf_files: list[str] = []
    resources: dict[str, dict[str, Any]] = {}
    missing_deletion_protection: list[str] = []

    stateful_types_with_del_prot = {
        "google_oracle_database_odb_network",
        "google_oracle_database_autonomous_database",
        "google_oracle_database_cloud_exadata_infrastructure",
        "google_oracle_database_cloud_vm_cluster",
        "google_oracle_database_exadb_vm_cluster",
        "google_oracle_database_db_system",
    }

    for tf_path in sorted(target_dir.rglob("*.tf")):
        if ".terraform" in tf_path.parts:
            continue
        if not str(tf_path.resolve()).startswith(str(target_dir) + os.sep):
            continue
        rel = str(tf_path.relative_to(target_dir))
        tf_files.append(rel)
        content = tf_path.read_text(encoding="utf-8", errors="replace")
        found = _extract_resources_from_hcl(content)
        for addr, meta in found.items():
            meta["file"] = rel
            resources[addr] = meta
            if (
                meta.get("resource_type") in stateful_types_with_del_prot
                and meta.get("deletion_protection") != "true"
            ):
                missing_deletion_protection.append(addr)

    return json.dumps(
        {
            "exists": True,
            "workspace_dir": str(target_dir),
            "tf_files": tf_files,
            "discovered_odb_resources": resources,
            "security_posture": {
                "resources_missing_deletion_protection": missing_deletion_protection,
                "recommendation": (
                    "All stateful ODB resources have deletion_protection = true."
                    if not missing_deletion_protection
                    else f"Enable deletion_protection = true on: {missing_deletion_protection}"
                ),
            },
            "safe_in_place_day2_operations": SAFE_IN_PLACE_DAY2_ATTRIBUTES,
            "immutable_force_new_attributes": IMMUTABLE_FORCE_NEW_ATTRIBUTES,
        },
        indent=2,
    )


def analyze_day2_terraform_diff(
    existing_hcl: str,
    proposed_hcl: str,
) -> str:
    """Checks a proposed Day-2 HCL modification against existing HCL for destructive resource replacements (`ForceNew`).

    Always call this tool before modifying an existing customer `.tf` file during Day-2 maintenance!

    Args:
        existing_hcl: The current `.tf` file contents before modification.
        proposed_hcl: The proposed updated `.tf` file contents.

    Returns:
        JSON string reporting whether the Day-2 change is safe (in-place update) or
        triggers a `CRITICAL_DESTRUCTIVE_REPLACE_WARNING` (`-/+ destroy and recreate`).
    """
    before_res = _extract_resources_from_hcl(existing_hcl)
    after_res = _extract_resources_from_hcl(proposed_hcl)

    destructive_warnings: list[dict[str, Any]] = []
    removed_resources: list[str] = []
    in_place_updates: list[dict[str, Any]] = []

    for addr, old_meta in before_res.items():
        if addr not in after_res:
            removed_resources.append(addr)
            destructive_warnings.append(
                {
                    "resource": addr,
                    "severity": "CRITICAL",
                    "action": "DESTROY (resource block removed from HCL)",
                    "reason": f"Resource {addr} existed in the workspace but is missing from proposed HCL.",
                }
            )
            continue

        new_meta = after_res[addr]
        r_type = old_meta["resource_type"]
        force_new_keys = set(IMMUTABLE_FORCE_NEW_ATTRIBUTES.get(r_type, []))

        old_attrs = old_meta["attributes"]
        new_attrs = new_meta["attributes"]

        for key in set(old_attrs.keys()) | set(new_attrs.keys()):
            old_v = old_attrs.get(key)
            new_v = new_attrs.get(key)
            if old_v != new_v:
                if key in force_new_keys:
                    destructive_warnings.append(
                        {
                            "resource": addr,
                            "attribute": key,
                            "old_value": old_v,
                            "new_value": new_v,
                            "severity": "CRITICAL_FORCE_NEW_REPLACE",
                            "action": "-/+ destroy and recreate",
                            "reason": (
                                f"Attribute '{key}' on {r_type} is immutable (ForceNew) in hashicorp/google. "
                                f"Changing it from {old_v} to {new_v} will DESTROY and recreate the database/network!"
                            ),
                        }
                    )
                else:
                    in_place_updates.append(
                        {
                            "resource": addr,
                            "attribute": key,
                            "old_value": old_v,
                            "new_value": new_v,
                            "action": "~ update in-place (safe)",
                        }
                    )

    return json.dumps(
        {
            "safe_day2_change": len(destructive_warnings) == 0,
            "destructive_replacement_warnings": destructive_warnings,
            "removed_resources": removed_resources,
            "safe_in_place_updates": in_place_updates,
        },
        indent=2,
    )
