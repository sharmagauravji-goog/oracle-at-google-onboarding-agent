"""Grounded Architecture & Onboarding Diagram Generator for Oracle Database@Google Cloud.

Generates syntax-verified Mermaid (`mermaid`) and terminal-friendly ASCII diagrams for:
- `end_to_end_onboarding`: Complete customer onboarding lifecycle (Prerequisites -> Marketplace -> Linking -> MOS CSI -> ODB Network -> Provisioning)
- `networking_standalone_vpc`: Single-Project VPC peered with ODB Network & Client/Backup Subnets
- `networking_shared_vpc`: Enterprise Shared VPC (Host Project VPC + Service Project ODB resources)
- `networking_hub_and_spoke_ha_dr`: Hybrid On-Prem / Cloud Interconnect / NCC Hub-and-Spoke + Data Guard DR
- `backup_and_recovery`: Automated backups, RMAN over BACKUP_SUBNET, GCS/OCI Object Storage & PITR
- `encryption_cmek`: TDE Master Key in Google Cloud KMS / OCI Vault + mTLS in-transit
- `monitoring_observability`: Cloud Monitoring, Cloud Audit Logs & Oracle Operations Insights / AWR
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from ai_agent.tools.network_validator import resolve_safe_workspace_path

_SAFE_TOKEN_RE = re.compile(r"^[a-zA-Z0-9._\-:/]+$")

SUPPORTED_DIAGRAM_TYPES: tuple[str, ...] = (
    "end_to_end_onboarding",
    "networking_standalone_vpc",
    "networking_shared_vpc",
    "networking_hub_and_spoke_ha_dr",
    "backup_and_recovery",
    "encryption_cmek",
    "monitoring_observability",
)


def _sanitize_label(val: str, default: str) -> str:
    cleaned = (val or "").strip()
    if not cleaned or not _SAFE_TOKEN_RE.match(cleaned):
        return default
    return cleaned


def generate_odb_architecture_diagram(
    diagram_type: str = "end_to_end_onboarding",
    project_id: str = "my-odb-project-01",
    region: str = "us-east4",
    gcp_oracle_zone: str = "us-east4-b-r1",
    vpc_cidr: str = "10.10.0.0/16",
    client_subnet_cidr: str = "10.20.1.0/24",
    backup_subnet_cidr: str = "10.20.2.0/24",
    save_to_workspace: bool = False,
    output_dir: str = "./output/diagrams",
    output_format: str = "both",
    save_to_file: str = "",
) -> str:
    """Generates a grounded, syntax-verified Mermaid and ASCII diagram for ODB@GCP onboarding or architecture.

    Always call this tool when the customer asks for a diagram, visual flow, networking topology illustration,
    or end-to-end onboarding flowchart.

    Args:
        diagram_type: One of:
            - `end_to_end_onboarding`
            - `networking_standalone_vpc`
            - `networking_shared_vpc`
            - `networking_hub_and_spoke_ha_dr`
            - `backup_and_recovery`
            - `encryption_cmek`
            - `monitoring_observability`
        project_id: Customer GCP Project ID to label in the diagram.
        region: GCP Region (e.g. `us-east4`).
        gcp_oracle_zone: Oracle Zone within the GCP region (e.g. `us-east4-b-r1`).
        vpc_cidr: Customer VPC CIDR range.
        client_subnet_cidr: ODB Client Subnet CIDR range (minimum `/28`).
        backup_subnet_cidr: ODB Backup Subnet CIDR range (minimum `/28`).
        save_to_workspace: If True, writes `<diagram_type>.md` inside `output_dir` (within the active workspace).
        output_dir: Relative directory inside the open workspace to save diagram files.
        output_format: `'mermaid'`, `'ascii'`, or `'both'`.
        save_to_file: Optional file path inside the workspace (e.g. `./output/diagrams/onboarding.md`) to write the diagram.

    Returns:
        JSON string containing `title`, `mermaid_code`, `mermaid_markdown`, `ascii_diagram`, `key_takeaways`, and optional `saved_file`.
    """
    proj = _sanitize_label(project_id, "my-odb-project-01")
    reg = _sanitize_label(region, "us-east4")
    ozone = _sanitize_label(gcp_oracle_zone, "us-east4-b-r1")
    v_cidr = _sanitize_label(vpc_cidr, "10.10.0.0/16")
    c_cidr = _sanitize_label(client_subnet_cidr, "10.20.1.0/24")
    b_cidr = _sanitize_label(backup_subnet_cidr, "10.20.2.0/24")

    dtype = (diagram_type or "end_to_end_onboarding").strip().lower()

    diagrams: dict[str, dict[str, Any]] = {
        "end_to_end_onboarding": {
            "title": "Oracle Database@Google Cloud — End-to-End Customer Onboarding Flow",
            "mermaid": f"""flowchart TB
    subgraph P1["Phase 1: GCP Prerequisites & IAM ({proj})"]
        A1["1. Enable APIs: oracledatabase, compute, servicenetworking, cloudkms, monitoring"]
        A2["2. Grant IAM: roles/oracledatabase.admin & roles/billing.admin + orderAdmin"]
        A1 --> A2
    end

    subgraph P2["Phase 2: Google Cloud Marketplace Procurement"]
        B1{{"Choose Commercial Model"}}
        B2["Option A: Marketplace Private Offer (100% MACC Commit Drawdown, BYOL / License Included)"]
        B3["Option B: Pay-As-You-Go / PAYG (Elastic On-Demand Billing for ADB & Exascale)"]
        B4["Entitlement Activated (entitlement_id)"]
        B1 --> B2
        B1 --> B3
        B2 --> B4
        B3 --> B4
    end

    subgraph P3["Phase 3: OCI Account Linking & Tenancy Setup"]
        C1{{"Tenancy Strategy"}}
        C2["Create New Partner-Linked OCI Tenancy from GCP Console"]
        C3["Link Existing OCI Tenancy (MulticloudLink Compartment Auto-Created)"]
        C1 --> C2
        C1 --> C3
    end

    subgraph P4["Phase 4: My Oracle Support (MOS) Registration"]
        D1["Retrieve Customer Support Identifier (CSI) from OCI Tenancy Details"]
        D2["Register CSI at support.oracle.com & Approve Customer User Admin (CUA)"]
        D1 --> D2
    end

    subgraph P5["Phase 5: Day-1 Terraform Provisioning & Day-2 Operations ({reg} / {ozone})"]
        E1["Provision google_oracle_database_odb_network + CLIENT_SUBNET ({c_cidr}) & BACKUP_SUBNET ({b_cidr})"]
        E2["Provision Workload (ADB / Exadata Dedicated / Exascale / BaseDB) with deletion_protection = true"]
        E3["Day-2 Operations: Cloud Monitoring, CMEK Key Rotation & Safe In-Place Scaling"]
        E1 --> E2 --> E3
    end

    P1 --> P2 --> P3 --> P4 --> P5""",
            "ascii": f"""
