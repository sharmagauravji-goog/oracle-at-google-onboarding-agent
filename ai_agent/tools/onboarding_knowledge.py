"""Grounded End-to-End Onboarding Lifecycle & Architecture Knowledge Engine for ODB@GCP.

Provides deterministic, anti-hallucination reference facts, checklists, and readiness
evaluators covering the complete Oracle Database@Google Cloud customer journey:
1. Prerequisites, GCP APIs, IAM Roles & Quotas (`prerequisites_and_iam`)
2. Marketplace Procurement: Private Offer vs. Pay-As-You-Go (`marketplace_procurement`)
3. OCI Account Linking & Multicloud Tenancy Provisioning (`account_linking_and_tenancy`)
4. My Oracle Support (MOS) & CSI Support Registration (`support_registration_mos`)
5. ODB Networks & Enterprise Networking Options (`odb_networks_and_topologies`)
6. Backup, Restore, PITR & Data Guard DR (`backup_and_recovery`)
7. Encryption, TDE, mTLS & CMEK with Cloud KMS / OCI Vault (`encryption_and_cmek`)
8. Monitoring, Cloud Logging, Audit Logs & Operations Insights (`monitoring_and_observability`)
"""

from __future__ import annotations

import json
import re
from typing import Any

_SAFE_PROJECT_ID_RE = re.compile(r"^[a-z][a-z0-9\-]{4,28}[a-z0-9]$")

