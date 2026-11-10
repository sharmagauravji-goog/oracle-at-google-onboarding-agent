"""Part 2 Interactive Agent & Workflow Capabilities (Items 4 to 7).

Provides deterministic, workspace-sandboxed engines that work identically across:
- Streamlit Web Studio (`odb-onboarding-agent studio` / `--cloud-shell`)
- Google Cloud Shell & Terminal CLI (`wizard`, `tracker`, `simulate-day2`, `ask`, `chat`)
- IDE MCP Clients (Antigravity, Cursor, Claude Code, VS Code, Gemini CLI)
- Conversational LLM Orchestrator (`ODBArchitectAgent`)

Capabilities included:
- Item 4 (`recommend_odb_architecture_wizard`): Guided Interactive Architecture Discovery & Sizing Wizard.
- Item 5 (`manage_onboarding_progress_tracker`): Stateful 6-Phase Onboarding Progress Tracker with Digital Twin overlays.
- Item 6 (`simulate_day2_scaling_what_if`): Interactive Day-2 What-If Scaling & `ForceNew` Blast-Radius Simulator.
- Item 7 (`build_guardrail_telemetry_summary` & `audit_workspace_and_hcl_guardrails`): Live 5-Layer Guardrail Telemetry & Scorecard.
"""

from __future__ import annotations

import datetime
import json
import os
from typing import Any

from ai_agent.tools.day2_maintenance import (
    IMMUTABLE_FORCE_NEW_ATTRIBUTES,
    SAFE_IN_PLACE_DAY2_ATTRIBUTES,
    analyze_day2_terraform_diff,
    inspect_existing_terraform_workspace,
)
from ai_agent.tools.golden_templates import generate_golden_odb_terraform
from ai_agent.tools.interactive_diagram import (
    build_day2_blast_radius_overlays,
    build_interactive_diagram_spec,
    build_readiness_node_overlays,
)
from ai_agent.tools.network_validator import (
    resolve_safe_workspace_path,
    save_generated_terraform_bundle,
    validate_odb_network_cidrs,
)
from ai_agent.tools.odb_live_discovery import (
    check_live_vpc_subnet_overlaps,
    verify_live_onboarding_and_iam_readiness,
)
from ai_agent.tools.onboarding_knowledge import (
    check_onboarding_response_for_hallucinations,
    evaluate_customer_onboarding_readiness,
)
from ai_agent.tools.terraform_registry import (
    check_hcl_for_provider_hallucinations,
    validate_terraform_hcl,
)

SUPPORTED_WORKLOAD_PROFILES = (
    "autonomous_ai_lakehouse",
    "oltp_mission_critical",
    "consolidated_erp_rac",
    "elastic_rac_cloud_native",
    "single_instance_dev_test",
)

SUPPORTED_HA_DR_TIERS = (
    "regional_ha",
    "multi_zone_or_cross_region_dr",
    "standard_single_zone",
)

SUPPORTED_NETWORK_GOVERNANCE_MODES = (
    "standalone_vpc",
    "shared_vpc",
    "hub_and_spoke",
)


# ============================================================================
# ITEM 4: Guided Interactive Architecture Discovery & Sizing Wizard
# ============================================================================


