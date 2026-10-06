"""LLM Connection & Authentication Manager for the ODB@GCP AI Agent.

Supports two primary customer connection modes via the official `google-genai` SDK:
1. Vertex AI / Google Cloud ADC (`vertex`): Uses the customer's existing
   `gcloud auth application-default login` credentials and GCP project. Zero API keys required.
2. Gemini Developer API (`api_key`): Uses a Google AI Studio API key (`GEMINI_API_KEY`).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Literal, Optional

from google import genai

AuthMode = Literal["auto", "vertex", "api_key"]

DEFAULT_MODEL = "gemini-3.8-flash"

SUPPORTED_MODELS: tuple[str, ...] = (
    "gemini-3.8-flash",
    "gemini-flash-latest",
    "gemini-3.1-pro-preview",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
)

_PROJECT_ID_PATTERN = re.compile(r"^[a-z][a-z0-9\-]{4,28}[a-z0-9]$")
_LOCATION_PATTERN = re.compile(r"^[a-z0-9\-]{2,32}$")


@dataclass(frozen=True)
class LLMConnectionConfig:
    """Resolved configuration for connecting to Gemini via Vertex AI or Developer API."""

    auth_mode: Literal["vertex", "api_key"]
    model: str = DEFAULT_MODEL
    project_id: Optional[str] = None
    location: str = "global"
    api_key: Optional[str] = None

    @property
    def masked_credential_summary(self) -> str:
        """Returns a PII/secret-safe summary string suitable for UI and logs."""
        if self.auth_mode == "api_key":
            return f"Gemini Developer API Key ({mask_secret(self.api_key or '')})"
        return f"Vertex AI ADC (project={self.project_id or 'unset'}, location={self.location})"


def mask_secret(secret: str) -> str:
    """Masks sensitive strings (API keys, tokens) for safe display."""
    cleaned = secret.strip()
    if not cleaned:
        return "not-configured"
    if len(cleaned) <= 8:
        return "****"
    return f"{cleaned[:4]}...{cleaned[-4:]}"


def normalize_model_name(model: Optional[str]) -> str:
    """Normalizes model names and upgrades deprecated 1.5/2.0/2.5 models to gemini-3.8-flash."""
    if not model or not model.strip():
        return DEFAULT_MODEL
    cleaned = model.strip()
    if cleaned.startswith(("gemini-1.5", "gemini-2.0", "gemini-2.5")):
        return DEFAULT_MODEL
    if cleaned in SUPPORTED_MODELS:
        return cleaned
    return DEFAULT_MODEL


def validate_gcp_project_id(project_id: str) -> str:
    """Validates a Google Cloud project ID against the strict allow-list format."""
    cleaned = project_id.strip()
    if not _PROJECT_ID_PATTERN.match(cleaned):
        raise ValueError(
            f"Invalid GCP project_id '{cleaned}'. Must be 6-30 lowercase letters, digits, or hyphens."
        )
    return cleaned


def validate_gcp_location(location: str) -> str:
    """Validates a Google Cloud location/region string against an allow-list regex."""
    cleaned = location.strip().lower()
    if not _LOCATION_PATTERN.match(cleaned):
        raise ValueError(f"Invalid GCP location '{cleaned}'.")
    return cleaned


def detect_gcloud_default_project() -> Optional[str]:
    """Safely queries `gcloud config get-value project` if gcloud is installed."""
    gcloud_bin = shutil.which("gcloud")
    if not gcloud_bin:
        return None
    try:
        proc = subprocess.run(
            [gcloud_bin, "config", "get-value", "project", "--quiet"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        candidate = (proc.stdout or "").strip()
        if candidate and candidate != "(unset)" and _PROJECT_ID_PATTERN.match(candidate):
            return candidate
    except (OSError, subprocess.SubprocessError):
        return None
    return None


def resolve_llm_config(
    auth_mode: AuthMode = "auto",
    model: Optional[str] = None,
    project_id: Optional[str] = None,
    location: Optional[str] = None,
    api_key: Optional[str] = None,
) -> LLMConnectionConfig:
    """Resolves LLM connection settings from explicit parameters, environment variables, or gcloud ADC."""
    resolved_model = normalize_model_name(model or os.environ.get("ODB_AGENT_MODEL"))
    env_mode = os.environ.get("ODB_AGENT_AUTH_MODE", "").strip().lower()
    effective_mode: str = auth_mode if auth_mode != "auto" else (env_mode or "auto")

    resolved_key = (
        api_key
        or os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
        or ""
    ).strip()

    resolved_project = (
        project_id
        or os.environ.get("GOOGLE_CLOUD_PROJECT")
        or os.environ.get("GCLOUD_PROJECT")
        or detect_gcloud_default_project()
        or ""
    ).strip()

    resolved_location = validate_gcp_location(
        location or os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
    )

    if effective_mode == "api_key":
        if not resolved_key:
            raise ValueError(
                "Gemini API Key mode selected, but no API key was provided. "
                "Set GEMINI_API_KEY in your environment or provide it in the UI."
            )
        return LLMConnectionConfig(
            auth_mode="api_key",
            model=resolved_model,
            api_key=resolved_key,
        )

    if effective_mode == "vertex":
        if not resolved_project:
            raise ValueError(
                "Vertex AI mode selected, but no GCP project ID was found. "
                "Set GOOGLE_CLOUD_PROJECT or run `gcloud config set project <PROJECT_ID>`."
            )
        validated_project = validate_gcp_project_id(resolved_project)
        return LLMConnectionConfig(
            auth_mode="vertex",
            model=resolved_model,
            project_id=validated_project,
            location=resolved_location,
        )

    # Auto mode: prefer API key if explicitly set, otherwise Vertex AI ADC
    if resolved_key:
        return LLMConnectionConfig(
            auth_mode="api_key",
            model=resolved_model,
            api_key=resolved_key,
        )
    if resolved_project:
        validated_project = validate_gcp_project_id(resolved_project)
        return LLMConnectionConfig(
            auth_mode="vertex",
            model=resolved_model,
            project_id=validated_project,
            location=resolved_location,
        )

    raise ValueError(
        "Could not auto-detect LLM credentials. Either:\n"
        "  1. Authenticate with Google Cloud (`gcloud auth application-default login` + `export GOOGLE_CLOUD_PROJECT=...`), or\n"
        "  2. Set `export GEMINI_API_KEY=...` for Gemini Developer API."
    )


from datetime import datetime, timedelta, timezone
import google.auth
from google.auth.credentials import Credentials as GoogleAuthCredentials
from google.auth.exceptions import DefaultCredentialsError, RefreshError


class _GcloudCLICredentials(GoogleAuthCredentials):
    """Auto-refreshing Google Auth Credentials backed by `gcloud auth print-access-token`.

    In Google Cloud Shell, the emulated GCE metadata server does not include an `'email'`
    field in `/computeMetadata/v1/instance/service-accounts/default/`, causing `google-auth`
    to fail with `Unexpected response from metadata server: service account info is missing 'email' field`.
    This credential provider transparently uses the active `gcloud` CLI session (`gcloud auth print-access-token`),
    allowing zero-friction execution in Cloud Shell and local environments where `gcloud` is logged in.
    """

    def __init__(self, quota_project_id: Optional[str] = None) -> None:
        super().__init__()
        self._quota_project_id = quota_project_id
        self.refresh(None)

    @property
    def quota_project_id(self) -> Optional[str]:
        return self._quota_project_id

    def refresh(self, request: object) -> None:  # noqa: ARG002
        gcloud_bin = shutil.which("gcloud")
        if not gcloud_bin:
            raise RefreshError("gcloud CLI not found on PATH.")
        proc = subprocess.run(
            [gcloud_bin, "auth", "print-access-token", "--quiet"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        token = (proc.stdout or "").strip()
        if proc.returncode != 0 or not token:
            stderr = (proc.stderr or "").strip()
            raise RefreshError(
                f"Failed to obtain access token from gcloud CLI: {stderr or 'no token returned'}"
            )
        self.token = token
        # Cache token for 45 minutes before automatically refreshing via gcloud
        self.expiry = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=45)


def _resolve_vertex_credentials(project_id: Optional[str]) -> Optional[GoogleAuthCredentials]:
    """Resolves Vertex AI credentials, falling back to `gcloud auth print-access-token` in Cloud Shell."""
    is_cloud_shell = (
        os.environ.get("CLOUD_SHELL", "").lower() == "true"
        or bool(os.environ.get("DEVSHELL_PROJECT_ID"))
    )
    if is_cloud_shell:
        try:
            return _GcloudCLICredentials(quota_project_id=project_id)
        except Exception:
            pass

    try:
        creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
            quota_project_id=project_id,
        )
        if not creds.valid:
            import google.auth.transport.requests

            creds.refresh(google.auth.transport.requests.Request())
        return creds
    except (DefaultCredentialsError, RefreshError, Exception) as exc:
        # Fallback for Cloud Shell metadata server (`missing 'email' field`) or `gcloud auth login` without ADC file
        if "email" in str(exc).lower() or shutil.which("gcloud"):
            try:
                return _GcloudCLICredentials(quota_project_id=project_id)
            except Exception:
                pass
        return None


def create_genai_client(config: LLMConnectionConfig) -> genai.Client:
    """Instantiates the official `google.genai.Client` for the resolved connection config."""
    if config.auth_mode == "api_key":
        return genai.Client(api_key=config.api_key)
    creds = _resolve_vertex_credentials(config.project_id)
    return genai.Client(
        vertexai=True,
        project=config.project_id,
        location=config.location,
        credentials=creds,
    )

