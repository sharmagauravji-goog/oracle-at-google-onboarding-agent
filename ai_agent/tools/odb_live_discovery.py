"""Live Google Cloud Oracle Database API (`oracledatabase.googleapis.com`) & VPC Subnet Discovery Tools (Guardrail 4).

Enables the AI Agent to query the customer's live Google Cloud project for:
- Currently supported ODB@GCP regions and `gcp_oracle_zone` identifiers
- Available hardware shapes (`dbSystemShapes`: Exadata X9M/X11M, Exascale, BaseDB VM shapes)
- Supported Oracle Grid Infrastructure (`giVersions`) and Autonomous DB versions (`autonomousDbVersions`)
- Live GCP VPC subnet CIDRs (`gcloud compute networks subnets list`) to prevent CIDR collisions with existing subnets
- GCP API enablement status (`oracledatabase.googleapis.com`, `aiplatform.googleapis.com`, etc.)
"""

from __future__ import annotations

import ipaddress
import json
import re
import shutil
import subprocess
from typing import Any

import httpx

_PROJECT_ID_PATTERN = re.compile(r"^[a-z][a-z0-9\-]{4,28}[a-z0-9]$")
_REGION_PATTERN = re.compile(r"^[a-z]+-[a-z]+[0-9]+$")
_VPC_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9\-]{0,61}[a-z0-9]$")

FALLBACK_REGIONS_AND_ZONES: dict[str, list[str]] = {
    "us-east4": ["us-east4-b-r1", "us-east4-c-r1"],
    "us-west3": ["us-west3-a-r1", "us-west3-b-r1"],
    "us-central1": ["us-central1-a-r1"],
    "europe-west2": ["europe-west2-a-r1", "europe-west2-b-r1"],
    "europe-west3": ["europe-west3-a-r1", "europe-west3-b-r1"],
    "asia-northeast1": ["asia-northeast1-a-r1", "asia-northeast1-b-r1"],
    "australia-southeast1": ["australia-southeast1-a-r1"],
}

FALLBACK_CAPABILITIES: dict[str, Any] = {
    "db_system_shapes": [
        {"shape": "Exadata.X11M", "family": "EXADATA_DEDICATED", "min_node_count": 2, "min_storage_count": 3},
        {"shape": "Exadata.X9M", "family": "EXADATA_DEDICATED", "min_node_count": 2, "min_storage_count": 3},
        {"shape": "Exadata.Exascale", "family": "EXASCALE", "min_node_count": 2, "storage_attributes": ["SMART_STORAGE", "BLOCK_STORAGE"]},
        {"shape": "VM.Standard.E4.Flex", "family": "BASE_DB", "compute_model": "ECPU", "max_nodes": 2},
        {"shape": "VM.Standard3.Flex", "family": "BASE_DB", "compute_model": "OCPU", "max_nodes": 2},
    ],
    "gi_versions": ["23.0.0.0", "19.0.0.0"],
    "autonomous_db_versions": ["23ai", "19c"],
    "autonomous_db_workloads": ["OLTP", "DW", "APEX", "AJD"],
}


