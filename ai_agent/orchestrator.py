"""LLM Agent Orchestrator for Oracle Database@Google Cloud.

Coordinates multi-turn conversations with Gemini (`gemini-3.8-flash` / `gemini-3.1-pro-preview`),
executes live discovery and validation tools, and records a full tool-call trace so customers
can see exactly which live APIs, Terraform Registry schemas, and documentation pages were consulted.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from google.genai import types

from ai_agent.llm_client import (
    LLMConnectionConfig,
    create_genai_client,
)
from ai_agent.tools.docs_fetcher import fetch_official_odb_documentation
from ai_agent.tools.network_validator import (
    save_generated_terraform_bundle,
    validate_odb_network_cidrs,
)
from ai_agent.tools.odb_live_discovery import (
    check_customer_gcp_readiness,
    discover_live_odb_regions_and_zones,
    discover_live_odb_shapes_and_versions,
)
from ai_agent.tools.terraform_registry import (
    get_latest_google_provider_version,
    get_odb_resource_documentation,
    list_odb_terraform_resources,
    validate_terraform_hcl,
)

SYSTEM_INSTRUCTION = """You are the **Oracle Database@Google Cloud (ODB@GCP) AI Principal Architect Agent**.

Unlike a static template wizard, you are an autonomous LLM agent equipped with live tools.
Always follow these operating principles:
1. **Verify Live Provider & Resource Schemas**:
   - Before answering questions about Terraform provider versions or writing Terraform HCL for `google_oracle_database_*` resources, call `get_latest_google_provider_version`, `list_odb_terraform_resources`, or `get_odb_resource_documentation` to inspect the latest upstream schema from the Terraform Registry and `hashicorp/terraform-provider-google`.
2. **Verify Live Cloud Regions, Shapes, and Versions**:
   - When a customer asks what regions, `gcp_oracle_zone` values, Exadata/Exascale/BaseDB shapes, GI versions, or Autonomous DB versions are supported, call `discover_live_odb_regions_and_zones` or `discover_live_odb_shapes_and_versions`.
   - When checking project prerequisites, call `check_customer_gcp_readiness`.
3. **Consult Live Official Documentation**:
   - For release notes, new feature announcements, IAM permissions, or architectural limitations, call `fetch_official_odb_documentation`.
4. **Enforce Deterministic Security & Network Guardrails**:
   - Always validate customer CIDRs using `validate_odb_network_cidrs` (minimum `/28` prefix for ODB subnets, zero overlap between VPC CIDR, `CLIENT_SUBNET`, and `BACKUP_SUBNET`).
   - Never hardcode database admin passwords in `terraform.tfvars`; always declare `variable "db_admin_password" { sensitive = true }` and instruct the customer to pass `TF_VAR_db_admin_password` via Secret Manager or CI/CD secrets.
   - When generating Terraform files, validate them with `validate_terraform_hcl` and offer to save them with `save_generated_terraform_bundle`.
"""


@dataclass
class ToolCallTrace:
    """Record of a single tool invocation executed by the LLM agent during a turn."""

    tool_name: str
    arguments: dict[str, Any]
    result_preview: str
    duration_ms: float


@dataclass
class AgentTurnResponse:
    """Structured response from a single agent turn, including text and tool trace."""

    text: str
    model: str
    auth_mode: str
    tool_traces: list[ToolCallTrace] = field(default_factory=list)


class ODBArchitectAgent:
    """Stateful LLM Agent with live Terraform Registry, ODB@GCP API, and Docs tools."""

    def __init__(self, config: LLMConnectionConfig) -> None:
        self.config = config
        self.client = create_genai_client(config)
        self._current_turn_traces: list[ToolCallTrace] = []
        self._tools = self._build_instrumented_tools()
        self._chat = self.client.chats.create(
            model=self.config.model,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                tools=self._tools,
                temperature=0.2,
            ),
        )

    def _wrap_tool(self, fn: Callable[..., str]) -> Callable[..., str]:
        """Wraps a tool function so every invocation by Gemini is timed and logged."""

        def wrapped(**kwargs: Any) -> str:
            start = time.perf_counter()
            try:
                output = fn(**kwargs)
            except Exception as exc:
                output = f'{{"error": "{exc}"}}'
            elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
            preview = output if len(output) <= 600 else output[:600] + "\n...[truncated]"
            self._current_turn_traces.append(
                ToolCallTrace(
                    tool_name=fn.__name__,
                    arguments=dict(kwargs),
                    result_preview=preview,
                    duration_ms=elapsed_ms,
                )
            )
            return output

        wrapped.__name__ = fn.__name__
        wrapped.__doc__ = fn.__doc__
        wrapped.__annotations__ = getattr(fn, "__annotations__", {})
        import inspect

        wrapped.__signature__ = inspect.signature(fn)  # type: ignore[attr-defined]
        return wrapped

    def _build_instrumented_tools(self) -> list[Callable[..., str]]:
        """Returns the list of Python tool functions exposed to Gemini function calling."""
        raw_tools: list[Callable[..., str]] = [
            get_latest_google_provider_version,
            list_odb_terraform_resources,
            get_odb_resource_documentation,
            validate_terraform_hcl,
            discover_live_odb_regions_and_zones,
            discover_live_odb_shapes_and_versions,
            check_customer_gcp_readiness,
            fetch_official_odb_documentation,
            validate_odb_network_cidrs,
            save_generated_terraform_bundle,
        ]
        return [self._wrap_tool(fn) for fn in raw_tools]

    def send_message(self, user_message: str) -> AgentTurnResponse:
        """Sends a user message to the agent, executes any required tools, and returns the response."""
        self._current_turn_traces = []
        response = self._chat.send_message(user_message)
        return AgentTurnResponse(
            text=response.text or "(No text returned by model)",
            model=self.config.model,
            auth_mode=self.config.auth_mode,
            tool_traces=list(self._current_turn_traces),
        )


def test_llm_connection(config: LLMConnectionConfig) -> dict[str, Any]:
    """Performs a lightweight connectivity check against the configured Gemini endpoint."""
    start = time.perf_counter()
    try:
        client = create_genai_client(config)
        resp = client.models.generate_content(
            model=config.model,
            contents="Reply with the exact word READY if you can read this.",
            config=types.GenerateContentConfig(
                temperature=0.0,
                max_output_tokens=256,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )
        latency_ms = round((time.perf_counter() - start) * 1000, 1)
        return {
            "connected": True,
            "model": config.model,
            "auth_mode": config.auth_mode,
            "credentials": config.masked_credential_summary,
            "latency_ms": latency_ms,
            "response": (resp.text or "READY").strip(),
        }
    except Exception as exc:
        return {
            "connected": False,
            "model": config.model,
            "auth_mode": config.auth_mode,
            "credentials": config.masked_credential_summary,
            "error": str(exc),
        }
