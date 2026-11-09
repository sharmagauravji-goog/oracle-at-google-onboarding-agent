"""Interactive HTML5 / Streamlit CCv2 Topology Explorer, Live Overlays & Blueprint Canvas.

Implements Part 1 interactive diagram capabilities for the Oracle@Google Onboarding Agent:
1. Interactive SVG Topology Explorer: Pan/zoom, search, click-to-inspect resource drawer
   (exact `hashicorp/google` HCL, least-privilege IAM roles, `/28` CIDR IP capacity math),
   and layer toggles (Separation-of-Duties team ownership colors, CMEK layer, Data Guard DR
   layer, and animated DNS/SQL*Net/RMAN packet flows).
2. Live "Digital Twin" Readiness & Day-2 Blast-Radius Overlays: Dynamic `verified` / `warning` /
   `blocker` status overlays from live GCP checks (with 1-click copyable `gcloud` fix commands)
   plus `scaling_safe` vs. `forcenew_hazard` blast-radius badges from Day-2 HCL diffs.
3. Bidirectional "Visual Blueprint-to-Terraform" Canvas: Edit subnet CIDRs, region/Oracle Zone,
   workload type, deployment layer, and ECPU/storage sliders directly in the diagram with
   real-time `/28` + RFC1918 overlap validation and 1-click Golden Terraform synchronization.
"""

from __future__ import annotations

import html
import ipaddress
import json
import re
import secrets
from typing import Any

_SAFE_TOKEN_RE = re.compile(r"^[a-zA-Z0-9._\-:/]+$")


def _clean_token(val: str, default: str) -> str:
    cleaned = (val or "").strip()
    if not cleaned or not _SAFE_TOKEN_RE.match(cleaned):
        return default
    return cleaned


def compute_cidr_ip_math(cidr_str: str, is_odb_subnet: bool = True) -> dict[str, Any]:
    """Calculates total/usable IPs, RFC1918 status, and `/28` compliance for a CIDR string."""
    raw = (cidr_str or "").strip()
    try:
        net = ipaddress.ip_network(raw, strict=False)
    except ValueError as exc:
        return {
            "cidr": raw,
            "valid": False,
            "meets_min_28": False,
            "total_ips": 0,
            "reserved_ips": 0,
            "usable_ips": 0,
            "is_private_rfc1918": False,
            "summary": f"Invalid CIDR '{raw}': {exc}",
        }

    total = int(net.num_addresses)
    reserved = min(total, 5)
    usable = max(0, total - reserved)
    meets_28 = net.prefixlen <= 28 if is_odb_subnet else net.prefixlen <= 29
    is_priv = bool(net.is_private)
    status_note = "Valid (/28+ compliant)" if meets_28 else f"INVALID prefix /{net.prefixlen} (must be /28 or larger)"
    return {
        "cidr": str(net),
        "valid": meets_28 and is_priv,
        "meets_min_28": meets_28,
        "prefixlen": net.prefixlen,
        "total_ips": total,
        "reserved_ips": reserved,
        "usable_ips": usable,
        "is_private_rfc1918": is_priv,
        "summary": f"{net} — {usable} usable IPs ({total} total, {reserved} reserved) • {status_note}",
    }


def validate_blueprint_cidrs(
    vpc_cidr: str,
    client_subnet_cidr: str,
    backup_subnet_cidr: str,
) -> dict[str, Any]:
    """Validates blueprint VPC, Client Subnet, and Backup Subnet CIDRs for `/28` rules and overlaps."""
    vpc_math = compute_cidr_ip_math(vpc_cidr, is_odb_subnet=False)
    client_math = compute_cidr_ip_math(client_subnet_cidr, is_odb_subnet=True)
    backup_math = compute_cidr_ip_math(backup_subnet_cidr, is_odb_subnet=True)

    errors: list[str] = []
    node_flags: dict[str, str] = {}

    for key, info, label in (
        ("vpc", vpc_math, "Customer VPC"),
        ("client_subnet", client_math, "CLIENT_SUBNET"),
        ("backup_subnet", backup_math, "BACKUP_SUBNET"),
    ):
        if not info["valid"]:
            errors.append(f"{label}: {info['summary']}")
            node_flags[key] = info["summary"]

    try:
        n_vpc = ipaddress.ip_network(vpc_cidr.strip(), strict=False)
        n_cli = ipaddress.ip_network(client_subnet_cidr.strip(), strict=False)
        n_bak = ipaddress.ip_network(backup_subnet_cidr.strip(), strict=False)

        if n_cli.overlaps(n_bak):
            msg = f"CIDR Collision: CLIENT_SUBNET ({n_cli}) overlaps BACKUP_SUBNET ({n_bak})."
            errors.append(msg)
            node_flags["client_subnet"] = msg
            node_flags["backup_subnet"] = msg
        if n_vpc.overlaps(n_cli):
            msg = f"CIDR Collision: VPC ({n_vpc}) overlaps ODB CLIENT_SUBNET ({n_cli})."
            errors.append(msg)
            node_flags["vpc"] = msg
            node_flags["client_subnet"] = msg
        if n_vpc.overlaps(n_bak):
            msg = f"CIDR Collision: VPC ({n_vpc}) overlaps ODB BACKUP_SUBNET ({n_bak})."
            errors.append(msg)
            node_flags["vpc"] = msg
            node_flags["backup_subnet"] = msg
    except ValueError:
        pass

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "node_flags": node_flags,
        "vpc_math": vpc_math,
        "client_math": client_math,
        "backup_math": backup_math,
    }


def build_readiness_node_overlays(
    live_readiness_json: str = "",
    checklist_readiness_json: str = "",
    live_subnet_overlap_json: str = "",
) -> dict[str, dict[str, str]]:
    """Maps live GCP / onboarding readiness outputs onto interactive diagram node statuses."""
    overlays: dict[str, dict[str, str]] = {}

    if live_readiness_json and live_readiness_json.strip():
        try:
            payload = json.loads(live_readiness_json)
        except json.JSONDecodeError:
            payload = {}

        if isinstance(payload, dict) and payload.get("valid"):
            proj = payload.get("project_id", "my-odb-project-01")
            api_rep = payload.get("api_readiness", {})
            iam_rep = payload.get("iam_readiness", {})
            missing_apis = api_rep.get("missing_apis", []) if isinstance(api_rep, dict) else []
            missing_roles = iam_rep.get("missing_odb_roles", []) if isinstance(iam_rep, dict) else []
            iam_cmds = iam_rep.get("remediation_commands", []) if isinstance(iam_rep, dict) else []

            if missing_apis or missing_roles:
                fix_cmds: list[str] = []
                if missing_apis:
                    fix_cmds.append(
                        f"gcloud services enable {' '.join(missing_apis)} --project={proj}"
                    )
                fix_cmds.extend(iam_cmds)
                detail_parts = []
                if missing_apis:
                    detail_parts.append(f"Missing APIs: {', '.join(missing_apis)}")
                if missing_roles:
                    detail_parts.append(f"Missing IAM: {', '.join(missing_roles)}")
                overlays["phase1_iam"] = {
                    "state": "blocker",
                    "badge_text": "BLOCKER: IAM / API",
                    "detail": " | ".join(detail_parts),
                    "remediation_cmd": "\n".join(fix_cmds),
                }
            elif iam_rep.get("iam_policy_inspected") or api_rep.get("status") == "ready":
                overlays["phase1_iam"] = {
                    "state": "verified",
                    "badge_text": "LIVE VERIFIED",
                    "detail": f"APIs & required {payload.get('team_role', 'full_stack')} IAM roles active in {proj}.",
                    "remediation_cmd": "",
                }
            else:
                overlays["phase1_iam"] = {
                    "state": "warning",
                    "badge_text": "AUTH CHECK NEEDED",
                    "detail": f"Could not inspect live IAM policy for {proj}; verify gcloud credentials.",
                    "remediation_cmd": f"gcloud projects get-iam-policy {proj}",
                }

            overlays["phase2_marketplace"] = {
                "state": "warning",
                "badge_text": "VERIFY ORDER",
                "detail": "Confirm Private Offer or PAYG subscription is ACTIVE in GCP Marketplace Orders.",
                "remediation_cmd": f"# Open Console:\n# https://console.cloud.google.com/marketplace/orders?project={proj}",
            }

    if checklist_readiness_json and checklist_readiness_json.strip():
        try:
            chk = json.loads(checklist_readiness_json)
        except json.JSONDecodeError:
            chk = {}

        if isinstance(chk, dict):
            proj_chk = chk.get("project_id", "my-odb-project-01")
            score = chk.get("readiness_score_pct")
            if score is None:
                score = chk.get("readiness_score", chk.get("score"))
            blockers = chk.get("blocking_items")
            if blockers is None:
                blockers = chk.get("blockers", [])

            phase_blocked: dict[str, list[str]] = {
                "phase1_iam": [],
                "phase2_marketplace": [],
                "phase3_oci": [],
                "phase4_mos": [],
            }
            for raw_b in blockers or []:
                b_str = str(raw_b)
                b_low = b_str.lower()
                if "phase 1" in b_low or "billing" in b_low or "oracledatabase.googleapis.com" in b_low:
                    phase_blocked["phase1_iam"].append(b_str)
                elif "phase 3" in b_low or "oci" in b_low or "tenancy" in b_low:
                    phase_blocked["phase3_oci"].append(b_str)
                elif "phase 4" in b_low or "mos" in b_low or "csi" in b_low:
                    phase_blocked["phase4_mos"].append(b_str)
                else:
                    phase_blocked["phase2_marketplace"].append(b_str)

            phase_fixes = {
                "phase1_iam": (
                    f"gcloud services enable oracledatabase.googleapis.com compute.googleapis.com "
                    f"servicenetworking.googleapis.com --project={proj_chk}"
                ),
                "phase2_marketplace": f"# Open Console:\n# https://console.cloud.google.com/marketplace/orders?project={proj_chk}",
                "phase3_oci": f"# Link OCI Tenancy:\n# https://console.cloud.google.com/oracledatabase/locations?project={proj_chk}",
                "phase4_mos": "# Register CSI at https://support.oracle.com -> My Account -> Request Access",
            }

            for pid, items in phase_blocked.items():
                if items:
                    overlays[pid] = {
                        "state": "blocker",
                        "badge_text": "CHECKLIST BLOCKER",
                        "detail": " | ".join(items),
                        "remediation_cmd": phase_fixes.get(pid, ""),
                    }
                elif isinstance(score, (int, float)):
                    overlays.setdefault(
                        pid,
                        {
                            "state": "verified",
                            "badge_text": "GATE PASSED",
                            "detail": "Verified ready in onboarding checklist evaluation.",
                            "remediation_cmd": "",
                        },
                    )

            if isinstance(score, (int, float)):
                if score >= 85 and not blockers:
                    ready_badge = {
                        "state": "verified",
                        "badge_text": f"READY ({int(score)}/100)",
                        "detail": "All evaluated onboarding checklist gates passed.",
                        "remediation_cmd": "",
                    }
                    overlays.setdefault("workload_db", dict(ready_badge))
                    overlays.setdefault("phase5_provision", dict(ready_badge))
                elif blockers:
                    warn_badge = {
                        "state": "warning",
                        "badge_text": f"SCORE {int(score)}/100",
                        "detail": f"Resolve {len(blockers)} upstream onboarding blocker(s) before provisioning.",
                        "remediation_cmd": "",
                    }
                    overlays.setdefault("workload_db", dict(warn_badge))
                    overlays.setdefault("phase5_provision", dict(warn_badge))

    if live_subnet_overlap_json and live_subnet_overlap_json.strip():
        try:
            sub_rep = json.loads(live_subnet_overlap_json)
        except json.JSONDecodeError:
            sub_rep = {}
        if isinstance(sub_rep, dict):
            overlaps = sub_rep.get("collisions")
            if overlaps is None:
                overlaps = sub_rep.get("overlapping_subnets", [])
            checked_cnt = sub_rep.get("existing_gcp_subnets_count")
            if checked_cnt is None:
                checked_cnt = sub_rep.get("checked_subnets_count", 0)

            if overlaps:
                overlays["client_subnet"] = {
                    "state": "blocker",
                    "badge_text": "LIVE VPC COLLISION",
                    "detail": f"Proposed CIDR collides with {len(overlaps)} live GCP subnet(s).",
                    "remediation_cmd": "gcloud compute networks subnets list --format='table(name,region,ipCidrRange)'",
                }
            elif sub_rep.get("live_vpc_checked") or (isinstance(checked_cnt, int) and checked_cnt > 0):
                overlays["client_subnet"] = {
                    "state": "verified",
                    "badge_text": "NO VPC COLLISION",
                    "detail": f"Verified non-overlapping against {checked_cnt} live GCP subnet(s).",
                    "remediation_cmd": "",
                }

    return overlays