def _get_gcloud_access_token() -> str | None:
    """Safely retrieves a short-lived OAuth2 access token from `gcloud auth print-access-token`."""
    gcloud_bin = shutil.which("gcloud")
    if not gcloud_bin:
        return None
    try:
        proc = subprocess.run(
            [gcloud_bin, "auth", "print-access-token", "--quiet"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return None


def discover_live_odb_regions_and_zones(project_id: str) -> str:
    """Queries the live Google Cloud Oracle Database API for available ODB@GCP regions and `gcp_oracle_zone` values.

    Args:
        project_id: The customer's Google Cloud Project ID (e.g. `my-odb-project-01`).

    Returns:
        JSON string containing live regions and Oracle zones discovered via `oracledatabase.googleapis.com`
        (or the reference catalog if live credentials/API are not yet active).
    """
    cleaned_project = project_id.strip()
    if not _PROJECT_ID_PATTERN.match(cleaned_project):
        return json.dumps(
            {
                "error": f"Invalid GCP project_id '{cleaned_project}'.",
                "reference_regions_and_zones": FALLBACK_REGIONS_AND_ZONES,
            },
            indent=2,
        )

    token = _get_gcloud_access_token()
    if not token:
        return json.dumps(
            {
                "source": "reference_catalog (no active gcloud access token)",
                "project_id": cleaned_project,
                "regions_and_zones": FALLBACK_REGIONS_AND_ZONES,
            },
            indent=2,
        )

    url = f"https://oracledatabase.googleapis.com/v1/projects/{cleaned_project}/locations"
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Goog-User-Project": cleaned_project,
    }
    with httpx.Client(timeout=12.0) as client:
        try:
            resp = client.get(url, headers=headers)
            if resp.status_code == 200:
                payload = resp.json()
                locations = payload.get("locations", [])
                discovered: dict[str, Any] = {}
                for loc in locations:
                    loc_id = loc.get("locationId")
                    metadata = loc.get("metadata", {})
                    zones = metadata.get("gcpOracleZones", [])
                    if loc_id:
                        discovered[loc_id] = zones
                return json.dumps(
                    {
                        "source": "live_oracledatabase_googleapis_com",
                        "project_id": cleaned_project,
                        "discovered_locations": discovered or FALLBACK_REGIONS_AND_ZONES,
                    },
                    indent=2,
                )
            return json.dumps(
                {
                    "source": f"reference_catalog (API returned HTTP {resp.status_code})",
                    "api_note": "Ensure oracledatabase.googleapis.com is enabled in the project.",
                    "project_id": cleaned_project,
                    "regions_and_zones": FALLBACK_REGIONS_AND_ZONES,
                },
                indent=2,
            )
        except Exception as exc:
            return json.dumps(
                {
                    "source": f"reference_catalog (network error: {exc})",
                    "project_id": cleaned_project,
                    "regions_and_zones": FALLBACK_REGIONS_AND_ZONES,
                },
                indent=2,
            )


def discover_live_odb_shapes_and_versions(project_id: str, region: str = "us-east4") -> str:
    """Queries `oracledatabase.googleapis.com` for live DB system shapes, GI versions, and Autonomous DB versions in a region.

    Args:
        project_id: The customer's Google Cloud Project ID.
        region: Target Google Cloud region (e.g. `us-east4`, `europe-west2`).

    Returns:
        JSON string containing live shapes (`dbSystemShapes`), Grid Infrastructure (`giVersions`),
        and Autonomous Database versions (`autonomousDbVersions`).
    """
    cleaned_project = project_id.strip()
    cleaned_region = region.strip().lower()
    if not _PROJECT_ID_PATTERN.match(cleaned_project):
        return json.dumps({"error": f"Invalid GCP project_id '{cleaned_project}'."})
    if not _REGION_PATTERN.match(cleaned_region):
        return json.dumps({"error": f"Invalid GCP region '{cleaned_region}'."})

    token = _get_gcloud_access_token()
    if not token:
        return json.dumps(
            {
                "source": "reference_catalog (no active gcloud access token)",
                "region": cleaned_region,
                "capabilities": FALLBACK_CAPABILITIES,
            },
            indent=2,
        )

    base_url = f"https://oracledatabase.googleapis.com/v1/projects/{cleaned_project}/locations/{cleaned_region}"
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Goog-User-Project": cleaned_project,
    }
    live_data: dict[str, Any] = {}
    endpoints = {
        "dbSystemShapes": "dbSystemShapes",
        "giVersions": "giVersions",
        "autonomousDbVersions": "autonomousDbVersions",
    }

    with httpx.Client(timeout=12.0) as client:
        for key, path_suffix in endpoints.items():
            try:
                resp = client.get(f"{base_url}/{path_suffix}", headers=headers)
                if resp.status_code == 200:
                    live_data[key] = resp.json().get(key, [])
            except Exception:
                continue

    if live_data:
        return json.dumps(
            {
                "source": "live_oracledatabase_googleapis_com",
                "project_id": cleaned_project,
                "region": cleaned_region,
                "live_capabilities": live_data,
            },
            indent=2,
        )

    return json.dumps(
        {
            "source": "reference_catalog (live API unavailable or not enabled in project)",
            "project_id": cleaned_project,
            "region": cleaned_region,
            "capabilities": FALLBACK_CAPABILITIES,
        },
        indent=2,
    )


