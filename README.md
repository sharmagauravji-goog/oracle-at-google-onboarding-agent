# Oracle@Google Onboarding Agent (`oracle-at-google-onboarding-agent`)

[![Open in Cloud Shell](https://gstatic.com/cloudssh/images/open-btn.svg)](https://ssh.cloud.google.com/cloudshell/editor?cloudshell_git_repo=https://github.com/sharmagauravji-goog/oracle-at-google-onboarding-agent.git&cloudshell_git_branch=main&cloudshell_tutorial=cloudshell_tutorial.md)

An LLM-powered **Oracle@Google Onboarding Agent** built on the official [`google-genai`](https://pypi.org/project/google-genai/) SDK that guides enterprise customers through the **entire Oracle Database@Google Cloud (`oracledatabase.googleapis.com`) onboarding journey**, answers deep architecture questions with anti-hallucination guardrails, generates **Mermaid & ASCII architecture diagrams**, produces **production-ready Day-1 & Day-2 Terraform (`hashicorp/google`)**, and integrates directly into customer IDEs (**VS Code, Cursor, Claude Desktop, Gemini CLI, and Antigravity IDE**) via a built-in **Model Context Protocol (`stdio` MCP) Server**.

---

## Key Capabilities of the Oracle@Google Onboarding Agent

### 1. End-to-End Onboarding Lifecycle Guidance (Anti-Hallucination Grounded)
- **Prerequisites & IAM (`prerequisites`)**: Google Cloud Billing Account, Organization Policies (`constraints/compute.vmExternalIpAccess`, Shared VPC constraints), API enablement (`oracledatabase.googleapis.com`, `compute.googleapis.com`, `servicenetworking.googleapis.com`, `cloudkms.googleapis.com`, `monitoring.googleapis.com`, `logging.googleapis.com`), and exact IAM roles (`roles/oracledatabase.admin`, `roles/compute.networkAdmin`, `roles/billing.admin`).
- **Google Cloud Marketplace Procurement (`marketplace_procurement`)**: Side-by-side comparison and step-by-step workflow for **Private Offer** (custom negotiated pricing, CUD drawdown, multi-year terms) vs. **Pay-As-You-Go (PAYG)** (on-demand ECPU/storage billing).
- **OCI Account Linking & Tenancy Federation (`account_linking`)**: Provisioning a new OCI tenancy vs. linking an existing OCI tenancy in the Partner Portal, control-plane IAM federation (`google_oracle_database_cloud_account` / Console onboarding), and billing unification on the Google Cloud invoice.
- **My Oracle Support (MOS) & CSI Registration (`support_registration`)**: How the **Customer Support Identifier (CSI)** is generated after OCI linking, associating the CSI in `support.oracle.com`, and joint Google Cloud + Oracle collaborative support routing (`gcloud beta support` <-> MOS SR severity handoff).

### 2. Deep Architecture Domain Grounding
- **ODB Networks & Enterprise Topologies (`odb_networks_and_topologies`)**:
  - `google_oracle_database_odb_network` and `google_oracle_database_odb_subnet` (`CLIENT_SUBNET` and `BACKUP_SUBNET`, minimum `/28` CIDR, non-overlapping IP math).
  - **Topology 1**: Single-Project Standalone VPC + ODB Network.
  - **Topology 2**: Enterprise Shared VPC (Host Project owns VPC/ODB Network; Service Projects host GKE/Compute Engine apps).
  - **Topology 3**: Hybrid / Multi-Region Hub-and-Spoke with **Network Connectivity Center (NCC)**, **Cloud Interconnect (Dedicated/Partner)**, or **HA VPN**, plus **Cloud DNS Private Zones** (`*.oraclevcn.com`) and Inbound/Outbound DNS Forwarding.
- **Backup & Recovery (`backup_and_recovery`)**:
  - Autonomous Database automated backups (1–60 days retention, PITR, Autonomous Data Guard).
  - Exadata VM Cluster / Exascale / BaseDB RMAN backups over `BACKUP_SUBNET` (`purpose = "BACKUP"`) to OCI Object Storage (in the partner region) or Google Cloud Storage (GCS), plus Active Data Guard.
- **Encryption & CMEK (`encryption_and_cmek`)**:
  - Default Oracle TDE at rest and mTLS/Native Network Encryption in transit.
  - **Google Cloud KMS (CMEK)** integration using the exact service agent `service-<PROJECT_NUMBER>@gcp-sa-oracledatabase.iam.gserviceaccount.com` with `roles/cloudkms.cryptoKeyEncrypterDecrypter`.
  - OCI Vault / KMS customer-managed keys.
- **Monitoring & Observability (`monitoring_and_observability`)**:
  - Native **Google Cloud Monitoring** (`oracledatabase.googleapis.com/*` metrics for CPU, storage, IOPS, sessions), **Cloud Logging** (`cloudaudit.googleapis.com/activity`), and **Oracle Operations Insights / Database Management / AWR**.

### 3. Grounded Architecture & Onboarding Diagram Generator
Generates syntax-verified **Mermaid (`mermaid`)** and **ASCII** diagrams via CLI, Web Studio, Chat, or IDE MCP Server:
- `end_to_end_onboarding`: Complete 6-stage onboarding journey (Prerequisites -> Marketplace Private Offer/PAYG -> OCI Linking -> MOS/CSI Support -> ODB Network -> Terraform Provisioning).
- `odb_network_standalone`: Single-Project VPC connected to `google_oracle_database_odb_network` (`CLIENT_SUBNET` + `BACKUP_SUBNET`).
- `odb_network_shared_vpc`: Enterprise Shared VPC Host Project + App Service Projects connected to ODB Network.
- `odb_network_hub_spoke_ncc`: Hybrid On-Premises + Cloud Interconnect/HA VPN + NCC Transit Hub + Private DNS (`*.oraclevcn.com`) + ODB Network.
- `backup_and_dr_architecture`: RMAN over `BACKUP_SUBNET`, Autonomous Backups, PITR, and Cross-Zone/Region Data Guard.
- `cmek_encryption_flow`: Google Cloud KMS CMEK key hierarchy, `gcp-sa-oracledatabase` IAM binding, and Oracle TDE wallet encryption.
- `monitoring_and_observability_flow`: Dual-plane telemetry across Cloud Monitoring, Cloud Audit Logs, and Oracle AWR/Operations Insights.

### 4. Production Terraform Generation & 5-Layer Anti-Hallucination Guardrails
- **Golden Baseline Templates (`generate_golden_odb_terraform`)** for Autonomous Database 23ai (`adb`), Exadata Dedicated (`exadata_dedicated`), Exascale (`exascale`), and BaseDB (`basedb`).
- **Exact `hashicorp/google` Schema Verification (`EXACT_ODB_RESOURCE_SCHEMAS`)** catching misplaced top-level vs. nested `properties {}` attributes and hallucinated arguments (`cpu_core_count`, `admin_password` in HCL, `cidr_range` instead of `cidr`).
- **Pre-Flight Network CIDR (`/28` minimum) + Secret Leak Guard + Strict Workspace Path Containment**.
- **Compiler Auto-Repair Loop (`validate_terraform_hcl`)** and **Day-2 `ForceNew` Destructive Replacement Guard**.

### 5. IDE Model Context Protocol (`stdio` MCP) Server
Exposes the agent's tools over JSON-RPC 2.0 `stdio` (`odb-mcp-server` or `odb-onboarding-agent mcp-serve`) for **VS Code**, **Cursor**, **Claude Desktop**, **Gemini CLI**, and **Antigravity IDE** with 5 strict engineering guardrails:
1. **Never Exposes `terraform apply` or `terraform destroy`**: Only read-only onboarding guides, diagram generation, golden HCL generation, fast schema validation, and non-destructive Day-2 workspace inspection are exposed.
2. **Strict `stdio` Stream Isolation**: Redirects `sys.stdout` to `sys.stderr` during tool execution so accidental `print()` statements or library warnings never corrupt the JSON-RPC stream.
3. **Workspace Path Containment**: `generate_golden_terraform` and `inspect_day2_workspace` reject any path outside `ODB_WORKSPACE_ROOT` (preventing `../` traversal or `/etc`, `/tmp`, `~/.ssh` access).
4. **IDE Timeout Protection (`<50ms`)**: Uses fast validation mode (`fast_mode=True`) and returns concise summaries pointing to `./output/<bundle>` instead of streaming multi-kilobyte HCL payloads or blocking on slow `terraform init` downloads.
5. **Configurable Model IDs via Environment Variables**: Set `ODB_AGENT_MODEL` or `GEMINI_MODEL` to any current or future Gemini model ID so you are never locked into a retired preview model.

---

## Option 1: One-Click Google Cloud Shell (Recommended — Zero Setup)

Click the button above or open directly in Google Cloud Shell:

```bash
git clone https://github.com/sharmagauravji-goog/oracle-at-google-onboarding-agent.git
cd oracle-at-google-onboarding-agent
./scripts/cloudshell_quickstart.sh
```

Or run the CLI commands directly:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt && pip install -e .

# 1. Verify environment & Vertex AI ADC connection
odb-onboarding-agent doctor --ping-llm

# 2. Query the Onboarding & Architecture Knowledge Base
odb-onboarding-agent onboarding-guide --topic overview
odb-onboarding-agent onboarding-guide --topic marketplace_procurement
odb-onboarding-agent onboarding-guide --topic odb_networks_and_topologies

# 3. Generate Grounded Mermaid & ASCII Diagrams
odb-onboarding-agent diagram --type end_to_end_onboarding --save-to ./output/diagrams/onboarding.md
odb-onboarding-agent diagram --type odb_network_hub_spoke_ncc --save-to ./output/diagrams/hub-spoke.md

# 4. Generate a Verified Day-1 Golden Terraform Bundle
odb-onboarding-agent generate-golden --project-id "$GOOGLE_CLOUD_PROJECT" --workload adb

# 5. Audit Day-2 Workspace Safety
odb-onboarding-agent inspect-day2 --workspace-dir ./output

# 6. Start Interactive Multi-Turn Onboarding & Architecture Chat
odb-onboarding-agent chat
```

> **Backwards Compatibility Note**: Both `odb-onboarding-agent` and `odb-ai-agent` CLI entrypoints are installed and supported.

---

## Option 2: Connect to Antigravity, VS Code, Cursor, or Claude Desktop via MCP Server

### Integrating with Antigravity IDE (Step-by-Step)

Follow these steps to register the **Oracle@Google Onboarding Agent** MCP server in **Antigravity**:

#### Step 1: Install the Package & MCP Binary Locally
Clone the repository and install the package into a virtual environment so the `odb-mcp-server` executable is created:

```bash
git clone https://github.com/sharmagauravji-goog/oracle-at-google-onboarding-agent.git
cd oracle-at-google-onboarding-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt && pip install -e .

# Verify the exact absolute path to the MCP server entrypoint
realpath .venv/bin/odb-mcp-server
```

#### Step 2: Add `oracle-google-onboarding-agent` to Antigravity's `mcp_config.json`
You can configure the MCP server via the Antigravity UI or by editing the configuration file directly:

- **Via Antigravity UI**: In the Antigravity Agent side pane, click **Additional Options (`...`)** at the top right → **MCP Servers** → **Manage MCP Servers** (or **View raw config**) to open `mcp_config.json`.
- **Via Config File Directly**: Open `~/.gemini/config/mcp_config.json` (or `~/.gemini/antigravity/mcp_config.json` depending on your environment).

Add the `oracle-google-onboarding-agent` entry under `"mcpServers"` (replace `/ABSOLUTE/PATH/TO/...` with the output of `realpath .venv/bin/odb-mcp-server` and your target workspace directory):

```json
{
  "mcpServers": {
    "oracle-google-onboarding-agent": {
      "command": "/ABSOLUTE/PATH/TO/oracle-at-google-onboarding-agent/.venv/bin/odb-mcp-server",
      "args": [],
      "env": {
        "ODB_WORKSPACE_ROOT": "/ABSOLUTE/PATH/TO/YOUR/TERRAFORM_WORKSPACE",
        "ODB_AGENT_MODEL": "gemini-3.8-flash",
        "ODB_FAST_VALIDATION": "1"
      }
    }
  }
}
```

> **Alternative Command**: You can also invoke the CLI entrypoint directly by setting `"command": "/ABSOLUTE/PATH/TO/oracle-at-google-onboarding-agent/.venv/bin/odb-onboarding-agent"` and `"args": ["mcp-serve"]`.

#### Step 3: Refresh & Verify Tool Discovery in Antigravity
1. Save `mcp_config.json`.
2. In the Antigravity Agent pane, navigate to **Additional Options (`...`) > MCP Servers** and click **Refresh** (or start a new conversation).
3. Confirm that **`oracle-google-onboarding-agent`** shows a green connected status and lists all 10 tools (`get_odb_onboarding_guide`, `evaluate_onboarding_readiness`, `verify_live_onboarding_and_iam_readiness`, `generate_odb_diagram`, `generate_golden_terraform`, `validate_odb_network_cidrs`, `validate_odb_terraform_hcl`, `inspect_day2_workspace`, `analyze_day2_terraform_diff`, and `list_odb_provider_resources`).
4. *(Optional)* To sanity-check the `stdio` server from your terminal before connecting:
   ```bash
   echo '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | .venv/bin/odb-mcp-server
   ```

#### Step 4: Invoke the MCP Tools from Antigravity Chat
Once connected, Antigravity automatically discovers and invokes the MCP tools when you ask questions such as:
- *"Use `evaluate_onboarding_readiness` to check our readiness for an Exadata Dedicated deployment in `us-east4` using a Shared VPC and CMEK."*
- *"Use `verify_live_onboarding_and_iam_readiness` to check if anything is missing in project `my-odb-prod` before deploying Oracle Autonomous Database."*
- *"Generate a hub-and-spoke HA/DR architecture diagram for Oracle Database@Google Cloud using `generate_odb_diagram`."*
- *"Use `generate_golden_terraform` to create a Day-1 Autonomous Database (`adb`) Terraform bundle for project `my-odb-prod`."*
- *"Run `inspect_day2_workspace` on `./output/odb-golden-bundle` and check for `ForceNew` replacement risks."*

---

### VS Code (`.vscode/mcp.json`) or Cursor (`.cursor/mcp.json`)
Create `.vscode/mcp.json` (or `.cursor/mcp.json`) in your project workspace:

```json
{
  "servers": {
    "oracle-google-onboarding-agent": {
      "type": "stdio",
      "command": "/ABSOLUTE/PATH/TO/oracle-at-google-onboarding-agent/.venv/bin/odb-mcp-server",
      "args": [],
      "env": {
        "ODB_WORKSPACE_ROOT": "${workspaceFolder}",
        "ODB_AGENT_MODEL": "gemini-3.8-flash",
        "ODB_FAST_VALIDATION": "1"
      }
    }
  }
}
```

### Claude Desktop (`claude_desktop_config.json`) / Gemini CLI (`settings.json`)
```json
{
  "mcpServers": {
    "oracle-google-onboarding-agent": {
      "command": "/ABSOLUTE/PATH/TO/oracle-at-google-onboarding-agent/.venv/bin/odb-mcp-server",
      "args": [],
      "env": {
        "ODB_WORKSPACE_ROOT": "/ABSOLUTE/PATH/TO/YOUR/TERRAFORM_WORKSPACE",
        "ODB_AGENT_MODEL": "gemini-3.8-flash",
        "ODB_FAST_VALIDATION": "1"
      }
    }
  }
}
```

### MCP Tools Exposed to Your IDE
| MCP Tool | Purpose | Safety Guardrail |
| :--- | :--- | :--- |
| `get_odb_onboarding_guide` | Grounded answers on Prerequisites, Marketplace (Private Offer vs PAYG), OCI Linking, MOS/CSI Support, ODB Networks, Backup, CMEK, Monitoring | Read-only knowledge base |
| `evaluate_onboarding_readiness` | Evaluates customer onboarding readiness (0–100 score + missing checklist items & `gcloud` bootstrap commands) | Read-only evaluator |
| `verify_live_onboarding_and_iam_readiness` | Queries live GCP project APIs (`oracledatabase.googleapis.com`), active IAM roles (`roles/oracledatabase.admin`), and Marketplace/OCI link readiness | Read-only live GCP pre-flight check |
| `generate_odb_diagram` | Generates syntax-verified Mermaid (`mermaid`) and ASCII architecture/onboarding diagrams | Workspace path sandboxed |
| `generate_golden_terraform` | Generates verified Day-1 Golden Terraform (`networking.tf`, `workload.tf`, `variables.tf`, `outputs.tf`, `versions.tf`) in `./output/<bundle>` | Fast validation (`<50ms`), concise summary, workspace sandboxed |
| `validate_odb_terraform_hcl` | Validates HCL against `EXACT_ODB_RESOURCE_SCHEMAS`, `/28` subnet rules, and secret-leak rules | Fast validation (`<50ms`), read-only |
| `validate_odb_network_cidrs` | Validates VPC, `CLIENT_SUBNET`, and `BACKUP_SUBNET` CIDR math (`/28` minimum, non-overlapping) | Read-only |
| `inspect_day2_workspace` | Audits `.tf` files in workspace for `deletion_protection` and `ForceNew` risks | Workspace path sandboxed, read-only |
| `analyze_day2_terraform_diff` | Compares Before vs. After HCL to block accidental database destruction (`ForceNew`) | Read-only |
| `list_odb_provider_resources` | Lists all `google_oracle_database_*` resources in `hashicorp/google` and exact `top_level` vs `properties {}` schemas | Read-only |

---

## Option 3: Launch the Streamlit Web Studio

```bash
streamlit run ai_agent/web.py --server.address=127.0.0.1 --server.port=8502
```

---

## Running Automated Tests

```bash
.venv/bin/pytest -v
```
