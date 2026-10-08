#!/usr/bin/env bash
set -euo pipefail

echo "=================================================================="
echo "  Oracle@Google Onboarding Agent — Google Cloud Shell Quickstart"
echo "=================================================================="

if command -v gcloud >/dev/null 2>&1; then
  ACTIVE_PROJECT="${1:-$(gcloud config get-value project 2>/dev/null || true)}"
  if [[ -z "${ACTIVE_PROJECT}" || "${ACTIVE_PROJECT}" == "(unset)" ]]; then
    ACTIVE_PROJECT="${GOOGLE_CLOUD_PROJECT:-${DEVSHELL_PROJECT_ID:-}}"
  fi
  if [[ -z "${ACTIVE_PROJECT}" || "${ACTIVE_PROJECT}" == "(unset)" ]]; then
    echo "-> No default GCP project configured in gcloud. Discovering active projects..."
    ACTIVE_PROJECT="$(gcloud projects list --filter="lifecycleState:ACTIVE" --format="value(projectId)" --limit=1 2>/dev/null | head -n 1 || true)"
    if [[ -n "${ACTIVE_PROJECT}" ]]; then
      echo "-> Auto-selecting active GCP project: ${ACTIVE_PROJECT}"
      gcloud config set project "${ACTIVE_PROJECT}" --quiet || true
      export GOOGLE_CLOUD_PROJECT="${ACTIVE_PROJECT}"
    else
      echo "-> WARNING: Could not auto-detect a GCP project. Run: gcloud config set project <YOUR_PROJECT_ID>"
    fi
  else
    export GOOGLE_CLOUD_PROJECT="${ACTIVE_PROJECT}"
  fi

  if [[ -n "${ACTIVE_PROJECT}" && "${ACTIVE_PROJECT}" != "(unset)" ]]; then
    echo "-> Enabling Vertex AI API (aiplatform.googleapis.com) in project: ${ACTIVE_PROJECT}"
    gcloud services enable aiplatform.googleapis.com --project="${ACTIVE_PROJECT}" --quiet || true
  fi
fi

echo "-> Creating Python virtual environment (.venv)..."
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate

echo "-> Installing dependencies & CLI entrypoints (odb-onboarding-agent, odb-ai-agent, odb-mcp-server)..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
pip install -e . -q

echo ""
echo "Setup complete! Running Environment Doctor..."
odb-onboarding-agent doctor --ping-llm