def check_live_vpc_subnet_overlaps(
    project_id: str,
    client_subnet_cidr: str,
    backup_subnet_cidr: str = "",
    vpc_name: str = "",
) -> str:
    """Queries live GCP VPC subnets in `project_id` and verifies that proposed ODB CIDRs do not collide with existing subnets.

    Args:
        project_id: Google Cloud project ID hosting the VPC (or Shared VPC host project).
        client_subnet_cidr: Proposed ODB Client Subnet CIDR (e.g. `10.20.1.0/24`).
        backup_subnet_cidr: Optional proposed ODB Backup Subnet CIDR (e.g. `10.20.2.0/24`).
        vpc_name: Optional VPC network name to filter subnets.

    Returns:
        JSON string reporting all discovered existing GCP subnets and any CIDR collisions.
    """
    cleaned_project = project_id.strip()
    if not _PROJECT_ID_PATTERN.match(cleaned_project):
        return json.dumps({"error": f"Invalid GCP project_id '{cleaned_project}'."})

    cleaned_vpc = vpc_name.strip()
    if cleaned_vpc and not _VPC_NAME_PATTERN.match(cleaned_vpc):
        return json.dumps({"error": f"Invalid vpc_name '{cleaned_vpc}'."})

    proposed_nets: dict[str, ipaddress.IPv4Network] = {}
    for label, raw_cidr in (
        ("client_subnet_cidr", client_subnet_cidr),
        ("backup_subnet_cidr", backup_subnet_cidr),
    ):
        if raw_cidr and raw_cidr.strip():
            try:
                proposed_nets[label] = ipaddress.IPv4Network(raw_cidr.strip(), strict=False)
            except ValueError as exc:
                return json.dumps({"error": f"Invalid {label} '{raw_cidr}': {exc}"})

    gcloud_bin = shutil.which("gcloud")
    if not gcloud_bin:
        return json.dumps(
            {
                "live_vpc_checked": False,
                "reason": "gcloud CLI not installed",
            },
            indent=2,
        )

    cmd = [
        gcloud_bin,
        "compute",
        "networks",
        "subnets",
        "list",
        f"--project={cleaned_project}",
        "--format=json",
        "--quiet",
    ]
    if cleaned_vpc:
        cmd.append(f"--network={cleaned_vpc}")

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if proc.returncode != 0:
            return json.dumps(
                {
                    "live_vpc_checked": False,
                    "project_id": cleaned_project,
                    "detail": (proc.stderr or "").strip()[:400],
                },
                indent=2,
            )

        subnets_data = json.loads(proc.stdout or "[]")
        existing_subnets: list[dict[str, str]] = []
        collisions: list[dict[str, str]] = []

        for item in subnets_data:
            s_name = item.get("name", "unknown")
            s_cidr = item.get("ipCidrRange", "")
            s_region = item.get("region", "").split("/")[-1]
            s_net = item.get("network", "").split("/")[-1]
            if not s_cidr:
                continue
            existing_subnets.append(
                {
                    "name": s_name,
                    "cidr": s_cidr,
                    "region": s_region,
                    "network": s_net,
                }
            )
            try:
                existing_ip_net = ipaddress.IPv4Network(s_cidr, strict=False)
                for prop_label, prop_net in proposed_nets.items():
                    if prop_net.overlaps(existing_ip_net):
                        collisions.append(
                            {
                                "proposed_odb_subnet": f"{prop_label} ({prop_net})",
                                "colliding_gcp_subnet": s_name,
                                "colliding_gcp_cidr": s_cidr,
                                "region": s_region,
                                "network": s_net,
                            }
                        )
            except ValueError:
                continue

        return json.dumps(
            {
                "live_vpc_checked": True,
                "project_id": cleaned_project,
                "collision_free": len(collisions) == 0,
                "collisions": collisions,
                "existing_gcp_subnets_count": len(existing_subnets),
                "existing_gcp_subnets_sample": existing_subnets[:20],
            },
            indent=2,
        )
    except Exception as exc:
        return json.dumps({"live_vpc_checked": False, "error": str(exc)}, indent=2)


