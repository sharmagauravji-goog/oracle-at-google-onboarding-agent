"""Unit tests for LLM Connection & Authentication Manager (`ai_agent.llm_client`)."""

from __future__ import annotations

import pytest

from ai_agent.llm_client import (
    DEFAULT_MODEL,
    mask_secret,
    normalize_model_name,
    resolve_llm_config,
    validate_gcp_location,
    validate_gcp_project_id,
)


def test_mask_secret_never_exposes_plaintext() -> None:
    assert mask_secret("") == "not-configured"
    assert mask_secret("short") == "****"
    masked = mask_secret("AIzaSyD1234567890abcdefXYZ")
    assert masked == "AIza...fXYZ"
    assert "1234567890" not in masked


def test_normalize_model_upgrades_legacy_models() -> None:
    assert normalize_model_name(None) == DEFAULT_MODEL
    assert normalize_model_name("gemini-2.5-flash") == "gemini-3.8-flash"
    assert normalize_model_name("gemini-2.0-flash") == "gemini-3.8-flash"
    assert normalize_model_name("gemini-1.5-pro") == "gemini-3.8-flash"
    assert normalize_model_name("gemini-3.1-pro-preview") == "gemini-3.1-pro-preview"


def test_validate_gcp_project_id_and_location() -> None:
    assert validate_gcp_project_id("my-odb-project-01") == "my-odb-project-01"
    with pytest.raises(ValueError, match="Invalid GCP project_id"):
        validate_gcp_project_id("BAD_PROJECT; rm -rf /")

    assert validate_gcp_location("us-central1") == "us-central1"
    with pytest.raises(ValueError, match="Invalid GCP location"):
        validate_gcp_location("us-central1; whoami")


def test_resolve_llm_config_vertex_and_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("ODB_AGENT_AUTH_MODE", raising=False)

    vertex_cfg = resolve_llm_config(
        auth_mode="vertex",
        project_id="odb-enterprise-prod-01",
        location="us-east4",
    )
    assert vertex_cfg.auth_mode == "vertex"
    assert vertex_cfg.project_id == "odb-enterprise-prod-01"
    assert vertex_cfg.location == "us-east4"
    assert "odb-enterprise-prod-01" in vertex_cfg.masked_credential_summary

    key_cfg = resolve_llm_config(
        auth_mode="api_key",
        api_key="AIzaSyTestKey1234567890",
    )
    assert key_cfg.auth_mode == "api_key"
    assert "AIza...7890" in key_cfg.masked_credential_summary
    assert "TestKey" not in key_cfg.masked_credential_summary