+-----------------------------------------------------------------------------------+
|          ORACLE DATABASE@GOOGLE CLOUD — END-TO-END ONBOARDING FLOW                |
+-----------------------------------------------------------------------------------+
  [Phase 1: Prerequisites & IAM ({proj})]
     |-- Enable: oracledatabase.googleapis.com, compute, servicenetworking, cloudkms
     |-- IAM: roles/oracledatabase.admin, roles/billing.admin, consumerprocurement.orderAdmin
     v
  [Phase 2: Google Cloud Marketplace Subscription]
     |-- Private Offer (MACC drawdown, custom commit)  OR  Pay-As-You-Go (PAYG)
     |-- Generates active Marketplace entitlement_id
     v
  [Phase 3: OCI Account Linking (GCP Console -> Oracle Database@Google Cloud)]
     |-- Create New OCI Tenancy  OR  Link Existing OCI Tenancy
     |-- Auto-provisions MulticloudLink compartment & federated identity
     v
  [Phase 4: My Oracle Support (MOS) & CSI Registration]
     |-- Copy CSI from OCI Tenancy Details -> Register at https://support.oracle.com
     |-- Dual-vendor support ready (Google Cloud Care + My Oracle Support)
     v
  [Phase 5: Day-1 Infrastructure & Day-2 Operations ({reg} / {ozone})]
     |-- ODB Network + CLIENT_SUBNET ({c_cidr}) + BACKUP_SUBNET ({b_cidr})
     |-- Provision ADB / Exadata / Exascale / BaseDB via hashicorp/google >= 7.0.0
