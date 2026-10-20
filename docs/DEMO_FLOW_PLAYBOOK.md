# Oracle@Google Onboarding Agent — Live Demo Flow Playbook (Antigravity IDE Edition)

**Target Audience:** Google Cloud & Oracle Internal Field Teams (CEs, Cloud Architects, FSRs) and Enterprise Customers  
**Deployment Environment:** Google Antigravity IDE + `oracle-google-onboarding-agent` MCP Server (`stdio`)  
**Repository:** [`sharmagauravji-goog/oracle-at-google-onboarding-agent`](https://github.com/sharmagauravji-goog/oracle-at-google-onboarding-agent)

---

## Executive Summary & Demo Value Proposition

Enterprise customers adopting **Oracle Database@Google Cloud (`oracledatabase.googleapis.com`)** face a multi-phase journey spanning Google Cloud IAM & APIs, Google Cloud Marketplace procurement (Private Offer vs. Pay-As-You-Go), OCI Tenancy Linking, My Oracle Support (MOS) CSI registration, ODB Network & NCC topology design, and `hashicorp/google >= 7.0.0` Terraform provisioning.

When integrated into **Google Antigravity IDE** via the built-in **Model Context Protocol (`stdio` MCP) Server**, the **Oracle@Google Onboarding Agent** acts as a domain-grounded co-pilot that:
1. **Eliminates Hallucinations:** Enforces exact `oracledatabase.googleapis.com` API rules, `/28` minimum subnet math, exact Cloud KMS service agent identities (`service-<PROJECT_NUMBER>@gcp-sa-oracledatabase.iam.gserviceaccount.com`), and verified `hashicorp/google` schemas (`top_level` vs. nested `properties {}`).
2. **Inspects Live Readiness:** Audits the customer's live GCP project for enabled APIs, missing ODB IAM permissions (`roles/oracledatabase.admin`, `roles/oracledatabase.networkAdmin`), and Marketplace/OCI link status.
3. **Generates Verified Visuals & Code in `<50ms`:** Produces syntax-verified **Mermaid & ASCII architecture diagrams** and **Golden Day-1 Terraform bundles** inside the customer's workspace.
4. **Enforces Human-in-the-Loop Execution Safety:** The MCP server intentionally blocks autonomous `terraform apply` / `terraform destroy` calls, ensuring infrastructure mutations only happen via Antigravity's supervised terminal confirmation or CI/CD.

---

## Pre-Demo Setup Checklist in Antigravity IDE (2 Minutes)

1. **Verify MCP Server Registration in Antigravity:**
   - Open the Antigravity Agent pane → click **Additional Options (`...`)** → **MCP Servers**.
   - Confirm **`oracle-google-onboarding-agent`** shows a **green connected dot** with all **10 MCP tools** loaded:
     - `get_odb_onboarding_guide`
     - `evaluate_onboarding_readiness`
     - `verify_live_onboarding_and_iam_readiness`
     - `generate_odb_diagram`
     - `generate_golden_terraform`
     - `validate_odb_network_cidrs`
     - `validate_odb_terraform_hcl`
     - `inspect_day2_workspace`
     - `analyze_day2_terraform_diff`
     - `list_odb_provider_resources`
2. **Optional Demo Simulation Setup (To Trigger Step 3 "Missing ODB Permission" Live):**
   - If using a live demo project (e.g., `my-odb-demo-proj`), ensure your demo user temporarily lacks `roles/oracledatabase.admin` (or pass a test principal email to `verify_live_onboarding_and_iam_readiness`) so the agent catches the missing IAM role live on screen and gives you the exact `gcloud` fix command.

---

## Demo Flow 1 (Flagship End-to-End Flow — 12 Mins): From Zero to Deployed ODB Network & Autonomous Database in Antigravity

> **Storyline:** An enterprise Cloud Architect opens Antigravity IDE to onboard their organization onto **Oracle Database@Google Cloud** and deploy an **Oracle Autonomous Database 23ai (`adb`)** with **Network Connectivity Center (NCC)** hybrid connectivity.

| Step | Customer Action in Antigravity | MCP Tool(s) Triggered | Key Demo Takeaway |
| :--- | :--- | :--- | :--- |
| **Step 1** | Asks what steps are required to deploy ODB@GCP | `get_odb_onboarding_guide` + `generate_odb_diagram` | Complete 6-phase lifecycle + Mermaid flowchart |
| **Step 2** | Asks if a specific step (Marketplace Private Offer & OCI Link) is done | `evaluate_onboarding_readiness` + `verify_live_onboarding_and_iam_readiness` | Explains Private Offer vs. PAYG entitlement & verifies status |
| **Step 3** | Asks if anything is missing before deploying Oracle ADB | `verify_live_onboarding_and_iam_readiness` | Detects **missing `roles/oracledatabase.admin` permission** & gives exact `gcloud` fix |
| **Step 4** | Fixes IAM permission, then asks about **NCC integration & architecture diagram** | `get_odb_onboarding_guide` + `generate_odb_diagram` | Renders Hub-and-Spoke NCC + Cloud Interconnect + Private DNS diagram |
| **Step 5** | Asks to create Terraform to deploy the ODB Network & ADB | `generate_golden_terraform` | Writes schema-verified HCL into `./output/odb-adb-demo` in `<50ms` |
| **Step 6** | Asks Antigravity to execute the Terraform deployment | Antigravity `run_command` (Human-in-the-loop) | Runs `terraform init`, `plan`, and supervised `apply` |

---

### Step 1: Customer Asks for the Complete End-to-End Deployment Process

**Presenter Talk Track:**  
*"Let's start in the shoes of an enterprise Cloud Architect who just opened Antigravity IDE. They know they want to deploy Oracle Database@Google Cloud, but they need to understand the complete end-to-end onboarding process across both Google Cloud and Oracle."*

**Prompt to Type in Antigravity Chat:**
```text
What are the complete end-to-end steps required to onboard and deploy Oracle Database@Google Cloud? Also show me the end-to-end onboarding flow diagram.
```

**What Antigravity Does Behind the Scenes:**
1. Calls MCP tool `get_odb_onboarding_guide(topic="all")`.
2. Calls MCP tool `generate_odb_diagram(diagram_type="end_to_end_onboarding")`.

**What the Agent Returns on Screen:**
- **Visual Flowchart:** Renders the syntax-verified Mermaid flowchart and ASCII diagram showing all 6 phases.
- **Structured 6-Phase Walkthrough:**
  1. **Phase 1 — Prerequisites & IAM:** Enabling `oracledatabase.googleapis.com`, `compute.googleapis.com`, `servicenetworking.googleapis.com`, `cloudkms.googleapis.com`, `monitoring.googleapis.com`, `logging.googleapis.com`, and granting `roles/billing.admin` + `roles/consumerprocurement.orderAdmin` (for procurement) and `roles/oracledatabase.admin` (for deployment).
  2. **Phase 2 — Google Cloud Marketplace Procurement:** Choosing between a negotiated **Private Offer** (100% MACC drawdown, BYOL or License Included) or **Pay-As-You-Go (PAYG)**.
  3. **Phase 3 — OCI Account Linking:** Creating a new partner-linked OCI tenancy or linking an existing OCI tenancy in the Google Cloud Console (`Oracle Database@Google Cloud -> Account setup`) to bind the Marketplace `entitlement_id`.
  4. **Phase 4 — My Oracle Support (MOS) & CSI Registration:** Registering the Customer Support Identifier (CSI) at `support.oracle.com`.
  5. **Phase 5 — ODB Network & Subnet Topology:** Provisioning `google_oracle_database_odb_network` and `google_oracle_database_odb_subnet` (`CLIENT_SUBNET` / `BACKUP_SUBNET`, minimum `/28` CIDR).
  6. **Phase 6 — Day-1 Terraform Provisioning & Observability:** Deploying Autonomous DB / Exadata via `hashicorp/google >= 7.0.0`.

---

### Step 2: Customer Asks if a Specific Step (Marketplace Private Offer) Is Done

**Presenter Talk Track:**  
*"Next, the customer knows their procurement team was working on a Google Cloud Marketplace Private Offer, and they want to check how Private Offer activation works and whether that step is complete for their project."*

**Prompt to Type in Antigravity Chat:**
```text
Can you check the Marketplace Private Offer step for project ad-auth-project? How do we verify if our Private Offer and OCI Account Linking are completed, and what is our onboarding readiness score if Private Offer is done but OCI Account Linking is still pending?
```

**What Antigravity Does Behind the Scenes:**
1. Calls MCP tool `get_odb_onboarding_guide(topic="marketplace_procurement")`.
2. Calls MCP tool `evaluate_onboarding_readiness(project_id="ad-auth-project", procurement_model="private_offer", workload_type="adb")`.
3. Calls MCP tool `verify_live_onboarding_and_iam_readiness(project_id="ad-auth-project", workload_type="adb")`.

**What the Agent Returns on Screen:**
- Explains that accepting the **Private Offer** in **Google Cloud Console → Marketplace → Orders** generates an active `entitlement_id` billed 100% through the Google Cloud invoice (with zero separate OCI invoice).
- Provides the direct Console verification links for project `ad-auth-project`:
  - Marketplace Orders: `https://console.cloud.google.com/marketplace/orders?project=ad-auth-project`
  - ODB Account Setup: `https://console.cloud.google.com/oracledatabase/locations?project=ad-auth-project`
- Shows the **Onboarding Readiness Checklist & Score** highlighting what is completed vs. what must be completed before database provisioning.

---

### Step 3: Customer Asks if Anything Is Missing Before Deploying Oracle Autonomous Database (ADB)

**Presenter Talk Track:**  
*"Now the customer says: 'Assume our Private Offer and account linking are set—is there anything missing in our GCP project before I deploy Oracle Autonomous Database?' Watch how the agent inspects the live GCP project and catches a missing ODB IAM permission."*

**Prompt to Type in Antigravity Chat:**
```text
Before we deploy Oracle Autonomous Database (adb) in project ad-auth-project, can you check our live project readiness to see if any required APIs or ODB IAM permissions are missing for principal devops-lead@example.com?
```
*(Tip: You can omit `for principal devops-lead@example.com` to inspect your own active `gcloud` identity, or specify any user/service-account email that lacks `roles/oracledatabase.admin` to guarantee the missing-permission alert triggers during the demo!)*

**What Antigravity Does Behind the Scenes:**
- Calls MCP tool `verify_live_onboarding_and_iam_readiness(project_id="ad-auth-project", workload_type="adb", principal_email="devops-lead@example.com")`.

**What the Agent Returns on Screen (The "Aha!" Moment):**
- **Blocker Detected — Missing ODB IAM Roles & APIs:**
  - **Missing IAM Roles:**
    - `roles/oracledatabase.admin` (or least-privilege `roles/oracledatabase.networkAdmin` + `roles/oracledatabase.autonomousDatabaseAdmin`)
    - `roles/compute.networkAdmin`
  - **Missing/Checked GCP APIs:** Checks `oracledatabase.googleapis.com` and `servicenetworking.googleapis.com`.
- **Exact Copy-Pasteable Remediation Commands:**
  ```bash
  # 1. Enable required Oracle Database@Google Cloud APIs
  gcloud services enable oracledatabase.googleapis.com compute.googleapis.com servicenetworking.googleapis.com --project=ad-auth-project

  # 2. Grant missing ODB & Network IAM permissions
  gcloud projects add-iam-policy-binding ad-auth-project \
    --member='user:devops-lead@example.com' \
    --role='roles/oracledatabase.admin'

  gcloud projects add-iam-policy-binding ad-auth-project \
    --member='user:devops-lead@example.com' \
    --role='roles/compute.networkAdmin'
  ```

---

### Step 4: Once Fixed, Customer Asks About NCC Integration & Architecture Diagram

**Presenter Talk Track:**  
*"Once the IAM permission is granted right from Antigravity's terminal, the customer asks an advanced enterprise networking question: How do we connect our on-premises data center and multiple regional application spokes to the ODB Network using Network Connectivity Center (NCC)? And can you generate the architecture diagram?"*

**Prompt to Type in Antigravity Chat:**
```text
We fixed the IAM permissions. Now we want to connect our on-premises network and multiple application VPCs to the ODB Network using Network Connectivity Center (NCC) in us-east4 (zone us-east4-b-r1). How does NCC integration work with ODB Network, and can you generate the architecture diagram and save it to ./output/diagrams?
```

**What Antigravity Does Behind the Scenes:**
1. Calls MCP tool `get_odb_onboarding_guide(topic="odb_networks_and_topologies")`.
2. Calls MCP tool `generate_odb_diagram(diagram_type="networking_hub_and_spoke_ha_dr", project_id="ad-auth-project", region="us-east4", gcp_oracle_zone="us-east4-b-r1", save_to_workspace=True, output_dir="./output/diagrams")`.

**What the Agent Returns on Screen:**
- **Anti-Hallucination Grounded Explanation of NCC + ODB Network:**
  - Explains **Topology 3 (Hub-and-Spoke with Network Connectivity Center)**:
    - On-premises connects via **Cloud Interconnect (Dedicated/Partner)** or **HA VPN** into a central **NCC Transit Hub VPC**.
    - Workload VPC spokes and the ODB-attached VPC connect via NCC spokes, enabling transitive routing without manual IPSec VPNs between GCP and OCI (`google_oracle_database_odb_network` uses Google-managed colocated partner interconnect in `us-east4-b-r1`).
    - Explains **Cloud DNS Private Zones (`*.oraclevcn.com`)** and Inbound/Outbound DNS Forwarding so on-prem and spoke apps resolve Oracle SCAN / mTLS hostnames.
- **Visual Diagram Rendered & Saved:**
  - Displays the full **Mermaid (`mermaid`)** and **ASCII** Hub-and-Spoke NCC architecture diagram in chat and writes `./output/diagrams/networking_hub_and_spoke_ha_dr.md` into the workspace.

---

### Step 5: Customer Asks to Create Terraform to Deploy the ODB Network & Autonomous Database

**Presenter Talk Track:**  
*"Now that the architecture is approved, the customer asks Antigravity to generate the production Terraform for the ODB Network (`google_oracle_database_odb_network`), the Client Subnet (`google_oracle_database_odb_subnet`), and the Autonomous Database (`google_oracle_database_autonomous_database`). Notice how fast this runs (`<50ms`) and how it enforces our 5-layer anti-hallucination guardrails."*

**Prompt to Type in Antigravity Chat:**
```text
Generate a production Golden Terraform bundle in ./output/odb-adb-demo for project ad-auth-project in region us-east4 (zone us-east4-b-r1) to deploy our ODB Network, Client Subnet (10.20.1.0/24), and an Oracle Autonomous Database 23ai (adb) named ODBDEMO1 with 4 ECPUs and 1 TB storage.
```

**What Antigravity Does Behind the Scenes:**
- Calls MCP tool `generate_golden_terraform`:
  ```json
  {
    "project_id": "ad-auth-project",
    "workload_type": "adb",
    "region": "us-east4",
    "gcp_oracle_zone": "us-east4-b-r1",
    "vpc_name": "odb-vpc",
    "vpc_cidr": "10.10.0.0/16",
    "client_subnet_cidr": "10.20.1.0/24",
    "db_name": "ODBDEMO1",
    "compute_count": 4,
    "storage_size_tb": 1,
    "bundle_name": "odb-adb-demo",
    "base_output_dir": "./output"
  }
  ```

**What the Agent Returns on Screen:**
- Writes 5 verified Terraform files directly into `./output/odb-adb-demo/`:
  - `versions.tf` (`hashicorp/google >= 7.0.0`)
  - `variables.tf` (`db_admin_password` marked `sensitive = true`, never hardcoded in HCL)
  - `networking.tf` (`google_compute_network`, `google_oracle_database_odb_network`, and `google_oracle_database_odb_subnet` with `purpose = "CLIENT_SUBNET"` and `/24` CIDR)
  - `workload.tf` (`google_oracle_database_autonomous_database` with exact `properties {}` block nesting and `deletion_protection = true`)
  - `outputs.tf`
- Displays the **Guardrail Verification Summary** confirming:
  - Zero `oci_*` provider hallucinations
  - Valid `/28`+ CIDR math (`10.20.1.0/24` vs `10.10.0.0/16` — zero overlap)
  - Exact `EXACT_ODB_RESOURCE_SCHEMAS` verification passed.

---

### Step 6: Customer Asks to Execute the Terraform Deployment

**Presenter Talk Track:**  
*"Finally, the customer asks Antigravity to execute the Terraform. Here is a critical enterprise safety feature to highlight: our MCP server intentionally refuses to expose `terraform apply` or `terraform destroy` as autonomous MCP tools. Instead, Antigravity uses its supervised terminal tool (`run_command`) to run `terraform init` and `terraform plan`, and asks the human engineer for explicit approval before executing `terraform apply`."*

**Prompt to Type in Antigravity Chat:**
```text
Now initialize and validate the Terraform bundle in ./output/odb-adb-demo, and run terraform plan so we can review and execute the deployment.
```

**What Antigravity Does Behind the Scenes:**
1. Uses Antigravity's terminal execution tool (`run_command`) inside `./output/odb-adb-demo`:
   ```bash
   export TF_VAR_db_admin_password="DemoStrongPassword#2026!"
   terraform -chdir=./output/odb-adb-demo init
   terraform -chdir=./output/odb-adb-demo validate
   terraform -chdir=./output/odb-adb-demo plan -out=tfplan
   ```
2. Shows the exact Terraform execution plan (`+ create` for `google_compute_network.odb_vpc`, `google_oracle_database_odb_network.primary`, `google_oracle_database_odb_subnet.client_subnet`, and `google_oracle_database_autonomous_database.adb`).
3. Prompts the user to approve:
   ```bash
   terraform -chdir=./output/odb-adb-demo apply tfplan
   ```

---

## Suggested Additional Demo Flows for Internal Teams & Customers

Below are **3 additional modular flows** (5–8 minutes each) that you can run standalone or append to Flow 1 depending on the audience (Security/Compliance teams, Platform Engineering teams, or Day-2 DBAs).

---

### Demo Flow 2: Regulated Enterprise Exadata Dedicated on Shared VPC + Cloud KMS (CMEK) + RMAN Backups (8 Mins)

**Best For:** Financial Services, Healthcare, and Public Sector customers with strict Shared VPC and Customer-Managed Encryption Key (CMEK) mandates.

1. **Step 1 — Shared VPC & Subnet CIDR Validation:**
   - **Customer Prompt:** *"We use an Enterprise Shared VPC in host project `corp-network-host-prod` (`10.10.0.0/16`) and want to deploy Exadata Dedicated (`Exadata.X11M`) in service project `odb-exadata-service-prod`. Can you validate if `10.20.1.0/24` (Client Subnet) and `10.20.2.0/24` (Backup Subnet) are compliant and non-overlapping?"*
   - **MCP Tool Triggered:** `validate_odb_network_cidrs`
   - **Result:** Confirms both subnets meet the `/28` minimum (256 IPs each) and have zero overlap with `10.10.0.0/16` or each other.
2. **Step 2 — Cloud KMS CMEK Service Agent & Encryption Diagram:**
   - **Customer Prompt:** *"We require Google Cloud KMS (CMEK) for Oracle TDE encryption at rest. Which exact GCP Service Agent needs `roles/cloudkms.cryptoKeyEncrypterDecrypter`, and can you show me the CMEK encryption flow diagram?"*
   - **MCP Tools Triggered:** `get_odb_onboarding_guide(topic="encryption_and_cmek")` + `generate_odb_diagram(diagram_type="encryption_cmek")`
   - **Result:** Highlights the anti-hallucination guardrail—gives the exact service agent `service-<PROJECT_NUMBER>@gcp-sa-oracledatabase.iam.gserviceaccount.com` (blocking common LLM hallucinations like `gcp-sa-oracle`) and renders the CMEK + TDE Master Key hierarchy diagram.
3. **Step 3 — Generate Shared VPC Exadata Dedicated Terraform:**
   - **Customer Prompt:** *"Generate the Golden Terraform bundle for `exadata_dedicated` in service project `odb-exadata-service-prod` attached to Shared VPC host project `corp-network-host-prod` in `./output/odb-exadata-shared-vpc`."*
   - **MCP Tool Triggered:** `generate_golden_terraform(project_id="odb-exadata-service-prod", shared_vpc_host_project_id="corp-network-host-prod", workload_type="exadata_dedicated", bundle_name="odb-exadata-shared-vpc")`
   - **Result:** Generates `google_oracle_database_cloud_exadata_infrastructure`, `google_oracle_database_cloud_vm_cluster`, `CLIENT_SUBNET`, and `BACKUP_SUBNET` wired to `projects/corp-network-host-prod/global/networks/odb-vpc`.

---

### Demo Flow 3: "Catching Bad AI Code" — 5-Layer Anti-Hallucination & Schema Validator (5 Mins)

**Best For:** Internal Google/Oracle Engineering teams and DevSecOps leads who ask *"Why can't we just use a generic ungrounded LLM to write ODB Terraform?"*

1. **Step 1 — Feed Hallucinated Terraform to the Agent:**
   - **Presenter Talk Track:** *"Generic LLMs frequently confuse OCI provider resources with Google Cloud provider resources, hallucinate resource names (`odbnetwork` without an underscore), use `/29` subnets that fail at deployment time, put nested attributes at the top level, or hardcode database passwords. Let's paste a broken snippet into Antigravity and ask the MCP server to validate it."*
   - **Customer Prompt:**
     ```text
     Can you validate this Terraform snippet using validate_odb_terraform_hcl and tell me everything wrong with it?

     resource "oci_database_autonomous_database" "bad_db" {}
     resource "google_oracle_database_odbnetwork" "bad_net" {
       project = "my-odb-project-01"
     }
     resource "google_oracle_database_odb_subnet" "bad_sub" {
       cidr_range = "10.20.1.0/29"
     }
     resource "google_oracle_database_autonomous_database" "bad_adb" {
       project = "my-odb-project-01"
       compute_count = 4
       admin_password = "HardcodedSecretPassword123!"
     }
     ```
2. **Step 2 — Instant Deterministic Catch (`<50ms`):**
   - **MCP Tool Triggered:** `validate_odb_terraform_hcl`
   - **Result:** Deterministically flags all 5 errors in a single pass:
     1. **Wrong Provider (`oci_*`):** Must use `hashicorp/google` (`google_oracle_database_*`), not `oci_*`.
     2. **Hallucinated Resource Type:** `google_oracle_database_odbnetwork` -> must be `google_oracle_database_odb_network`.
     3. **Invalid Attribute & CIDR Prefix:** `cidr_range = "10.20.1.0/29"` -> attribute is `cidr` (not `cidr_range`), and `/29` violates the mandatory `/28` minimum prefix length.
     4. **Misplaced Nested Attribute:** `compute_count = 4` must be nested inside `properties { compute_count = 4 }`, not at the top level.
     5. **Hardcoded Secret Violation:** `admin_password` must use a sensitive input variable (`var.db_admin_password`) injected via `TF_VAR_db_admin_password` or Secret Manager.

---

### Demo Flow 4: Day-2 Production Operations & Blocking Destructive `ForceNew` Replacements (5 Mins)

**Best For:** Database Reliability Engineers (DBREs) and Production Operations teams worried about Terraform accidentally destroying a live production database during Day-2 scaling.

1. **Step 1 — Audit Existing Production Workspace:**
   - **Customer Prompt:** *"Inspect our deployed Terraform workspace in `./output/odb-adb-demo` using `inspect_day2_workspace` and summarize our `deletion_protection` posture and which attributes can be scaled in-place vs. which trigger destructive `ForceNew` recreation."*
   - **MCP Tool Triggered:** `inspect_day2_workspace(workspace_dir="./output/odb-adb-demo")`
   - **Result:** Inventories all resources in `./output/odb-adb-demo`, confirms `deletion_protection = true`, lists safe in-place mutable attributes (`compute_count`, `data_storage_size_tb`), and warns against immutable `ForceNew` fields (`autonomous_database_id`, `odb_network`, `odb_subnet`, `cidr`, `gcp_oracle_zone`).
2. **Step 2 — Catch an Accidental `ForceNew` Outage Before `terraform plan`:**
   - **Customer Prompt:** *"A developer proposed a Day-2 PR that scales `compute_count` from `4` to `8` ECPUs, disables `deletion_protection = false`, and changes `odb_subnet` to a new subnet. Run `analyze_day2_terraform_diff` to check if this change is safe."*
   - **MCP Tool Triggered:** `analyze_day2_terraform_diff`
   - **Result:**
     - **Approves** `compute_count: 4 -> 8` as a safe online Day-2 scaling operation.
     - **BLOCKS** the `odb_subnet` change (`CRITICAL: Modifying immutable ForceNew attribute 'odb_subnet' will force Terraform to DESTROY and RECREATE the live database!`) and flags `deletion_protection = false` as a high-severity production risk.