ONBOARDING_KNOWLEDGE_BASE: dict[str, dict[str, Any]] = {
    "prerequisites_and_iam": {
        "title": "Phase 1: Prerequisites, GCP APIs, IAM Roles & Organization Policies",
        "summary": (
            "Before purchasing or provisioning Oracle Database@Google Cloud (ODB@GCP), the customer's "
            "Google Cloud Organization and target Project(s) must have the required APIs, IAM roles, "
            "and VPC networking prerequisites in place."
        ),
        "required_gcp_apis": [
            "oracledatabase.googleapis.com (Oracle Database@Google Cloud API — primary control plane)",
            "compute.googleapis.com (Compute Engine API — VPC networks, subnets, firewall rules)",
            "servicenetworking.googleapis.com (Service Networking API — partner network peering)",
            "cloudresourcemanager.googleapis.com (Cloud Resource Manager API)",
            "cloudkms.googleapis.com (Cloud KMS API — required if using CMEK encryption)",
            "monitoring.googleapis.com (Cloud Monitoring API — native ODB metrics)",
            "logging.googleapis.com (Cloud Logging API — audit & operational logs)",
        ],
        "required_iam_roles": {
            "Procurement & Marketplace Subscription": [
                "roles/billing.admin (Billing Account Administrator — required to purchase Private Offer or enable PAYG)",
                "roles/consumerprocurement.orderAdmin (Consumer Procurement Order Administrator)",
            ],
            "Account Linking & ODB Administration": [
                "roles/oracledatabase.admin (Oracle Database Admin — full control over ODB resources and account linking)",
            ],
            "Least-Privilege Operational Roles": [
                "roles/oracledatabase.networkAdmin (create/manage ODB Networks and ODB Subnets)",
                "roles/oracledatabase.autonomousDatabaseAdmin (create/manage Autonomous Databases)",
                "roles/oracledatabase.exadataAdmin (create/manage Exadata Infrastructure & VM Clusters)",
                "roles/oracledatabase.viewer (read-only access to ODB@GCP resources)",
                "roles/compute.networkAdmin (or roles/compute.networkViewer + Shared VPC host permissions)",
            ],
        },
        "gcloud_bootstrap_commands": [
            "gcloud services enable oracledatabase.googleapis.com compute.googleapis.com servicenetworking.googleapis.com cloudkms.googleapis.com monitoring.googleapis.com logging.googleapis.com --project=<PROJECT_ID>",
        ],
        "anti_hallucination_rules": [
            "ODB@GCP uses the native Google Cloud API `oracledatabase.googleapis.com`, NOT custom third-party endpoints.",
            "Marketplace Private Offer acceptance requires BOTH `roles/billing.admin` (on the Billing Account) and `roles/consumerprocurement.orderAdmin`.",
        ],
    },
    "marketplace_procurement": {
        "title": "Phase 2: Google Cloud Marketplace Procurement — Private Offer vs. Pay-As-You-Go (PAYG)",
        "summary": (
            "Oracle Database@Google Cloud is procured directly through Google Cloud Marketplace and billed "
            "on the customer's Google Cloud invoice. Customers can subscribe via either a negotiated Private Offer "
            "or on-demand Pay-As-You-Go (PAYG)."
        ),
        "comparison": {
            "Private Offer": {
                "best_for": "Production enterprise deployments, Exadata Dedicated Infrastructure, Exascale, BaseDB, and committed Autonomous DB workloads.",
                "billing_mechanism": "Custom pricing and terms negotiated with Oracle Sales and transacted via Google Cloud Marketplace. Draws down 100% against Google Cloud committed spend (MACC).",
                "license_options": "Supports both Bring Your Own License (BYOL) and License Included.",
                "workflow": [
                    "1. Work with your Oracle and Google Cloud account teams to size workloads (Exadata shapes, ECPU/OCPU counts, storage TB, region).",
                    "2. Oracle publishes a private offer targeting your Google Cloud Billing Account ID.",
                    "3. In Google Cloud Console -> Marketplace -> Private Offers, a user with `roles/billing.admin` and `roles/consumerprocurement.orderAdmin` reviews and accepts the offer.",
                    "4. Accepting the offer generates an active `entitlement_id` in your Google Cloud project/organization.",
                ],
            },
            "Pay-As-You-Go (PAYG)": {
                "best_for": "Rapid onboarding, PoCs, elastic Autonomous Database Serverless (`adb`) and Exascale (`exascale`) deployments without upfront annual commitments.",
                "billing_mechanism": "Metered hourly/per-second consumption billed directly to your Google Cloud Billing Account; counts toward Google Cloud spend.",
                "license_options": "Supports License Included and BYOL.",
                "workflow": [
                    "1. Open Google Cloud Console -> Marketplace and search for 'Oracle Database@Google Cloud'.",
                    "2. Select the Pay-As-You-Go plan and click Subscribe.",
                    "3. Select your target Google Cloud Billing Account and accept the terms.",
                    "4. Proceed directly to OCI Account Linking in the Oracle Database@Google Cloud console.",
                ],
            },
        },
        "anti_hallucination_rules": [
            "Customers do NOT pay Oracle via a separate OCI invoice for ODB@GCP Marketplace purchases; billing is consolidated through Google Cloud Marketplace.",
            "Both Private Offers and PAYG require completing the OCI Account Linking step before databases can be provisioned.",
        ],
    },
    "account_linking_and_tenancy": {
        "title": "Phase 3: OCI Account Linking & Multicloud Tenancy Federation",
        "summary": (
            "After subscribing in Google Cloud Marketplace, the customer links their Google Cloud account/project "
            "to an Oracle Cloud Infrastructure (OCI) tenancy so the colocated OCI control plane can manage the underlying "
            "Exadata/ADB database lifecycle while exposing native GCP resources."
        ),
        "linking_options": {
            "Option A — Create a New OCI Tenancy (Recommended for greenfield)": [
                "1. In Google Cloud Console, navigate to Oracle Database@Google Cloud -> Account setup.",
                "2. Choose 'Create a new OCI account' after accepting the Marketplace offer.",
                "3. Provide the primary administrator email and tenancy name.",
                "4. Google Cloud and Oracle automatically provision the partner-linked OCI tenancy, create the `multicloudlink` compartment, and bind the Marketplace `entitlement_id`.",
            ],
            "Option B — Link an Existing OCI Tenancy": [
                "1. In Google Cloud Console -> Oracle Database@Google Cloud -> Account setup, choose 'Link an existing OCI account'.",
                "2. Authenticate into your existing OCI home region as an OCI Tenancy Administrator (`Administrators` group).",
                "3. Confirm the Multicloud link handshake. Automated IAM policies and a dedicated `MulticloudLink` compartment are created in your OCI tenancy.",
            ],
        },
        "verification": [
            "Verify that the Marketplace entitlement state is `ACTIVE` in Google Cloud Console (`Oracle Database@Google Cloud -> Overview`).",
            "Once linked, every provisioned ODB@GCP resource exports an `oci_url` / `oci_uri` deep-link and an `entitlement_id` attribute in Terraform.",
        ],
        "anti_hallucination_rules": [
            "Customers provision Day-1 infrastructure (ODB Networks, Subnets, Autonomous DB, Exadata, Exascale, BaseDB) via Google Cloud APIs / `hashicorp/google` Terraform provider, NOT by manually creating VCNs in the OCI Console.",
        ],
    },
    "support_registration_mos": {
        "title": "Phase 4: My Oracle Support (MOS) & Customer Support Identifier (CSI) Registration",
        "summary": (
            "Oracle Database@Google Cloud uses a collaborative dual-vendor support model between Google Cloud Customer Care "
            "and My Oracle Support (MOS). Registering your Customer Support Identifier (CSI) in MOS is mandatory for production readiness."
        ),
        "step_by_step_mos_registration": [
            "1. Locate your **Customer Support Identifier (CSI)**: After OCI Account Linking completes, find your CSI number in the OCI Console (`Governance & Administration -> Tenancy Management -> Tenancy Details`) or in your Oracle Welcome email.",
            "2. Sign in to **My Oracle Support (`https://support.oracle.com`)** using your corporate Oracle Account.",
            "3. Navigate to `Settings -> My Account -> Request Access` and enter your ODB@GCP **CSI number**.",
            "4. If you are the first user for that CSI, you become the **Customer User Administrator (CUA)**; otherwise the existing CUA approves your request.",
            "5. If bringing your own licenses (**BYOL**), verify that your existing license CSIs are also linked to your MOS profile alongside the ODB@GCP cloud CSI.",
        ],
        "collaborative_support_matrix": {
            "Google Cloud Customer Care": [
                "Google Cloud Console & `oracledatabase.googleapis.com` API control plane",
                "Google Cloud Marketplace billing, Private Offer entitlements & quotas",
                "Customer VPC, Shared VPC, Cloud Interconnect, Cloud Router, Cloud DNS & Cloud KMS (CMEK)",
                "Cloud Monitoring & Cloud Logging pipelines",
            ],
            "My Oracle Support (MOS)": [
                "Oracle Database engine internals (`ORA-*` errors, SQL performance, optimizer, Data Guard)",
                "Exadata Database Server (Dom0/DomU), Exadata Storage Server cells, and Grid Infrastructure (`gi_version`) patching",
                "Autonomous Database wallet, APEX, RMAN backup/restore internals, and OCI Vault",
            ],
        },
        "anti_hallucination_rules": [
            "Customers can open support tickets with EITHER Google Cloud Support or My Oracle Support (MOS); Google and Oracle have joint backline escalation engineering workflows.",
        ],
    },
    "odb_networks_and_topologies": {
        "title": "ODB Networks, ODB Subnets & Enterprise Networking Topologies",
        "summary": (
            "An ODB Network (`google_oracle_database_odb_network`) is a dedicated, ultra-low-latency partner network fabric "
            "colocated within a specific Google Cloud region and `gcp_oracle_zone` (e.g. `us-east4-b-r1`), directly peered "
            "with a customer's Google Cloud VPC (`google_compute_network`)."
        ),
        "core_concepts": {
            "ODB Network (`google_oracle_database_odb_network`)": (
                "Links a customer VPC (`network = projects/<project>/global/networks/<vpc>`) to an Oracle zone "
                "(`gcp_oracle_zone`). Uses Google-managed partner interconnect under the hood—no manual IPSec VPN or "
                "customer-configured Cloud Interconnect VLAN attachments are required between GCP and OCI!"
            ),
            "ODB Subnets (`google_oracle_database_odb_subnet`)": (
                "Carved inside the ODB Network (`odbnetwork` attribute). Every subnet MUST have a minimum CIDR prefix "
                "of `/28` (16 IP addresses) and MUST NOT overlap with any existing subnet in the peered VPC:\n"
                "- `CLIENT_SUBNET`: Required for all workloads (ADB, Exadata, Exascale, BaseDB). Recommended `/24` for Exadata/Exascale.\n"
                "- `BACKUP_SUBNET`: Required for Exadata Dedicated (`cloud_vm_cluster`) and Exascale (`exadb_vm_cluster`). Recommended `/24`."
            ),
        },
        "deployment_topologies": {
            "1. Standalone Single-Project VPC": (
                "The customer VPC (`google_compute_network`) and all `google_oracle_database_*` resources reside in the same GCP project. "
                "Simplest topology for dedicated database projects."
            ),
            "2. Shared VPC (Host Project + Service Project)": (
                "Enterprise standard: The VPC lives in a central Shared VPC Host Project (`projects/<host-project>/global/networks/<vpc>`), "
                "while the `google_oracle_database_odb_network`, subnets, and databases are deployed in a Service Project. "
                "Requires `roles/compute.networkUser` / Service Networking permissions on the Host Project."
            ),
            "3. Hub-and-Spoke with NCC / Cloud Interconnect / HA VPN": (
                "When application VMs, GKE clusters, or on-premises users connect from a different VPC or on-prem datacenter via "
                "Network Connectivity Center (NCC), VPC Network Peering, or Cloud Interconnect/VPN, ensure custom route export/import "
                "(`export_custom_routes = true` / `import_custom_routes = true`) and Cloud Router custom route advertisements include the ODB `CLIENT_SUBNET` CIDR."
            ),
            "4. Private DNS Resolution (`*.oraclevcn.com`)": (
                "ODB@GCP automatically configures DNS forwarding for the ODB Network's private DNS domain (e.g., `*.oraclevcn.com`) "
                "into the linked customer VPC so SCAN listeners and Autonomous DB private endpoints resolve seamlessly."
            ),
        },
        "anti_hallucination_rules": [
            "NEVER tell a customer to manually set up an IPSec VPN or Cross-Cloud Interconnect between GCP and OCI to create an ODB Network; `google_oracle_database_odb_network` handles the colocated partner peering automatically.",
            "NEVER use a CIDR smaller than `/28` (such as `/29` or `/30`) for an ODB Subnet.",
            "In `hashicorp/google`, the parent network attribute on `google_oracle_database_odb_subnet` is `odbnetwork` (no underscore), while on workload resources it is `odb_network`.",
        ],
    },
    "backup_and_recovery": {
        "title": "Backup, Recovery, Point-in-Time Recovery (PITR) & High Availability / DR",
        "summary": (
            "Oracle Database@Google Cloud provides native automated backups, point-in-time recovery (PITR), and "
            "Oracle Data Guard / Active Data Guard across all database offerings."
        ),
        "by_workload": {
            "Autonomous Database (`google_oracle_database_autonomous_database`)": [
                "Automated daily backups stored in Oracle-managed OCI Multicloud Object Storage.",
                "Configurable retention period: `backup_retention_period_days` (1 to 60 days; default 60 days).",
                "Point-in-Time Recovery (PITR) down to the second within the retention window.",
                "High Availability & DR: Supports Autonomous Data Guard (local standby in another zone or cross-region standby).",
            ],
            "Exadata Dedicated (`cloud_vm_cluster`) & Exascale (`exadb_vm_cluster`)": [
                "Backup traffic flows over the dedicated `BACKUP_SUBNET` (`purpose = \"BACKUP_SUBNET\"`) so backup I/O never contends with client SQL traffic on `CLIENT_SUBNET`.",
                "Supports Oracle Database Autonomous Recovery Service (Zero Data Loss Recovery Appliance / ZDLRA) and automated RMAN backups to OCI Object Storage (1–60 days).",
                "Customers can also run custom RMAN backups directly to **Google Cloud Storage (GCS)** buckets via Private Google Access.",
                "High Availability & DR: Native Oracle Real Application Clusters (RAC) across 2+ compute nodes + Oracle Active Data Guard across availability zones or regions.",
            ],
            "Base Database Service VM (`google_oracle_database_db_system`)": [
                "Automated daily incremental RMAN backups managed via OCI control plane or custom RMAN to Google Cloud Storage (GCS).",
                "Supports 1-node VM or 2-node RAC with Oracle Data Guard for disaster recovery.",
            ],
        },
        "anti_hallucination_rules": [
            "Exadata (`cloud_vm_cluster`) and Exascale (`exadb_vm_cluster`) REQUIRE both `odb_subnet` (`CLIENT_SUBNET`) and `backup_odb_subnet` (`BACKUP_SUBNET`).",
            "Autonomous Database (`autonomous_database`) and BaseDB (`db_system`) only require `odb_subnet` (`CLIENT_SUBNET`).",
        ],
    },
    "encryption_and_cmek": {
        "title": "Encryption at Rest (TDE), In-Transit (mTLS/TLS) & Customer-Managed Encryption Keys (CMEK)",
        "summary": (
            "All Oracle Database@Google Cloud workloads are encrypted at rest using Oracle Transparent Data Encryption (TDE) "
            "and encrypted in transit using TLS 1.2+ / Mutual TLS (mTLS). Customers can use Oracle-managed keys or bring "
            "Customer-Managed Encryption Keys (CMEK) via Google Cloud KMS or OCI Vault."
        ),
        "encryption_layers": {
            "1. Default Encryption at Rest (TDE)": (
                "Enabled automatically on 100% of ODB@GCP databases (ADB, Exadata, Exascale, BaseDB) using AES-256 "
                "Transparent Data Encryption (TDE) with zero performance overhead."
            ),
            "2. Encryption in Transit (mTLS & TLS)": (
                "Autonomous Database supports `mtls_connection_required = true` (enforcing Wallet-based mutual TLS) or "
                "`mtls_connection_required = false` (allowing walletless TLS 1.2+ connections strictly from inside the peered VPC)."
            ),
            "3. Customer-Managed Encryption Keys (CMEK) with Google Cloud KMS": (
                "Customers can manage the TDE Master Encryption Key in **Google Cloud KMS** (`cloudkms.googleapis.com`, including Cloud HSM and Cloud EKM) "
                "or in **OCI Vault** (`vault_id` / `secret_id`):\n"
                "- Create a Cloud KMS KeyRing and symmetric CryptoKey in the same GCP region as the ODB deployment.\n"
                "- Grant the ODB Service Agent (`service-<PROJECT_NUMBER>@gcp-sa-oracledatabase.iam.gserviceaccount.com`) the "
                "`roles/cloudkms.cryptoKeyEncrypterDecrypter` IAM role on the Cloud KMS key.\n"
                "- Configure the KMS key in the database security settings or OCI Multicloud key management integration."
            ),
        },
        "cmek_iam_command": (
            "gcloud kms keys add-iam-policy-binding <KEY_NAME> "
            "--keyring=<KEYRING_NAME> --location=<REGION> "
            "--member=\"serviceAccount:service-<PROJECT_NUMBER>@gcp-sa-oracledatabase.iam.gserviceaccount.com\" "
            "--role=\"roles/cloudkms.cryptoKeyEncrypterDecrypter\" --project=<PROJECT_ID>"
        ),
        "anti_hallucination_rules": [
            "TDE encryption at rest cannot be disabled on ODB@GCP; it is always active.",
            "When using Google Cloud KMS for CMEK, the `roles/cloudkms.cryptoKeyEncrypterDecrypter` role must be granted to the ODB Service Agent before creating or rotating the database master key.",
        ],
    },
    "monitoring_and_observability": {
        "title": "Monitoring, Cloud Logging, Audit Logs & Oracle Operations Insights",
        "summary": (
            "ODB@GCP integrates natively with Google Cloud Observability (Cloud Monitoring & Cloud Logging) while also "
            "providing full access to Oracle's deep database diagnostics (Operations Insights, Database Management, AWR)."
        ),
        "observability_stack": {
            "1. Google Cloud Monitoring (`monitoring.googleapis.com`)": [
                "Metrics are automatically exported under the `oracledatabase.googleapis.com` metric namespace.",
                "Key metrics: CPU / ECPU utilization, storage space used/allocated, IOPS, throughput, active sessions, and node health.",
                "Build Cloud Monitoring Dashboards and Alerting Policies (e.g. pager alerts when storage > 80% or ECPU > 90%).",
            ],
            "2. Google Cloud Logging & Cloud Audit Logs (`logging.googleapis.com`)": [
                "Captures Admin Activity and Data Access audit logs for all `oracledatabase.googleapis.com` API calls.",
                "VM Cluster diagnostic events (`data_collection_options { is_diagnostics_events_enabled = true, is_health_monitoring_enabled = true, is_incident_logs_enabled = true }`).",
            ],
            "3. Oracle Operations Insights & Database Management": [
                "On Autonomous Database: `operations_insights_state = \"ENABLED\"` inside `properties { ... }`.",
                "On BaseDB / Exadata: `database_management_config` and Automatic Workload Repository (AWR) / Active Session History (ASH) via the `oci_url` console link or Enterprise Manager.",
            ],
        },
        "anti_hallucination_rules": [
            "On `google_oracle_database_autonomous_database`, `operations_insights_state` is nested inside `properties { ... }` (`ENABLED` or `NOT_ENABLED`).",
            "On `google_oracle_database_cloud_vm_cluster` and `google_oracle_database_exadb_vm_cluster`, `data_collection_options` is a nested block inside `properties { ... }`.",
        ],
    },
}