def build_day2_blast_radius_overlays(day2_diff_json: str) -> dict[str, dict[str, str]]:
    """Maps `analyze_day2_terraform_diff` output onto interactive diagram node blast-radius badges."""
    overlays: dict[str, dict[str, str]] = {}
    if not day2_diff_json or not day2_diff_json.strip():
        return overlays

    try:
        diff = json.loads(day2_diff_json)
    except json.JSONDecodeError:
        return overlays

    if not isinstance(diff, dict):
        return overlays

    def _target_node_ids(resource_addr: str, attr: str = "") -> list[str]:
        addr_low = resource_addr.lower()
        attr_low = attr.lower()
        if "odb_subnet" in addr_low:
            if "backup" in addr_low:
                return ["backup_subnet", "phase5_provision"]
            return ["client_subnet", "phase5_provision"]
        if "odb_network" in addr_low:
            return ["odb_net", "odb_net_dr", "phase5_provision"]
        if "kms" in addr_low or "kms_key" in attr_low:
            return ["cmek_kms", "workload_db"]
        if "exadata_infrastructure" in addr_low or "storage_vault" in addr_low:
            return ["exadata_infra", "workload_db", "phase5_provision"]
        return ["workload_db", "phase5_provision"]

    for upd in diff.get("safe_in_place_updates", []):
        res_addr = str(upd.get("resource", ""))
        attr = str(upd.get("attribute", ""))
        old_v = upd.get("old_value")
        new_v = upd.get("new_value")
        for nid in _target_node_ids(res_addr, attr):
            overlays[nid] = {
                "state": "scaling_safe",
                "badge_text": f"~ SAFE ONLINE: {attr}",
                "detail": f"Zero-downtime in-place update on {res_addr}: {attr} ({old_v} -> {new_v}).",
                "remediation_cmd": "terraform plan -out=day2-scale.tfplan",
            }

    for warn in diff.get("destructive_replacement_warnings", []):
        res_addr = str(warn.get("resource", ""))
        attr = str(warn.get("attribute", "resource"))
        reason = str(warn.get("reason", "Destructive ForceNew replacement detected."))
        for nid in _target_node_ids(res_addr, attr):
            overlays[nid] = {
                "state": "forcenew_hazard",
                "badge_text": f"-/+ FORCENEW RISK: {attr}",
                "detail": reason,
                "remediation_cmd": (
                    "# DO NOT run terraform apply -auto-approve!\n"
                    "# Ensure deletion_protection = true, provision a parallel resource, and migrate via Data Guard / RMAN."
                ),
            }

    return overlays


