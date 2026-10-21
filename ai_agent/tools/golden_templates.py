"""Guardrail 1: Golden Baseline Terraform Generator for ODB@GCP.

Eliminates LLM boilerplate hallucinations by rendering proven, schema-verified
Terraform (`hashicorp/google >= 7.0.0`) from strict typed parameters while enforcing:
- CIDR `/28` minimum prefix & zero overlap validation before rendering
- `deletion_protection = true` on stateful resources
- `sensitive = true` on `db_admin_password` (never written to `terraform.tfvars`)
"""

from __future__ import annotations

import json
import re
from typing import Any

from ai_agent.tools.network_validator import validate_odb_network_cidrs

_SAFE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9\-]{1,61}[a-z0-9]$")
_ORACLE_DB_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,13}$")


def generate_golden_odb_terraform(
    project_id: str,
    region: str = "us-east4",
    gcp_oracle_zone: str = "us-east4-b-r1",
    workload_type: str = "adb",
    environment_prefix: str = "odb-prod",
    vpc_name: str = "odb-vpc",
    vpc_cidr: str = "10.10.0.0/16",
    client_subnet_cidr: str = "10.20.1.0/24",
    backup_subnet_cidr: str = "10.20.2.0/24",
    shared_vpc_host_project_id: str = "",
    db_name: str = "ODBPROD1",
    db_version: str = "23ai",
    compute_count: int = 4,
    storage_size_tb: int = 1,
    exadata_shape: str = "Exadata.X11M",
    license_model: str = "LICENSE_INCLUDED",
    enable_deletion_protection: bool = True,
    deployment_layer: str = "full_stack",
    existing_odb_network: str = "",
    existing_client_odb_subnet: str = "",
    existing_backup_odb_subnet: str = "",
    existing_exadata_infrastructure: str = "",
) -> str:
    """Generates a complete, production-ready Golden Terraform bundle (`hashicorp/google >= 7.0.0`) for ODB@GCP.

    Supports both monolithic full-stack deployments (`deployment_layer="full_stack"`) and Enterprise
    Separation of Duties across Network, Infrastructure, and Database teams:
    - `deployment_layer="network_only"`: Generates only `networking.tf` (ODB Network + Client/Backup Subnets) for the Network Team.
    - `deployment_layer="infra_only"`: Generates only Exadata Infrastructure / Exascale Storage Vault for the Infrastructure Team.
    - `deployment_layer="database_only"`: Generates only the Database / VM Cluster resource referencing pre-existing ODB Network/Infra variables for the Database Team.

    Args:
        project_id: Target Google Cloud service project ID.
        region: Google Cloud region (e.g. `us-east4`, `us-west3`, `europe-west2`).
        gcp_oracle_zone: Oracle zone within the region (e.g. `us-east4-b-r1`).
        workload_type: One of `adb` (Autonomous DB), `exadata_dedicated`, `exascale`, or `basedb`.
        environment_prefix: Resource naming prefix (e.g. `odb-prod`).
        vpc_name: Name of the customer VPC to peer with the ODB Network.
        vpc_cidr: Primary VPC CIDR (used for overlap checking, e.g. `10.10.0.0/16`).
        client_subnet_cidr: ODB Client Subnet CIDR (minimum `/28`, e.g. `10.20.1.0/24`).
        backup_subnet_cidr: ODB Backup Subnet CIDR (required for `exadata_dedicated` and `exascale`).
        shared_vpc_host_project_id: Optional Shared VPC host project ID if using Shared VPC.
        db_name: Oracle database name (alphanumeric, max 14 chars, e.g. `ODBPROD1`).
        db_version: Oracle version (`23ai` or `19c`).
        compute_count: ECPU / OCPU count.
        storage_size_tb: Storage allocation in TB.
        exadata_shape: Hardware shape for Exadata (`Exadata.X11M`, `Exadata.X9M`) or BaseDB (`VM.Standard.E4.Flex`).
        license_model: `LICENSE_INCLUDED` or `BRING_YOUR_OWN_LICENSE`.
        enable_deletion_protection: Whether to set `deletion_protection = true` (default `True`).
        deployment_layer: Separation-of-Duties layer: `'full_stack'` (default), `'network_only'`, `'infra_only'`, or `'database_only'`.
        existing_odb_network: Pre-existing ODB Network resource name/ID handed off by the Network Team (used when `deployment_layer='database_only'`).
        existing_client_odb_subnet: Pre-existing Client ODB Subnet resource name/ID handed off by the Network Team.
        existing_backup_odb_subnet: Pre-existing Backup ODB Subnet resource name/ID handed off by the Network Team.
        existing_exadata_infrastructure: Pre-existing Exadata Infrastructure (or Exascale Vault) resource name/ID handed off by the Infrastructure Team.

    Returns:
        JSON string containing `valid`, `deployment_layer`, `files` (mapping of `.tf` filenames to HCL code), and `guardrail_checks`.
    """
    workload = workload_type.strip().lower()
    if workload not in {"adb", "exadata_dedicated", "exascale", "basedb"}:
        return json.dumps(
            {
                "valid": False,
                "error": f"Unsupported workload_type '{workload}'. Must be one of: adb, exadata_dedicated, exascale, basedb.",
            },
            indent=2,
        )

    raw_layer = (deployment_layer or "full_stack").strip().lower()
    layer_aliases = {
        "full_stack": "full_stack",
        "full": "full_stack",
        "all": "full_stack",
        "network_only": "network_only",
        "network": "network_only",
        "networking": "network_only",
        "infra_only": "infra_only",
        "infrastructure_only": "infra_only",
        "infrastructure": "infra_only",
        "infra": "infra_only",
        "database_only": "database_only",
        "db_only": "database_only",
        "database": "database_only",
        "workload_only": "database_only",
        "vm_cluster_only": "database_only",
    }
    layer = layer_aliases.get(raw_layer, "")
    if not layer:
        return json.dumps(
            {
                "valid": False,
                "error": (
                    f"Unsupported deployment_layer '{deployment_layer}'. "
                    "Must be one of: full_stack, network_only, infra_only, database_only."
                ),
            },
            indent=2,
        )

    for field_name, val in (
        ("project_id", project_id),
        ("environment_prefix", environment_prefix),
        ("vpc_name", vpc_name),
    ):
        if not _SAFE_ID_PATTERN.match(val.strip()):
            return json.dumps(
                {
                    "valid": False,
                    "error": f"Invalid {field_name} '{val}'. Must contain only lowercase letters, digits, and hyphens.",
                },
                indent=2,
            )

    if not _ORACLE_DB_NAME_PATTERN.match(db_name.strip()):
        return json.dumps(
            {
                "valid": False,
                "error": f"Invalid Oracle db_name '{db_name}'. Must start with a letter and be 1-14 alphanumeric characters.",
            },
            indent=2,
        )

    needs_backup = workload in {"exadata_dedicated", "exascale"}
    if layer in {"full_stack", "network_only"}:
        cidr_check = json.loads(
            validate_odb_network_cidrs(
                vpc_cidr=vpc_cidr,
                client_subnet_cidr=client_subnet_cidr,
                backup_subnet_cidr=backup_subnet_cidr if needs_backup else "",
            )
        )
        if not cidr_check.get("valid"):
            return json.dumps(
                {
                    "valid": False,
                    "error": "Network CIDR guardrail validation failed.",
                    "cidr_validation": cidr_check,
                },
                indent=2,
            )

    proj = project_id.strip()
    reg = region.strip()
    ozone = gcp_oracle_zone.strip()
    env_pfx = environment_prefix.strip()
    network_project = shared_vpc_host_project_id.strip() or proj
    del_prot_str = "true" if enable_deletion_protection else "false"

    versions_tf = """terraform {
  required_version = ">= 1.3.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 7.0.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = ">= 7.0.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}
"""

    # -------------------------------------------------------------------------
    # LAYER 1: NETWORK TEAM ONLY (`deployment_layer == "network_only"`)
    # -------------------------------------------------------------------------
    if layer == "network_only":
        variables_tf = f"""variable "project_id" {{
  description = "Google Cloud project ID for ODB Network & Subnets (Network Team)."
  type        = string
  default     = "{proj}"
}}

variable "network_project_id" {{
  description = "Google Cloud project ID hosting the VPC (Host project for Shared VPC, or same as project_id)."
  type        = string
  default     = "{network_project}"
}}

variable "region" {{
  description = "Google Cloud region for ODB@GCP deployment."
  type        = string
  default     = "{reg}"
}}

variable "gcp_oracle_zone" {{
  description = "Oracle Database@Google Cloud zone within the region."
  type        = string
  default     = "{ozone}"
}}

variable "environment_prefix" {{
  description = "Resource naming prefix."
  type        = string
  default     = "{env_pfx}"
}}

variable "vpc_name" {{
  description = "Existing customer VPC name to link with the ODB Network."
  type        = string
  default     = "{vpc_name.strip()}"
}}

variable "client_subnet_cidr" {{
  description = "CIDR range for ODB CLIENT_SUBNET (minimum /28)."
  type        = string
  default     = "{client_subnet_cidr.strip()}"
}}

variable "backup_subnet_cidr" {{
  description = "CIDR range for ODB BACKUP_SUBNET (minimum /28, required for Exadata/Exascale)."
  type        = string
  default     = "{backup_subnet_cidr.strip()}"
}}
"""
        backup_subnet_hcl = ""
        backup_output_hcl = ""
        if needs_backup:
            backup_subnet_hcl = f"""
resource "google_oracle_database_odb_subnet" "backup_subnet" {{
  project             = var.project_id
  location            = var.region
  odbnetwork          = google_oracle_database_odb_network.odb_net.odb_network_id
  odb_subnet_id       = "${{var.environment_prefix}}-backup-subnet"
  cidr_range          = var.backup_subnet_cidr
  purpose             = "BACKUP_SUBNET"
  deletion_protection = {del_prot_str}

  labels = {{
    environment = var.environment_prefix
    managed_by  = "terraform-network-team"
  }}
}}
"""
            backup_output_hcl = """
output "backup_odb_subnet_name" {
  description = "Handoff output for Infrastructure / Database Team (var.existing_backup_odb_subnet)."
  value       = google_oracle_database_odb_subnet.backup_subnet.name
}
"""

        networking_tf = f"""data "google_compute_network" "customer_vpc" {{
  name    = var.vpc_name
  project = var.network_project_id
}}

resource "google_oracle_database_odb_network" "odb_net" {{
  project             = var.project_id
  location            = var.region
  odb_network_id      = "${{var.environment_prefix}}-odb-net"
  network             = data.google_compute_network.customer_vpc.id
  gcp_oracle_zone     = var.gcp_oracle_zone
  deletion_protection = {del_prot_str}

  labels = {{
    environment = var.environment_prefix
    managed_by  = "terraform-network-team"
  }}
}}

resource "google_oracle_database_odb_subnet" "client_subnet" {{
  project             = var.project_id
  location            = var.region
  odbnetwork          = google_oracle_database_odb_network.odb_net.odb_network_id
  odb_subnet_id       = "${{var.environment_prefix}}-client-subnet"
  cidr_range          = var.client_subnet_cidr
  purpose             = "CLIENT_SUBNET"
  deletion_protection = {del_prot_str}

  labels = {{
    environment = var.environment_prefix
    managed_by  = "terraform-network-team"
  }}
}}
{backup_subnet_hcl}"""

        outputs_tf = f"""output "odb_network_id" {{
  value = google_oracle_database_odb_network.odb_net.id
}}

output "odb_network_name" {{
  description = "Handoff output for Infrastructure / Database Team (var.existing_odb_network)."
  value       = google_oracle_database_odb_network.odb_net.name
}}

output "client_odb_subnet_name" {{
  description = "Handoff output for Infrastructure / Database Team (var.existing_client_odb_subnet)."
  value       = google_oracle_database_odb_subnet.client_subnet.name
}}
{backup_output_hcl}"""

        tfvars_content = f"""# Generated by ODB@GCP AI Architect Agent — Network Team Layer (network_only)
project_id         = "{proj}"
network_project_id = "{network_project}"
region             = "{reg}"
gcp_oracle_zone    = "{ozone}"
environment_prefix = "{env_pfx}"
vpc_name           = "{vpc_name.strip()}"
client_subnet_cidr = "{client_subnet_cidr.strip()}"
backup_subnet_cidr = "{backup_subnet_cidr.strip()}"
"""
        files = {
            "versions.tf": versions_tf,
            "variables.tf": variables_tf,
            "networking.tf": networking_tf,
            "outputs.tf": outputs_tf,
            "terraform.tfvars": tfvars_content,
        }
        return json.dumps(
            {
                "valid": True,
                "workload_type": workload,
                "deployment_layer": "network_only",
                "team_role": "network",
                "guardrail_checks": {
                    "cidr_slash28_and_overlap": "PASSED",
                    "deletion_protection_enabled": enable_deletion_protection,
                    "separation_of_duties_layer": "network_only (no database resources or passwords in network state)",
                    "provider_constraint": "hashicorp/google >= 7.0.0",
                },
                "files": files,
            },
            indent=2,
        )

    # -------------------------------------------------------------------------
    # LAYER 2: INFRASTRUCTURE TEAM ONLY (`deployment_layer == "infra_only"`)
    # -------------------------------------------------------------------------
    if layer == "infra_only":
        variables_tf = f"""variable "project_id" {{
  description = "Google Cloud service project ID for Oracle Exadata / Exascale Infrastructure (Infrastructure Team)."
  type        = string
  default     = "{proj}"
}}

variable "region" {{
  description = "Google Cloud region for ODB@GCP deployment."
  type        = string
  default     = "{reg}"
}}

variable "gcp_oracle_zone" {{
  description = "Oracle Database@Google Cloud zone within the region."
  type        = string
  default     = "{ozone}"
}}

variable "environment_prefix" {{
  description = "Resource naming prefix."
  type        = string
  default     = "{env_pfx}"
}}
"""
        if workload == "exascale":
            workload_tf = f"""resource "google_oracle_database_exascale_db_storage_vault" "vault" {{
  project                      = var.project_id
  location                     = var.region
  gcp_oracle_zone              = var.gcp_oracle_zone
  exascale_db_storage_vault_id = "${{var.environment_prefix}}-exascale-vault"
  display_name                 = "${{var.environment_prefix}}-exascale-vault"
  deletion_protection          = {del_prot_str}

  properties {{
    additional_flash_cache_percent = 100
    exascale_db_storage_details {{
      total_size_gbs = {max(300, int(storage_size_tb) * 1024)}
    }}
  }}
}}
"""
            outputs_tf = """output "exascale_vault_id" {
  value = google_oracle_database_exascale_db_storage_vault.vault.id
}

output "exascale_vault_name" {
  description = "Handoff output for Database Team (var.existing_exadata_infrastructure)."
  value       = google_oracle_database_exascale_db_storage_vault.vault.name
}
"""
        else:
            workload_tf = f"""resource "google_oracle_database_cloud_exadata_infrastructure" "exa_infra" {{
  project                         = var.project_id
  location                        = var.region
  gcp_oracle_zone                 = var.gcp_oracle_zone
  cloud_exadata_infrastructure_id = "${{var.environment_prefix}}-exa-infra"
  display_name                    = "${{var.environment_prefix}}-exa-infra"
  deletion_protection             = {del_prot_str}

  properties {{
    shape         = "{exadata_shape.strip()}"
    compute_count = 2
    storage_count = 3
  }}
}}
"""
            outputs_tf = """output "exadata_infrastructure_id" {
  value = google_oracle_database_cloud_exadata_infrastructure.exa_infra.id
}

output "exadata_infrastructure_name" {
  description = "Handoff output for Database Team (var.existing_exadata_infrastructure)."
  value       = google_oracle_database_cloud_exadata_infrastructure.exa_infra.name
}
"""

        tfvars_content = f"""# Generated by ODB@GCP AI Architect Agent — Infrastructure Team Layer (infra_only)
project_id         = "{proj}"
region             = "{reg}"
gcp_oracle_zone    = "{ozone}"
environment_prefix = "{env_pfx}"
"""
        files = {
            "versions.tf": versions_tf,
            "variables.tf": variables_tf,
            "workload.tf": workload_tf,
            "outputs.tf": outputs_tf,
            "terraform.tfvars": tfvars_content,
        }
        return json.dumps(
            {
                "valid": True,
                "workload_type": workload,
                "deployment_layer": "infra_only",
                "team_role": "infrastructure",
                "guardrail_checks": {
                    "deletion_protection_enabled": enable_deletion_protection,
                    "separation_of_duties_layer": "infra_only (Exadata/Exascale infrastructure isolated from Network & DBA state)",
                    "provider_constraint": "hashicorp/google >= 7.0.0",
                },
                "files": files,
            },
            indent=2,
        )

    # -------------------------------------------------------------------------
    # LAYER 3: DATABASE TEAM ONLY (`deployment_layer == "database_only"`)
    # -------------------------------------------------------------------------
    if layer == "database_only":
        default_odb_net = (
            existing_odb_network.strip()
            or f"projects/{proj}/locations/{reg}/odbNetworks/{env_pfx}-odb-net"
        )
        default_client_sub = (
            existing_client_odb_subnet.strip()
            or f"projects/{proj}/locations/{reg}/odbNetworks/{env_pfx}-odb-net/odbSubnets/{env_pfx}-client-subnet"
        )
        default_backup_sub = (
            existing_backup_odb_subnet.strip()
            or f"projects/{proj}/locations/{reg}/odbNetworks/{env_pfx}-odb-net/odbSubnets/{env_pfx}-backup-subnet"
        )
        default_exa_infra = (
            existing_exadata_infrastructure.strip()
            or (
                f"projects/{proj}/locations/{reg}/exascaleDbStorageVaults/{env_pfx}-exascale-vault"
                if workload == "exascale"
                else f"projects/{proj}/locations/{reg}/cloudExadataInfrastructures/{env_pfx}-exa-infra"
            )
        )

        extra_upstream_vars = ""
        extra_upstream_tfvars = ""
        if needs_backup:
            extra_upstream_vars = f"""
variable "existing_backup_odb_subnet" {{
  description = "Pre-existing BACKUP_SUBNET resource name handed off by the Network Team."
  type        = string
  default     = "{default_backup_sub}"
}}

variable "existing_exadata_infrastructure" {{
  description = "Pre-existing Exadata Infrastructure or Exascale Vault resource name handed off by the Infrastructure Team."
  type        = string
  default     = "{default_exa_infra}"
}}
"""
            extra_upstream_tfvars = f"""existing_backup_odb_subnet      = "{default_backup_sub}"
existing_exadata_infrastructure = "{default_exa_infra}"
"""

        variables_tf = f"""variable "project_id" {{
  description = "Google Cloud service project ID for Oracle Database workload (Database Team)."
  type        = string
  default     = "{proj}"
}}

variable "region" {{
  description = "Google Cloud region for ODB@GCP deployment."
  type        = string
  default     = "{reg}"
}}

variable "gcp_oracle_zone" {{
  description = "Oracle Database@Google Cloud zone within the region."
  type        = string
  default     = "{ozone}"
}}

variable "environment_prefix" {{
  description = "Resource naming prefix."
  type        = string
  default     = "{env_pfx}"
}}

variable "existing_odb_network" {{
  description = "Pre-existing ODB Network resource name handed off by the Network Team."
  type        = string
  default     = "{default_odb_net}"
}}

variable "existing_client_odb_subnet" {{
  description = "Pre-existing CLIENT_SUBNET resource name handed off by the Network Team."
  type        = string
  default     = "{default_client_sub}"
}}
{extra_upstream_vars}
variable "db_admin_password" {{
  description = "Administrator password injected at runtime via TF_VAR_db_admin_password (never stored in tfvars)."
  type        = string
  sensitive   = true
  default     = null
}}

variable "ssh_public_keys" {{
  description = "List of SSH public keys for Exadata/Exascale/BaseDB cluster nodes."
  type        = list(string)
  default     = []
}}
"""

        if workload == "adb":
            workload_tf = f"""resource "google_oracle_database_autonomous_database" "adb" {{
  project                = var.project_id
  location               = var.region
  autonomous_database_id = "${{var.environment_prefix}}-adb"
  database               = "{db_name.strip()}"
  admin_password         = var.db_admin_password
  odb_network            = var.existing_odb_network
  odb_subnet             = var.existing_client_odb_subnet
  deletion_protection    = {del_prot_str}

  properties {{
    compute_count            = {int(compute_count)}
    data_storage_size_tb     = {int(storage_size_tb)}
    db_version               = "{db_version.strip()}"
    db_workload              = "OLTP"
    license_type             = "{license_model.strip()}"
    is_auto_scaling_enabled  = true
    mtls_connection_required = true
  }}

  labels = {{
    environment = var.environment_prefix
    workload    = "autonomous-db"
    managed_by  = "terraform-database-team"
  }}
}}
"""
            outputs_tf = """output "autonomous_database_id" {
  value = google_oracle_database_autonomous_database.adb.id
}
"""
        elif workload == "exadata_dedicated":
            workload_tf = f"""resource "google_oracle_database_cloud_vm_cluster" "vm_cluster" {{
  project                = var.project_id
  location               = var.region
  cloud_vm_cluster_id    = "${{var.environment_prefix}}-vm-cluster"
  display_name           = "${{var.environment_prefix}}-vm-cluster"
  exadata_infrastructure = var.existing_exadata_infrastructure
  odb_network            = var.existing_odb_network
  odb_subnet             = var.existing_client_odb_subnet
  backup_odb_subnet      = var.existing_backup_odb_subnet
  deletion_protection    = {del_prot_str}

  properties {{
    gi_version              = "23.0.0.0"
    cpu_core_count          = {int(compute_count)}
    data_storage_size_tb    = {max(2, int(storage_size_tb))}
    db_node_storage_size_gb = 120
    memory_size_gb          = 60
    license_type            = "{license_model.strip()}"
    ssh_public_keys         = var.ssh_public_keys
    hostname_prefix         = "exa"
    time_zone {{
      id = "UTC"
    }}
  }}
}}
"""
            outputs_tf = """output "cloud_vm_cluster_id" {
  value = google_oracle_database_cloud_vm_cluster.vm_cluster.id
}
"""
        elif workload == "exascale":
            workload_tf = f"""resource "google_oracle_database_exadb_vm_cluster" "exadb_cluster" {{
  project             = var.project_id
  location            = var.region
  gcp_oracle_zone     = var.gcp_oracle_zone
  exadb_vm_cluster_id = "${{var.environment_prefix}}-exadb-cluster"
  display_name        = "${{var.environment_prefix}}-exadb-cluster"
  odb_network         = var.existing_odb_network
  odb_subnet          = var.existing_client_odb_subnet
  backup_odb_subnet   = var.existing_backup_odb_subnet
  deletion_protection = {del_prot_str}

  properties {{
    grid_image_id                  = "gi-23ai"
    shape_attribute                = "SMART_STORAGE"
    node_count                     = 2
    enabled_ecpu_count_per_node    = {max(8, int(compute_count))}
    additional_ecpu_count_per_node = 0
    exascale_db_storage_vault      = var.existing_exadata_infrastructure
    license_model                  = "{license_model.strip()}"
    ssh_public_keys                = var.ssh_public_keys
    hostname_prefix                = "exascale"
    vm_file_system_storage {{
      size_in_gbs_per_node = 300
    }}
  }}
}}
"""
            outputs_tf = """output "exadb_vm_cluster_id" {
  value = google_oracle_database_exadb_vm_cluster.exadb_cluster.id
}
"""
        else:  # basedb
            workload_tf = f"""resource "google_oracle_database_db_system" "basedb" {{
  project             = var.project_id
  location            = var.region
  gcp_oracle_zone     = var.gcp_oracle_zone
  db_system_id        = "${{var.environment_prefix}}-basedb"
  display_name        = "${{var.environment_prefix}}-basedb"
  odb_network         = var.existing_odb_network
  odb_subnet          = var.existing_client_odb_subnet
  deletion_protection = {del_prot_str}

  properties {{
    shape                        = "VM.Standard.E4.Flex"
    compute_count                = {max(2, int(compute_count))}
    compute_model                = "ECPU"
    initial_data_storage_size_gb = {max(256, int(storage_size_tb) * 1024)}
    database_edition             = "ENTERPRISE_EDITION"
    license_model                = "{license_model.strip()}"
    node_count                   = 1
    storage_management           = "ASM"
    ssh_public_keys              = var.ssh_public_keys
    hostname_prefix              = "basedb"

    db_home {{
      db_version = "{db_version.strip()}"
      database {{
        admin_password = var.db_admin_password
        db_name        = "{db_name.strip()}"
        character_set  = "AL32UTF8"
        ncharacter_set = "AL16UTF16"
      }}
    }}
  }}
}}
"""
            outputs_tf = """output "db_system_id" {
  value = google_oracle_database_db_system.basedb.id
}
"""

        tfvars_content = f"""# Generated by ODB@GCP AI Architect Agent — Database Team Layer (database_only)
# NOTE: Never place db_admin_password here. Export TF_VAR_db_admin_password at runtime.
project_id                 = "{proj}"
region                     = "{reg}"
gcp_oracle_zone            = "{ozone}"
environment_prefix         = "{env_pfx}"
existing_odb_network       = "{default_odb_net}"
existing_client_odb_subnet = "{default_client_sub}"
{extra_upstream_tfvars}"""

        files = {
            "versions.tf": versions_tf,
            "variables.tf": variables_tf,
            "workload.tf": workload_tf,
            "outputs.tf": outputs_tf,
            "terraform.tfvars": tfvars_content,
        }
        return json.dumps(
            {
                "valid": True,
                "workload_type": workload,
                "deployment_layer": "database_only",
                "team_role": "database",
                "guardrail_checks": {
                    "deletion_protection_enabled": enable_deletion_protection,
                    "sensitive_password_excluded_from_tfvars": "PASSED",
                    "separation_of_duties_layer": "database_only (consumes pre-existing ODB Network/Infra variables without recreating network)",
                    "provider_constraint": "hashicorp/google >= 7.0.0",
                },
                "files": files,
            },
            indent=2,
        )

    # -------------------------------------------------------------------------
    # DEFAULT LAYER: FULL STACK (`deployment_layer == "full_stack"`)
    # -------------------------------------------------------------------------
    variables_tf = f"""variable "project_id" {{
  description = "Google Cloud service project ID for Oracle Database@Google Cloud resources."
  type        = string
  default     = "{proj}"
}}

variable "network_project_id" {{
  description = "Google Cloud project ID hosting the VPC (Host project for Shared VPC, or same as project_id)."
  type        = string
  default     = "{network_project}"
}}

variable "region" {{
  description = "Google Cloud region for ODB@GCP deployment."
  type        = string
  default     = "{reg}"
}}

variable "gcp_oracle_zone" {{
  description = "Oracle Database@Google Cloud zone within the region."
  type        = string
  default     = "{ozone}"
}}

variable "environment_prefix" {{
  description = "Resource naming prefix."
  type        = string
  default     = "{env_pfx}"
}}

variable "vpc_name" {{
  description = "Existing customer VPC name to link with the ODB Network."
  type        = string
  default     = "{vpc_name.strip()}"
}}

variable "client_subnet_cidr" {{
  description = "CIDR range for ODB CLIENT_SUBNET (minimum /28)."
  type        = string
  default     = "{client_subnet_cidr.strip()}"
}}

variable "backup_subnet_cidr" {{
  description = "CIDR range for ODB BACKUP_SUBNET (minimum /28, required for Exadata/Exascale)."
  type        = string
  default     = "{backup_subnet_cidr.strip()}"
}}

variable "db_admin_password" {{
  description = "Administrator password injected at runtime via TF_VAR_db_admin_password (never stored in tfvars)."
  type        = string
  sensitive   = true
  default     = null
}}

variable "ssh_public_keys" {{
  description = "List of SSH public keys for Exadata/Exascale/BaseDB cluster nodes."
  type        = list(string)
  default     = []
}}
"""

    backup_subnet_hcl = ""
    if needs_backup:
        backup_subnet_hcl = f"""
resource "google_oracle_database_odb_subnet" "backup_subnet" {{
  project             = var.project_id
  location            = var.region
  odbnetwork          = google_oracle_database_odb_network.odb_net.odb_network_id
  odb_subnet_id       = "${{var.environment_prefix}}-backup-subnet"
  cidr_range          = var.backup_subnet_cidr
  purpose             = "BACKUP_SUBNET"
  deletion_protection = {del_prot_str}

  labels = {{
    environment = var.environment_prefix
    managed_by  = "terraform"
  }}
}}
"""

    networking_tf = f"""data "google_compute_network" "customer_vpc" {{
  name    = var.vpc_name
  project = var.network_project_id
}}

resource "google_oracle_database_odb_network" "odb_net" {{
  project             = var.project_id
  location            = var.region
  odb_network_id      = "${{var.environment_prefix}}-odb-net"
  network             = data.google_compute_network.customer_vpc.id
  gcp_oracle_zone     = var.gcp_oracle_zone
  deletion_protection = {del_prot_str}

  labels = {{
    environment = var.environment_prefix
    managed_by  = "terraform"
  }}
}}

resource "google_oracle_database_odb_subnet" "client_subnet" {{
  project             = var.project_id
  location            = var.region
  odbnetwork          = google_oracle_database_odb_network.odb_net.odb_network_id
  odb_subnet_id       = "${{var.environment_prefix}}-client-subnet"
  cidr_range          = var.client_subnet_cidr
  purpose             = "CLIENT_SUBNET"
  deletion_protection = {del_prot_str}

  labels = {{
    environment = var.environment_prefix
    managed_by  = "terraform"
  }}
}}
{backup_subnet_hcl}"""

    if workload == "adb":
        workload_tf = f"""resource "google_oracle_database_autonomous_database" "adb" {{
  project                = var.project_id
  location               = var.region
  autonomous_database_id = "${{var.environment_prefix}}-adb"
  database               = "{db_name.strip()}"
  admin_password         = var.db_admin_password
  odb_network            = google_oracle_database_odb_network.odb_net.name
  odb_subnet             = google_oracle_database_odb_subnet.client_subnet.name
  deletion_protection    = {del_prot_str}

  properties {{
    compute_count            = {int(compute_count)}
    data_storage_size_tb     = {int(storage_size_tb)}
    db_version               = "{db_version.strip()}"
    db_workload              = "OLTP"
    license_type             = "{license_model.strip()}"
    is_auto_scaling_enabled  = true
    mtls_connection_required = true
  }}

  labels = {{
    environment = var.environment_prefix
    workload    = "autonomous-db"
    managed_by  = "terraform"
  }}
}}
"""
        outputs_tf = """output "odb_network_id" {
  value = google_oracle_database_odb_network.odb_net.id
}

output "autonomous_database_id" {
  value = google_oracle_database_autonomous_database.adb.id
}
"""
    elif workload == "exadata_dedicated":
        workload_tf = f"""resource "google_oracle_database_cloud_exadata_infrastructure" "exa_infra" {{
  project                         = var.project_id
  location                        = var.region
  gcp_oracle_zone                 = var.gcp_oracle_zone
  cloud_exadata_infrastructure_id = "${{var.environment_prefix}}-exa-infra"
  display_name                    = "${{var.environment_prefix}}-exa-infra"
  deletion_protection             = {del_prot_str}

  properties {{
    shape         = "{exadata_shape.strip()}"
    compute_count = 2
    storage_count = 3
  }}
}}

resource "google_oracle_database_cloud_vm_cluster" "vm_cluster" {{
  project                = var.project_id
  location               = var.region
  cloud_vm_cluster_id    = "${{var.environment_prefix}}-vm-cluster"
  display_name           = "${{var.environment_prefix}}-vm-cluster"
  exadata_infrastructure = google_oracle_database_cloud_exadata_infrastructure.exa_infra.name
  odb_network            = google_oracle_database_odb_network.odb_net.name
  odb_subnet             = google_oracle_database_odb_subnet.client_subnet.name
  backup_odb_subnet      = google_oracle_database_odb_subnet.backup_subnet.name
  deletion_protection    = {del_prot_str}

  properties {{
    gi_version              = "23.0.0.0"
    cpu_core_count          = {int(compute_count)}
    data_storage_size_tb    = {max(2, int(storage_size_tb))}
    db_node_storage_size_gb = 120
    memory_size_gb          = 60
    license_type            = "{license_model.strip()}"
    ssh_public_keys         = var.ssh_public_keys
    hostname_prefix         = "exa"
    time_zone {{
      id = "UTC"
    }}
  }}
}}
"""
        outputs_tf = """output "odb_network_id" {
  value = google_oracle_database_odb_network.odb_net.id
}

output "exadata_infrastructure_id" {
  value = google_oracle_database_cloud_exadata_infrastructure.exa_infra.id
}

output "cloud_vm_cluster_id" {
  value = google_oracle_database_cloud_vm_cluster.vm_cluster.id
}
"""
    elif workload == "exascale":
        workload_tf = f"""resource "google_oracle_database_exascale_db_storage_vault" "vault" {{
  project                      = var.project_id
  location                     = var.region
  gcp_oracle_zone              = var.gcp_oracle_zone
  exascale_db_storage_vault_id = "${{var.environment_prefix}}-exascale-vault"
  display_name                 = "${{var.environment_prefix}}-exascale-vault"
  deletion_protection          = {del_prot_str}

  properties {{
    additional_flash_cache_percent = 100
    exascale_db_storage_details {{
      total_size_gbs = {max(300, int(storage_size_tb) * 1024)}
    }}
  }}
}}

resource "google_oracle_database_exadb_vm_cluster" "exadb_cluster" {{
  project             = var.project_id
  location            = var.region
  gcp_oracle_zone     = var.gcp_oracle_zone
  exadb_vm_cluster_id = "${{var.environment_prefix}}-exadb-cluster"
  display_name        = "${{var.environment_prefix}}-exadb-cluster"
  odb_network         = google_oracle_database_odb_network.odb_net.name
  odb_subnet          = google_oracle_database_odb_subnet.client_subnet.name
  backup_odb_subnet   = google_oracle_database_odb_subnet.backup_subnet.name
  deletion_protection = {del_prot_str}

  properties {{
    grid_image_id                  = "gi-23ai"
    shape_attribute                = "SMART_STORAGE"
    node_count                     = 2
    enabled_ecpu_count_per_node    = {max(8, int(compute_count))}
    additional_ecpu_count_per_node = 0
    exascale_db_storage_vault      = google_oracle_database_exascale_db_storage_vault.vault.name
    license_model                  = "{license_model.strip()}"
    ssh_public_keys                = var.ssh_public_keys
    hostname_prefix                = "exascale"
    vm_file_system_storage {{
      size_in_gbs_per_node = 300
    }}
  }}
}}
"""
        outputs_tf = """output "odb_network_id" {
  value = google_oracle_database_odb_network.odb_net.id
}

output "exascale_vault_id" {
  value = google_oracle_database_exascale_db_storage_vault.vault.id
}

output "exadb_vm_cluster_id" {
  value = google_oracle_database_exadb_vm_cluster.exadb_cluster.id
}
"""
    else:  # basedb
        workload_tf = f"""resource "google_oracle_database_db_system" "basedb" {{
  project             = var.project_id
  location            = var.region
  gcp_oracle_zone     = var.gcp_oracle_zone
  db_system_id        = "${{var.environment_prefix}}-basedb"
  display_name        = "${{var.environment_prefix}}-basedb"
  odb_network         = google_oracle_database_odb_network.odb_net.name
  odb_subnet          = google_oracle_database_odb_subnet.client_subnet.name
  deletion_protection = {del_prot_str}

  properties {{
    shape                        = "VM.Standard.E4.Flex"
    compute_count                = {max(2, int(compute_count))}
    compute_model                = "ECPU"
    initial_data_storage_size_gb = {max(256, int(storage_size_tb) * 1024)}
    database_edition             = "ENTERPRISE_EDITION"
    license_model                = "{license_model.strip()}"
    node_count                   = 1
    storage_management           = "ASM"
    ssh_public_keys              = var.ssh_public_keys
    hostname_prefix              = "basedb"

    db_home {{
      db_version = "{db_version.strip()}"
      database {{
        admin_password = var.db_admin_password
        db_name        = "{db_name.strip()}"
        character_set  = "AL32UTF8"
        ncharacter_set = "AL16UTF16"
      }}
    }}
  }}
}}
"""
        outputs_tf = """output "odb_network_id" {
  value = google_oracle_database_odb_network.odb_net.id
}

output "db_system_id" {
  value = google_oracle_database_db_system.basedb.id
}
"""

    tfvars_content = f"""# Generated by ODB@GCP AI Architect Agent (Golden Baseline)
# NOTE: Never place db_admin_password here. Export TF_VAR_db_admin_password at runtime.
project_id         = "{proj}"
network_project_id = "{network_project}"
region             = "{reg}"
gcp_oracle_zone    = "{ozone}"
environment_prefix = "{env_pfx}"
vpc_name           = "{vpc_name.strip()}"
client_subnet_cidr = "{client_subnet_cidr.strip()}"
backup_subnet_cidr = "{backup_subnet_cidr.strip()}"
"""

    files = {
        "versions.tf": versions_tf,
        "variables.tf": variables_tf,
        "networking.tf": networking_tf,
        "workload.tf": workload_tf,
        "outputs.tf": outputs_tf,
        "terraform.tfvars": tfvars_content,
    }

    result: dict[str, Any] = {
        "valid": True,
        "workload_type": workload,
        "deployment_layer": "full_stack",
        "team_role": "full_stack",
        "guardrail_checks": {
            "cidr_slash28_and_overlap": "PASSED",
            "deletion_protection_enabled": enable_deletion_protection,
            "sensitive_password_excluded_from_tfvars": "PASSED",
            "provider_constraint": "hashicorp/google >= 7.0.0",
        },
        "files": files,
    }
    return json.dumps(result, indent=2)