SUPPORTED_ONBOARDING_TOPICS: tuple[str, ...] = ("all",) + tuple(ONBOARDING_KNOWLEDGE_BASE.keys())


def get_odb_onboarding_and_architecture_guide(topic: str = "all") -> str:
    """Retrieves authoritative, hallucination-free onboarding and architecture documentation for ODB@GCP.

    Always call this tool when a customer asks about:
    - End-to-end onboarding steps, Prerequisites, IAM roles, or GCP APIs (`prerequisites_and_iam`)
    - Purchasing via Google Cloud Marketplace: Private Offer vs. Pay-As-You-Go (`marketplace_procurement`)
    - OCI Account Linking, Multicloud tenancy setup, or entitlements (`account_linking_and_tenancy`)
    - My Oracle Support (MOS) registration, CSI numbers, or support responsibilities (`support_registration_mos`)
    - ODB Networks, ODB Subnets, Shared VPC, Hub-and-Spoke, or DNS (`odb_networks_and_topologies`)
    - Backup and Recovery, RMAN, PITR, or Data Guard DR (`backup_and_recovery`)
    - Encryption at rest (TDE), mTLS, or CMEK with Google Cloud KMS / OCI Vault (`encryption_and_cmek`)
    - Monitoring, Cloud Logging, Audit Logs, or Operations Insights (`monitoring_and_observability`)

    Args:
        topic: One of `all`, `prerequisites_and_iam`, `marketplace_procurement`,
            `account_linking_and_tenancy`, `support_registration_mos`,
            `odb_networks_and_topologies`, `backup_and_recovery`,
            `encryption_and_cmek`, or `monitoring_and_observability`.

    Returns:
        JSON string containing the grounded onboarding & architecture guide for the requested topic.
    """
    cleaned = (topic or "all").strip().lower()
    if cleaned in ONBOARDING_KNOWLEDGE_BASE:
        entry = ONBOARDING_KNOWLEDGE_BASE[cleaned]
        return json.dumps(
            {
                "valid": True,
                "topic": cleaned,
                "title": entry.get("title", cleaned),
                "available_topics": list(ONBOARDING_KNOWLEDGE_BASE.keys()),
                "guide": entry,
            },
            indent=2,
        )

    # Fuzzy match if user passed a partial keyword like "cmek", "backup", "support", "marketplace", "network"
    keyword_map = {
        "prereq": "prerequisites_and_iam",
        "iam": "prerequisites_and_iam",
        "market": "marketplace_procurement",
        "offer": "marketplace_procurement",
        "payg": "marketplace_procurement",
        "link": "account_linking_and_tenancy",
        "tenancy": "account_linking_and_tenancy",
        "support": "support_registration_mos",
        "mos": "support_registration_mos",
        "csi": "support_registration_mos",
        "network": "odb_networks_and_topologies",
        "vpc": "odb_networks_and_topologies",
        "subnet": "odb_networks_and_topologies",
        "backup": "backup_and_recovery",
        "recovery": "backup_and_recovery",
        "encrypt": "encryption_and_cmek",
        "cmek": "encryption_and_cmek",
        "kms": "encryption_and_cmek",
        "monitor": "monitoring_and_observability",
        "log": "monitoring_and_observability",
    }
    for kw, mapped_topic in keyword_map.items():
        if kw in cleaned:
            entry = ONBOARDING_KNOWLEDGE_BASE[mapped_topic]
            return json.dumps(
                {
                    "valid": True,
                    "topic": mapped_topic,
                    "title": entry.get("title", mapped_topic),
                    "available_topics": list(ONBOARDING_KNOWLEDGE_BASE.keys()),
                    "guide": entry,
                },
                indent=2,
            )

    return json.dumps(
        {
            "valid": True,
            "topic": "all" if cleaned in ("all", "") else cleaned,
            "title": "Oracle Database@Google Cloud — End-to-End Onboarding Lifecycle Overview",
            "available_topics": list(ONBOARDING_KNOWLEDGE_BASE.keys()),
            "end_to_end_onboarding_phases": [
                "Phase 1: Prerequisites, GCP APIs & IAM Roles (prerequisites_and_iam)",
                "Phase 2: Google Cloud Marketplace — Private Offer or Pay-As-You-Go (marketplace_procurement)",
                "Phase 3: OCI Account Linking & Tenancy Federation (account_linking_and_tenancy)",
                "Phase 4: My Oracle Support (MOS) & CSI Registration (support_registration_mos)",
                "Phase 5: ODB Network & Subnet Provisioning (odb_networks_and_topologies)",
                "Phase 6: Database Provisioning, Backup/Recovery, CMEK Encryption & Monitoring",
            ],
            "guides": ONBOARDING_KNOWLEDGE_BASE,
        },
        indent=2,
    )