def build_interactive_diagram_spec(
    diagram_type: str = "end_to_end_onboarding",
    project_id: str = "my-odb-project-01",
    region: str = "us-east4",
    gcp_oracle_zone: str = "us-east4-b-r1",
    vpc_cidr: str = "10.10.0.0/16",
    client_subnet_cidr: str = "10.20.1.0/24",
    backup_subnet_cidr: str = "10.20.2.0/24",
    workload_type: str = "adb",
    deployment_layer: str = "full_stack",
    compute_count: int = 4,
    storage_size_tb: int = 1,
    node_overlays: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Builds the complete interactive topology specification (nodes, edges, HCL, IAM, IP math, overlays)."""
    proj = _clean_token(project_id, "my-odb-project-01")
    reg = _clean_token(region, "us-east4")
    ozone = _clean_token(gcp_oracle_zone, f"{reg}-b-r1")
    v_cidr = _clean_token(vpc_cidr, "10.10.0.0/16")
    c_cidr = _clean_token(client_subnet_cidr, "10.20.1.0/24")
    b_cidr = _clean_token(backup_subnet_cidr, "10.20.2.0/24")
    wkl = _clean_token(workload_type, "adb").lower()
    dlayer = _clean_token(deployment_layer, "full_stack").lower()
    cpus = max(2, min(256, int(compute_count or 4)))
    tbs = max(1, min(256, int(storage_size_tb or 1)))

    cidr_report = validate_blueprint_cidrs(v_cidr, c_cidr, b_cidr)
    merged_overlays: dict[str, dict[str, str]] = {}
    if node_overlays:
        for k, v in node_overlays.items():
            if isinstance(v, dict):
                merged_overlays[k] = dict(v)

    # Surface CIDR errors immediately onto the corresponding nodes if no higher-priority overlay is set
    for flag_key, err_msg in cidr_report["node_flags"].items():
        merged_overlays.setdefault(
            flag_key,
            {
                "state": "blocker",
                "badge_text": "CIDR GUARDRAIL",
                "detail": err_msg,
                "remediation_cmd": "# Fix CIDR in the Blueprint Editor tab (non-overlapping RFC1918 >= /28).",
            },
        )

    workload_label_map = {
        "adb": "Autonomous Database 23ai",
        "exadata_dedicated": "Exadata VM Cluster (Dedicated)",
        "exascale": "Exascale DB VM Cluster",
        "basedb": "Oracle Base Database System",
    }
    workload_res_map = {
        "adb": "google_oracle_database_autonomous_database",
        "exadata_dedicated": "google_oracle_database_cloud_vm_cluster",
        "exascale": "google_oracle_database_exadb_vm_cluster",
        "basedb": "google_oracle_database_db_system",
    }
    w_label = workload_label_map.get(wkl, workload_label_map["adb"])
    w_res = workload_res_map.get(wkl, workload_res_map["adb"])

    # Reusable HCL snippets
    hcl_odb_net = (
        f'resource "google_oracle_database_odb_network" "odb_net" {{\n'
        f'  odb_network_id  = "odb-prod-net"\n'
        f'  location        = "{reg}"\n'
        f'  project         = "{proj}"\n'
        f'  network         = google_compute_network.vpc.id\n'
        f'  gcp_oracle_zone = "{ozone}"\n'
        f'  deletion_protection = true\n'
        f'}}'
    )
    hcl_client_sub = (
        f'resource "google_oracle_database_odb_subnet" "client" {{\n'
        f'  odb_subnet_id = "odb-client-subnet"\n'
        f'  odbnetwork    = google_oracle_database_odb_network.odb_net.odb_network_id\n'
        f'  location      = "{reg}"\n'
        f'  project       = "{proj}"\n'
        f'  cidr_range    = "{c_cidr}"\n'
        f'  purpose       = "CLIENT_SUBNET"\n'
        f'}}'
    )
    hcl_backup_sub = (
        f'resource "google_oracle_database_odb_subnet" "backup" {{\n'
        f'  odb_subnet_id = "odb-backup-subnet"\n'
        f'  odbnetwork    = google_oracle_database_odb_network.odb_net.odb_network_id\n'
        f'  location      = "{reg}"\n'
        f'  project       = "{proj}"\n'
        f'  cidr_range    = "{b_cidr}"\n'
        f'  purpose       = "BACKUP_SUBNET"\n'
        f'}}'
    )
    hcl_workload = (
        f'resource "{w_res}" "primary" {{\n'
        f'  location            = "{reg}"\n'
        f'  project             = "{proj}"\n'
        f'  odb_network         = google_oracle_database_odb_network.odb_net.name\n'
        f'  odb_subnet          = google_oracle_database_odb_subnet.client.name\n'
        f'  deletion_protection = true\n'
        f'  properties {{\n'
        f'    compute_count        = {cpus}\n'
        f'    data_storage_size_tb = {tbs}\n'
        f'  }}\n'
        f'}}'
    )
    hcl_cmek = (
        f'resource "google_kms_crypto_key_iam_member" "odb_cmek" {{\n'
        f'  crypto_key_id = google_kms_crypto_key.odb_tde_key.id\n'
        f'  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"\n'
        f'  member        = "serviceAccount:service-${{data.google_project.current.number}}@gcp-sa-oracledatabase.iam.gserviceaccount.com"\n'
        f'}}'
    )

    dtype = (diagram_type or "end_to_end_onboarding").strip().lower()

    def _node(
        nid: str,
        label: str,
        subtitle: str,
        x: int,
        y: int,
        w: int = 230,
        h: int = 82,
        team_owner: str = "platform",
        layer: str = "core",
        terraform_resource: str = "",
        hcl_snippet: str = "",
        iam_roles: list[str] | None = None,
        ip_math: str = "",
        doc_url: str = "https://cloud.google.com/oracle/docs/overview",
        editable_field: str = "",
    ) -> dict[str, Any]:
        ov = merged_overlays.get(
            nid,
            {
                "state": "neutral",
                "badge_text": "",
                "detail": "",
                "remediation_cmd": "",
            },
        )
        return {
            "id": nid,
            "label": label,
            "subtitle": subtitle,
            "x": x,
            "y": y,
            "width": w,
            "height": h,
            "team_owner": team_owner,
            "layer": layer,
            "terraform_resource": terraform_resource,
            "hcl_snippet": hcl_snippet,
            "iam_roles": iam_roles or [],
            "ip_math": ip_math,
            "doc_url": doc_url,
            "editable_field": editable_field,
            "status_overlay": ov,
        }

    groups: list[dict[str, Any]] = []
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    title = "Oracle Database@Google Cloud — Interactive Topology Explorer"

    if dtype == "end_to_end_onboarding":
        title = f"End-to-End Customer Onboarding Journey ({proj} • {reg})"
        groups = [
            {"id": "g_gov", "label": "Commercial, Governance & Account Federation (Day 0)", "x": 30, "y": 36, "width": 1040, "height": 230, "team_owner": "procurement"},
            {"id": "g_iaac", "label": f"Cloud Network, Security & Terraform Provisioning ({reg} / {ozone})", "x": 30, "y": 296, "width": 1040, "height": 286, "team_owner": "network"},
        ]
        nodes = [
            _node(
                "phase1_iam",
                "Phase 1: GCP APIs & IAM",
                f"Project: {proj}",
                60,
                88,
                220,
                92,
                team_owner="procurement",
                terraform_resource="google_project_service",
                hcl_snippet=(
                    f'resource "google_project_service" "odb_api" {{\n'
                    f'  project = "{proj}"\n'
                    f'  service = "oracledatabase.googleapis.com"\n'
                    f'}}'
                ),
                iam_roles=[
                    "roles/oracledatabase.admin",
                    "roles/serviceusage.serviceUsageAdmin",
                    "roles/compute.networkAdmin",
                ],
                editable_field="project_id",
            ),
            _node(
                "phase2_marketplace",
                "Phase 2: GCP Marketplace",
                "Private Offer / PAYG Order",
                315,
                88,
                220,
                92,
                team_owner="procurement",
                terraform_resource="Marketplace Entitlement",
                hcl_snippet="# Subscribed in Google Cloud Marketplace (100% MACC drawdown eligible).\n# Consolidated on your monthly Google Cloud Billing invoice.",
                iam_roles=["roles/billing.admin", "roles/consumerprocurement.orderAdmin"],
            ),
            _node(
                "phase3_oci",
                "Phase 3: OCI Account Link",
                "MulticloudLink Federation",
                570,
                88,
                220,
                92,
                team_owner="procurement",
                terraform_resource="Partner OCI Tenancy Link",
                hcl_snippet="# One-time GCP Console action:\n# Oracle Database@Google Cloud -> Link New or Existing OCI Tenancy",
                iam_roles=["roles/oracledatabase.admin"],
            ),
            _node(
                "phase4_mos",
                "Phase 4: MOS & CSI Support",
                "support.oracle.com CSI",
                825,
                88,
                215,
                92,
                team_owner="procurement",
                terraform_resource="Customer Support Identifier",
                hcl_snippet="# Retrieve CSI from OCI Tenancy Details and register at https://support.oracle.com\n# Enables joint Google Cloud Care + Oracle collaborative Sev-1 triage.",
                iam_roles=["roles/cloudsupport.techSupportEditor"],
            ),
            _node(
                "odb_net",
                "Phase 5A: ODB Network",
                f"VPC {v_cidr} <-> {ozone}",
                60,
                350,
                235,
                94,
                team_owner="network",
                terraform_resource="google_oracle_database_odb_network",
                hcl_snippet=hcl_odb_net,
                iam_roles=["roles/oracledatabase.networkAdmin", "roles/compute.networkAdmin"],
                ip_math=cidr_report["vpc_math"]["summary"],
                editable_field="vpc_cidr",
            ),
            _node(
                "client_subnet",
                "Phase 5B: ODB Subnets",
                f"CLIENT {c_cidr} | BKP {b_cidr}",
                335,
                350,
                250,
                94,
                team_owner="network",
                terraform_resource="google_oracle_database_odb_subnet",
                hcl_snippet=hcl_client_sub + "\n\n" + hcl_backup_sub,
                iam_roles=["roles/oracledatabase.networkAdmin"],
                ip_math=f"CLIENT: {cidr_report['client_math']['summary']} | BACKUP: {cidr_report['backup_math']['summary']}",
                editable_field="client_subnet_cidr",
            ),
            _node(
                "phase5_provision",
                f"Phase 5C: {w_label}",
                f"{cpus} ECPUs • {tbs} TB • Layer: {dlayer}",
                625,
                350,
                245,
                94,
                team_owner="database",
                terraform_resource=w_res,
                hcl_snippet=hcl_workload,
                iam_roles=[
                    "roles/oracledatabase.autonomousDatabaseAdmin",
                    "roles/oracledatabase.exadataAdmin",
                    "roles/oracledatabase.viewer",
                ],
                editable_field="workload_type",
            ),
            _node(
                "cmek_kms",
                "Cloud KMS CMEK Envelope",
                f"gcp-sa-oracledatabase ({reg})",
                625,
                472,
                245,
                84,
                team_owner="infrastructure",
                layer="cmek",
                terraform_resource="google_kms_crypto_key_iam_member",
                hcl_snippet=hcl_cmek,
                iam_roles=["roles/cloudkms.admin", "roles/cloudkms.cryptoKeyEncrypterDecrypter"],
            ),
            _node(
                "dr_standby",
                "Data Guard DR Standby",
                "Zero-Data-Loss Redo Sync",
                895,
                350,
                160,
                94,
                team_owner="database",
                layer="dr",
                terraform_resource="Data Guard Association",
                hcl_snippet="# Autonomous Data Guard / Active Data Guard standby in secondary Oracle Zone",
                iam_roles=["roles/oracledatabase.exadataAdmin"],
            ),
        ]
        edges = [
            {"id": "e1", "from": "phase1_iam", "to": "phase2_marketplace", "label": "APIs Ready", "flow_type": "control", "layer": "core"},
            {"id": "e2", "from": "phase2_marketplace", "to": "phase3_oci", "label": "Entitlement", "flow_type": "control", "layer": "core"},
            {"id": "e3", "from": "phase3_oci", "to": "phase4_mos", "label": "CSI Issued", "flow_type": "control", "layer": "core"},
            {"id": "e4", "from": "phase4_mos", "to": "odb_net", "label": "Day-1 Ready", "flow_type": "control", "layer": "core", "dashed": True},
            {"id": "e5", "from": "odb_net", "to": "client_subnet", "label": "/28+ Subnets", "flow_type": "sql", "layer": "core"},
            {"id": "e6", "from": "client_subnet", "to": "phase5_provision", "label": "SQL*Net / RMAN", "flow_type": "sql", "layer": "core"},
            {"id": "e7", "from": "cmek_kms", "to": "phase5_provision", "label": "TDE Key Wrap", "flow_type": "cmek", "layer": "cmek", "dashed": True},
            {"id": "e8", "from": "phase5_provision", "to": "dr_standby", "label": "Redo Sync", "flow_type": "dr", "layer": "dr", "dashed": True},
        ]

    elif dtype in ("networking_shared_vpc", "odb_network_shared_vpc"):
        title = f"Enterprise Shared VPC Topology — Host + Service Projects ({reg} / {ozone})"
        groups = [
            {"id": "g_host", "label": f"Shared VPC Host Project (VPC CIDR {v_cidr})", "x": 30, "y": 40, "width": 450, "height": 250, "team_owner": "network"},
            {"id": "g_app", "label": "Application Service Project", "x": 30, "y": 325, "width": 450, "height": 235, "team_owner": "platform"},
            {"id": "g_db", "label": f"ODB Database Service Project ({proj} • {ozone})", "x": 525, "y": 40, "width": 555, "height": 520, "team_owner": "database"},
        ]
        nodes = [
            _node(
                "vpc",
                "Host Shared VPC Network",
                f"CIDR: {v_cidr}",
                65,
                95,
                210,
                88,
                team_owner="network",
                terraform_resource="google_compute_shared_vpc_host_project",
                hcl_snippet=(
                    f'data "google_compute_network" "shared_vpc" {{\n'
                    f'  name    = "corp-shared-vpc"\n'
                    f'  project = var.shared_vpc_host_project_id\n'
                    f'}}'
                ),
                iam_roles=["roles/compute.xpnAdmin", "roles/compute.networkAdmin"],
                ip_math=cidr_report["vpc_math"]["summary"],
                editable_field="vpc_cidr",
            ),
            _node(
                "cloud_dns",
                "Cloud DNS Private Zone",
                "*.oraclevcn.com Forwarding",
                290,
                95,
                170,
                88,
                team_owner="network",
                terraform_resource="google_dns_managed_zone",
                hcl_snippet="# Auto-configured partner DNS peering/forwarding for SCAN & ADB private endpoints",
                iam_roles=["roles/dns.admin"],
            ),
            _node(
                "app_tier",
                "GKE / Compute App Tier",
                "mTLS / TLS 1.2 SQL Clients",
                125,
                395,
                250,
                92,
                team_owner="platform",
                terraform_resource="google_container_cluster",
                hcl_snippet="# App pods in Service Project connect over low-latency (<2ms) private peering",
                iam_roles=["roles/compute.networkUser"],
            ),
            _node(
                "odb_net",
                "ODB Partner Network",
                f"Zone: {ozone}",
                560,
                95,
                225,
                88,
                team_owner="network",
                terraform_resource="google_oracle_database_odb_network",
                hcl_snippet=hcl_odb_net,
                iam_roles=["roles/oracledatabase.networkAdmin", "roles/compute.networkUser"],
            ),
            _node(
                "client_subnet",
                "CLIENT_SUBNET",
                f"CIDR: {c_cidr}",
                560,
                225,
                225,
                88,
                team_owner="network",
                terraform_resource="google_oracle_database_odb_subnet",
                hcl_snippet=hcl_client_sub,
                iam_roles=["roles/oracledatabase.networkAdmin"],
                ip_math=cidr_report["client_math"]["summary"],
                editable_field="client_subnet_cidr",
            ),
            _node(
                "backup_subnet",
                "BACKUP_SUBNET",
                f"CIDR: {b_cidr}",
                820,
                225,
                225,
                88,
                team_owner="network",
                terraform_resource="google_oracle_database_odb_subnet",
                hcl_snippet=hcl_backup_sub,
                iam_roles=["roles/oracledatabase.networkAdmin"],
                ip_math=cidr_report["backup_math"]["summary"],
                editable_field="backup_subnet_cidr",
            ),
            _node(
                "workload_db",
                w_label,
                f"{cpus} ECPUs • {tbs} TB ({proj})",
                560,
                365,
                245,
                95,
                team_owner="database",
                terraform_resource=w_res,
                hcl_snippet=hcl_workload,
                iam_roles=["roles/oracledatabase.autonomousDatabaseAdmin", "roles/oracledatabase.viewer"],
                editable_field="workload_type",
            ),
            _node(
                "cmek_kms",
                "Cloud KMS CMEK",
                f"KeyRing in {reg}",
                830,
                365,
                215,
                85,
                team_owner="infrastructure",
                layer="cmek",
                terraform_resource="google_kms_crypto_key_iam_member",
                hcl_snippet=hcl_cmek,
                iam_roles=["roles/cloudkms.cryptoKeyEncrypterDecrypter"],
            ),
            _node(
                "dr_standby",
                "Standby DR Database",
                "Cross-Zone / Region Data Guard",
                830,
                465,
                215,
                80,
                team_owner="database",
                layer="dr",
                terraform_resource="Data Guard Standby",
                hcl_snippet="# Continuous redo transport to secondary Oracle Zone",
                iam_roles=["roles/oracledatabase.exadataAdmin"],
            ),
        ]
        edges = [
            {"id": "e1", "from": "app_tier", "to": "vpc", "label": "Shared Subnet", "flow_type": "sql", "layer": "core"},
            {"id": "e2", "from": "vpc", "to": "odb_net", "label": "Partner Peering (<2ms)", "flow_type": "sql", "layer": "core"},
            {"id": "e3", "from": "cloud_dns", "to": "client_subnet", "label": "*.oraclevcn.com DNS", "flow_type": "dns", "layer": "core", "dashed": True},
            {"id": "e4", "from": "odb_net", "to": "client_subnet", "label": "App Plane", "flow_type": "sql", "layer": "core"},
            {"id": "e5", "from": "odb_net", "to": "backup_subnet", "label": "Backup Plane", "flow_type": "backup", "layer": "core", "dashed": True},
            {"id": "e6", "from": "client_subnet", "to": "workload_db", "label": "SQL*Net 1521/2484", "flow_type": "sql", "layer": "core"},
            {"id": "e7", "from": "backup_subnet", "to": "workload_db", "label": "RMAN Backup I/O", "flow_type": "backup", "layer": "core", "dashed": True},
            {"id": "e8", "from": "cmek_kms", "to": "workload_db", "label": "CMEK TDE Wrap", "flow_type": "cmek", "layer": "cmek", "dashed": True},
            {"id": "e9", "from": "workload_db", "to": "dr_standby", "label": "Data Guard Sync", "flow_type": "dr", "layer": "dr", "dashed": True},
        ]

    elif dtype in ("networking_hub_and_spoke_ha_dr", "odb_network_hub_spoke_ncc"):
        title = f"Hybrid Hub-and-Spoke (NCC + Interconnect) & Data Guard HA/DR ({reg})"
        groups = [
            {"id": "g_onprem", "label": "On-Premises Datacenter", "x": 25, "y": 60, "width": 225, "height": 220, "team_owner": "network"},
            {"id": "g_hub", "label": f"GCP Transit Hub ({v_cidr})", "x": 280, "y": 60, "width": 270, "height": 470, "team_owner": "network"},
            {"id": "g_prim", "label": f"Primary ODB Zone ({reg} / {ozone})", "x": 585, "y": 45, "width": 500, "height": 265, "team_owner": "database"},
            {"id": "g_dr", "label": "Standby DR Region / Oracle Zone", "x": 585, "y": 335, "width": 500, "height": 225, "team_owner": "database"},
        ]
        nodes = [
            _node(
                "onprem_dc",
                "On-Prem Apps & GoldenGate",
                "Corporate Datacenter",
                45,
                125,
                185,
                95,
                team_owner="platform",
                terraform_resource="External Hybrid Peer",
                hcl_snippet=f"# BGP receives custom advertised route for ODB CLIENT_SUBNET ({c_cidr})",
                iam_roles=["roles/compute.networkAdmin"],
            ),
            _node(
                "interconnect",
                "Cloud Interconnect / VPN",
                f"Cloud Router BGP ({c_cidr})",
                305,
                115,
                220,
                92,
                team_owner="network",
                terraform_resource="google_compute_router",
                hcl_snippet=(
                    f'resource "google_compute_router_peer" "onprem_bgp" {{\n'
                    f'  advertise_mode = "CUSTOM"\n'
                    f'  advertised_ip_ranges {{ range = "{c_cidr}" }}\n'
                    f'}}'
                ),
                iam_roles=["roles/compute.networkAdmin"],
            ),
            _node(
                "vpc",
                "NCC Hub & Transit VPC",
                f"export_custom_routes ({v_cidr})",
                305,
                260,
                220,
                92,
                team_owner="network",
                terraform_resource="google_network_connectivity_hub",
                hcl_snippet="# NCC Hub bridges hybrid spokes and exports custom routes to ODB VPC",
                iam_roles=["roles/networkconnectivity.hubAdmin", "roles/compute.networkAdmin"],
                ip_math=cidr_report["vpc_math"]["summary"],
                editable_field="vpc_cidr",
            ),
            _node(
                "cmek_kms",
                "Cloud KMS CMEK",
                f"gcp-sa-oracledatabase ({reg})",
                305,
                405,
                220,
                88,
                team_owner="infrastructure",
                layer="cmek",
                terraform_resource="google_kms_crypto_key_iam_member",
                hcl_snippet=hcl_cmek,
                iam_roles=["roles/cloudkms.cryptoKeyEncrypterDecrypter"],
            ),
            _node(
                "client_subnet",
                "Primary ODB Network",
                f"CLIENT {c_cidr} | BKP {b_cidr}",
                610,
                105,
                220,
                95,
                team_owner="network",
                terraform_resource="google_oracle_database_odb_subnet",
                hcl_snippet=hcl_odb_net + "\n\n" + hcl_client_sub,
                iam_roles=["roles/oracledatabase.networkAdmin"],
                ip_math=cidr_report["client_math"]["summary"],
                editable_field="client_subnet_cidr",
            ),
            _node(
                "workload_db",
                f"Primary {w_label}",
                f"{cpus} ECPUs • {tbs} TB ({proj})",
                855,
                105,
                210,
                95,
                team_owner="database",
                terraform_resource=w_res,
                hcl_snippet=hcl_workload,
                iam_roles=["roles/oracledatabase.exadataAdmin", "roles/oracledatabase.autonomousDatabaseAdmin"],
                editable_field="workload_type",
            ),
            _node(
                "odb_net_dr",
                "Standby ODB Network",
                "Secondary Region / Zone",
                610,
                400,
                220,
                95,
                team_owner="network",
                layer="core",
                terraform_resource="google_oracle_database_odb_network",
                hcl_snippet="# Isolated DR ODB Network in secondary region with non-overlapping CIDRs",
                iam_roles=["roles/oracledatabase.networkAdmin"],
            ),
            _node(
                "dr_standby",
                f"Standby {w_label}",
                "Active / Autonomous Data Guard",
                855,
                400,
                210,
                95,
                team_owner="database",
                layer="core",
                terraform_resource="Data Guard Standby",
                hcl_snippet="# Synchronous / Fast-Start Failover Data Guard standby database",
                iam_roles=["roles/oracledatabase.exadataAdmin"],
            ),
        ]
        edges = [
            {"id": "e1", "from": "onprem_dc", "to": "interconnect", "label": "Dedicated VLAN / VPN", "flow_type": "sql", "layer": "core"},
            {"id": "e2", "from": "interconnect", "to": "vpc", "label": "BGP Custom Routes", "flow_type": "sql", "layer": "core"},
            {"id": "e3", "from": "vpc", "to": "client_subnet", "label": "NCC / Partner Peering", "flow_type": "sql", "layer": "core"},
            {"id": "e4", "from": "client_subnet", "to": "workload_db", "label": "SQL*Net 2484", "flow_type": "sql", "layer": "core"},
            {"id": "e5", "from": "vpc", "to": "odb_net_dr", "label": "DR Route Failover", "flow_type": "dr", "layer": "core", "dashed": True},
            {"id": "e6", "from": "odb_net_dr", "to": "dr_standby", "label": "Standby Client", "flow_type": "dr", "layer": "core", "dashed": True},
            {"id": "e7", "from": "workload_db", "to": "dr_standby", "label": "Data Guard Redo Sync", "flow_type": "dr", "layer": "core"},
            {"id": "e8", "from": "cmek_kms", "to": "workload_db", "label": "CMEK Key Wrap", "flow_type": "cmek", "layer": "cmek", "dashed": True},
        ]

    elif dtype in ("backup_and_recovery", "backup_and_dr_architecture"):
        title = f"Backup, Restore, 1-Second PITR & RMAN Storage Architecture ({ozone})"
        groups = [
            {"id": "g_sub", "label": "Isolated ODB Network Planes", "x": 30, "y": 55, "width": 310, "height": 490, "team_owner": "network"},
            {"id": "g_wkl", "label": f"Database Workloads ({proj} • {ozone})", "x": 375, "y": 55, "width": 320, "height": 490, "team_owner": "database"},
            {"id": "g_tgt", "label": "Immutable Backup & Recovery Destinations", "x": 730, "y": 55, "width": 355, "height": 490, "team_owner": "infrastructure"},
        ]
        nodes = [
            _node(
                "client_subnet",
                "CLIENT_SUBNET",
                f"Low-Latency SQL ({c_cidr})",
                55,
                130,
                255,
                95,
                team_owner="network",
                terraform_resource="google_oracle_database_odb_subnet",
                hcl_snippet=hcl_client_sub,
                iam_roles=["roles/oracledatabase.networkAdmin"],
                ip_math=cidr_report["client_math"]["summary"],
                editable_field="client_subnet_cidr",
            ),
            _node(
                "backup_subnet",
                "BACKUP_SUBNET",
                f"Dedicated RMAN I/O ({b_cidr})",
                55,
                345,
                255,
                95,
                team_owner="network",
                terraform_resource="google_oracle_database_odb_subnet",
                hcl_snippet=hcl_backup_sub,
                iam_roles=["roles/oracledatabase.networkAdmin"],
                ip_math=cidr_report["backup_math"]["summary"],
                editable_field="backup_subnet_cidr",
            ),
            _node(
                "workload_db",
                w_label,
                f"{cpus} ECPUs • {tbs} TB • Retention 1-60d",
                405,
                220,
                260,
                105,
                team_owner="database",
                terraform_resource=w_res,
                hcl_snippet=hcl_workload,
                iam_roles=["roles/oracledatabase.autonomousDatabaseAdmin", "roles/oracledatabase.exadataAdmin"],
                editable_field="workload_type",
            ),
            _node(
                "cmek_kms",
                "Cloud KMS Backup CMEK",
                f"Encrypts TDE & RMAN Backups ({reg})",
                405,
                405,
                260,
                90,
                team_owner="infrastructure",
                layer="cmek",
                terraform_resource="google_kms_crypto_key_iam_member",
                hcl_snippet=hcl_cmek,
                iam_roles=["roles/cloudkms.cryptoKeyEncrypterDecrypter"],
            ),
            _node(
                "oci_recovery",
                "Oracle Managed Object Storage",
                "Automated Backups & 1-Sec PITR",
                760,
                115,
                295,
                95,
                team_owner="infrastructure",
                terraform_resource="Managed Backup Destination",
                hcl_snippet="# Configured via backup_retention_period_days = 30 inside properties {}",
                iam_roles=["roles/oracledatabase.viewer"],
            ),
            _node(
                "gcs_bucket",
                "Google Cloud Storage (GCS)",
                "Optional Custom RMAN Archive",
                760,
                260,
                295,
                95,
                team_owner="infrastructure",
                terraform_resource="google_storage_bucket",
                hcl_snippet=(
                    f'resource "google_storage_bucket" "rman_archive" {{\n'
                    f'  name                        = "{proj}-odb-rman-backups"\n'
                    f'  location                    = "{reg}"\n'
                    f'  uniform_bucket_level_access = true\n'
                    f'}}'
                ),
                iam_roles=["roles/storage.objectAdmin"],
            ),
            _node(
                "dr_standby",
                "Oracle Data Guard Standby",
                "Continuous Redo Shipping",
                760,
                405,
                295,
                95,
                team_owner="database",
                layer="dr",
                terraform_resource="Data Guard Association",
                hcl_snippet="# Zero-data-loss standby database in secondary zone/region",
                iam_roles=["roles/oracledatabase.exadataAdmin"],
            ),
        ]
        edges = [
            {"id": "e1", "from": "client_subnet", "to": "workload_db", "label": "Production SQL Only", "flow_type": "sql", "layer": "core"},
            {"id": "e2", "from": "workload_db", "to": "backup_subnet", "label": "Isolated RMAN Traffic", "flow_type": "backup", "layer": "core"},
            {"id": "e3", "from": "backup_subnet", "to": "oci_recovery", "label": "Daily Auto Backup + PITR", "flow_type": "backup", "layer": "core"},
            {"id": "e4", "from": "backup_subnet", "to": "gcs_bucket", "label": "Custom RMAN Channels", "flow_type": "backup", "layer": "core", "dashed": True},
            {"id": "e5", "from": "cmek_kms", "to": "workload_db", "label": "AES-256 Backup Key", "flow_type": "cmek", "layer": "cmek", "dashed": True},
            {"id": "e6", "from": "workload_db", "to": "dr_standby", "label": "Redo Log Shipping", "flow_type": "dr", "layer": "dr", "dashed": True},
        ]

    elif dtype in ("encryption_cmek", "cmek_encryption_flow"):
        title = f"End-to-End Encryption (mTLS In-Transit + Cloud KMS CMEK TDE At-Rest in {reg})"
        groups = [
            {"id": "g_cli", "label": f"Customer VPC ({v_cidr})", "x": 30, "y": 70, "width": 280, "height": 440, "team_owner": "network"},
            {"id": "g_kms", "label": f"Google Cloud KMS ({proj} • {reg})", "x": 345, "y": 70, "width": 360, "height": 440, "team_owner": "infrastructure"},
            {"id": "g_tde", "label": f"Oracle TDE Security Plane ({ozone})", "x": 740, "y": 70, "width": 345, "height": 440, "team_owner": "database"},
        ]
        nodes = [
            _node(
                "vpc",
                "GKE / App Client (mTLS)",
                f"TLS 1.2+ Wallet ({v_cidr})",
                55,
                160,
                230,
                95,
                team_owner="platform",
                terraform_resource="mTLS / TLS 1.2 Connection",
                hcl_snippet="# Configure mtls_connection_required = true inside Autonomous DB properties {}",
                iam_roles=["roles/compute.networkUser"],
                ip_math=cidr_report["vpc_math"]["summary"],
                editable_field="vpc_cidr",
            ),
            _node(
                "client_subnet",
                "CLIENT_SUBNET",
                f"Private Endpoint ({c_cidr})",
                55,
                325,
                230,
                95,
                team_owner="network",
                terraform_resource="google_oracle_database_odb_subnet",
                hcl_snippet=hcl_client_sub,
                iam_roles=["roles/oracledatabase.networkAdmin"],
                ip_math=cidr_report["client_math"]["summary"],
                editable_field="client_subnet_cidr",
            ),
            _node(
                "odb_sa",
                "ODB GCP Service Agent",
                "service-<NUM>@gcp-sa-oracledatabase",
                375,
                145,
                300,
                98,
                team_owner="infrastructure",
                terraform_resource="google_project_service_identity",
                hcl_snippet=(
                    f'resource "google_project_service_identity" "odb_sa" {{\n'
                    f'  provider = google-beta\n'
                    f'  project  = "{proj}"\n'
                    f'  service  = "oracledatabase.googleapis.com"\n'
                    f'}}'
                ),
                iam_roles=["roles/serviceusage.serviceUsageAdmin"],
            ),
            _node(
                "cmek_kms",
                "Cloud KMS CryptoKey",
                f"HSM / EKM / Software ({reg})",
                375,
                325,
                300,
                98,
                team_owner="infrastructure",
                layer="core",
                terraform_resource="google_kms_crypto_key",
                hcl_snippet=hcl_cmek,
                iam_roles=["roles/cloudkms.admin", "roles/cloudkms.cryptoKeyEncrypterDecrypter"],
            ),
            _node(
                "workload_db",
                f"{w_label} (TDE)",
                "Master Encryption Key Envelope",
                770,
                150,
                285,
                98,
                team_owner="database",
                terraform_resource=w_res,
                hcl_snippet=hcl_workload,
                iam_roles=["roles/oracledatabase.autonomousDatabaseAdmin"],
                editable_field="workload_type",
            ),
            _node(
                "tde_storage",
                "AES-256 Encrypted Datafiles",
                "Tablespaces, Flash, Redo & RMAN",
                770,
                325,
                285,
                98,
                team_owner="database",
                terraform_resource="Oracle TDE Tablespaces",
                hcl_snippet="# Transparent Data Encryption (TDE) is always active at rest; CMEK controls the master key.",
                iam_roles=["roles/oracledatabase.viewer"],
            ),
        ]
        edges = [
            {"id": "e1", "from": "vpc", "to": "client_subnet", "label": "mTLS 2484", "flow_type": "sql", "layer": "core"},
            {"id": "e2", "from": "client_subnet", "to": "workload_db", "label": "Encrypted SQL", "flow_type": "sql", "layer": "core"},
            {"id": "e3", "from": "odb_sa", "to": "cmek_kms", "label": "EncrypterDecrypter IAM", "flow_type": "cmek", "layer": "core"},
            {"id": "e4", "from": "cmek_kms", "to": "workload_db", "label": "Envelope Key Wrap", "flow_type": "cmek", "layer": "core"},
            {"id": "e5", "from": "workload_db", "to": "tde_storage", "label": "AES-256 Data Encryption", "flow_type": "cmek", "layer": "core"},
        ]

    elif dtype in ("monitoring_observability", "monitoring_and_observability_flow"):
        title = f"Dual-Plane Monitoring, Audit Logging & Oracle Diagnostics ({proj} • {ozone})"
        groups = [
            {"id": "g_src", "label": f"ODB@GCP Workload Plane ({ozone})", "x": 35, "y": 90, "width": 330, "height": 420, "team_owner": "database"},
            {"id": "g_gcp", "label": f"Google Cloud Observability ({proj})", "x": 415, "y": 50, "width": 665, "height": 235, "team_owner": "platform"},
            {"id": "g_ora", "label": "Oracle Deep Diagnostics (Federated oci_url)", "x": 415, "y": 315, "width": 665, "height": 235, "team_owner": "database"},
        ]
        nodes = [
            _node(
                "workload_db",
                w_label,
                f"{cpus} ECPUs • {tbs} TB ({ozone})",
                65,
                165,
                270,
                105,
                team_owner="database",
                terraform_resource=w_res,
                hcl_snippet=hcl_workload,
                iam_roles=["roles/oracledatabase.viewer", "roles/oracledatabase.autonomousDatabaseAdmin"],
                editable_field="workload_type",
            ),
            _node(
                "cmek_kms",
                "Cloud KMS Audit Trail",
                f"Key Usage Access Logs ({reg})",
                65,
                340,
                270,
                90,
                team_owner="infrastructure",
                layer="cmek",
                terraform_resource="Cloud KMS Data Access Logs",
                hcl_snippet=hcl_cmek,
                iam_roles=["roles/logging.privateLogViewer"],
            ),
            _node(
                "cloud_mon",
                "Google Cloud Monitoring",
                "oracledatabase.googleapis.com/*",
                450,
                115,
                285,
                100,
                team_owner="platform",
                terraform_resource="google_monitoring_alert_policy",
                hcl_snippet=(
                    '# Metrics: cpu_utilization, storage_utilization, iops, active_sessions\n'
                    '# Filter: resource.type="oracledatabase.googleapis.com/AutonomousDatabase"'
                ),
                iam_roles=["roles/monitoring.viewer", "roles/monitoring.alertPolicyEditor"],
            ),
            _node(
                "cloud_log",
                "Cloud Logging & Audit Logs",
                "cloudaudit.googleapis.com/activity",
                765,
                115,
                285,
                100,
                team_owner="platform",
                terraform_resource="google_logging_project_sink",
                hcl_snippet="# Captures control-plane mutations, Day-2 scaling events, and IAM checks.",
                iam_roles=["roles/logging.viewer"],
            ),
            _node(
                "ora_opi",
                "Oracle Operations Insights",
                "SQL Warehouse & Capacity Forecast",
                450,
                380,
                285,
                100,
                team_owner="database",
                terraform_resource="operations_insights_state",
                hcl_snippet='operations_insights_state = "ENABLED"',
                iam_roles=["roles/oracledatabase.viewer"],
            ),
            _node(
                "ora_awr",
                "AWR, ASH & DB Management",
                "Wait Events & Execution Plans",
                765,
                380,
                285,
                100,
                team_owner="database",
                terraform_resource="data_collection_options",
                hcl_snippet=(
                    "data_collection_options {\n"
                    "  is_diagnostics_events_enabled = true\n"
                    "  is_health_monitoring_enabled  = true\n"
                    "}"
                ),
                iam_roles=["roles/oracledatabase.viewer"],
            ),
        ]
        edges = [
            {"id": "e1", "from": "workload_db", "to": "cloud_mon", "label": "CPU / Storage / IOPS", "flow_type": "telemetry", "layer": "core"},
            {"id": "e2", "from": "workload_db", "to": "cloud_log", "label": "Admin & Event Logs", "flow_type": "telemetry", "layer": "core"},
            {"id": "e3", "from": "workload_db", "to": "ora_opi", "label": "SQL Telemetry", "flow_type": "telemetry", "layer": "core", "dashed": True},
            {"id": "e4", "from": "workload_db", "to": "ora_awr", "label": "ASH / AWR Snapshots", "flow_type": "telemetry", "layer": "core", "dashed": True},
            {"id": "e5", "from": "cmek_kms", "to": "cloud_log", "label": "KMS Crypto Audit", "flow_type": "cmek", "layer": "cmek", "dashed": True},
        ]

    else:
        # Default / networking_standalone_vpc
        dtype = "networking_standalone_vpc"
        title = f"Standalone Single-Project VPC & ODB Network Topology ({proj} • {reg} / {ozone})"
        groups = [
            {"id": "g_gcp", "label": f"Google Cloud Project ({proj}) — Customer VPC ({v_cidr})", "x": 30, "y": 50, "width": 360, "height": 505, "team_owner": "network"},
            {"id": "g_odb", "label": f"Colocated Oracle Database@Google Cloud Zone ({ozone})", "x": 430, "y": 50, "width": 660, "height": 505, "team_owner": "database"},
        ]
        nodes = [
            _node(
                "vpc",
                "Customer VPC & App Tier",
                f"GKE / GCE ({v_cidr})",
                65,
                125,
                285,
                95,
                team_owner="network",
                terraform_resource="google_compute_network",
                hcl_snippet=(
                    f'resource "google_compute_network" "vpc" {{\n'
                    f'  name                    = "odb-prod-vpc"\n'
                    f'  project                 = "{proj}"\n'
                    f'  auto_create_subnetworks = false\n'
                    f'}}'
                ),
                iam_roles=["roles/compute.networkAdmin"],
                ip_math=cidr_report["vpc_math"]["summary"],
                editable_field="vpc_cidr",
            ),
            _node(
                "cloud_dns",
                "Cloud DNS Private Zone",
                "*.oraclevcn.com Auto-Forwarded",
                65,
                280,
                285,
                90,
                team_owner="network",
                terraform_resource="Cloud DNS Peering",
                hcl_snippet="# Automatically resolves private SCAN & Autonomous DB FQDNs inside Customer VPC",
                iam_roles=["roles/dns.admin"],
            ),
            _node(
                "cmek_kms",
                "Cloud KMS CMEK Key",
                f"gcp-sa-oracledatabase ({reg})",
                65,
                420,
                285,
                92,
                team_owner="infrastructure",
                layer="cmek",
                terraform_resource="google_kms_crypto_key_iam_member",
                hcl_snippet=hcl_cmek,
                iam_roles=["roles/cloudkms.cryptoKeyEncrypterDecrypter"],
            ),
            _node(
                "odb_net",
                "ODB Partner Network",
                f"Partner Interconnect (<2ms)",
                465,
                125,
                260,
                95,
                team_owner="network",
                terraform_resource="google_oracle_database_odb_network",
                hcl_snippet=hcl_odb_net,
                iam_roles=["roles/oracledatabase.networkAdmin", "roles/compute.networkAdmin"],
            ),
            _node(
                "client_subnet",
                "CLIENT_SUBNET",
                f"SQL App Subnet ({c_cidr})",
                465,
                275,
                260,
                92,
                team_owner="network",
                terraform_resource="google_oracle_database_odb_subnet",
                hcl_snippet=hcl_client_sub,
                iam_roles=["roles/oracledatabase.networkAdmin"],
                ip_math=cidr_report["client_math"]["summary"],
                editable_field="client_subnet_cidr",
            ),
            _node(
                "backup_subnet",
                "BACKUP_SUBNET",
                f"RMAN Subnet ({b_cidr})",
                465,
                415,
                260,
                92,
                team_owner="network",
                terraform_resource="google_oracle_database_odb_subnet",
                hcl_snippet=hcl_backup_sub,
                iam_roles=["roles/oracledatabase.networkAdmin"],
                ip_math=cidr_report["backup_math"]["summary"],
                editable_field="backup_subnet_cidr",
            ),
            _node(
                "workload_db",
                w_label,
                f"{cpus} ECPUs • {tbs} TB • {dlayer}",
                785,
                215,
                275,
                105,
                team_owner="database",
                terraform_resource=w_res,
                hcl_snippet=hcl_workload,
                iam_roles=[
                    "roles/oracledatabase.autonomousDatabaseAdmin",
                    "roles/oracledatabase.exadataAdmin",
                    "roles/oracledatabase.viewer",
                ],
                editable_field="workload_type",
            ),
            _node(
                "dr_standby",
                "Standby DR Database",
                "Cross-Zone Data Guard Sync",
                785,
                410,
                275,
                95,
                team_owner="database",
                layer="dr",
                terraform_resource="Data Guard Standby",
                hcl_snippet="# Optional Data Guard standby in secondary Oracle Zone",
                iam_roles=["roles/oracledatabase.exadataAdmin"],
            ),
        ]
        edges = [
            {"id": "e1", "from": "vpc", "to": "odb_net", "label": "Partner Peering (<2ms)", "flow_type": "sql", "layer": "core"},
            {"id": "e2", "from": "cloud_dns", "to": "client_subnet", "label": "*.oraclevcn.com DNS", "flow_type": "dns", "layer": "core", "dashed": True},
            {"id": "e3", "from": "odb_net", "to": "client_subnet", "label": "Client Plane", "flow_type": "sql", "layer": "core"},
            {"id": "e4", "from": "odb_net", "to": "backup_subnet", "label": "Backup Plane", "flow_type": "backup", "layer": "core", "dashed": True},
            {"id": "e5", "from": "client_subnet", "to": "workload_db", "label": "SQL*Net 1521/2484", "flow_type": "sql", "layer": "core"},
            {"id": "e6", "from": "backup_subnet", "to": "workload_db", "label": "RMAN Backup I/O", "flow_type": "backup", "layer": "core", "dashed": True},
            {"id": "e7", "from": "cmek_kms", "to": "workload_db", "label": "CMEK Key Wrap", "flow_type": "cmek", "layer": "cmek", "dashed": True},
            {"id": "e8", "from": "workload_db", "to": "dr_standby", "label": "Data Guard Redo", "flow_type": "dr", "layer": "dr", "dashed": True},
        ]

    return {
        "diagram_type": dtype,
        "title": title,
        "viewBox": {"width": 1110, "height": 585},
        "blueprint": {
            "project_id": proj,
            "region": reg,
            "gcp_oracle_zone": ozone,
            "vpc_cidr": v_cidr,
            "client_subnet_cidr": c_cidr,
            "backup_subnet_cidr": b_cidr,
            "workload_type": wkl,
            "deployment_layer": dlayer,
            "compute_count": cpus,
            "storage_size_tb": tbs,
        },
        "cidr_validation": cidr_report,
        "groups": groups,
        "nodes": nodes,
        "edges": edges,
    }


INTERACTIVE_DIAGRAM_HTML = """
<div class="odb-explorer-shell" id="odb-explorer-root">
  <div class="odb-toolbar" role="toolbar" aria-label="Architecture diagram controls">
    <div class="odb-toolbar-left">
      <button type="button" class="odb-btn" data-action="zoom-in" title="Zoom in">+</button>
      <button type="button" class="odb-btn" data-action="zoom-out" title="Zoom out">-</button>
      <button type="button" class="odb-btn" data-action="zoom-reset" title="Reset zoom and pan">Reset</button>
      <input type="search" class="odb-search" id="odb-node-search" placeholder="Search resource, CIDR, or IAM role..." aria-label="Search diagram nodes" />
    </div>
    <div class="odb-toolbar-toggles">
      <button type="button" class="odb-pill active" data-toggle="animateFlows">Animate Flows</button>
      <button type="button" class="odb-pill" data-toggle="showTeamColors">Team Ownership (SoD)</button>
      <button type="button" class="odb-pill" data-toggle="showCmek">CMEK Layer</button>
      <button type="button" class="odb-pill" data-toggle="showDr">Data Guard DR</button>
    </div>
  </div>
  <div class="odb-legend-bar" id="odb-legend-bar"></div>
  <div class="odb-validation-banner" id="odb-validation-banner" hidden></div>
  <div class="odb-workspace-split">
    <div class="odb-canvas-wrap" id="odb-canvas-wrap">
      <svg class="odb-svg-canvas" id="odb-svg-canvas" viewBox="0 0 1110 585" role="img" aria-label="Interactive Oracle Database at Google Cloud topology diagram"></svg>
      <div class="odb-canvas-hint">Scroll to zoom • Drag background to pan • Click any node to inspect HCL, IAM &amp; edit blueprint</div>
    </div>
    <aside class="odb-drawer" id="odb-drawer" aria-label="Resource inspector and blueprint editor">
      <div class="odb-drawer-tabs">
        <button type="button" class="odb-tab active" data-tab="inspect">Resource Inspector</button>
        <button type="button" class="odb-tab" data-tab="blueprint">Visual Blueprint Editor</button>
      </div>
      <div class="odb-drawer-body" id="odb-drawer-body"></div>
    </aside>
  </div>
</div>
"""

INTERACTIVE_DIAGRAM_CSS = """
.odb-explorer-shell {
  font-family: var(--st-font, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif);
  color: var(--st-text-color, #0f172a);
  background: var(--st-background-color, #ffffff);
  border: 1px solid var(--st-border-color, #cbd5e1);
  border-radius: var(--st-base-radius, 10px);
  overflow: hidden;
  box-sizing: border-box;
}
.odb-explorer-shell *, .odb-explorer-shell *::before, .odb-explorer-shell *::after {
  box-sizing: border-box;
}
.odb-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  background: var(--st-secondary-background-color, #f8fafc);
  border-bottom: 1px solid var(--st-border-color, #e2e8f0);
}
.odb-toolbar-left, .odb-toolbar-toggles {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}
.odb-btn {
  padding: 5px 10px;
  font-size: 12px;
  font-weight: 600;
  color: var(--st-text-color, #0f172a);
  background: var(--st-background-color, #ffffff);
  border: 1px solid var(--st-border-color, #cbd5e1);
  border-radius: var(--st-button-radius, 6px);
  cursor: pointer;
}
.odb-btn:hover {
  border-color: var(--st-primary-color, #2563eb);
}
.odb-btn-primary {
  width: 100%;
  padding: 8px 12px;
  margin-top: 8px;
  background: var(--st-primary-color, #2563eb);
  color: #ffffff;
  border: none;
  border-radius: var(--st-button-radius, 6px);
  font-weight: 600;
  cursor: pointer;
}
.odb-btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.odb-search {
  padding: 5px 10px;
  min-width: 210px;
  font-size: 12px;
  color: var(--st-text-color, #0f172a);
  background: var(--st-background-color, #ffffff);
  border: 1px solid var(--st-border-color, #cbd5e1);
  border-radius: var(--st-button-radius, 6px);
}
.odb-pill {
  padding: 5px 10px;
  font-size: 12px;
  font-weight: 600;
  border-radius: 999px;
  border: 1px solid var(--st-border-color, #cbd5e1);
  background: var(--st-background-color, #ffffff);
  color: var(--st-text-color, #334155);
  cursor: pointer;
}
.odb-pill.active {
  background: var(--st-primary-color, #2563eb);
  border-color: var(--st-primary-color, #2563eb);
  color: #ffffff;
}
.odb-legend-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  padding: 6px 12px;
  font-size: 11px;
  background: var(--st-background-color, #ffffff);
  border-bottom: 1px solid var(--st-border-color, #e2e8f0);
}
.odb-legend-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.odb-legend-swatch {
  width: 10px;
  height: 10px;
  border-radius: 3px;
  display: inline-block;
}
.odb-validation-banner {
  padding: 8px 12px;
  font-size: 12px;
  font-weight: 600;
  background: var(--st-red-background-color, #fef2f2);
  color: var(--st-red-text-color, #b91c1c);
  border-bottom: 1px solid var(--st-red-color, #ef4444);
}
.odb-validation-banner.ok {
  background: var(--st-green-background-color, #f0fdf4);
  color: var(--st-green-text-color, #15803d);
  border-bottom-color: var(--st-green-color, #22c55e);
}
.odb-workspace-split {
  display: grid;
  grid-template-columns: minmax(0, 1.85fr) minmax(300px, 1fr);
  min-height: 540px;
}
@media (max-width: 920px) {
  .odb-workspace-split {
    grid-template-columns: 1fr;
  }
}
.odb-canvas-wrap {
  position: relative;
  background: var(--st-background-color, #ffffff);
  border-right: 1px solid var(--st-border-color, #e2e8f0);
  overflow: hidden;
  user-select: none;
}
.odb-svg-canvas {
  width: 100%;
  height: 540px;
  display: block;
  cursor: grab;
}
.odb-svg-canvas:active {
  cursor: grabbing;
}
.odb-canvas-hint {
  position: absolute;
  left: 10px;
  bottom: 8px;
  padding: 3px 8px;
  font-size: 11px;
  border-radius: 4px;
  background: var(--st-secondary-background-color, rgba(248, 250, 252, 0.92));
  color: var(--st-text-color, #475569);
  border: 1px solid var(--st-border-color, #e2e8f0);
  pointer-events: none;
}
.odb-drawer {
  display: flex;
  flex-direction: column;
  background: var(--st-secondary-background-color, #f8fafc);
  max-height: 540px;
}
.odb-drawer-tabs {
  display: grid;
  grid-template-columns: 1fr 1fr;
  border-bottom: 1px solid var(--st-border-color, #cbd5e1);
}
.odb-tab {
  padding: 9px 8px;
  font-size: 12px;
  font-weight: 600;
  background: transparent;
  color: var(--st-text-color, #475569);
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
}
.odb-tab.active {
  color: var(--st-primary-color, #2563eb);
  border-bottom-color: var(--st-primary-color, #2563eb);
  background: var(--st-background-color, #ffffff);
}
.odb-drawer-body {
  padding: 12px;
  overflow-y: auto;
  flex: 1;
  font-size: 12.5px;
}
.odb-card {
  background: var(--st-background-color, #ffffff);
  border: 1px solid var(--st-border-color, #e2e8f0);
  border-radius: 8px;
  padding: 10px;
  margin-bottom: 10px;
}
.odb-card-title {
  font-size: 13px;
  font-weight: 700;
  margin: 0 0 4px 0;
}
.odb-meta-label {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  opacity: 0.72;
  margin: 8px 0 4px 0;
}
.odb-code {
  font-family: var(--st-code-font, ui-monospace, SFMono-Regular, Menlo, monospace);
  font-size: 11.5px;
  background: var(--st-code-background-color, #0f172a);
  color: var(--st-code-text-color, #f8fafc);
  padding: 8px;
  border-radius: 6px;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
  margin: 4px 0;
}
.odb-role-chip {
  display: inline-block;
  padding: 2px 7px;
  margin: 2px 4px 2px 0;
  font-size: 11px;
  font-family: var(--st-code-font, monospace);
  border-radius: 4px;
  background: var(--st-secondary-background-color, #e2e8f0);
  border: 1px solid var(--st-border-color, #cbd5e1);
}
.odb-alert-box {
  padding: 8px 10px;
  border-radius: 6px;
  margin-bottom: 10px;
  font-size: 12px;
  border: 1px solid #ef4444;
  background: rgba(239, 68, 68, 0.1);
}
.odb-alert-box.safe {
  border-color: #22c55e;
  background: rgba(34, 197, 94, 0.1);
}
.odb-alert-box.warn {
  border-color: #f59e0b;
  background: rgba(245, 158, 11, 0.12);
}
.odb-field {
  margin-bottom: 8px;
}
.odb-field label {
  display: block;
  font-size: 11.5px;
  font-weight: 600;
  margin-bottom: 3px;
}
.odb-field input, .odb-field select {
  width: 100%;
  padding: 5px 8px;
  font-size: 12px;
  color: var(--st-text-color, #0f172a);
  background: var(--st-background-color, #ffffff);
  border: 1px solid var(--st-border-color, #cbd5e1);
  border-radius: 5px;
}
.odb-node-group {
  cursor: pointer;
  transition: opacity 0.15s ease;
}
.odb-node-group.dimmed {
  opacity: 0.25;
}
@keyframes odbDashFlow {
  to {
    stroke-dashoffset: -28;
  }
}
.odb-edge-animated {
  stroke-dasharray: 7 7;
  animation: odbDashFlow 0.9s linear infinite;
}
@keyframes odbHazardPulse {
  0%, 100% { stroke-width: 2.5; }
  50% { stroke-width: 4.5; }
}
.odb-hazard-rect {
  animation: odbHazardPulse 1.2s ease-in-out infinite;
}
"""

INTERACTIVE_DIAGRAM_JS = """
const INSTANCE_STATE = new WeakMap();

const TEAM_PALETTE = {
  procurement: { label: "Procurement / Billing", stroke: "#d97706", fill: "rgba(245, 158, 11, 0.13)" },
  network: { label: "Network Admin (network_only)", stroke: "#2563eb", fill: "rgba(37, 99, 235, 0.12)" },
  infrastructure: { label: "Infra Admin (infra_only)", stroke: "#7c3aed", fill: "rgba(124, 58, 237, 0.12)" },
  database: { label: "Oracle DBA (database_only)", stroke: "#059669", fill: "rgba(5, 150, 105, 0.12)" },
  platform: { label: "Platform / App Tier", stroke: "#475569", fill: "rgba(100, 116, 139, 0.10)" }
};

const STATUS_PALETTE = {
  verified: { stroke: "#16a34a", badgeBg: "#16a34a", cls: "safe" },
  warning: { stroke: "#d97706", badgeBg: "#d97706", cls: "warn" },
  blocker: { stroke: "#dc2626", badgeBg: "#dc2626", cls: "err" },
  scaling_safe: { stroke: "#0284c7", badgeBg: "#0284c7", cls: "safe" },
  forcenew_hazard: { stroke: "#dc2626", badgeBg: "#b91c1c", cls: "err" }
};

const FLOW_COLORS = {
  sql: "#2563eb",
  dns: "#0891b2",
  backup: "#7c3aed",
  cmek: "#d97706",
  dr: "#dc2626",
  telemetry: "#059669",
  control: "#64748b"
};

function el(tag, attrs, text) {
  const node = document.createElement(tag);
  if (attrs) {
    Object.keys(attrs).forEach((k) => {
      if (attrs[k] !== undefined && attrs[k] !== null) {
        node.setAttribute(k, String(attrs[k]));
      }
    });
  }
  if (text !== undefined && text !== null) {
    node.textContent = String(text);
  }
  return node;
}

function svgEl(tag, attrs, text) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  if (attrs) {
    Object.keys(attrs).forEach((k) => {
      if (attrs[k] !== undefined && attrs[k] !== null) {
        node.setAttribute(k, String(attrs[k]));
      }
    });
  }
  if (text !== undefined && text !== null) {
    node.textContent = String(text);
  }
  return node;
}

function parseIpv4Cidr(raw, requireMin28) {
  const trimmed = String(raw || "").trim();
  const parts = trimmed.split("/");
  if (parts.length !== 2) {
    return { valid: false, summary: "Invalid CIDR format (expected A.B.C.D/prefix)." };
  }
  const octets = parts[0].split(".");
  const prefix = Number(parts[1]);
  if (octets.length !== 4 || !Number.isInteger(prefix) || prefix < 8 || prefix > 32) {
    return { valid: false, summary: "Invalid IPv4 address or prefix length." };
  }
  let ipInt = 0;
  for (let i = 0; i < 4; i += 1) {
    const n = Number(octets[i]);
    if (!Number.isInteger(n) || n < 0 || n > 255) {
      return { valid: false, summary: "IPv4 octets must be 0..255." };
    }
    ipInt = ((ipInt << 8) | n) >>> 0;
  }
  const isPrivate =
    octets[0] === "10" ||
    (Number(octets[0]) === 172 && Number(octets[1]) >= 16 && Number(octets[1]) <= 31) ||
    (Number(octets[0]) === 192 && Number(octets[1]) === 168);

  const mask = prefix === 0 ? 0 : ((0xffffffff << (32 - prefix)) >>> 0);
  const netStart = (ipInt & mask) >>> 0;
  const total = Math.pow(2, 32 - prefix);
  const netEnd = netStart + total - 1;
  const usable = Math.max(0, total - 5);

  if (requireMin28 && prefix > 28) {
    return {
      valid: false,
      netStart,
      netEnd,
      usable,
      summary: "Invalid ODB subnet /" + prefix + ": minimum prefix is /28 (16 IPs)."
    };
  }
  if (!isPrivate) {
    return {
      valid: false,
      netStart,
      netEnd,
      usable,
      summary: "CIDR " + trimmed + " is not private RFC1918 space."
    };
  }
  return {
    valid: true,
    netStart,
    netEnd,
    usable,
    summary: trimmed + " (" + usable + " usable IPs)"
  };
}

function validateClientBlueprint(bp) {
  const vpc = parseIpv4Cidr(bp.vpc_cidr, false);
  const cli = parseIpv4Cidr(bp.client_subnet_cidr, true);
  const bak = parseIpv4Cidr(bp.backup_subnet_cidr, true);
  const errors = [];
  const nodeFlags = {};

  if (!vpc.valid) { errors.push("VPC: " + vpc.summary); nodeFlags.vpc = vpc.summary; }
  if (!cli.valid) { errors.push("CLIENT_SUBNET: " + cli.summary); nodeFlags.client_subnet = cli.summary; }
  if (!bak.valid) { errors.push("BACKUP_SUBNET: " + bak.summary); nodeFlags.backup_subnet = bak.summary; }

  const overlaps = (a, b) => a.netStart !== undefined && b.netStart !== undefined && a.netStart <= b.netEnd && b.netStart <= a.netEnd;
  if (cli.valid && bak.valid && overlaps(cli, bak)) {
    const msg = "CIDR Collision: CLIENT_SUBNET overlaps BACKUP_SUBNET.";
    errors.push(msg);
    nodeFlags.client_subnet = msg;
    nodeFlags.backup_subnet = msg;
  }
  if (vpc.valid && cli.valid && overlaps(vpc, cli)) {
    const msg = "CIDR Collision: Customer VPC overlaps CLIENT_SUBNET.";
    errors.push(msg);
    nodeFlags.vpc = msg;
    nodeFlags.client_subnet = msg;
  }
  if (vpc.valid && bak.valid && overlaps(vpc, bak)) {
    const msg = "CIDR Collision: Customer VPC overlaps BACKUP_SUBNET.";
    errors.push(msg);
    nodeFlags.vpc = msg;
    nodeFlags.backup_subnet = msg;
  }
  return { valid: errors.length === 0, errors, nodeFlags, vpc, cli, bak };
}

export default function renderOdbInteractiveDiagram(component) {
  const { data, parentElement, setStateValue, setTriggerValue } = component;
  if (!parentElement || !data || !data.spec) return;

  const root = parentElement.querySelector("#odb-explorer-root");
  if (!root) return;

  let st = INSTANCE_STATE.get(parentElement);
  if (!st) {
    st = {
      zoom: 1.0,
      panX: 0,
      panY: 0,
      isDragging: false,
      dragStartX: 0,
      dragStartY: 0,
      searchQuery: "",
      animateFlows: true,
      showTeamColors: false,
      showCmek: false,
      showDr: false,
      activeTab: "inspect",
      selectedNodeId: null,
      specFingerprint: "",
      blueprint: null,
      statusNotice: ""
    };
    INSTANCE_STATE.set(parentElement, st);
  }

  const spec = data.spec;
  const incomingFp = JSON.stringify({
    dt: spec.diagram_type,
    bp: spec.blueprint,
    ov: (spec.nodes || []).map((n) => n.status_overlay)
  });

  if (st.specFingerprint !== incomingFp) {
    st.specFingerprint = incomingFp;
    st.blueprint = Object.assign({}, spec.blueprint || {});
    if (spec.diagram_type === "encryption_cmek") st.showCmek = true;
    if (spec.diagram_type === "networking_hub_and_spoke_ha_dr") st.showDr = true;
    const firstNode = (spec.nodes || [])[0];
    if (!st.selectedNodeId || !(spec.nodes || []).some((n) => n.id === st.selectedNodeId)) {
      st.selectedNodeId = firstNode ? firstNode.id : null;
    }
  }

  const svg = root.querySelector("#odb-svg-canvas");
  const legendBar = root.querySelector("#odb-legend-bar");
  const banner = root.querySelector("#odb-validation-banner");
  const drawerBody = root.querySelector("#odb-drawer-body");
  const searchInput = root.querySelector("#odb-node-search");

  function isLayerVisible(layerName) {
    if (!layerName || layerName === "core") return true;
    if (layerName === "cmek") return st.showCmek;
    if (layerName === "dr") return st.showDr;
    return true;
  }

  function effectiveNodeSubtitle(n, bpCheck) {
    const bp = st.blueprint || {};
    if (n.id === "vpc") return "CIDR: " + bp.vpc_cidr + (bpCheck.vpc.usable !== undefined ? " (" + bpCheck.vpc.usable + " IPs)" : "");
    if (n.id === "client_subnet") return "CLIENT: " + bp.client_subnet_cidr + (bpCheck.cli.usable !== undefined ? " (" + bpCheck.cli.usable + " IPs)" : "");
    if (n.id === "backup_subnet") return "BACKUP: " + bp.backup_subnet_cidr + (bpCheck.bak.usable !== undefined ? " (" + bpCheck.bak.usable + " IPs)" : "");
    if (n.id === "workload_db" || n.id === "phase5_provision") {
      return bp.workload_type + " • " + bp.compute_count + " ECPUs • " + bp.storage_size_tb + " TB (" + bp.deployment_layer + ")";
    }
    if (n.id === "phase1_iam") return "Project: " + bp.project_id;
    return n.subtitle || "";
  }

  function effectiveOverlay(n, bpCheck) {
    if (bpCheck.nodeFlags[n.id]) {
      return {
        state: "blocker",
        badge_text: "CIDR COLLISION / <28",
        detail: bpCheck.nodeFlags[n.id],
        remediation_cmd: "# Update CIDR in the Visual Blueprint Editor so all ranges are RFC1918, non-overlapping, and >= /28."
      };
    }
    return n.status_overlay || { state: "neutral", badge_text: "", detail: "", remediation_cmd: "" };
  }

  function renderLegend() {
    legendBar.replaceChildren();
    if (st.showTeamColors) {
      Object.keys(TEAM_PALETTE).forEach((k) => {
        const item = el("span", { class: "odb-legend-item" });
        const sw = el("span", { class: "odb-legend-swatch", style: "background:" + TEAM_PALETTE[k].stroke });
        item.appendChild(sw);
        item.appendChild(el("span", null, TEAM_PALETTE[k].label));
        legendBar.appendChild(item);
      });
    } else {
      [
        ["SQL*Net / Peering", FLOW_COLORS.sql],
        ["Private DNS (*.oraclevcn.com)", FLOW_COLORS.dns],
        ["RMAN Backup Plane", FLOW_COLORS.backup],
        ["CMEK Key Wrap", FLOW_COLORS.cmek],
        ["Data Guard Redo", FLOW_COLORS.dr]
      ].forEach((pair) => {
        const item = el("span", { class: "odb-legend-item" });
        const sw = el("span", { class: "odb-legend-swatch", style: "background:" + pair[1] });
        item.appendChild(sw);
        item.appendChild(el("span", null, pair[0]));
        legendBar.appendChild(item);
      });
    }
  }

  function renderBanner(bpCheck) {
    if (!bpCheck.valid) {
      banner.hidden = false;
      banner.className = "odb-validation-banner";
      banner.textContent = bpCheck.errors.join("  •  ");
    } else if (st.statusNotice) {
      banner.hidden = false;
      banner.className = "odb-validation-banner ok";
      banner.textContent = st.statusNotice;
    } else {
      banner.hidden = true;
      banner.textContent = "";
    }
  }

  function renderSvg(bpCheck) {
    svg.replaceChildren();
    const vbW = (spec.viewBox && spec.viewBox.width) || 1110;
    const vbH = (spec.viewBox && spec.viewBox.height) || 585;
    svg.setAttribute("viewBox", "0 0 " + vbW + " " + vbH);

    const defs = svgEl("defs");
    Object.keys(FLOW_COLORS).forEach((fk) => {
      const marker = svgEl("marker", {
        id: "odb-arrow-" + fk,
        viewBox: "0 0 10 10",
        refX: "9",
        refY: "5",
        markerWidth: "6",
        markerHeight: "6",
        orient: "auto-start-reverse"
      });
      marker.appendChild(svgEl("path", { d: "M 0 1 L 10 5 L 0 9 z", fill: FLOW_COLORS[fk] }));
      defs.appendChild(marker);
    });
    svg.appendChild(defs);

    const viewport = svgEl("g", {
      transform: "translate(" + st.panX + "," + st.panY + ") scale(" + st.zoom + ")"
    });

    // Groups
    (spec.groups || []).forEach((grp) => {
      const teamTheme = TEAM_PALETTE[grp.team_owner] || TEAM_PALETTE.platform;
      const gStroke = st.showTeamColors ? teamTheme.stroke : "#94a3b8";
      const gFill = st.showTeamColors ? teamTheme.fill : "rgba(148, 163, 184, 0.07)";
      const gBox = svgEl("g");
      gBox.appendChild(
        svgEl("rect", {
          x: grp.x,
          y: grp.y,
          width: grp.width,
          height: grp.height,
          rx: 12,
          fill: gFill,
          stroke: gStroke,
          "stroke-width": "1.5",
          "stroke-dasharray": "6 4"
        })
      );
      gBox.appendChild(
        svgEl(
          "text",
          {
            x: grp.x + 14,
            y: grp.y + 22,
            fill: gStroke,
            "font-size": "12",
            "font-weight": "700"
          },
          grp.label
        )
      );
      viewport.appendChild(gBox);
    });

    const nodeMap = {};
    (spec.nodes || []).forEach((n) => {
      if (isLayerVisible(n.layer)) {
        nodeMap[n.id] = n;
      }
    });

    // Edges
    (spec.edges || []).forEach((ed) => {
      if (!isLayerVisible(ed.layer)) return;
      const src = nodeMap[ed.from];
      const dst = nodeMap[ed.to];
      if (!src || !dst) return;

      const srcCx = src.x + src.width / 2;
      const srcCy = src.y + src.height / 2;
      const dstCx = dst.x + dst.width / 2;
      const dstCy = dst.y + dst.height / 2;

      let x1 = srcCx;
      let y1 = srcCy;
      let x2 = dstCx;
      let y2 = dstCy;

      if (Math.abs(dstCx - srcCx) >= Math.abs(dstCy - srcCy)) {
        x1 = dstCx >= srcCx ? src.x + src.width : src.x;
        x2 = dstCx >= srcCx ? dst.x : dst.x + dst.width;
      } else {
        y1 = dstCy >= srcCy ? src.y + src.height : src.y;
        y2 = dstCy >= srcCy ? dst.y : dst.y + dst.height;
      }

      const midX = (x1 + x2) / 2;
      const dPath = "M " + x1 + " " + y1 + " C " + midX + " " + y1 + ", " + midX + " " + y2 + ", " + x2 + " " + y2;
      const fType = FLOW_COLORS[ed.flow_type] ? ed.flow_type : "control";
      const color = FLOW_COLORS[fType];

      const pathAttrs = {
        d: dPath,
        fill: "none",
        stroke: color,
        "stroke-width": "2.2",
        "marker-end": "url(#odb-arrow-" + fType + ")"
      };
      if (st.animateFlows) {
        pathAttrs.class = "odb-edge-animated";
      } else if (ed.dashed) {
        pathAttrs["stroke-dasharray"] = "5 5";
      }
      viewport.appendChild(svgEl("path", pathAttrs));

      if (ed.label) {
        const lx = (x1 + x2) / 2;
        const ly = (y1 + y2) / 2 - 6;
        const labelBgW = Math.max(66, ed.label.length * 6.2 + 12);
        viewport.appendChild(
          svgEl("rect", {
            x: lx - labelBgW / 2,
            y: ly - 11,
            width: labelBgW,
            height: 16,
            rx: 4,
            fill: "#0f172a",
            opacity: "0.84"
          })
        );
        viewport.appendChild(
          svgEl(
            "text",
            {
              x: lx,
              y: ly + 1,
              "text-anchor": "middle",
              fill: "#f8fafc",
              "font-size": "10",
              "font-weight": "600"
            },
            ed.label
          )
        );
      }
    });

    // Nodes
    const q = st.searchQuery.trim().toLowerCase();
    Object.keys(nodeMap).forEach((nid) => {
      const n = nodeMap[nid];
      const subText = effectiveNodeSubtitle(n, bpCheck);
      const ov = effectiveOverlay(n, bpCheck);
      const isSelected = st.selectedNodeId === n.id;

      const hay = [n.label, subText, n.terraform_resource, (n.iam_roles || []).join(" ")].join(" ").toLowerCase();
      const matchesSearch = !q || hay.indexOf(q) !== -1;

      const teamTheme = TEAM_PALETTE[n.team_owner] || TEAM_PALETTE.platform;
      const statusTheme = STATUS_PALETTE[ov.state] || null;

      let borderStroke = isSelected ? "#2563eb" : "#64748b";
      let rectFill = "#ffffff";
      if (st.showTeamColors) {
        borderStroke = teamTheme.stroke;
      }
      if (statusTheme) {
        borderStroke = statusTheme.stroke;
      }

      const gNode = svgEl("g", {
        class: "odb-node-group" + (matchesSearch ? "" : " dimmed"),
        "data-node-id": n.id
      });

      const rectAttrs = {
        x: n.x,
        y: n.y,
        width: n.width,
        height: n.height,
        rx: 9,
        fill: rectFill,
        stroke: borderStroke,
        "stroke-width": isSelected ? "3.2" : "2"
      };
      if (ov.state === "forcenew_hazard") {
        rectAttrs.class = "odb-hazard-rect";
        rectAttrs["stroke-dasharray"] = "6 3";
      }
      gNode.appendChild(svgEl("rect", rectAttrs));

      // Top color accent strip
      gNode.appendChild(
        svgEl("rect", {
          x: n.x,
          y: n.y,
          width: n.width,
          height: 6,
          rx: 3,
          fill: statusTheme ? statusTheme.stroke : teamTheme.stroke
        })
      );

      // Node title & subtitle
      const trunc = (s, maxLen) => (s.length > maxLen ? s.slice(0, maxLen - 1) + "…" : s);
      gNode.appendChild(
        svgEl(
          "text",
          {
            x: n.x + 12,
            y: n.y + 27,
            fill: "#0f172a",
            "font-size": "12.5",
            "font-weight": "700"
          },
          trunc(n.label, 30)
        )
      );
      gNode.appendChild(
        svgEl(
          "text",
          {
            x: n.x + 12,
            y: n.y + 45,
            fill: "#475569",
            "font-size": "11"
          },
          trunc(subText, 35)
        )
      );

      // Resource chip or Status Overlay Pill
      if (ov.badge_text && statusTheme) {
        const pillW = Math.min(n.width - 20, Math.max(88, ov.badge_text.length * 6.4 + 14));
        gNode.appendChild(
          svgEl("rect", {
            x: n.x + 10,
            y: n.y + n.height - 24,
            width: pillW,
            height: 17,
            rx: 4,
            fill: statusTheme.badgeBg
          })
        );
        gNode.appendChild(
          svgEl(
            "text",
            {
              x: n.x + 16,
              y: n.y + n.height - 12,
              fill: "#ffffff",
              "font-size": "9.8",
              "font-weight": "700"
            },
            trunc(ov.badge_text, 28)
          )
        );
      } else if (n.terraform_resource) {
        gNode.appendChild(
          svgEl(
            "text",
            {
              x: n.x + 12,
              y: n.y + n.height - 11,
              fill: teamTheme.stroke,
              "font-size": "10",
              "font-weight": "600"
            },
            trunc(n.terraform_resource, 34)
          )
        );
      }

      gNode.onclick = (ev) => {
        ev.stopPropagation();
        st.selectedNodeId = n.id;
        renderAll();
      };

      viewport.appendChild(gNode);
    });

    svg.appendChild(viewport);
  }

  function renderDrawer(bpCheck) {
    drawerBody.replaceChildren();
    const nodes = spec.nodes || [];
    const selected = nodes.find((n) => n.id === st.selectedNodeId) || nodes[0];

    if (st.activeTab === "inspect") {
      if (!selected) {
        drawerBody.appendChild(el("p", null, "Click any node on the canvas to inspect its Terraform schema and IAM roles."));
        return;
      }
      const ov = effectiveOverlay(selected, bpCheck);
      if (ov && ov.state && ov.state !== "neutral") {
        const cls = STATUS_PALETTE[ov.state] ? STATUS_PALETTE[ov.state].cls : "warn";
        const alertBox = el("div", { class: "odb-alert-box " + cls });
        alertBox.appendChild(el("div", { class: "odb-card-title" }, ov.badge_text || ov.state.toUpperCase()));
        alertBox.appendChild(el("div", null, ov.detail || ""));
        if (ov.remediation_cmd) {
          alertBox.appendChild(el("pre", { class: "odb-code" }, ov.remediation_cmd));
          const copyFixBtn = el("button", { type: "button", class: "odb-btn" }, "Copy Remediation Command");
          copyFixBtn.onclick = () => {
            if (navigator.clipboard) navigator.clipboard.writeText(ov.remediation_cmd);
            st.statusNotice = "Copied remediation command to clipboard.";
            renderBanner(bpCheck);
          };
          alertBox.appendChild(copyFixBtn);
        }
        drawerBody.appendChild(alertBox);
      }

      const card = el("div", { class: "odb-card" });
      card.appendChild(el("div", { class: "odb-card-title" }, selected.label));
      card.appendChild(el("div", null, effectiveNodeSubtitle(selected, bpCheck)));

      const teamInfo = TEAM_PALETTE[selected.team_owner] || TEAM_PALETTE.platform;
      card.appendChild(el("div", { class: "odb-meta-label" }, "Separation-of-Duties Owner"));
      card.appendChild(el("div", null, teamInfo.label));

      if (selected.terraform_resource) {
        card.appendChild(el("div", { class: "odb-meta-label" }, "Terraform Resource (hashicorp/google)"));
        card.appendChild(el("span", { class: "odb-role-chip" }, selected.terraform_resource));
      }

      if (selected.ip_math || selected.id === "vpc" || selected.id === "client_subnet" || selected.id === "backup_subnet") {
        card.appendChild(el("div", { class: "odb-meta-label" }, "Live CIDR & IP Capacity Math"));
        let ipSummary = selected.ip_math;
        if (selected.id === "vpc") ipSummary = bpCheck.vpc.summary;
        if (selected.id === "client_subnet") ipSummary = bpCheck.cli.summary;
        if (selected.id === "backup_subnet") ipSummary = bpCheck.bak.summary;
        card.appendChild(el("div", null, ipSummary));
      }

      if (selected.iam_roles && selected.iam_roles.length > 0) {
        card.appendChild(el("div", { class: "odb-meta-label" }, "Required Least-Privilege IAM Roles"));
        const rolesWrap = el("div");
        selected.iam_roles.forEach((r) => rolesWrap.appendChild(el("span", { class: "odb-role-chip" }, r)));
        card.appendChild(rolesWrap);
      }

      if (selected.hcl_snippet) {
        card.appendChild(el("div", { class: "odb-meta-label" }, "Grounded HCL Snippet"));
        card.appendChild(el("pre", { class: "odb-code" }, selected.hcl_snippet));
        const copyHclBtn = el("button", { type: "button", class: "odb-btn" }, "Copy HCL Block");
        copyHclBtn.onclick = () => {
          if (navigator.clipboard) navigator.clipboard.writeText(selected.hcl_snippet);
          st.statusNotice = "Copied HCL snippet for " + selected.label + " to clipboard.";
          renderBanner(bpCheck);
        };
        card.appendChild(copyHclBtn);
      }

      if (selected.editable_field) {
        const jumpBtn = el("button", { type: "button", class: "odb-btn-primary" }, "Edit Parameter in Blueprint Canvas");
        jumpBtn.onclick = () => {
          st.activeTab = "blueprint";
          syncTabsUi();
          renderDrawer(bpCheck);
        };
        card.appendChild(jumpBtn);
      }

      drawerBody.appendChild(card);
      return;
    }

    // Visual Blueprint Editor tab
    const bp = st.blueprint;
    const formCard = el("div", { class: "odb-card" });
    formCard.appendChild(el("div", { class: "odb-card-title" }, "Bidirectional Blueprint -> Terraform"));

    const addTextField = (key, labelText) => {
      const wrap = el("div", { class: "odb-field" });
      wrap.appendChild(el("label", null, labelText));
      const inp = el("input", { type: "text", value: bp[key] || "" });
      inp.oninput = (e) => {
        bp[key] = e.target.value;
        st.statusNotice = "";
        const nextCheck = validateClientBlueprint(bp);
        renderBanner(nextCheck);
        renderSvg(nextCheck);
        syncBtn.disabled = !nextCheck.valid;
        if (setStateValue) setStateValue("blueprint", Object.assign({}, bp));
      };
      wrap.appendChild(inp);
      formCard.appendChild(wrap);
    };

    const addSelectField = (key, labelText, options) => {
      const wrap = el("div", { class: "odb-field" });
      wrap.appendChild(el("label", null, labelText));
      const sel = el("select");
      options.forEach((opt) => {
        const o = el("option", { value: opt[0] }, opt[1]);
        if (bp[key] === opt[0]) o.selected = true;
        sel.appendChild(o);
      });
      sel.onchange = (e) => {
        bp[key] = e.target.value;
        const nextCheck = validateClientBlueprint(bp);
        renderSvg(nextCheck);
        if (setStateValue) setStateValue("blueprint", Object.assign({}, bp));
      };
      wrap.appendChild(sel);
      formCard.appendChild(wrap);
    };

    const addRangeField = (key, labelText, minV, maxV, stepV) => {
      const wrap = el("div", { class: "odb-field" });
      const lbl = el("label", null, labelText + ": " + bp[key]);
      wrap.appendChild(lbl);
      const rng = el("input", { type: "range", min: minV, max: maxV, step: stepV, value: bp[key] });
      rng.oninput = (e) => {
        bp[key] = Number(e.target.value);
        lbl.textContent = labelText + ": " + bp[key];
        const nextCheck = validateClientBlueprint(bp);
        renderSvg(nextCheck);
        if (setStateValue) setStateValue("blueprint", Object.assign({}, bp));
      };
      wrap.appendChild(rng);
      formCard.appendChild(wrap);
    };

    addTextField("project_id", "GCP Project ID");
    addTextField("region", "GCP Region");
    addTextField("gcp_oracle_zone", "Oracle Zone (gcp_oracle_zone)");
    addTextField("vpc_cidr", "Customer VPC CIDR");
    addTextField("client_subnet_cidr", "ODB CLIENT_SUBNET CIDR (>= /28)");
    addTextField("backup_subnet_cidr", "ODB BACKUP_SUBNET CIDR (>= /28)");
    addSelectField("workload_type", "Oracle Workload Type", [
      ["adb", "Autonomous Database 23ai (adb)"],
      ["exadata_dedicated", "Exadata VM Cluster (exadata_dedicated)"],
      ["exascale", "Exascale VM Cluster (exascale)"],
      ["basedb", "Base Database System (basedb)"]
    ]);
    addSelectField("deployment_layer", "Separation-of-Duties Layer", [
      ["full_stack", "Full Stack Bundle (full_stack)"],
      ["network_only", "Network Admin Only (network_only)"],
      ["infra_only", "Infra Admin Only (infra_only)"],
      ["database_only", "DBA Workload Only (database_only)"]
    ]);
    addRangeField("compute_count", "Compute Count (ECPUs / OCPUs)", 2, 64, 2);
    addRangeField("storage_size_tb", "Storage Size (TB)", 1, 64, 1);

    const isEmbeddedStreamlit = Boolean(data.is_streamlit);
    const syncLabel = isEmbeddedStreamlit
      ? "Sync Blueprint & Generate Golden Terraform"
      : "Copy Updated terraform.tfvars";
    const syncBtn = el("button", { type: "button", class: "odb-btn-primary" }, syncLabel);
    syncBtn.disabled = !bpCheck.valid;
    syncBtn.onclick = () => {
      const checkNow = validateClientBlueprint(bp);
      if (!checkNow.valid) {
        renderBanner(checkNow);
        return;
      }
      if (isEmbeddedStreamlit && setTriggerValue) {
        if (setStateValue) setStateValue("blueprint", Object.assign({}, bp));
        setTriggerValue("sync_terraform", Object.assign({ ts: Date.now() }, bp));
        st.statusNotice = "Syncing blueprint to Golden Terraform bundle...";
        renderBanner(checkNow);
      } else {
        const tfvars = [
          'project_id         = "' + bp.project_id + '"',
          'region             = "' + bp.region + '"',
          'gcp_oracle_zone    = "' + bp.gcp_oracle_zone + '"',
          'vpc_cidr           = "' + bp.vpc_cidr + '"',
          'client_subnet_cidr = "' + bp.client_subnet_cidr + '"',
          'backup_subnet_cidr = "' + bp.backup_subnet_cidr + '"',
          "compute_count      = " + bp.compute_count,
          "storage_size_tb    = " + bp.storage_size_tb
        ].join("\\n");
        if (navigator.clipboard) navigator.clipboard.writeText(tfvars);
        st.statusNotice = "Copied validated terraform.tfvars to clipboard.";
        renderBanner(checkNow);
      }
    };
    formCard.appendChild(syncBtn);
    drawerBody.appendChild(formCard);
  }

  function syncTabsUi() {
    root.querySelectorAll(".odb-tab").forEach((btn) => {
      btn.classList.toggle("active", btn.getAttribute("data-tab") === st.activeTab);
    });
    root.querySelectorAll(".odb-pill[data-toggle]").forEach((btn) => {
      const tKey = btn.getAttribute("data-toggle");
      btn.classList.toggle("active", Boolean(st[tKey]));
    });
  }

  function renderAll() {
    const bpCheck = validateClientBlueprint(st.blueprint || {});
    syncTabsUi();
    renderLegend();
    renderBanner(bpCheck);
    renderSvg(bpCheck);
    renderDrawer(bpCheck);
  }

  // Bind toolbar actions idempotently
  root.querySelectorAll("[data-action]").forEach((btn) => {
    btn.onclick = () => {
      const act = btn.getAttribute("data-action");
      if (act === "zoom-in") st.zoom = Math.min(2.2, +(st.zoom + 0.15).toFixed(2));
      if (act === "zoom-out") st.zoom = Math.max(0.55, +(st.zoom - 0.15).toFixed(2));
      if (act === "zoom-reset") { st.zoom = 1.0; st.panX = 0; st.panY = 0; }
      renderSvg(validateClientBlueprint(st.blueprint || {}));
    };
  });

  root.querySelectorAll(".odb-pill[data-toggle]").forEach((btn) => {
    btn.onclick = () => {
      const tKey = btn.getAttribute("data-toggle");
      st[tKey] = !st[tKey];
      renderAll();
    };
  });

  root.querySelectorAll(".odb-tab").forEach((btn) => {
    btn.onclick = () => {
      st.activeTab = btn.getAttribute("data-tab") || "inspect";
      renderAll();
    };
  });

  if (searchInput) {
    if (searchInput.value !== st.searchQuery) searchInput.value = st.searchQuery;
    searchInput.oninput = (e) => {
      st.searchQuery = e.target.value || "";
      renderSvg(validateClientBlueprint(st.blueprint || {}));
    };
  }

  svg.onwheel = (e) => {
    e.preventDefault();
    const delta = e.deltaY < 0 ? 0.1 : -0.1;
    st.zoom = Math.min(2.2, Math.max(0.55, +(st.zoom + delta).toFixed(2)));
    renderSvg(validateClientBlueprint(st.blueprint || {}));
  };

  svg.onmousedown = (e) => {
    if (e.target.closest && e.target.closest(".odb-node-group")) return;
    st.isDragging = true;
    st.dragStartX = e.clientX - st.panX;
    st.dragStartY = e.clientY - st.panY;
  };

  const onMouseMove = (e) => {
    if (!st.isDragging) return;
    st.panX = e.clientX - st.dragStartX;
    st.panY = e.clientY - st.dragStartY;
    renderSvg(validateClientBlueprint(st.blueprint || {}));
  };

  const onMouseUp = () => {
    st.isDragging = false;
  };

  window.addEventListener("mousemove", onMouseMove);
  window.addEventListener("mouseup", onMouseUp);

  renderAll();

  return () => {
    window.removeEventListener("mousemove", onMouseMove);
    window.removeEventListener("mouseup", onMouseUp);
  };
}
"""


def render_standalone_interactive_html(spec: dict[str, Any]) -> str:
    """Packages an interactive topology spec into a zero-CDN, nonce-CSP standalone HTML5 document."""
    nonce = secrets.token_urlsafe(16)
    safe_title = html.escape(str(spec.get("title", "Oracle@Google Interactive Topology Explorer")))
    payload_json = json.dumps({"spec": spec, "is_streamlit": False}).replace("</", "<\\/")
    standalone_boot_js = INTERACTIVE_DIAGRAM_JS.replace(
        "export default function renderOdbInteractiveDiagram(component)",
        "function renderOdbInteractiveDiagram(component)",
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'nonce-{nonce}'; script-src 'nonce-{nonce}'; img-src data:;" />
  <title>{safe_title}</title>
  <style nonce="{nonce}">
    body {{
      margin: 0;
      padding: 18px;
      background: #f1f5f9;
      color: #0f172a;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }}
    .odb-page-header {{
      max-width: 1360px;
      margin: 0 auto 12px auto;
    }}
    .odb-page-header h1 {{
      margin: 0 0 4px 0;
      font-size: 20px;
    }}
    .odb-page-header p {{
      margin: 0;
      font-size: 13px;
      color: #475569;
    }}
    #odb-standalone-host {{
      max-width: 1360px;
      margin: 0 auto;
    }}
    {INTERACTIVE_DIAGRAM_CSS}
  </style>
</head>
<body>
  <header class="odb-page-header">
    <h1>{safe_title}</h1>
    <p>Interactive Oracle Database@Google Cloud Topology Explorer — Click nodes to inspect HCL &amp; IAM, toggle layers, or validate CIDRs.</p>
  </header>
  <main id="odb-standalone-host">
    {INTERACTIVE_DIAGRAM_HTML}
  </main>
  <script id="odb-spec-data" type="application/json" nonce="{nonce}">{payload_json}</script>
  <script nonce="{nonce}">
    {standalone_boot_js}
    (function () {{
      const raw = document.getElementById("odb-spec-data");
      const host = document.getElementById("odb-standalone-host");
      if (!raw || !host) return;
      const parsed = JSON.parse(raw.textContent || "{{}}");
      renderOdbInteractiveDiagram({{
        parentElement: host,
        data: parsed,
        setStateValue: function () {{}},
        setTriggerValue: function () {{}}
      }});
    }})();
  </script>
</body>
</html>
"""