+-----------------------------------------------------------------------------------+
""".strip(),
            "key_takeaways": [
                "Billing is consolidated on your Google Cloud invoice via Google Cloud Marketplace (Private Offer or PAYG).",
                "OCI Account Linking is a one-time setup performed directly from the Google Cloud Console.",
                "Registering your CSI in My Oracle Support (`support.oracle.com`) is essential before going live in production.",
            ],
        },
        "networking_standalone_vpc": {
            "title": f"ODB@GCP Standalone Single-Project VPC Topology ({reg} / {ozone})",
            "mermaid": f"""flowchart LR
    subgraph GCP["Google Cloud Project ({proj}) — Region: {reg}"]
        subgraph VPC["Customer VPC ({v_cidr})"]
            AppVM["GKE / Compute Engine App Tier"]
            CloudDNS["Cloud DNS (*.oraclevcn.com Auto-Forwarded)"]
        end
    end

    subgraph Colocated["Colocated Oracle Database@Google Cloud Zone ({ozone})"]
        subgraph ODBNet["google_oracle_database_odb_network (Partner Interconnect <1-2ms)"]
            ClientSub["google_oracle_database_odb_subnet\npurpose = CLIENT_SUBNET ({c_cidr})\nodbnetwork = odb_net.odb_network_id"]
            BackupSub["google_oracle_database_odb_subnet\npurpose = BACKUP_SUBNET ({b_cidr})\nodbnetwork = odb_net.odb_network_id"]
            DB["ODB Workload (ADB / Exadata / Exascale / BaseDB)\nodb_network = odb_net.name"]
            ClientSub --> DB
            BackupSub -. "RMAN / Backup Traffic" .-> DB
        end
    end

    AppVM <== "Private IP / mTLS SQL Traffic" ==> ClientSub
    CloudDNS -. "Private Endpoint / SCAN DNS Resolution" .-> ClientSub""",
            "ascii": f"""
+--------------------------------------+      Partner Interconnect (<2ms)     +-----------------------------------------------+
| Google Cloud Project: {proj:<14} | <==================================> | Colocated ODB Zone: {ozone:<25} |
| Customer VPC ({v_cidr:<16})      |   google_oracle_database_odb_network |                                               |
|                                      |                                      |  +-----------------------------------------+  |
|  [GKE / Compute Engine App VMs]      | ------ SQL / mTLS Traffic ---------> |  | CLIENT_SUBNET ({c_cidr:<15})         |  |
|  [Cloud DNS: *.oraclevcn.com]        |                                      |  | -> Autonomous DB / Exadata VM Cluster   |  |
|                                      |                                      |  +-----------------------------------------+  |
|                                      |                                      |  +-----------------------------------------+  |
|                                      |                                      |  | BACKUP_SUBNET ({b_cidr:<15})         |  |
|                                      |                                      |  | -> Dedicated Exadata/Exascale Backups   |  |
|                                      |                                      |  +-----------------------------------------+  |
+--------------------------------------+                                      +-----------------------------------------------+
""".strip(),
            "key_takeaways": [
                "`google_oracle_database_odb_network` automatically establishes high-speed partner peering with the customer VPC—no manual IPSec VPN or VLAN attachment needed.",
                "`CLIENT_SUBNET` and `BACKUP_SUBNET` must each be `/28` or larger and must NOT overlap with `vpc_cidr` (`" + v_cidr + "`).",
            ],
        },
        "networking_shared_vpc": {
            "title": f"ODB@GCP Enterprise Shared VPC Topology (Host + Service Project in {reg})",
            "mermaid": f"""flowchart TB
    subgraph HostProj["Shared VPC Host Project (network_project_id)"]
        SharedVPC["Shared VPC Network ({v_cidr})\nprojects/<host-project>/global/networks/<vpc>"]
        DNS["Cloud DNS Private Forwarding (*.oraclevcn.com)"]
    end

    subgraph AppServiceProj["App Service Project"]
        GKE["GKE / App Workloads\n(Subnets shared from Host VPC)"]
    end

    subgraph ODBServiceProj["Database Service Project ({proj}) — Zone: {ozone}"]
        ODBNet["google_oracle_database_odb_network\nnetwork = data.google_compute_network.shared_vpc.id"]
        ClientSub["google_oracle_database_odb_subnet\nCLIENT_SUBNET ({c_cidr})"]
        BackupSub["google_oracle_database_odb_subnet\nBACKUP_SUBNET ({b_cidr})"]
        Exa["ODB Workload (ADB / Exadata / Exascale)"]
        ODBNet --> ClientSub --> Exa
        ODBNet --> BackupSub -.-> Exa
    end

    GKE --> SharedVPC
    SharedVPC <== "Partner Peering" ==> ODBNet""",
            "ascii": f"""
