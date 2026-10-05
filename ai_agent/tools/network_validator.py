"""Deterministic Network CIDR Validation & Sandboxed Terraform Exporter Tools.

Provides mathematical CIDR validation (`/28` minimum prefix, pairwise overlap checks)
and a path-traversal-safe Terraform bundle writer that the LLM agent calls before
delivering infrastructure code to the customer.
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
from pathlib import Path
from typing import Any

_SAFE_RELATIVE_PATH_PATTERN = re.compile(r"^[a-zA-Z0-9_\-/]+\.(tf|tfvars|md|yml|yaml|sh)$")


def validate_odb_network_cidrs(
    vpc_cidr: str,
    client_subnet_cidr: str,
    backup_subnet_cidr: str = "",
) -> str:
    """Validates ODB@GCP network CIDRs for minimum `/28` prefix length and pairwise overlap.

    Args:
        vpc_cidr: Customer VPC CIDR range (e.g. `10.10.0.0/16`).
        client_subnet_cidr: ODB Client Subnet CIDR range (e.g. `10.20.1.0/24`, minimum `/28`).
        backup_subnet_cidr: Optional ODB Backup Subnet CIDR range (required for Exadata/Exascale, minimum `/28`).

    Returns:
        JSON string indicating whether the CIDRs are valid and non-overlapping, with host capacity details.
    """
    errors: list[str] = []
    parsed: dict[str, ipaddress.IPv4Network] = {}

    for label, raw in (
        ("vpc_cidr", vpc_cidr),
        ("client_subnet_cidr", client_subnet_cidr),
        ("backup_subnet_cidr", backup_subnet_cidr),
    ):
        cleaned = (raw or "").strip()
        if not cleaned:
            if label != "backup_subnet_cidr":
                errors.append(f"{label} is required.")
            continue
        try:
            net = ipaddress.IPv4Network(cleaned, strict=False)
            parsed[label] = net
            if label in ("client_subnet_cidr", "backup_subnet_cidr") and net.prefixlen > 28:
                errors.append(
                    f"{label} ({net}) has prefix /{net.prefixlen}, which is smaller than the ODB@GCP minimum /28 (16 IPs)."
                )
        except ValueError as exc:
            errors.append(f"Invalid IPv4 CIDR for {label} ('{cleaned}'): {exc}")

    # Pairwise overlap check
    keys = list(parsed.keys())
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            k1, k2 = keys[i], keys[j]
            n1, n2 = parsed[k1], parsed[k2]
            if n1.overlaps(n2):
                errors.append(f"CIDR overlap detected between {k1} ({n1}) and {k2} ({n2}).")

    summary: dict[str, Any] = {
        "valid": len(errors) == 0,
        "errors": errors,
        "networks": {
            k: {
                "normalized_cidr": str(v),
                "prefix_length": v.prefixlen,
                "total_addresses": v.num_addresses,
            }
            for k, v in parsed.items()
        },
    }
    return json.dumps(summary, indent=2)


def save_generated_terraform_bundle(
    files_json: str,
    bundle_name: str = "odb-generated-infra",
    base_output_dir: str = "./output",
) -> str:
    """Safely writes generated Terraform and CI/CD files into an isolated subdirectory under `base_output_dir`.

    Enforces strict path traversal protection (`resolved.startswith(sandbox_dir + os.sep)`)
    and blocks hardcoded passwords in `.tfvars` files.

    Args:
        files_json: JSON object mapping relative file paths (e.g. `main.tf`, `modules/adb/main.tf`)
            to their file contents.
        bundle_name: Subdirectory name inside `base_output_dir` (alphanumeric, hyphens, underscores).
        base_output_dir: Base output directory (default `./output`).

    Returns:
        JSON string listing all written file paths or validation errors.
    """
    try:
        files_map = json.loads(files_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"saved": False, "error": f"Invalid JSON in files_json: {exc}"})

    if not isinstance(files_map, dict) or not files_map:
        return json.dumps({"saved": False, "error": "files_json must be a non-empty JSON object."})

    safe_bundle = re.sub(r"[^a-zA-Z0-9_\-]", "-", os.path.basename(bundle_name.strip())) or "odb-bundle"
    sandbox_root = Path(base_output_dir).resolve()
    bundle_dir = (sandbox_root / safe_bundle).resolve()

    if not str(bundle_dir).startswith(str(sandbox_root) + os.sep):
        return json.dumps({"saved": False, "error": "Bundle directory escaped output sandbox."})

    bundle_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    skipped: list[str] = []

    for rel_path, content in files_map.items():
        cleaned_rel = str(rel_path).strip().lstrip("/")
        if ".." in cleaned_rel or not _SAFE_RELATIVE_PATH_PATTERN.match(cleaned_rel):
            skipped.append(f"{rel_path} (rejected by path/extension allow-list)")
            continue

        # Normalize each segment via os.path.basename to prevent traversal
        parts = [os.path.basename(p) for p in cleaned_rel.split("/") if p and p != "."]
        if not parts or len(parts) > 4:
            skipped.append(f"{rel_path} (invalid path depth)")
            continue

        target_file = bundle_dir.joinpath(*parts).resolve()
        if not str(target_file).startswith(str(bundle_dir) + os.sep):
            skipped.append(f"{rel_path} (escaped bundle boundary)")
            continue

        content_str = str(content)
        if target_file.name.endswith(".tfvars") and re.search(
            r'(?i)(admin_password|db_password)\s*=\s*"[^"]+"', content_str
        ):
            skipped.append(
                f"{rel_path} (blocked: sensitive passwords must be passed via TF_VAR_* env vars, not .tfvars)"
            )
            continue

        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text(content_str, encoding="utf-8")
        written.append(str(target_file.relative_to(bundle_dir)))

    return json.dumps(
        {
            "saved": len(written) > 0,
            "output_directory": str(bundle_dir),
            "written_files": written,
            "skipped_files": skipped,
        },
        indent=2,
    )
