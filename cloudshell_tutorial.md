# Oracle@Google Onboarding Agent — Cloud Shell Tutorial

Welcome to the **Oracle@Google Onboarding Agent** (`odb-onboarding-agent`)! This tutorial guides you through running the agent directly in **Google Cloud Shell** using your active Google Cloud credentials (Vertex AI ADC — zero API keys needed).

---

## Step 1: Set Up the Virtual Environment & Enable APIs

Run the automated Cloud Shell quickstart script to enable `aiplatform.googleapis.com` and install the `odb-onboarding-agent` CLI:

```bash
chmod +x scripts/cloudshell_quickstart.sh
./scripts/cloudshell_quickstart.sh
source .venv/bin/activate
```

---

## Step 2: Run the Environment Doctor

Verify your active Google Cloud project, Terraform CLI, live `hashicorp/google` Registry connection, and Vertex AI LLM reachability:

```bash
odb-onboarding-agent doctor --ping-llm
```

---

## Step 3: Explore the End-to-End Onboarding Lifecycle & Architecture Guides

Inspect the grounded, anti-hallucination guides for Prerequisites, Marketplace Private Offer vs. Pay-As-You-Go, OCI Account Linking, My Oracle Support (CSI) Registration, ODB Networks, Backup & Recovery, CMEK Encryption, and Monitoring:

```bash
odb-onboarding-agent onboarding-guide --topic overview
odb-onboarding-agent onboarding-guide --topic marketplace_procurement
odb-onboarding-agent onboarding-guide --topic odb_networks_and_topologies
odb-onboarding-agent onboarding-guide --topic encryption_and_cmek
```

---

## Step 4: Run the Guided Architecture Discovery & Sizing Wizard

Recommend the right Oracle Database@Google Cloud service (`adb`, `exadata_dedicated`, `exascale`, or `basedb`), non-overlapping `/24` + `/27` CIDR layout, interactive HTML5 diagram, and verified Golden Terraform bundle:

```bash
odb-onboarding-agent wizard \
  --workload-profile autonomous_ai_lakehouse \
  --ha-dr-tier regional_ha \
  --network-model shared_vpc \
  --encryption gcp_cmek \
  --project-id "$GOOGLE_CLOUD_PROJECT" \
  --generate-bundle \
  --save-html
```

*(Tip: Run `odb-onboarding-agent wizard --interactive` for guided terminal prompts!)*

---

## Step 5: Track & Auto-Verify Your 6-Phase Onboarding Journey

Auto-verify your active Google Cloud project's APIs, IAM roles, VPC subnets, and generated Terraform files across the 6 onboarding phases (persisted in `./output/onboarding_progress.json`):

```bash
odb-onboarding-agent tracker \
  --action auto_verify \
  --project-id "$GOOGLE_CLOUD_PROJECT" \
  --region us-east4
```

Mark a manual phase (such as Marketplace subscription) complete:

```bash
odb-onboarding-agent tracker \
  --action update_phase \
  --phase 2 \
  --status completed \
  --notes "Marketplace Private Offer accepted"
```

---

## Step 6: Generate Interactive HTML5, Mermaid & ASCII Architecture Diagrams

Generate syntax-verified Mermaid (`mermaid`), terminal ASCII, and standalone interactive HTML5 topology explorers:

```bash
odb-onboarding-agent diagram --type end_to_end_onboarding --save-to ./output/diagrams/onboarding.md
odb-onboarding-agent diagram --type networking_hub_and_spoke_ha_dr --format interactive_html --save-to ./output/diagrams/hub-spoke.html

# Optional: Download the standalone interactive HTML5 topology explorer to your browser
cloudshell download ./output/diagrams/hub-spoke.html
```

To launch the full **Interactive Topology, Architecture Wizard, 6-Phase Progress Tracker & Day-2 Simulator Studio** in **Cloud Shell Web Preview** (port `8080`):

```bash
odb-onboarding-agent studio --cloud-shell
```

Then click **Web Preview -> Preview on port 8080** in the Cloud Shell toolbar (press `Ctrl+C` when ready to continue to Step 7).

---

## Step 7: Simulate Day-2 Scaling & Guard Against `ForceNew` Replacements

Simulate scaling ECPUs and storage online vs. mutating immutable `ForceNew` attributes (`client_subnet_cidr`, `gcp_oracle_zone`):

```bash
odb-onboarding-agent simulate-day2 \
  --workload adb \
  --current-compute 4 \
  --proposed-compute 16 \
  --current-storage-tb 1 \
  --proposed-storage-tb 4 \
  --save-html
```

Run the Day-2 Maintenance Guard against `./output` to verify `deletion_protection = true`:

```bash
odb-onboarding-agent inspect-day2 --workspace-dir ./output
```

---

## Step 8: Launch Interactive Multi-Turn Onboarding & Architecture Chat

Start a conversational session with the **Oracle@Google Onboarding Agent** (featuring live streaming tool telemetry and the 5-Layer Guardrail Scorecard):

```bash
odb-onboarding-agent chat
```

Try asking:
- *"Run the architecture discovery wizard for a mission-critical OLTP RAC workload with cross-region Data Guard and Shared VPC."*
- *"Check our 6-phase onboarding progress tracker and auto-verify our live GCP readiness."*
- *"Simulate scaling our Autonomous Database from 4 to 16 ECPUs and check if changing `client_subnet_cidr` triggers a `ForceNew` replacement."*
- *"Explain ODB Networks (`CLIENT_SUBNET` vs `BACKUP_SUBNET`) and generate a Hub-and-Spoke NCC + Cloud Interconnect diagram."*