+-----------------------------------------------------------------------+
| Shared VPC Host Project (network_project_id)                          |
|   Shared VPC: projects/<host-project>/global/networks/<vpc>           |
|   CIDR: {v_cidr:<18} | Cloud DNS (*.oraclevcn.com)              |
+-----------------------------------+-----------------------------------+
                                    |
            +-----------------------+-----------------------+
            | (Shared Subnets)                              | (network = host_vpc.id)
            v                                               v
+-------------------------------+           +-------------------------------------------+
| App Service Project           |           | ODB Database Service Project ({proj}) |
|  [GKE / Compute Engine Apps]  | ==SQL==>  |  [google_oracle_database_odb_network]     |
|                               |           |  |-- CLIENT_SUBNET ({c_cidr:<15})      |
|                               |           |  |-- BACKUP_SUBNET ({b_cidr:<15})      |
|                               |           |  +-- ADB / Exadata / Exascale in {ozone} |
+-------------------------------+           +-------------------------------------------+
""".strip(),
            "key_takeaways": [
                "In Shared VPC deployments, `google_oracle_database_odb_network` is created in the Database Service Project, while its `network` attribute references the Host Project VPC ID.",
                "Ensure the Service Project identity has `roles/compute.networkUser` and Service Networking permissions on the Host Project.",
            ],
        },
        "networking_hub_and_spoke_ha_dr": {
            "title": "ODB@GCP Hub-and-Spoke Hybrid Connectivity & Cross-Region Data Guard DR",
            "mermaid": f"""flowchart LR
    subgraph OnPrem["Corporate On-Premises Datacenter"]
        CorpClients["On-Premises Apps / RMAN / GoldenGate"]
    end

    subgraph Hub["GCP Transit Hub VPC"]
        Interconnect["Cloud Interconnect / HA VPN + Cloud Router\n(Advertise ODB CIDR {c_cidr})"]
        NCC["Network Connectivity Center (NCC) / VPC Peering\n(export_custom_routes = true)"]
        Interconnect --> NCC
    end

    subgraph PrimaryRegion["Primary Region ({reg} / {ozone})"]
        ODBNet1["Primary ODB Network\nCLIENT_SUBNET ({c_cidr})"]
        PrimDB["Primary Exadata / Autonomous DB"]
        ODBNet1 --> PrimDB
    end

    subgraph DRRegion["DR Region (Standby gcp_oracle_zone)"]
        ODBNet2["DR ODB Network\nStandby CLIENT_SUBNET"]
        StandbyDB["Standby Exadata / Autonomous Data Guard"]
        ODBNet2 --> StandbyDB
    end

    CorpClients <==> Interconnect
    NCC <==> ODBNet1
    PrimDB <== "Active Data Guard / Autonomous Data GuardSync" ==> StandbyDB""",
            "ascii": f"""