def evaluate_customer_onboarding_readiness(
    project_id: str = "my-odb-project-01",
    procurement_model: str = "private_offer",
    networking_topology: str = "standalone_vpc",
    workload_type: str = "adb",
    encryption_mode: str = "google_managed",
    has_gcp_billing_and_org_admin: bool = True,
    has_enabled_oracledatabase_api: bool = True,
    marketplace_procurement_mode: str = "",
    has_linked_oci_tenancy: bool = True,
    has_mos_account_and_csi: bool = True,
) -> str:
    """Generates a tailored End-to-End Onboarding Checklist & Readiness Score for a customer's ODB@GCP scenario.

    Args:
        project_id: Target Google Cloud Project ID.
        procurement_model: `private_offer` or `payg` (Pay-As-You-Go).
        networking_topology: `standalone_vpc`, `shared_vpc`, or `hub_and_spoke`.
        workload_type: `adb`, `exadata_dedicated`, `exascale`, or `basedb`.
        encryption_mode: `google_managed` (default TDE) or `cmek` (Cloud KMS / OCI Vault).
        has_gcp_billing_and_org_admin: Whether GCP billing & org admin prerequisites are complete.
        has_enabled_oracledatabase_api: Whether `oracledatabase.googleapis.com` is enabled.
        marketplace_procurement_mode: Optional override for `procurement_model` (`private_offer`, `payg`, or `none`).
        has_linked_oci_tenancy: Whether the OCI tenancy is linked.
        has_mos_account_and_csi: Whether My Oracle Support (MOS) CSI is registered.

    Returns:
        JSON string with readiness score, blocking items, ordered onboarding steps, and exact `gcloud` commands.
    """
    cleaned_project = (project_id or "my-odb-project-01").strip()
    if not _SAFE_PROJECT_ID_RE.match(cleaned_project):
        cleaned_project = "my-odb-project-01"

    effective_proc = (marketplace_procurement_mode or procurement_model or "private_offer").strip().lower()
    net_topo = networking_topology.strip().lower()
    workload = workload_type.strip().lower()
    enc_mode = encryption_mode.strip().lower()

    needs_backup_subnet = workload in {"exadata_dedicated", "exascale"}

    blocking_items: list[str] = []
    completed_checks = 0
    if has_gcp_billing_and_org_admin:
        completed_checks += 1
    else:
        blocking_items.append("Phase 1 Blocker: Active Google Cloud Billing Account and Org/Project Admin roles required.")

    if has_enabled_oracledatabase_api:
        completed_checks += 1
    else:
        blocking_items.append("Phase 1 Blocker: Enable `oracledatabase.googleapis.com` and `servicenetworking.googleapis.com`.")

    if effective_proc in {"private_offer", "payg"}:
        completed_checks += 1
    else:
        blocking_items.append("Phase 2 Blocker: Subscribe via Google Cloud Marketplace Private Offer or Pay-As-You-Go (PAYG).")

    if has_linked_oci_tenancy:
        completed_checks += 1
    else:
        blocking_items.append("Phase 3 Blocker: Complete OCI Account Linking in the Google Cloud Oracle Database partner portal.")

    if has_mos_account_and_csi:
        completed_checks += 1
    else:
        blocking_items.append("Phase 4 Blocker: Register Customer Support Identifier (CSI) in My Oracle Support (support.oracle.com).")

    readiness_score_pct = int((completed_checks / 5) * 100)

    steps: list[dict[str, Any]] = [
        {
            "step": 1,
            "phase": "GCP Project & API Prerequisites",
            "actions": [
                f"Enable required Google Cloud APIs in project `{cleaned_project}`.",
                "Grant `roles/oracledatabase.admin` to the onboarding architect and `roles/billing.admin` + `roles/consumerprocurement.orderAdmin` to the Marketplace buyer.",
            ],
            "commands": [
                f"gcloud services enable oracledatabase.googleapis.com compute.googleapis.com servicenetworking.googleapis.com cloudkms.googleapis.com monitoring.googleapis.com logging.googleapis.com --project={cleaned_project}"
            ],
        },
        {
            "step": 2,
            "phase": (
                "Google Cloud Marketplace — Private Offer Acceptance"
                if "private" in effective_proc
                else "Google Cloud Marketplace — Pay-As-You-Go (PAYG) Subscription"
            ),
            "actions": (
                [
                    "Coordinate with Oracle & Google Cloud Sales to publish the Private Offer to your Billing Account.",
                    "In Google Cloud Console -> Marketplace -> Private Offers, accept the offer to activate your `entitlement_id` (100% MACC eligible).",
                ]
                if "private" in effective_proc
                else [
                    "In Google Cloud Console -> Marketplace, search for 'Oracle Database@Google Cloud', select Pay-As-You-Go, and subscribe with your Billing Account.",
                ]
            ),
        },
        {
            "step": 3,
            "phase": "OCI Account Linking & Tenancy Setup",
            "actions": [
                "Open Google Cloud Console -> Oracle Database@Google Cloud -> Account setup.",
                "Either create a new Partner-linked OCI tenancy or link your existing OCI tenancy.",
                "Verify the Marketplace entitlement status transitions to `ACTIVE`.",
            ],
        },
        {
            "step": 4,
            "phase": "My Oracle Support (MOS) CSI Registration",
            "actions": [
                "Copy your Customer Support Identifier (CSI) from OCI Console -> Tenancy Details (or Oracle welcome email).",
                "Log in to https://support.oracle.com -> My Account -> Request Access -> register the CSI and designate a Customer User Administrator (CUA).",
                "If using BYOL, ensure your existing Oracle license CSIs are also linked to your MOS account.",
            ],
        },
        {
            "step": 5,
            "phase": f"ODB Network & Subnet Design ({net_topo})",
            "actions": [
                (
                    "In your Shared VPC Host Project, ensure the Service Project has `roles/compute.networkUser` and reference `projects/<HOST_PROJECT>/global/networks/<VPC_NAME>`."
                    if "shared" in net_topo
                    else "Ensure your target VPC exists and select non-overlapping CIDRs (minimum `/28`, recommended `/24`) in your target `gcp_oracle_zone`."
                ),
                (
                    "Allocate TWO non-overlapping ODB subnets: `CLIENT_SUBNET` (e.g. `10.20.1.0/24`) and `BACKUP_SUBNET` (e.g. `10.20.2.0/24`)."
                    if needs_backup_subnet
                    else "Allocate ONE non-overlapping ODB subnet: `CLIENT_SUBNET` (e.g. `10.20.1.0/24`)."
                ),
            ],
        },
    ]

    if "cmek" in enc_mode or "kms" in enc_mode:
        steps.append(
            {
                "step": 6,
                "phase": "CMEK Encryption Setup (Google Cloud KMS / OCI Vault)",
                "actions": [
                    "Create a regional Cloud KMS KeyRing and symmetric CryptoKey in the target region.",
                    "Grant `roles/cloudkms.cryptoKeyEncrypterDecrypter` to the ODB Service Agent (`service-<PROJECT_NUMBER>@gcp-sa-oracledatabase.iam.gserviceaccount.com`).",
                ],
                "commands": [
                    f"gcloud kms keyrings create odb-keyring --location=us-east4 --project={cleaned_project}",
                    f"gcloud kms keys create odb-tde-key --keyring=odb-keyring --location=us-east4 --purpose=encryption --project={cleaned_project}",
                ],
            }
        )

    steps.append(
        {
            "step": len(steps) + 1,
            "phase": f"Day-1 Terraform Generation & Monitoring ({workload})",
            "actions": [
                f"Generate the verified `hashicorp/google >= 7.0.0` Terraform bundle using `generate_golden_odb_terraform` for workload `{workload}`.",
                "Verify Cloud Monitoring metrics (`oracledatabase.googleapis.com/*`) and enable Oracle Operations Insights / diagnostic collection.",
            ],
        }
    )

    return json.dumps(
        {
            "valid": True,
            "project_id": cleaned_project,
            "procurement_model": effective_proc,
            "networking_topology": net_topo,
            "workload_type": workload,
            "encryption_mode": enc_mode,
            "readiness_score_pct": readiness_score_pct,
            "blocking_items": blocking_items,
            "onboarding_checklist": steps,
        },
        indent=2,
    )


