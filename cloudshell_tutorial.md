# Oracle Database@Google Cloud — AI Architect Agent (Cloud Shell Walkthrough)

Welcome to the **Oracle Database@Google Cloud (ODB@GCP) AI Architect Agent**!
Because you are running inside **Google Cloud Shell**, `gcloud`, `terraform`, and `python3` are already pre-installed.

---

## Step 1: Set Your Google Cloud Project

Select the Google Cloud project where you want to deploy or maintain Oracle Database@Google Cloud:

```bash
gcloud config set project YOUR_PROJECT_ID
export GOOGLE_CLOUD_PROJECT=$(gcloud config get-value project)
export GOOGLE_CLOUD_LOCATION="global"
```

Enable the Vertex AI API (for zero-key LLM access) and Oracle Database@Google Cloud API:

```bash
gcloud services enable aiplatform.googleapis.com oracledatabase.googleapis.com compute.googleapis.com servicenetworking.googleapis.com
```

---

## Step 2: Install the Agent in a Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

---

## Step 3: Verify Your Environment & Live LLM Connection

Run the built-in environment doctor to confirm Vertex AI ADC (`gemini-3.8-flash`), `terraform`, and live `registry.terraform.io` connectivity:

```bash
odb-ai-agent doctor --ping-llm
```

---

## Step 4: Generate Production Terraform or Start Interactive Chat

### Option A: Deterministic Golden Baseline + Compiler Validation
```bash
odb-ai-agent generate-golden --project-id "$GOOGLE_CLOUD_PROJECT" --workload adb
```

### Option B: Interactive AI Architect Chat (Day-1 Creation & Day-2 Maintenance)
```bash
odb-ai-agent chat
```

### Option C: Launch the Web Studio (Preview on Port 8502)
```bash
streamlit run ai_agent/web.py --server.address=127.0.0.1 --server.port=8502
```
Click the **Web Preview** icon in the top-right of Cloud Shell and change the port to **`8502`**.