[On-Premises DC] <==Cloud Interconnect / HA VPN==> [GCP Transit Hub VPC (Cloud Router + NCC)]
                                                             | (Custom Route Export: {c_cidr})
                                                             v
                                        +-----------------------------------------+
                                        | Primary Region ({reg} / {ozone})        |
                                        |  Primary ODB Network ({c_cidr})     |
                                        |  [Primary Exadata / Autonomous DB]      |
                                        +--------------------+--------------------+
                                                             |
                                                             | Oracle Active Data Guard /
                                                             | Autonomous Data Guard Replication
                                                             v
                                        +-----------------------------------------+
                                        | DR Region (Standby Oracle Zone)         |
                                        |  Standby ODB Network                    |
                                        |  [Standby Exadata / Autonomous DB]      |
                                        +-----------------------------------------+
""".strip(),
            "key_takeaways": [
                "When connecting from on-premises or spoke VPCs via Cloud Interconnect/NCC, advertise the ODB `CLIENT_SUBNET` CIDR (`" + c_cidr + "`) on Cloud Router and enable custom route export/import.",
                "Use Autonomous Data Guard (for ADB) or Oracle Active Data Guard (for Exadata/BaseDB) for low-RPO/RTO cross-zone or cross-region disaster recovery.",
            ],
        },
        "backup_and_recovery": {
            "title": "ODB@GCP Backup, Restore, PITR & RMAN Storage Architecture",
            "mermaid": f"""flowchart TB
    subgraph Workloads["ODB@GCP Workloads ({ozone})"]
        ADB["Autonomous Database\n(backup_retention_period_days = 1..60)"]
        Exa["Exadata / Exascale VM Cluster\n(RAC Nodes)"]
    end

    subgraph Subnets["Isolated ODB Network Planes"]
        Client["CLIENT_SUBNET ({c_cidr})\nLow-Latency App SQL Traffic Only"]
        Backup["BACKUP_SUBNET ({b_cidr})\nDedicated High-Throughput RMAN Backup Traffic"]
    end

    subgraph Targets["Backup & Recovery Destinations"]
        OCIObj["Oracle Managed Object Storage / Autonomous Recovery Service\n(Automated Daily Backups + 1-Second PITR)"]
        GCS["Google Cloud Storage (GCS Bucket)\n(Optional Customer-Managed RMAN Backups via Private Google Access)"]
        DataGuard["Oracle Data Guard / Autonomous Data Guard\n(Continuous Redo Shipping to Standby)"]
    end

    Client <--> ADB
    Client <--> Exa
    ADB == "Automated Backups & PITR" ==> OCIObj
    Exa == "RMAN over BACKUP_SUBNET" ==> Backup
    Backup ==> OCIObj
    Backup -. "Custom RMAN Channels" .-> GCS
    ADB -. "Zero-Data-Loss Standby" .-> DataGuard
    Exa -. "Active Data Guard Redo" .-> DataGuard""",
            "ascii": f"""
+--------------------------------------------------------------------------+
| ODB@GCP BACKUP & RECOVERY ARCHITECTURE ({ozone})                         |
+--------------------------------------------------------------------------+
  [App Tier] <=== SQL Traffic ({c_cidr}) ===> [CLIENT_SUBNET]
                                                      |
                                         +------------+------------+
                                         |                         |
                                         v                         v
                              [Autonomous Database]     [Exadata / Exascale Cluster]
                                         |                         |
       Automated Daily Backups & PITR    |                         | Dedicated Backup I/O
       (1-60 Days Retention)             |                         v
                                         |              [BACKUP_SUBNET ({b_cidr})]
                                         |                         |
                                         v                         v
                        +----------------------------------------------------+
                        | Oracle Managed Object Storage / Recovery Appliance |
                        | + Optional RMAN to Google Cloud Storage (GCS)      |
                        +----------------------------------------------------+