def check_customer_gcp_readiness(project_id: str) -> str:
    """Checks whether required Google Cloud APIs (Oracle Database, Compute, Service Networking, Vertex AI) are enabled.

    Args:
        project_id: Target Google Cloud project ID.

    Returns:
        JSON string summarizing enabled vs. missing APIs and remediation `gcloud` commands.
    """
    cleaned_project = project_id.strip()
    if not _PROJECT_ID_PATTERN.match(cleaned_project):
        return json.dumps({"error": f"Invalid GCP project_id '{cleaned_project}'."})

    required_apis = [
        "oracledatabase.googleapis.com",
        "compute.googleapis.com",
        "servicenetworking.googleapis.com",
        "cloudresourcemanager.googleapis.com",
        "aiplatform.googleapis.com",
    ]
    gcloud_bin = shutil.which("gcloud")
    if not gcloud_bin:
        return json.dumps(
            {
                "project_id": cleaned_project,
                "gcloud_installed": False,
                "required_apis": required_apis,
                "remediation": (
                    f"gcloud services enable {' '.join(required_apis)} --project={cleaned_project}"
                ),
            },
            indent=2,
        )

    try:
        proc = subprocess.run(
            [
                gcloud_bin,
                "services",
                "list",
                "--enabled",
                f"--project={cleaned_project}",
                "--format=value(config.name)",
                "--quiet",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if proc.returncode != 0:
            return json.dumps(
                {
                    "project_id": cleaned_project,
                    "status": "unable_to_query",
                    "detail": (proc.stderr or "").strip()[:500],
                    "required_apis": required_apis,
                },
                indent=2,
            )
        enabled_set = set((proc.stdout or "").splitlines())
        missing = [api for api in required_apis if api not in enabled_set]
        return json.dumps(
            {
                "project_id": cleaned_project,
                "status": "ready" if not missing else "missing_apis",
                "enabled_required_apis": [api for api in required_apis if api in enabled_set],
                "missing_apis": missing,
                "remediation_command": (
                    f"gcloud services enable {' '.join(missing)} --project={cleaned_project}"
                    if missing
                    else None
                ),
            },
            indent=2,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return json.dumps({"project_id": cleaned_project, "error": str(exc)})


def verify_live_onboarding_and_iam_readiness(
    project_id: str,
    workload_type: str = "adb",
    principal_email: str = "",
) -> str:
    """Performs a live pre-deployment readiness check for ODB@GCP APIs, IAM permissions, and Marketplace/OCI link status.

    Args:
        project_id: Target Google Cloud project ID.
        workload_type: Target Oracle workload (`adb`, `exadata_dedicated`, `exascale`, `basedb`).
        principal_email: Optional IAM user/service-account email to inspect (defaults to active `gcloud` account).

    Returns:
        JSON string detailing API status, Marketplace/OCI link status, missing ODB IAM roles, and exact `gcloud` fix commands.
    """
    cleaned_project = (project_id or "").strip()
    if not _PROJECT_ID_PATTERN.match(cleaned_project):
        return json.dumps({"valid": False, "error": f"Invalid GCP project_id '{cleaned_project}'."}, indent=2)

    workload = (workload_type or "adb").strip().lower()
    api_report = json.loads(check_customer_gcp_readiness(cleaned_project))

    gcloud_bin = shutil.which("gcloud")
    active_account = principal_email.strip()
    if not active_account and gcloud_bin:
        try:
            acct_proc = subprocess.run(
                [gcloud_bin, "config", "get-value", "account", "--quiet"],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
            if acct_proc.returncode == 0:
                active_account = (acct_proc.stdout or "").strip()
        except (OSError, subprocess.SubprocessError):
            active_account = ""

    required_odb_roles = [
        "roles/oracledatabase.admin",
        "roles/oracledatabase.networkAdmin",
        "roles/compute.networkAdmin",
    ]
    if workload == "adb":
        required_odb_roles.append("roles/oracledatabase.autonomousDatabaseAdmin")
    elif workload in {"exadata_dedicated", "exascale"}:
        required_odb_roles.append("roles/oracledatabase.exadataAdmin")

    granted_roles: list[str] = []
    missing_odb_roles: list[str] = []
    iam_checked = False

    if gcloud_bin and active_account:
        try:
            iam_proc = subprocess.run(
                [
                    gcloud_bin,
                    "projects",
                    "get-iam-policy",
                    cleaned_project,
                    "--format=json",
                    "--quiet",
                ],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            if iam_proc.returncode == 0 and iam_proc.stdout.strip():
                iam_checked = True
                policy = json.loads(iam_proc.stdout)
                for binding in policy.get("bindings", []):
                    role = binding.get("role", "")
                    members = binding.get("members", [])
                    if any(active_account in m for m in members):
                        granted_roles.append(role)
        except Exception:
            iam_checked = False

    has_odb_admin = "roles/oracledatabase.admin" in granted_roles
    for req_role in required_odb_roles:
        if req_role not in granted_roles and not (
            has_odb_admin and req_role.startswith("roles/oracledatabase.")
        ):
            missing_odb_roles.append(req_role)

    member_prefix = (
        f"serviceAccount:{active_account}"
        if active_account.endswith(".gserviceaccount.com")
        else f"user:{active_account or '<YOUR_EMAIL>'}"
    )
    iam_remediation_commands = [
        f"gcloud projects add-iam-policy-binding {cleaned_project} --member='{member_prefix}' --role='{role}'"
        for role in missing_odb_roles
    ]

    return json.dumps(
        {
            "valid": True,
            "project_id": cleaned_project,
            "workload_type": workload,
            "active_principal": active_account or "unknown",
            "api_readiness": api_report,
            "iam_readiness": {
                "iam_policy_inspected": iam_checked,
                "granted_roles_for_principal": granted_roles,
                "missing_odb_roles": missing_odb_roles,
                "ready_for_odb_deployment": len(missing_odb_roles) == 0 and api_report.get("status") == "ready",
                "remediation_commands": iam_remediation_commands,
            },
            "marketplace_and_oci_linking_check": {
                "console_verification_url": (
                    f"https://console.cloud.google.com/oracledatabase/locations?project={cleaned_project}"
                ),
                "marketplace_orders_url": (
                    f"https://console.cloud.google.com/marketplace/orders?project={cleaned_project}"
                ),
                "note": (
                    "Verify in Google Cloud Console -> Marketplace Orders that your Oracle Database@Google Cloud "
                    "Private Offer (or PAYG subscription) is ACTIVE and linked to your OCI tenancy."
                ),
            },
        },
        indent=2,
    )