def recommend_odb_architecture_wizard(
    project_id: str = "my-odb-project-01",
    region: str = "us-east4",
    gcp_oracle_zone: str = "us-east4-b-r1",
    workload_profile: str = "autonomous_ai_lakehouse",
    ha_dr_tier: str = "regional_ha",
    cpu_cores_needed: int = 8,
    storage_tb_needed: int = 2,
    network_governance: str = "standalone_vpc",
    encryption_compliance: str = "google_managed",
    procurement_preference: str = "private_offer",
    separation_of_duties_mode: str = "full_stack",
    vpc_cidr: str = "10.10.0.0/16",
    client_subnet_cidr: str = "10.20.1.0/24",
    backup_subnet_cidr: str = "10.20.2.0/24",
    generate_artifacts: bool = False,
    bundle_name: str = "",
    base_output_dir: str = "./output",
) -> str:
    """Evaluates customer workload, HA/DR, sizing, networking, and compliance requirements to recommend a grounded ODB@GCP blueprint.

    Can optionally generate and validate the recommended Golden Terraform bundle and interactive topology spec in one call.

    Args:
        project_id: Target Google Cloud project ID.
        region: Target Google Cloud region (e.g., `us-east4`, `us-west3`, `europe-west2`).
        gcp_oracle_zone: Target colocated Oracle zone (e.g., `us-east4-b-r1`).
        workload_profile: One of `autonomous_ai_lakehouse`, `oltp_mission_critical`, `consolidated_erp_rac`,
            `elastic_rac_cloud_native`, or `single_instance_dev_test` (also accepts direct workload types `adb`, `exadata_dedicated`, `exascale`, `basedb`).
        ha_dr_tier: One of `regional_ha` (99.99%), `multi_zone_or_cross_region_dr` (99.995%+ Data Guard), or `standard_single_zone`.
        cpu_cores_needed: Estimated ECPU / OCPU compute cores required.
        storage_tb_needed: Estimated storage capacity in TB.
        network_governance: One of `standalone_vpc`, `shared_vpc`, or `hub_and_spoke`.
        encryption_compliance: One of `google_managed`, `gcp_cmek`, or `oci_vault`.
        procurement_preference: `private_offer` or `payg`.
        separation_of_duties_mode: `full_stack` (single bundle) or `enterprise_layered` (`network_only`, `infra_only`, `database_only`).
        vpc_cidr: Customer VPC CIDR block.
        client_subnet_cidr: ODB `CLIENT_SUBNET` CIDR block (minimum `/28`).
        backup_subnet_cidr: ODB `BACKUP_SUBNET` CIDR block (minimum `/28`).
        generate_artifacts: When True, writes the recommended Golden Terraform bundle into `base_output_dir`.
        bundle_name: Optional custom output subdirectory name under `base_output_dir`.
        base_output_dir: Workspace-contained output directory (default `./output`).

    Returns:
        JSON string containing the recommended workload type, Terraform resource types, hardware shape,
        sizing rationale, networking & diagram mapping, Separation-of-Duties plan, interactive topology spec,
        and generated Terraform bundle summary if `generate_artifacts=True`.
    """
    profile_raw = (workload_profile or "autonomous_ai_lakehouse").strip().lower()
    ha_raw = (ha_dr_tier or "regional_ha").strip().lower()
    net_raw = (network_governance or "standalone_vpc").strip().lower()
    enc_raw = (encryption_compliance or "google_managed").strip().lower()
    proc_raw = (procurement_preference or "private_offer").strip().lower()
    sod_raw = (separation_of_duties_mode or "full_stack").strip().lower()

    cores = max(2, int(cpu_cores_needed or 4))
    storage_tb = max(1, int(storage_tb_needed or 1))

    # Map workload profile + scale to deterministic ODB@GCP workload_type
    if profile_raw in {"adb", "autonomous_ai_lakehouse"}:
        recommended_workload = "adb"
        recommended_tf_resources = [
            "google_oracle_database_odb_network",
            "google_oracle_database_odb_subnet",
            "google_oracle_database_autonomous_database",
        ]
        recommended_shape = "Autonomous Database Serverless (23ai ECPU)"
        recommended_compute = max(4, cores)
        recommended_storage_tb = max(1, storage_tb)
        requires_backup_subnet = False
        rationale = [
            "Autonomous Database Serverless (`google_oracle_database_autonomous_database`) provides fully managed Oracle 23ai AI Vector Search, auto-scaling ECPUs, and zero infrastructure patching.",
            "Only a single `CLIENT_SUBNET` (minimum `/28`) is required inside `google_oracle_database_odb_network`; RMAN/Autonomous backups stream directly to managed storage without requiring a `BACKUP_SUBNET`.",
        ]
    elif profile_raw in {"exadata_dedicated", "consolidated_erp_rac"} or (
        profile_raw == "oltp_mission_critical" and (cores >= 32 or storage_tb >= 16)
    ):
        recommended_workload = "exadata_dedicated"
        recommended_tf_resources = [
            "google_oracle_database_odb_network",
            "google_oracle_database_odb_subnet (CLIENT_SUBNET)",
            "google_oracle_database_odb_subnet (BACKUP_SUBNET)",
            "google_oracle_database_cloud_exadata_infrastructure",
            "google_oracle_database_cloud_vm_cluster",
        ]
        recommended_shape = "Exadata.X9M / Exadata.X11M Dedicated Infrastructure"
        recommended_compute = max(16, cores)
        recommended_storage_tb = max(2, storage_tb)
        requires_backup_subnet = True
        rationale = [
            "Exadata Database Service on Dedicated Infrastructure (`google_oracle_database_cloud_exadata_infrastructure` + `google_oracle_database_cloud_vm_cluster`) provides bare-metal RDMA over Converged Ethernet (RoCE), Smart Scan storage offload, and full root/GI control for large ERP and mission-critical RAC consolidation.",
            "Requires both `CLIENT_SUBNET` (minimum `/28`, `/24` recommended) and `BACKUP_SUBNET` (minimum `/28`) in `google_oracle_database_odb_network`.",
        ]
    elif profile_raw in {"exascale", "elastic_rac_cloud_native", "oltp_mission_critical"}:
        recommended_workload = "exascale"
        recommended_tf_resources = [
            "google_oracle_database_odb_network",
            "google_oracle_database_odb_subnet (CLIENT_SUBNET)",
            "google_oracle_database_odb_subnet (BACKUP_SUBNET)",
            "google_oracle_database_exascale_db_storage_vault",
            "google_oracle_database_exadb_vm_cluster",
        ]
        recommended_shape = "Exadata Database Service on Exascale (ECPU + Exascale Vault)"
        recommended_compute = max(8, cores)
        recommended_storage_tb = max(1, storage_tb)
        requires_backup_subnet = True
        rationale = [
            "Exadata Database Service on Exascale (`google_oracle_database_exascale_db_storage_vault` + `google_oracle_database_exadb_vm_cluster`) delivers full Exadata Smart Scan & Oracle RAC high availability without dedicated physical storage servers, allowing elastic ECPU and storage scaling at a lower entry footprint.",
            "Requires both `CLIENT_SUBNET` and `BACKUP_SUBNET` (minimum `/28` each) in `google_oracle_database_odb_network`.",
        ]
    else:
        recommended_workload = "basedb"
        recommended_tf_resources = [
            "google_oracle_database_odb_network",
            "google_oracle_database_odb_subnet (CLIENT_SUBNET)",
            "google_oracle_database_db_system",
        ]
        recommended_shape = "VM.Standard.x86 (Oracle Base Database Service)"
        recommended_compute = max(4, cores)
        recommended_storage_tb = max(1, storage_tb)
        requires_backup_subnet = False
        rationale = [
            "Oracle Base Database Service (`google_oracle_database_db_system`) is ideal for single-instance Oracle 19c/23ai workloads, departmental databases, and predictable x86 VM licensing.",
            "Uses a single `CLIENT_SUBNET` (minimum `/28`) on `google_oracle_database_odb_network`.",
        ]

    # Map HA/DR & Networking to recommended diagram & DR posture
    if ha_raw == "multi_zone_or_cross_region_dr" or net_raw in {"hub_and_spoke", "hub_and_spoke_ncc"}:
        recommended_diagram_type = "networking_hub_and_spoke_ha_dr"
        normalized_net = "hub_and_spoke"
        dr_strategy = (
            "Cross-Zone / Cross-Region Active Data Guard (or Autonomous Data Guard) over Network Connectivity Center (NCC) "
            "with paired ODB Networks and automated RMAN / Autonomous backup policies."
        )
    elif net_raw == "shared_vpc":
        recommended_diagram_type = "networking_shared_vpc"
        normalized_net = "shared_vpc"
        dr_strategy = (
            "Regional High Availability within the colocated `gcp_oracle_zone` attached to the enterprise Shared VPC Host Project, "
            "paired with automated 30-day RMAN / Autonomous backups."
        )
    else:
        recommended_diagram_type = "networking_standalone_vpc"
        normalized_net = "standalone_vpc"
        dr_strategy = (
            "Regional High Availability in a Standalone VPC peered via Google's managed partner interconnect to `google_oracle_database_odb_network`, "
            "paired with automated daily backups."
        )

    cidr_check = json.loads(
        validate_odb_network_cidrs(
            vpc_cidr=vpc_cidr,
            client_subnet_cidr=client_subnet_cidr,
            backup_subnet_cidr=backup_subnet_cidr if requires_backup_subnet else "",
        )
    )

    sod_layers = (
        ["network_only", "infra_only", "database_only"]
        if sod_raw in {"enterprise_layered", "layered", "separation_of_duties"}
        and recommended_workload in {"exadata_dedicated", "exascale"}
        else (
            ["network_only", "database_only"]
            if sod_raw in {"enterprise_layered", "layered", "separation_of_duties"}
            else ["full_stack"]
        )
    )
    primary_layer = "full_stack" if sod_layers == ["full_stack"] else sod_layers[0]

    readiness_plan = json.loads(
        evaluate_customer_onboarding_readiness(
            project_id=project_id,
            procurement_model="payg" if proc_raw == "payg" else "private_offer",
            networking_topology=normalized_net,
            workload_type=recommended_workload,
            encryption_mode="cmek" if "cmek" in enc_raw or "vault" in enc_raw else "google_managed",
            team_role="full_stack",
        )
    )

    interactive_spec = build_interactive_diagram_spec(
        diagram_type=recommended_diagram_type,
        project_id=project_id,
        region=region,
        gcp_oracle_zone=gcp_oracle_zone,
        vpc_cidr=vpc_cidr,
        client_subnet_cidr=client_subnet_cidr,
        backup_subnet_cidr=backup_subnet_cidr,
        workload_type=recommended_workload,
        deployment_layer=primary_layer,
        compute_count=recommended_compute,
        storage_size_tb=recommended_storage_tb,
    )

    generated_bundle_summary: dict[str, Any] | None = None
    if generate_artifacts and cidr_check.get("valid"):
        target_bundle = (
            bundle_name.strip()
            if bundle_name and bundle_name.strip()
            else f"wizard-{recommended_workload}-{normalized_net}".replace("_", "-")
        )
        raw_tf = json.loads(
            generate_golden_odb_terraform(
                project_id=project_id,
                region=region,
                gcp_oracle_zone=gcp_oracle_zone,
                workload_type=recommended_workload,
                vpc_cidr=vpc_cidr,
                client_subnet_cidr=client_subnet_cidr,
                backup_subnet_cidr=backup_subnet_cidr,
                compute_count=recommended_compute,
                storage_size_tb=recommended_storage_tb,
                deployment_layer="full_stack",
            )
        )
        if raw_tf.get("valid"):
            files_json = json.dumps(raw_tf["files"])
            val_res = json.loads(validate_terraform_hcl(files_json, fast_mode=True))
            save_res = json.loads(
                save_generated_terraform_bundle(
                    files_json=files_json,
                    bundle_name=target_bundle,
                    base_output_dir=base_output_dir,
                )
            )
            generated_bundle_summary = {
                "saved": bool(save_res.get("saved")),
                "output_directory": save_res.get("output_directory"),
                "written_files": save_res.get("written_files", []),
                "validation": val_res,
                "files": raw_tf.get("files", {}),
                "error": save_res.get("error", ""),
            }

    return json.dumps(
        {
            "valid": bool(cidr_check.get("valid", True)),
            "wizard_summary": {
                "project_id": project_id,
                "region": region,
                "gcp_oracle_zone": gcp_oracle_zone,
                "workload_profile": profile_raw,
                "recommended_workload_type": recommended_workload,
                "recommended_shape": recommended_shape,
                "recommended_compute_count": recommended_compute,
                "recommended_storage_size_tb": recommended_storage_tb,
                "requires_backup_subnet": requires_backup_subnet,
                "recommended_networking_topology": normalized_net,
                "recommended_diagram_type": recommended_diagram_type,
                "ha_dr_tier": ha_raw,
                "dr_strategy": dr_strategy,
                "encryption_compliance": enc_raw,
                "procurement_preference": proc_raw,
                "separation_of_duties_layers": sod_layers,
                "terraform_resources": recommended_tf_resources,
                "architectural_rationale": rationale,
            },
            "cidr_validation": cidr_check,
            "onboarding_readiness_plan": {
                "readiness_score_pct": readiness_plan.get("readiness_score_pct"),
                "status": readiness_plan.get("status"),
                "blocking_items": readiness_plan.get("blocking_items", []),
            },
            "interactive_spec": interactive_spec,
            "generated_bundle": generated_bundle_summary,
        },
        indent=2,
    )