""".strip(),
            "key_takeaways": [
                "Exadata and Exascale route all backup I/O over `BACKUP_SUBNET` (`" + b_cidr + "`) so RMAN jobs never impact production SQL latency on `CLIENT_SUBNET`.",
                "Autonomous Database includes automated daily backups and point-in-time recovery (PITR) with 1–60 days configurable retention (`backup_retention_period_days`).",
            ],
        },
        "encryption_cmek": {
            "title": "ODB@GCP Encryption at Rest (TDE), In-Transit (mTLS) & CMEK Architecture",
            "mermaid": f"""flowchart LR
    subgraph ClientSide["Application Tier (Customer VPC)"]
        App["App / GKE Pod\n(TLS 1.2+ or mTLS Wallet)"]
    end

    subgraph GCPKMS["Google Cloud KMS ({proj} / {reg})"]
        KeyRing["Cloud KMS KeyRing & CryptoKey\n(Software / Cloud HSM / Cloud EKM)"]
        SA["ODB Service Agent\nservice-<PROJECT_NUMBER>@gcp-sa-oracledatabase.iam.gserviceaccount.com\nRole: roles/cloudkms.cryptoKeyEncrypterDecrypter"]
        SA --> KeyRing
    end

    subgraph ODBZone["ODB@GCP Workload ({ozone})"]
        TDE["Oracle Transparent Data Encryption (TDE)\nMaster Encryption Key Envelope"]
        DataFiles["Encrypted Tablespaces, Redo Logs & RMAN Backups\n(AES-256 at Rest)"]
        TDE --> DataFiles
    end

    App == "Encrypted In-Transit (mTLS / TLS 1.2+)" ==> TDE
    KeyRing <== "CMEK Key Wrap / Rotation" ==> TDE""",
            "ascii": f"""
+---------------------------+                   +--------------------------------------------------+
| App / GKE in Customer VPC | ==mTLS / TLS 1.2=>| ODB@GCP Database ({ozone})                       |
+---------------------------+                   |  [Oracle Transparent Data Encryption (TDE)]      |
                                                |  [Encrypted Tablespaces, Flash Cache & Backups]  |
                                                +-------------------------^------------------------+
                                                                          |
                                                           CMEK Master Key Wrap / Unwrap
                                                                          |
                                                +-------------------------v------------------------+
                                                | Google Cloud KMS ({proj} / {reg})                |
                                                |  KeyRing / CryptoKey (HSM / EKM / Software)      |
                                                |  IAM: roles/cloudkms.cryptoKeyEncrypterDecrypter |
                                                |  Member: service-<PROJ_NUM>@gcp-sa-oracledatabase|
                                                +--------------------------------------------------+
