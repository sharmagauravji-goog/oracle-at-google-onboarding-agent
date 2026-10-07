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

## Step 4: Generate Grounded Mermaid & ASCII Architecture Diagrams

Generate syntax-verified Mermaid (`mermaid`) and ASCII diagrams for the end-to-end onboarding flow and enterprise networking topologies:

```bash
odb-onboarding-agent diagram --type end_to_end_onboarding --save-to ./output/diagrams/onboarding.md
odb-onboarding-agent diagram --type odb_network_hub_spoke_ncc --save-to ./output/diagrams/hub-spoke.md
```

---

## Step 5: Generate a Verified Day-1 Golden Terraform Bundle

Generate a deterministic, compiler-verified Terraform bundle (`main.tf`, `variables.tf`, `outputs.tf`, `versions.tf`) for an **Oracle 23ai Autonomous Database** (`adb`), **Exadata Dedicated** (`exadata_dedicated`), **Exascale** (`exascale`), or **BaseDB** (`basedb`):

```bash
odb-onboarding-agent generate-golden \
  --project-id "$GOOGLE_CLOUD_PROJECT" \
  --workload adb \
  --region us-east4 \
  --oracle-zone us-east4-b-r1 \
  --bundle-name adb-prod
```

Inspect the generated files inside `./output/adb-prod`:

```bash
ls -la ./output/adb-prod
```

---

## Step 6: Audit Day-2 Maintenance & `deletion_protection` Posture

Run the Day-2 Maintenance Guard against `./output` to verify `deletion_protection = true` and identify `ForceNew` replacement risks before modifying existing Terraform code:

```bash
odb-onboarding-agent inspect-day2 --workspace-dir ./output
```

---

## Step 7: Launch Interactive Multi-Turn Onboarding & Architecture Chat

Start a conversational session with the **Oracle@Google Onboarding Agent**:

```bash
odb-onboarding-agent chat
```

Try asking:
- *"Walk me through the complete Oracle@Google onboarding process — Prerequisites, Marketplace Private Offer vs PAYG, OCI Account Linking, and MOS CSI registration — and include an end-to-end Mermaid diagram."*
- *"Explain ODB Networks (`CLIENT_SUBNET` vs `BACKUP_SUBNET`) and generate a Hub-and-Spoke NCC + Cloud Interconnect diagram."*
- *"How do Backup & Recovery, Google Cloud KMS CMEK (`gcp-sa-oracledatabase`), and Cloud Monitoring work for Exadata VM Clusters?"*
- *"Inspect ./output/adb-prod and modify it to scale compute_count from 4 to 8 ECPUs in-place without triggering a ForceNew replacement."*