# ============================================================================
# ITEM 5: Stateful 6-Phase Onboarding Progress Tracker
# ============================================================================

DEFAULT_TRACKER_PHASES: list[dict[str, Any]] = [
    {
        "phase_id": "phase_1",
        "phase_number": 1,
        "title": "Phase 1: GCP Prerequisites, Billing & Least-Privilege IAM",
        "team_owner": "procurement",
        "diagram_node_ids": ["phase1_iam", "iam_gate", "host_proj", "svc_proj"],
        "status": "pending",
        "verification_command": (
            "gcloud services enable oracledatabase.googleapis.com servicenetworking.googleapis.com "
            "cloudresourcemanager.googleapis.com compute.googleapis.com --project=<PROJECT_ID>"
        ),
        "deliverables": [
            "Enable `oracledatabase.googleapis.com` and `servicenetworking.googleapis.com` APIs",
            "Assign least-privilege ODB IAM roles across Network (`odbNetworkAdmin`), Infrastructure (`cloudExadataInfrastructureAdmin`), and Database (`autonomousDatabaseAdmin` / `cloudVmClusterAdmin`) teams",
        ],
        "notes": "",
    },
    {
        "phase_id": "phase_2",
        "phase_number": 2,
        "title": "Phase 2: Google Cloud Marketplace Order (Private Offer / PAYG)",
        "team_owner": "procurement",
        "diagram_node_ids": ["phase2_mkt"],
        "status": "pending",
        "verification_command": (
            "# Verify active Oracle Database@Google Cloud order in Google Cloud Console -> Marketplace -> Your Orders"
        ),
        "deliverables": [
            "Accept Oracle Database@Google Cloud Private Offer or subscribe to Pay-As-You-Go (PAYG) in Google Cloud Marketplace",
            "Confirm Billing Account Admin (`roles/billing.admin`) approval on the linked Cloud Billing account",
        ],
        "notes": "",
    },
    {
        "phase_id": "phase_3",
        "phase_number": 3,
        "title": "Phase 3: OCI Account Linking & My Oracle Support (MOS / CSI)",
        "team_owner": "procurement",
        "diagram_node_ids": ["phase3_oci", "phase3_mos"],
        "status": "pending",
        "verification_command": (
            "gcloud oracle-database cloud-exadata-infrastructures list --location=<REGION> --project=<PROJECT_ID>"
        ),
        "deliverables": [
            "Complete the guided OCI Account Creation or Existing Tenancy Linking flow from the Google Cloud Console partner portal",
            "Register your Customer Support Identifier (CSI) in My Oracle Support (`https://support.oracle.com`) and approve Support Admin access",
        ],
        "notes": "",
    },
    {
        "phase_id": "phase_4",
        "phase_number": 4,
        "title": "Phase 4: ODB Network & Subnets (CLIENT_SUBNET & BACKUP_SUBNET min /28)",
        "team_owner": "network",
        "diagram_node_ids": [
            "phase4_net",
            "odb_net",
            "client_sub",
            "backup_sub",
            "partner_psa",
            "hub_vpc",
            "spoke_prod",
        ],
        "status": "pending",
        "verification_command": (
            "odb-onboarding-agent generate-golden --project-id <PROJECT_ID> --layer network_only"
        ),
        "deliverables": [
            "Validate non-overlapping RFC1918 CIDRs with minimum `/28` prefix length for `CLIENT_SUBNET` and `BACKUP_SUBNET`",
            "Provision `google_oracle_database_odb_network` and `google_oracle_database_odb_subnet` inside the target `gcp_oracle_zone`",
        ],
        "notes": "",
    },
    {
        "phase_id": "phase_5",
        "phase_number": 5,
        "title": "Phase 5: Workload Provisioning, CMEK Encryption & Separation of Duties",
        "team_owner": "database",
        "diagram_node_ids": ["phase5_db", "workload_db", "exadata_infra", "cmek_kms", "sa_agent"],
        "status": "pending",
        "verification_command": (
            "odb-onboarding-agent generate-golden --project-id <PROJECT_ID> --workload adb --layer full_stack"
        ),
        "deliverables": [
            "Generate and validate schema-grounded `hashicorp/google` (`google_oracle_database_*`) Terraform with `deletion_protection = true`",
            "If using CMEK, grant `roles/cloudkms.cryptoKeyEncrypterDecrypter` to `service-<PROJECT_NUMBER>@gcp-sa-oracledatabase.iam.gserviceaccount.com` before DB creation",
        ],
        "notes": "",
    },
    {
        "phase_id": "phase_6",
        "phase_number": 6,
        "title": "Phase 6: Day-2 Observability, RMAN/Autonomous Backups & ForceNew Guard",
        "team_owner": "database",
        "diagram_node_ids": [
            "phase6_day2",
            "dr_standby",
            "cloud_mon",
            "cloud_log",
            "oci_ops",
            "oci_awr",
            "auto_bkp",
            "gcs_rman",
        ],
        "status": "pending",
        "verification_command": "odb-onboarding-agent inspect-day2 --workspace-dir ./output",
        "deliverables": [
            "Enable Cloud Monitoring (`oracledatabase.googleapis.com/*`) and Oracle Operations Insights (`operations_insights_state = \"ENABLED\"`)",
            "Verify `deletion_protection = true` and run `analyze_day2_terraform_diff` before any Day-2 Terraform change",
        ],
        "notes": "",
    },
]