""".strip(),
            "key_takeaways": [
                "Transparent Data Encryption (TDE) at rest and TLS 1.2+/mTLS in transit are enabled by default for all ODB@GCP databases.",
                "For Customer-Managed Encryption Keys (CMEK) via Google Cloud KMS, grant `roles/cloudkms.cryptoKeyEncrypterDecrypter` to `service-<PROJECT_NUMBER>@gcp-sa-oracledatabase.iam.gserviceaccount.com`.",
            ],
        },
        "monitoring_observability": {
            "title": "ODB@GCP Dual-Plane Monitoring, Logging & Observability Architecture",
            "mermaid": f"""flowchart LR
    subgraph ODB["ODB@GCP Resources ({ozone})"]
        DB["Autonomous DB / Exadata / Exascale / BaseDB\n(data_collection_options & operations_insights_state = ENABLED)"]
    end

    subgraph GCPObs["Google Cloud Observability ({proj})"]
        CM["Cloud Monitoring\nNamespace: oracledatabase.googleapis.com/*\n(CPU, Storage, IOPS, Sessions, Alerts)"]
        CL["Cloud Logging & Cloud Audit Logs\n(Admin Activity, Data Access & Incident Logs)"]
    end

    subgraph OracleObs["Oracle Deep Database Diagnostics (via oci_url)"]
        OPI["Oracle Operations Insights & SQL Warehouse\n(Capacity Forecasting & SQL Degradation)"]
        AWR["Database Management, AWR & ASH Analytics\n(Wait Events, Execution Plans, RAC Interconnect)"]
    end

    DB ==> CM
    DB ==> CL
    DB ==> OPI
    DB ==> AWR""",
            "ascii": f"""
                                     +---> [Google Cloud Monitoring (oracledatabase.googleapis.com/*)]
                                     |       (Dashboards, Pager Alerts, CPU/Storage/IOPS Metrics)
                                     |
[ODB@GCP Database in {ozone}] -------+---> [Google Cloud Logging & Cloud Audit Logs]
                                     |       (API Audit Trail, Health & Incident Events)
                                     |
                                     +---> [Oracle Operations Insights, AWR & ASH (via oci_url)]
                                             (Deep SQL Tuning, Wait Events & Capacity Forecasting)
""".strip(),
            "key_takeaways": [
                "Infrastructure and database health metrics stream natively into Google Cloud Monitoring under `oracledatabase.googleapis.com/*`.",
                "Deep Oracle performance diagnostics (AWR, ASH, SQL tuning, Operations Insights) are available by setting `operations_insights_state = \"ENABLED\"` and `data_collection_options`.",
            ],
        },
    }

    # Fuzzy match if customer passes shorthand like "onboarding", "shared_vpc", "cmek", "backup", "monitoring"
    selected_key = dtype if dtype in diagrams else "end_to_end_onboarding"
    if dtype not in diagrams:
        for key in diagrams:
            if dtype in key or any(part in dtype for part in key.split("_") if len(part) > 3):
                selected_key = key
                break

    chosen = diagrams[selected_key]
    saved_file_path: str | None = None
    md_doc = (
        f"# {chosen['title']}\n\n"
        f"```mermaid\n{chosen['mermaid']}\n```\n\n"
        f"## Terminal ASCII View\n\n```text\n{chosen['ascii']}\n```\n\n"
        "## Key Architectural Takeaways\n"
        + "\n".join(f"- {item}" for item in chosen["key_takeaways"])
        + "\n"
    )

    if save_to_file and save_to_file.strip():
        try:
            target_file = resolve_safe_workspace_path(save_to_file.strip())
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_text(md_doc, encoding="utf-8")
            saved_file_path = str(target_file)
        except ValueError as exc:
            return json.dumps(
                {
                    "valid": False,
                    "error": str(exc),
                },
                indent=2,
            )
    elif save_to_workspace:
        try:
            target_dir = resolve_safe_workspace_path(output_dir)
            target_dir.mkdir(parents=True, exist_ok=True)
            safe_filename = f"{selected_key}.md"
            file_path = (target_dir / safe_filename).resolve()
            if str(file_path).startswith(str(target_dir) + os.sep):
                file_path.write_text(md_doc, encoding="utf-8")
                saved_file_path = str(file_path)
        except ValueError as exc:
            return json.dumps(
                {
                    "valid": False,
                    "error": str(exc),
                },
                indent=2,
            )

    fmt = (output_format or "both").strip().lower()
    mermaid_md = f"```mermaid\n{chosen['mermaid']}\n```" if fmt in ("both", "mermaid") else ""
    ascii_str = chosen["ascii"] if fmt in ("both", "ascii") else ""

    return json.dumps(
        {
            "valid": True,
            "diagram_type": selected_key,
            "available_diagram_types": list(diagrams.keys()),
            "title": chosen["title"],
            "summary": chosen["key_takeaways"][0] if chosen.get("key_takeaways") else chosen["title"],
            "mermaid_code": chosen["mermaid"],
            "mermaid_markdown": mermaid_md,
            "ascii_diagram": ascii_str,
            "key_takeaways": chosen["key_takeaways"],
            "saved_file": saved_file_path,
        },
        indent=2,
    )