def check_onboarding_response_for_hallucinations(response_text: str) -> list[str]:
    """Scans LLM onboarding/architecture responses for common factual or diagram hallucinations."""
    issues: list[str] = []
    lower_text = (response_text or "").lower()

    # 1. Misconception that ODB Network requires manual IPSec VPN between GCP and OCI
    if re.search(
        r"manual\s+(ipsec\s+)?vpn\s+between\s+(gcp|google\s+cloud)\s+and\s+oci",
        lower_text,
    ):
        issues.append(
            "ONBOARDING_HALLUCINATION: ODB@GCP does NOT require a manual IPSec VPN between GCP and OCI. "
            "`google_oracle_database_odb_network` uses dedicated, Google-managed partner interconnect colocated in the GCP region."
        )

    # 2. Suggesting /29, /30, /31, or /32 for an ODB Subnet
    if re.search(
        r"(client_subnet|backup_subnet|odb_subnet|cidr_range)[^\n]{0,40}/(29|30|31|32)\b",
        lower_text,
    ):
        issues.append(
            "ONBOARDING_HALLUCINATION: ODB Subnets (`google_oracle_database_odb_subnet`) require a minimum CIDR prefix of `/28` (16 IPs). "
            "Prefixes `/29` through `/32` are rejected by the ODB@GCP API."
        )

    # 3. Wrong KMS service agent email (`gcp-sa-oracle.iam` instead of `gcp-sa-oracledatabase.iam`)
    if "@gcp-sa-oracle.iam.gserviceaccount.com" in lower_text or "@gcp-sa-odb.iam.gserviceaccount.com" in lower_text:
        issues.append(
            "ONBOARDING_HALLUCINATION: Wrong CMEK service agent email. The exact ODB@GCP Service Agent is "
            "`service-<PROJECT_NUMBER>@gcp-sa-oracledatabase.iam.gserviceaccount.com`."
        )

    # 4. Broken Mermaid diagram syntax check (unquoted parentheses inside square brackets `id[Label (info)]`)
    for mermaid_match in re.finditer(r"```mermaid\s*\n(.*?)```", response_text or "", re.DOTALL):
        diagram_body = mermaid_match.group(1)
        if re.search(r"\b[A-Za-z0-9_]+\[[^\"\]\n]*\([^\]\n]*\)\]", diagram_body):
            issues.append(
                "DIAGRAM_SYNTAX_GUARDRAIL: Mermaid node labels containing parentheses `(...)` must be enclosed in double quotes "
                "(e.g., `NodeID[\"Label (Detail)\"]`) to prevent Mermaid parser errors."
            )

    return issues