def _build_tracker_digital_twin_overlays(phases: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    """Maps the 6-phase tracker state directly onto interactive topology node IDs (`verified`, `warning`, `blocker`)."""
    overlays: dict[str, dict[str, str]] = {}
    for ph in phases:
        st_val = str(ph.get("status", "pending")).lower()
        title = str(ph.get("title", ph.get("phase_id", "")))
        cmd = str(ph.get("verification_command", ""))
        note = str(ph.get("notes", "")).strip()
        if st_val == "completed":
            badge = "verified"
            label = f"PHASE {ph.get('phase_number')} COMPLETE"
            detail = f"{title} is marked completed in the Onboarding Progress Tracker." + (
                f" Note: {note}" if note else ""
            )
            rem_cmd = ""
        elif st_val == "blocked":
            badge = "blocker"
            label = f"PHASE {ph.get('phase_number')} BLOCKED"
            detail = f"{title} is currently blocked." + (f" Blocker: {note}" if note else "")
            rem_cmd = cmd
        elif st_val == "in_progress":
            badge = "warning"
            label = f"PHASE {ph.get('phase_number')} IN PROGRESS"
            detail = f"{title} is actively in progress." + (f" Note: {note}" if note else "")
            rem_cmd = cmd
        else:
            badge = "warning"
            label = f"PHASE {ph.get('phase_number')} PENDING"
            detail = f"{title} is pending completion."
            rem_cmd = cmd

        for nid in ph.get("diagram_node_ids", []):
            overlays[str(nid)] = {
                "status": badge,
                "badge_label": label,
                "detail": detail,
                "remediation_command": rem_cmd,
            }
    return overlays


def manage_onboarding_progress_tracker(
    action: str = "status",
    project_id: str = "my-odb-project-01",
    region: str = "us-east4",
    phase_id: str = "",
    status: str = "",
    notes: str = "",
    tracker_file: str = "./output/onboarding_progress.json",
) -> str:
    """Manages the stateful 6-Phase Oracle@Google Onboarding Progress Tracker inside the workspace.

    Enforces strict workspace path containment (`resolve_safe_workspace_path`) and emits live
    `node_overlays` so the Interactive Digital Twin Topology Canvas reflects saved tracker state.

    Args:
        action: One of `'status'` (read current state), `'update_phase'` (update a phase status/note),
            `'auto_verify'` (probe live GCP readiness, subnet overlaps, and workspace `.tf` files to auto-advance phases),
            or `'reset'` (reset all 6 phases to pending).
        project_id: Target GCP project ID.
        region: Target GCP region.
        phase_id: Phase identifier for `'update_phase'` (`'phase_1'` .. `'phase_6'` or `'1'` .. `'6'`).
        status: New phase status for `'update_phase'`: `'completed'`, `'in_progress'`, `'blocked'`, or `'pending'`.
        notes: Optional engineering note or blocker reason to store on the phase.
        tracker_file: Workspace-relative path for persisting tracker JSON (default `./output/onboarding_progress.json`).

    Returns:
        JSON string containing overall completion percentage, phase-by-phase breakdown, next recommended action,
        and `digital_twin_node_overlays` for interactive topology rendering.
    """
    act = (action or "status").strip().lower()
    if act not in {"status", "update_phase", "auto_verify", "reset"}:
        return json.dumps(
            {
                "valid": False,
                "error": f"Unsupported action '{act}'. Must be one of: status, update_phase, auto_verify, reset.",
            },
            indent=2,
        )

    try:
        safe_path = resolve_safe_workspace_path(tracker_file)
    except ValueError as exc:
        return json.dumps({"valid": False, "error": str(exc)}, indent=2)

    # Load existing state or initialize default 6-phase tracker
    state: dict[str, Any] = {}
    if safe_path.exists() and safe_path.is_file() and act != "reset":
        try:
            loaded = json.loads(safe_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and isinstance(loaded.get("phases"), list):
                state = loaded
        except Exception:
            state = {}

    if not state or act == "reset":
        state = {
            "project_id": project_id,
            "region": region,
            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "phases": [dict(p) for p in DEFAULT_TRACKER_PHASES],
        }
    else:
        if project_id and project_id != "my-odb-project-01":
            state["project_id"] = project_id
        if region:
            state["region"] = region

    phases: list[dict[str, Any]] = state["phases"]
    for ph in phases:
        ph["verification_command"] = (
            str(ph.get("verification_command", ""))
            .replace("<PROJECT_ID>", str(state.get("project_id") or project_id))
            .replace("<REGION>", str(state.get("region") or region))
        )

    if act == "update_phase":
        raw_pid = (phase_id or "").strip().lower()
        if raw_pid.isdigit():
            raw_pid = f"phase_{raw_pid}"
        norm_status = (status or "completed").strip().lower()
        if norm_status not in {"completed", "in_progress", "blocked", "pending"}:
            return json.dumps(
                {
                    "valid": False,
                    "error": f"Invalid phase status '{norm_status}'. Use: completed, in_progress, blocked, or pending.",
                },
                indent=2,
            )
        matched = False
        for ph in phases:
            if ph.get("phase_id") == raw_pid:
                ph["status"] = norm_status
                if notes is not None and notes != "":
                    ph["notes"] = notes.strip()
                matched = True
                break
        if not matched:
            return json.dumps(
                {
                    "valid": False,
                    "error": f"Unknown phase_id '{phase_id}'. Valid phase IDs: phase_1 through phase_6.",
                },
                indent=2,
            )

    auto_verify_details: dict[str, Any] = {}
    if act == "auto_verify":
        target_proj = str(state.get("project_id") or project_id or "my-odb-project-01")
        live_iam = json.loads(
            verify_live_onboarding_and_iam_readiness(
                project_id=target_proj,
                workload_type="adb",
                team_role="full_stack",
            )
        )
        sub_check = json.loads(
            check_live_vpc_subnet_overlaps(
                project_id=target_proj,
                client_subnet_cidr="10.20.1.0/24",
                backup_subnet_cidr="10.20.2.0/24",
            )
        )
        ws_parent = str(safe_path.parent)
        ws_inspect = json.loads(inspect_existing_terraform_workspace(ws_parent))
        discovered_res = ws_inspect.get("discovered_odb_resources", {}) or {}
        missing_del_prot = (
            ws_inspect.get("security_posture", {}).get("resources_missing_deletion_protection", [])
            or []
        )

        # Phase 1 evaluation from live readiness probe
        if live_iam.get("overall_status") == "READY":
            phases[0]["status"] = "completed"
            phases[0]["notes"] = "Auto-verified: ODB & Service Networking APIs and IAM bindings ready."
        elif live_iam.get("live_project_inspected"):
            phases[0]["status"] = "in_progress"
            phases[0]["notes"] = f"Live probe status: {live_iam.get('overall_status')}."

        # Phase 4 evaluation from workspace ODB network / subnet resources + CIDR collision check
        has_odb_net_tf = any(
            meta.get("resource_type") == "google_oracle_database_odb_network"
            for meta in discovered_res.values()
        )
        has_odb_sub_tf = any(
            meta.get("resource_type") == "google_oracle_database_odb_subnet"
            for meta in discovered_res.values()
        )
        if not sub_check.get("collision_free", True):
            phases[3]["status"] = "blocked"
            phases[3]["notes"] = "Subnet overlap detected against existing GCP VPC subnets."
        elif has_odb_net_tf and has_odb_sub_tf:
            phases[3]["status"] = "completed"
            phases[3]["notes"] = (
                "Auto-verified: google_oracle_database_odb_network and google_oracle_database_odb_subnet "
                "bundles generated and CIDR collision check passed."
            )

        # Phase 5 evaluation from workload `.tf` resources in workspace
        workload_rtypes = {
            "google_oracle_database_autonomous_database",
            "google_oracle_database_cloud_vm_cluster",
            "google_oracle_database_exadb_vm_cluster",
            "google_oracle_database_db_system",
        }
        has_workload_tf = any(
            meta.get("resource_type") in workload_rtypes for meta in discovered_res.values()
        )
        if has_workload_tf:
            phases[4]["status"] = "completed"
            phases[4]["notes"] = (
                f"Auto-verified: {len(discovered_res)} ODB Terraform resource(s) discovered in workspace."
            )

        # Phase 6 evaluation from deletion_protection posture
        if discovered_res and not missing_del_prot:
            phases[5]["status"] = "completed"
            phases[5]["notes"] = (
                "Auto-verified: All stateful ODB Terraform resources enforce deletion_protection = true."
            )
        elif missing_del_prot:
            phases[5]["status"] = "blocked"
            phases[5]["notes"] = f"Resources missing deletion_protection = true: {missing_del_prot}"

        auto_verify_details = {
            "live_readiness_status": live_iam.get("overall_status"),
            "subnet_collision_free": sub_check.get("collision_free", True),
            "discovered_terraform_resources_count": len(discovered_res),
            "resources_missing_deletion_protection": missing_del_prot,
        }

    state["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    safe_path.parent.mkdir(parents=True, exist_ok=True)
    if str(safe_path.resolve()).startswith(str(safe_path.parent.resolve()) + os.sep):
        safe_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    completed_count = sum(1 for p in phases if p.get("status") == "completed")
    in_progress_count = sum(1 for p in phases if p.get("status") == "in_progress")
    blocked_count = sum(1 for p in phases if p.get("status") == "blocked")
    completion_pct = int(round((completed_count / len(phases)) * 100)) if phases else 0

    next_phase = next(
        (p for p in phases if p.get("status") in {"blocked", "in_progress", "pending"}),
        None,
    )
    node_overlays = _build_tracker_digital_twin_overlays(phases)

    return json.dumps(
        {
            "valid": True,
            "action": act,
            "tracker_file": str(safe_path),
            "project_id": state.get("project_id"),
            "region": state.get("region"),
            "updated_at": state.get("updated_at"),
            "completion_pct": completion_pct,
            "completed_phases": completed_count,
            "in_progress_phases": in_progress_count,
            "blocked_phases": blocked_count,
            "total_phases": len(phases),
            "next_recommended_phase": (
                {
                    "phase_id": next_phase["phase_id"],
                    "title": next_phase["title"],
                    "status": next_phase["status"],
                    "team_owner": next_phase["team_owner"],
                    "verification_command": next_phase["verification_command"],
                }
                if next_phase
                else None
            ),
            "phases": phases,
            "auto_verify_summary": auto_verify_details if auto_verify_details else None,
            "digital_twin_node_overlays": node_overlays,
        },
        indent=2,
    )


# ============================================================================
# ITEM 6: Interactive Day-2 What-If Scaling & ForceNew Simulator
# ============================================================================


def _render_simulated_workload_hcl(
    *,
    workload_type: str,
    project_id: str,
    region: str,
    gcp_oracle_zone: str,
    odb_network: str,
    client_subnet_cidr: str,
    db_name: str,
    compute_count: int,
    storage_size_tb: int,
    auto_scaling: bool,
    deletion_protection: bool,
    exadata_shape: str = "Exadata.X9M",
) -> str:
    """Renders deterministic Day-1 vs. Day-2 HCL for `analyze_day2_terraform_diff` simulation."""
    wkl = (workload_type or "adb").strip().lower()
    del_str = "true" if deletion_protection else "false"
    auto_str = "true" if auto_scaling else "false"

    network_blocks = (
        f'resource "google_oracle_database_odb_network" "main" {{\n'
        f'  odb_network_id      = "{odb_network}"\n'
        f'  project             = "{project_id}"\n'
        f'  location            = "{region}"\n'
        f'  gcp_oracle_zone     = "{gcp_oracle_zone}"\n'
        f'  network             = "projects/{project_id}/global/networks/odb-vpc"\n'
        f'  deletion_protection = {del_str}\n'
        f'}}\n\n'
        f'resource "google_oracle_database_odb_subnet" "client" {{\n'
        f'  odb_subnet_id = "{odb_network}-client"\n'
        f'  project       = "{project_id}"\n'
        f'  location      = "{region}"\n'
        f'  odbnetwork    = google_oracle_database_odb_network.main.id\n'
        f'  cidr_range    = "{client_subnet_cidr}"\n'
        f'  purpose       = "CLIENT_SUBNET"\n'
        f'}}\n\n'
    )

    if wkl == "exadata_dedicated":
        workload_block = (
            f'resource "google_oracle_database_cloud_exadata_infrastructure" "infra" {{\n'
            f'  cloud_exadata_infrastructure_id = "odb-prod-exadata"\n'
            f'  project                         = "{project_id}"\n'
            f'  location                        = "{region}"\n'
            f'  gcp_oracle_zone                 = "{gcp_oracle_zone}"\n'
            f'  shape                           = "{exadata_shape}"\n'
            f'  deletion_protection             = {del_str}\n'
            f'  properties {{\n'
            f'    compute_count = 2\n'
            f'    storage_count = 3\n'
            f'  }}\n'
            f'}}\n\n'
            f'resource "google_oracle_database_cloud_vm_cluster" "vm_cluster" {{\n'
            f'  cloud_vm_cluster_id    = "odb-prod-vmcluster"\n'
            f'  project                = "{project_id}"\n'
            f'  location               = "{region}"\n'
            f'  exadata_infrastructure = google_oracle_database_cloud_exadata_infrastructure.infra.id\n'
            f'  odb_network            = "{odb_network}"\n'
            f'  odb_subnet             = google_oracle_database_odb_subnet.client.id\n'
            f'  hostname_prefix        = "{db_name.lower()[:8]}"\n'
            f'  deletion_protection    = {del_str}\n'
            f'  properties {{\n'
            f'    cpu_core_count       = {compute_count}\n'
            f'    data_storage_size_tb = {storage_size_tb}\n'
            f'  }}\n'
            f'}}\n'
        )
    elif wkl == "exascale":
        workload_block = (
            f'resource "google_oracle_database_exadb_vm_cluster" "exascale_cluster" {{\n'
            f'  exadb_vm_cluster_id       = "odb-prod-exascale"\n'
            f'  project                   = "{project_id}"\n'
            f'  location                  = "{region}"\n'
            f'  gcp_oracle_zone           = "{gcp_oracle_zone}"\n'
            f'  odb_network               = "{odb_network}"\n'
            f'  odb_subnet                = google_oracle_database_odb_subnet.client.id\n'
            f'  hostname_prefix           = "{db_name.lower()[:8]}"\n'
            f'  deletion_protection       = {del_str}\n'
            f'  properties {{\n'
            f'    node_count                  = 2\n'
            f'    enabled_ecpu_count_per_node = {compute_count}\n'
            f'  }}\n'
            f'}}\n'
        )
    elif wkl == "basedb":
        workload_block = (
            f'resource "google_oracle_database_db_system" "basedb" {{\n'
            f'  db_system_id        = "odb-prod-basedb"\n'
            f'  project             = "{project_id}"\n'
            f'  location            = "{region}"\n'
            f'  gcp_oracle_zone     = "{gcp_oracle_zone}"\n'
            f'  odb_network         = "{odb_network}"\n'
            f'  odb_subnet          = google_oracle_database_odb_subnet.client.id\n'
            f'  shape               = "{exadata_shape}"\n'
            f'  hostname_prefix     = "{db_name.lower()[:8]}"\n'
            f'  deletion_protection = {del_str}\n'
            f'  properties {{\n'
            f'    cpu_core_count       = {compute_count}\n'
            f'    data_storage_size_gb = {storage_size_tb * 1024}\n'
            f'  }}\n'
            f'}}\n'
        )
    else:
        workload_block = (
            f'resource "google_oracle_database_autonomous_database" "adb" {{\n'
            f'  autonomous_database_id = "odb-prod-adb"\n'
            f'  project                = "{project_id}"\n'
            f'  location               = "{region}"\n'
            f'  database               = "{db_name}"\n'
            f'  odb_network            = "{odb_network}"\n'
            f'  odb_subnet             = google_oracle_database_odb_subnet.client.id\n'
            f'  deletion_protection    = {del_str}\n'
            f'  properties {{\n'
            f'    compute_count           = {compute_count}\n'
            f'    data_storage_size_tb    = {storage_size_tb}\n'
            f'    is_auto_scaling_enabled = {auto_str}\n'
            f'  }}\n'
            f'}}\n'
        )

    return network_blocks + workload_block


def simulate_day2_scaling_what_if(
    workload_type: str = "adb",
    project_id: str = "my-odb-project-01",
    region: str = "us-east4",
    current_gcp_oracle_zone: str = "us-east4-b-r1",
    proposed_gcp_oracle_zone: str = "us-east4-b-r1",
    current_odb_network: str = "odb-prod-net",
    proposed_odb_network: str = "odb-prod-net",
    current_client_subnet_cidr: str = "10.20.1.0/24",
    proposed_client_subnet_cidr: str = "10.20.1.0/24",
    current_db_name: str = "ODBPROD1",
    proposed_db_name: str = "ODBPROD1",
    current_compute_count: int = 4,
    proposed_compute_count: int = 8,
    current_storage_size_tb: int = 1,
    proposed_storage_size_tb: int = 2,
    current_auto_scaling: bool = True,
    proposed_auto_scaling: bool = True,
    current_deletion_protection: bool = True,
    proposed_deletion_protection: bool = True,
    apply_to_bundle_dir: str = "",
) -> str:
    """Simulates a Day-2 parameter change on an ODB@GCP workload to evaluate online scaling vs. `ForceNew` replacement hazards.

    Generates `before_hcl` and `after_hcl`, executes `analyze_day2_terraform_diff`, calculates downtime and
    blast-radius impact, and produces a ready-to-render Day-2 Blast-Radius Interactive Topology Spec.
    If `apply_to_bundle_dir` is specified, writes `day2_simulated_update.tf` inside the workspace ONLY when
    `safe_day2_change` is True and `proposed_deletion_protection` is True.

    Returns:
        JSON string containing `safe_day2_change`, `downtime_impact`, `before_hcl`, `after_hcl`,
        `diff_analysis`, `deletion_protection_warning`, `interactive_spec`, and `saved_file` (if requested and safe).
    """
    wkl = (workload_type or "adb").strip().lower()
    if wkl not in {"adb", "exadata_dedicated", "exascale", "basedb"}:
        wkl = "adb"

    default_shape = "Exadata.X9M" if wkl == "exadata_dedicated" else "VM.Standard.E4.Flex"

    before_hcl = _render_simulated_workload_hcl(
        workload_type=wkl,
        project_id=project_id,
        region=region,
        gcp_oracle_zone=current_gcp_oracle_zone,
        odb_network=current_odb_network,
        client_subnet_cidr=current_client_subnet_cidr,
        db_name=current_db_name,
        compute_count=int(current_compute_count),
        storage_size_tb=int(current_storage_size_tb),
        auto_scaling=bool(current_auto_scaling),
        deletion_protection=bool(current_deletion_protection),
        exadata_shape=default_shape,
    )
    after_hcl = _render_simulated_workload_hcl(
        workload_type=wkl,
        project_id=project_id,
        region=region,
        gcp_oracle_zone=proposed_gcp_oracle_zone,
        odb_network=proposed_odb_network,
        client_subnet_cidr=proposed_client_subnet_cidr,
        db_name=proposed_db_name,
        compute_count=int(proposed_compute_count),
        storage_size_tb=int(proposed_storage_size_tb),
        auto_scaling=bool(proposed_auto_scaling),
        deletion_protection=bool(proposed_deletion_protection),
        exadata_shape=default_shape,
    )

    diff_raw = analyze_day2_terraform_diff(before_hcl, after_hcl)
    diff_report = json.loads(diff_raw)

    del_prot_warning = ""
    if current_deletion_protection and not proposed_deletion_protection:
        del_prot_warning = (
            "WARNING: Disabling `deletion_protection = false` exposes live production ODB@GCP resources "
            "to accidental `terraform destroy`. Keep `deletion_protection = true` on all stateful resources."
        )

    is_safe = bool(diff_report.get("safe_day2_change", True))
    destructive_list = diff_report.get("destructive_replacement_warnings", []) or []
    safe_updates_list = diff_report.get("safe_in_place_updates", []) or []

    if not is_safe:
        downtime_impact = (
            "CRITICAL (`-/+ destroy and recreate`): One or more immutable `ForceNew` attributes were modified. "
            "Applying this change in-place would DESTROY the live database/network. "
            "Use a blue/green ODB Network or Oracle Data Guard switchover instead."
        )
    elif safe_updates_list:
        downtime_impact = (
            "ZERO-DOWNTIME ONLINE SCALING (`~ update in-place`): All modified attributes support online elastic "
            "modification in `hashicorp/google` without recreating the database or interrupting active sessions."
        )
    else:
        downtime_impact = "NO-OP: No attribute differences between current and proposed configuration."

    node_overlays = build_day2_blast_radius_overlays(diff_raw)
    interactive_spec = build_interactive_diagram_spec(
        diagram_type="networking_standalone_vpc",
        project_id=project_id,
        region=region,
        gcp_oracle_zone=proposed_gcp_oracle_zone,
        client_subnet_cidr=proposed_client_subnet_cidr,
        workload_type=wkl,
        compute_count=int(proposed_compute_count),
        storage_size_tb=int(proposed_storage_size_tb),
        node_overlays=node_overlays,
    )

    saved_file_path: str | None = None
    save_blocked_reason: str | None = None
    if apply_to_bundle_dir and apply_to_bundle_dir.strip():
        if not is_safe:
            save_blocked_reason = (
                "Guardrail 6 Blocked Write: Refusing to write Day-2 HCL containing destructive `ForceNew` replacements."
            )
        elif not proposed_deletion_protection:
            save_blocked_reason = (
                "Guardrail 6 Blocked Write: Refusing to write Day-2 HCL with `deletion_protection = false`."
            )
        else:
            try:
                target_dir = resolve_safe_workspace_path(apply_to_bundle_dir.strip())
                target_dir.mkdir(parents=True, exist_ok=True)
                out_file = (target_dir / "day2_simulated_update.tf").resolve()
                if str(out_file).startswith(str(target_dir) + os.sep):
                    out_file.write_text(after_hcl, encoding="utf-8")
                    saved_file_path = str(out_file)
            except ValueError as exc:
                save_blocked_reason = str(exc)

    return json.dumps(
        {
            "valid": True,
            "workload_type": wkl,
            "safe_day2_change": is_safe,
            "downtime_impact": downtime_impact,
            "deletion_protection_warning": del_prot_warning,
            "delta_summary": {
                "compute_delta": int(proposed_compute_count) - int(current_compute_count),
                "storage_tb_delta": int(proposed_storage_size_tb) - int(current_storage_size_tb),
                "safe_in_place_updates_count": len(safe_updates_list),
                "destructive_forcenew_warnings_count": len(destructive_list),
            },
            "diff_analysis": diff_report,
            "before_hcl": before_hcl,
            "after_hcl": after_hcl,
            "saved_file": saved_file_path,
            "save_blocked_reason": save_blocked_reason,
            "interactive_spec": interactive_spec,
        },
        indent=2,
    )


# ============================================================================
# ITEM 7: Live 5-Layer Guardrail & Tool-Execution Telemetry Scorecard
# ============================================================================

TOOL_TO_GUARDRAIL_LAYER: dict[str, dict[str, str]] = {
    "get_odb_onboarding_and_architecture_guide": {
        "layer_id": "layer_1",
        "layer_name": "Layer 1: Onboarding & Separation-of-Duties Knowledge Base",
    },
    "evaluate_customer_onboarding_readiness": {
        "layer_id": "layer_1",
        "layer_name": "Layer 1: Onboarding & Separation-of-Duties Knowledge Base",
    },
    "fetch_official_odb_documentation": {
        "layer_id": "layer_1",
        "layer_name": "Layer 1: Onboarding & Separation-of-Duties Knowledge Base",
    },
    "manage_onboarding_progress_tracker": {
        "layer_id": "layer_1",
        "layer_name": "Layer 1: Onboarding & Separation-of-Duties Knowledge Base",
    },
    "generate_odb_architecture_diagram": {
        "layer_id": "layer_2",
        "layer_name": "Layer 2: Interactive SVG, Mermaid & ASCII Topology Engine",
    },
    "recommend_odb_architecture_wizard": {
        "layer_id": "layer_2",
        "layer_name": "Layer 2: Interactive SVG, Mermaid & ASCII Topology Engine",
    },
    "generate_golden_odb_terraform": {
        "layer_id": "layer_3",
        "layer_name": "Layer 3: Golden Terraform & Exact Provider Schema Grounding",
    },
    "get_latest_google_provider_version": {
        "layer_id": "layer_3",
        "layer_name": "Layer 3: Golden Terraform & Exact Provider Schema Grounding",
    },
    "list_odb_terraform_resources": {
        "layer_id": "layer_3",
        "layer_name": "Layer 3: Golden Terraform & Exact Provider Schema Grounding",
    },
    "get_odb_resource_documentation": {
        "layer_id": "layer_3",
        "layer_name": "Layer 3: Golden Terraform & Exact Provider Schema Grounding",
    },
    "validate_terraform_hcl": {
        "layer_id": "layer_3",
        "layer_name": "Layer 3: Golden Terraform & Exact Provider Schema Grounding",
    },
    "validate_odb_network_cidrs": {
        "layer_id": "layer_4",
        "layer_name": "Layer 4: Deterministic /28 CIDR, Live GCP IAM & Workspace Sandbox",
    },
    "save_generated_terraform_bundle": {
        "layer_id": "layer_4",
        "layer_name": "Layer 4: Deterministic /28 CIDR, Live GCP IAM & Workspace Sandbox",
    },
    "discover_live_odb_regions_and_zones": {
        "layer_id": "layer_4",
        "layer_name": "Layer 4: Deterministic /28 CIDR, Live GCP IAM & Workspace Sandbox",
    },
    "discover_live_odb_shapes_and_versions": {
        "layer_id": "layer_4",
        "layer_name": "Layer 4: Deterministic /28 CIDR, Live GCP IAM & Workspace Sandbox",
    },
    "check_live_vpc_subnet_overlaps": {
        "layer_id": "layer_4",
        "layer_name": "Layer 4: Deterministic /28 CIDR, Live GCP IAM & Workspace Sandbox",
    },
    "check_customer_gcp_readiness": {
        "layer_id": "layer_4",
        "layer_name": "Layer 4: Deterministic /28 CIDR, Live GCP IAM & Workspace Sandbox",
    },
    "inspect_existing_terraform_workspace": {
        "layer_id": "layer_5",
        "layer_name": "Layer 5: Post-Gen Compiler Auto-Repair & Day-2 ForceNew Guard",
    },
    "analyze_day2_terraform_diff": {
        "layer_id": "layer_5",
        "layer_name": "Layer 5: Post-Gen Compiler Auto-Repair & Day-2 ForceNew Guard",
    },
    "simulate_day2_scaling_what_if": {
        "layer_id": "layer_5",
        "layer_name": "Layer 5: Post-Gen Compiler Auto-Repair & Day-2 ForceNew Guard",
    },
    "post_generation_hcl_guardrail": {
        "layer_id": "layer_5",
        "layer_name": "Layer 5: Post-Gen Compiler Auto-Repair & Day-2 ForceNew Guard",
    },
}


def build_guardrail_telemetry_summary(
    tool_traces: list[dict[str, Any]],
    *,
    guardrail_verified: bool = True,
    auto_repairs_triggered: int = 0,
) -> dict[str, Any]:
    """Maps raw tool execution traces and post-generation checks into a structured 5-Layer Guardrail Scorecard."""
    layers: dict[str, dict[str, Any]] = {
        "layer_1": {
            "layer_id": "layer_1",
            "title": "Layer 1: Onboarding & Separation-of-Duties Knowledge Base",
            "status": "standby",
            "invocations": 0,
            "duration_ms": 0.0,
            "tools_called": [],
        },
        "layer_2": {
            "layer_id": "layer_2",
            "title": "Layer 2: Interactive SVG, Mermaid & ASCII Topology Engine",
            "status": "standby",
            "invocations": 0,
            "duration_ms": 0.0,
            "tools_called": [],
        },
        "layer_3": {
            "layer_id": "layer_3",
            "title": "Layer 3: Golden Terraform & Exact Provider Schema Grounding",
            "status": "standby",
            "invocations": 0,
            "duration_ms": 0.0,
            "tools_called": [],
        },
        "layer_4": {
            "layer_id": "layer_4",
            "title": "Layer 4: Deterministic /28 CIDR, Live GCP IAM & Workspace Sandbox",
            "status": "standby",
            "invocations": 0,
            "duration_ms": 0.0,
            "tools_called": [],
        },
        "layer_5": {
            "layer_id": "layer_5",
            "title": "Layer 5: Post-Gen Compiler Auto-Repair & Day-2 ForceNew Guard",
            "status": "verified" if guardrail_verified else "warning",
            "invocations": 0,
            "duration_ms": 0.0,
            "tools_called": [],
        },
    }

    total_ms = 0.0
    for tr in tool_traces or []:
        tname = str(tr.get("tool_name", ""))
        dur = float(tr.get("duration_ms") or 0.0)
        total_ms += dur
        meta = TOOL_TO_GUARDRAIL_LAYER.get(
            tname,
            {
                "layer_id": "layer_5",
                "layer_name": "Layer 5: Post-Gen Compiler Auto-Repair & Day-2 ForceNew Guard",
            },
        )
        lid = meta["layer_id"]
        entry = layers[lid]
        entry["invocations"] += 1
        entry["duration_ms"] = round(entry["duration_ms"] + dur, 1)
        if tname not in entry["tools_called"]:
            entry["tools_called"].append(tname)
        entry["status"] = "verified"

    if not guardrail_verified:
        layers["layer_5"]["status"] = "warning"

    active_layers = sum(1 for lyr in layers.values() if lyr["invocations"] > 0 or lyr["layer_id"] == "layer_5")
    return {
        "overall_status": "VERIFIED" if guardrail_verified else "AUTO_REPAIR_WARNING",
        "guardrail_verified": guardrail_verified,
        "auto_repairs_triggered": auto_repairs_triggered,
        "total_tool_invocations": len(tool_traces or []),
        "active_guardrail_layers": active_layers,
        "total_duration_ms": round(total_ms, 1),
        "layers": list(layers.values()),
    }


def audit_workspace_and_hcl_guardrails(
    workspace_dir: str = "./output",
    hcl_content: str = "",
    response_text: str = "",
    vpc_cidr: str = "10.10.0.0/16",
    client_subnet_cidr: str = "10.20.1.0/24",
    backup_subnet_cidr: str = "10.20.2.0/24",
) -> str:
    """Runs an on-demand 5-Layer Guardrail Telemetry Audit across a workspace directory, HCL snippet, and response text.

    Ideal for IDE MCP clients (Antigravity, Cursor, Claude Code) and CI/CD pre-commit verification.
    """
    import time

    traces: list[dict[str, Any]] = []
    issues: list[str] = []

    # Layer 1 & 5: Onboarding response anti-hallucination check
    t0 = time.perf_counter()
    text_issues = check_onboarding_response_for_hallucinations(response_text or "")
    issues.extend(text_issues)
    traces.append(
        {
            "tool_name": "get_odb_onboarding_and_architecture_guide",
            "duration_ms": round((time.perf_counter() - t0) * 1000, 2),
        }
    )

    # Layer 3: HCL schema & provider hallucination check
    t1 = time.perf_counter()
    hcl_issues = check_hcl_for_provider_hallucinations(hcl_content or "")
    issues.extend(hcl_issues)
    traces.append(
        {
            "tool_name": "validate_terraform_hcl",
            "duration_ms": round((time.perf_counter() - t1) * 1000, 2),
        }
    )

    # Layer 4: Deterministic CIDR `/28` & overlap validation
    t2 = time.perf_counter()
    cidr_res = json.loads(
        validate_odb_network_cidrs(
            vpc_cidr=vpc_cidr,
            client_subnet_cidr=client_subnet_cidr,
            backup_subnet_cidr=backup_subnet_cidr,
        )
    )
    if not cidr_res.get("valid"):
        issues.extend(cidr_res.get("errors", []))
    traces.append(
        {
            "tool_name": "validate_odb_network_cidrs",
            "duration_ms": round((time.perf_counter() - t2) * 1000, 2),
        }
    )

    # Layer 5: Day-2 workspace inspection & deletion_protection audit
    t3 = time.perf_counter()
    ws_res = json.loads(inspect_existing_terraform_workspace(workspace_dir))
    if "error" in ws_res:
        issues.append(str(ws_res["error"]))
    missing_del_prot = (
        ws_res.get("security_posture", {}).get("resources_missing_deletion_protection", [])
        or []
    )
    traces.append(
        {
            "tool_name": "inspect_existing_terraform_workspace",
            "duration_ms": round((time.perf_counter() - t3) * 1000, 2),
        }
    )

    scorecard = build_guardrail_telemetry_summary(
        traces,
        guardrail_verified=len(issues) == 0,
        auto_repairs_triggered=0,
    )
    return json.dumps(
        {
            "valid": len(issues) == 0,
            "scorecard": scorecard,
            "detected_issues": issues,
            "cidr_validation": cidr_res,
            "workspace_posture": {
                "workspace_dir": ws_res.get("workspace_dir"),
                "exists": ws_res.get("exists", False),
                "tf_files": ws_res.get("tf_files", []),
                "resources_missing_deletion_protection": missing_del_prot,
                "safe_in_place_day2_operations": SAFE_IN_PLACE_DAY2_ATTRIBUTES,
                "immutable_force_new_attributes": IMMUTABLE_FORCE_NEW_ATTRIBUTES,
            },
        },
        indent=2,
    )
