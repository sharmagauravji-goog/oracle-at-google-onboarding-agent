"""LLM Agent Orchestrator with 5-Layer Anti-Hallucination & Day-2 Maintenance Guardrails.

Coordinates multi-turn conversations with Gemini (`gemini-3.8-flash` / `gemini-3.1-pro-preview`),
executes live discovery and validation tools, and runs an automatic post-generation
anti-hallucination self-repair loop whenever Terraform HCL blocks are emitted.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from google.genai import types

from ai_agent.llm_client import (
    LLMConnectionConfig,
    create_genai_client,
)
from ai_agent.tools.day2_maintenance import (
    analyze_day2_terraform_diff,
    inspect_existing_terraform_workspace,
)
from ai_agent.tools.docs_fetcher import fetch_official_odb_documentation
from ai_agent.tools.golden_templates import generate_golden_odb_terraform
from ai_agent.tools.network_validator import (
    save_generated_terraform_bundle,
    validate_odb_network_cidrs,
)
from ai_agent.tools.odb_live_discovery import (
    check_customer_gcp_readiness,
    check_live_vpc_subnet_overlaps,
    discover_live_odb_regions_and_zones,
    discover_live_odb_shapes_and_versions,
)
from ai_agent.tools.terraform_registry import (
    check_hcl_for_provider_hallucinations,
    get_latest_google_provider_version,
    get_odb_resource_documentation,
    list_odb_terraform_resources,
    validate_terraform_hcl,
)

SYSTEM_INSTRUCTION = """You are the **Oracle Database@Google Cloud (ODB@GCP) AI Principal Architect Agent**.

You help customers create (Day-1) and maintain/evolve (Day-2) production-ready Terraform for Oracle Database@Google Cloud with zero hallucinations.

Always enforce these 5 Guardrails:
1. **Guardrail 1 — Golden Baseline First (Day-1 Creation)**:
   - When asked to generate a new ODB@GCP environment (Autonomous DB, Exadata Dedicated, Exascale, or BaseDB), ALWAYS call `generate_golden_odb_terraform` first to produce a proven, schema-verified baseline (`hashicorp/google >= 7.0.0`), and only customize specific blocks if the customer needs non-standard settings.
2. **Guardrail 2 — Exact Provider Schema Grounding**:
   - Never use `oci_database_*` resources; ODB@GCP uses `google_oracle_database_*` from `hashicorp/google`.
   - On `google_oracle_database_odb_subnet`, the parent network argument is `odbnetwork` (no underscore), whereas on workload resources (`autonomous_database`, `cloud_vm_cluster`, `exadb_vm_cluster`, `db_system`) it is `odb_network`.
   - Workload sizing attributes (`compute_count`, `data_storage_size_tb`, `db_version`, `db_workload`, `cpu_core_count`, `gi_version`, `grid_image_id`, `shape`) MUST be nested inside a `properties { ... }` block.
   - If unsure of any attribute, call `get_odb_resource_documentation` or `list_odb_terraform_resources`.
3. **Guardrail 3 — Deterministic Network & Secret Validation**:
   - Always call `validate_odb_network_cidrs` to verify `/28` minimum subnet prefixes and zero CIDR overlap.
   - Never place `admin_password` values in `terraform.tfvars`; use `var.db_admin_password` (`sensitive = true`).
4. **Guardrail 4 — Live GCP Environment Grounding & Compiler Validation**:
   - Call `discover_live_odb_regions_and_zones`, `discover_live_odb_shapes_and_versions`, and `check_live_vpc_subnet_overlaps` to ground configurations in the customer's real GCP project.
   - Call `validate_terraform_hcl` to verify generated `.tf` files before presenting or saving them.
5. **Guardrail 5 — Safe Day-2 Maintenance (No Accidental Destroy)**:
   - Before modifying existing customer Terraform files, call `inspect_existing_terraform_workspace` and `analyze_day2_terraform_diff` to ensure no `ForceNew` immutable attribute (`odb_network_id`, `cidr_range`, `gcp_oracle_zone`, `database`, `shape`) is changed in a way that would trigger `-/+ destroy and recreate` on a live production database.
"""

_HCL_CODE_BLOCK_REGEX = re.compile(r"```(?:hcl|terraform|tf)\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)


@dataclass
class ToolCallTrace:
    """Record of a single tool invocation or guardrail check executed during a turn."""

    tool_name: str
    arguments: dict[str, Any]
    result_preview: str
    duration_ms: float


@dataclass
class AgentTurnResponse:
    """Structured response from a single agent turn, including text, tool trace, and guardrail status."""

    text: str
    model: str
    auth_mode: str
    tool_traces: list[ToolCallTrace] = field(default_factory=list)
    guardrail_verified: bool = True
    auto_repairs_triggered: int = 0


def extract_hcl_blocks(markdown_text: str) -> list[str]:
    """Extracts all fenced `hcl` / `terraform` / `tf` code blocks from markdown text."""
    return [m.group(1) for m in _HCL_CODE_BLOCK_REGEX.finditer(markdown_text or "")]


class ODBArchitectAgent:
    """Stateful LLM Agent with 5-layer anti-hallucination guardrails and Day-2 maintenance tools."""

    def __init__(self, config: LLMConnectionConfig, max_auto_repairs: int = 2) -> None:
        self.config = config
        self.max_auto_repairs = max_auto_repairs
        self.client = create_genai_client(config)
        self._current_turn_traces: list[ToolCallTrace] = []
        self._tools = self._build_instrumented_tools()
        self._chat = self.client.chats.create(
            model=self.config.model,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                tools=self._tools,
                temperature=0.1,
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
        """Returns the list of 13 live discovery, golden template, and Day-2 maintenance tools."""
        raw_tools: list[Callable[..., str]] = [
            generate_golden_odb_terraform,
            get_latest_google_provider_version,
            list_odb_terraform_resources,
            get_odb_resource_documentation,
            validate_terraform_hcl,
            discover_live_odb_regions_and_zones,
            discover_live_odb_shapes_and_versions,
            check_live_vpc_subnet_overlaps,
            check_customer_gcp_readiness,
            fetch_official_odb_documentation,
            validate_odb_network_cidrs,
            save_generated_terraform_bundle,
            inspect_existing_terraform_workspace,
            analyze_day2_terraform_diff,
        ]
        return [self._wrap_tool(fn) for fn in raw_tools]

    def send_message(self, user_message: str) -> AgentTurnResponse:
        """Sends a user message, executes tools, and runs post-generation HCL guardrail verification."""
        self._current_turn_traces = []
        response = self._chat.send_message(user_message)
        reply_text = response.text or "(No text returned by model)"

        repairs = 0
        guardrail_ok = True

        # Post-generation Guardrail 3: Inspect any emitted HCL code blocks for provider hallucinations
        for attempt in range(self.max_auto_repairs):
            hcl_blocks = extract_hcl_blocks(reply_text)
            if not hcl_blocks:
                break

            combined_hcl = "\n\n".join(hcl_blocks)
            start_check = time.perf_counter()
            issues = check_hcl_for_provider_hallucinations(combined_hcl)
            elapsed_ms = round((time.perf_counter() - start_check) * 1000, 1)

            self._current_turn_traces.append(
                ToolCallTrace(
                    tool_name="post_generation_hcl_guardrail",
                    arguments={"hcl_blocks_inspected": len(hcl_blocks), "attempt": attempt + 1},
                    result_preview=json.dumps(
                        {"passed": len(issues) == 0, "issues": issues},
                        indent=2,
                    ),
                    duration_ms=elapsed_ms,
                )
            )

            if not issues:
                guardrail_ok = True
                break

            # Trigger automatic self-healing turn with the exact compiler/schema errors
            guardrail_ok = False
            repairs += 1
            repair_prompt = (
                "[GUARDRAIL AUTO-REPAIR] Your generated Terraform HCL contained schema hallucinations:\n"
                + "\n".join(f"- {iss}" for iss in issues)
                + "\nPlease fix the HCL using the exact `hashicorp/google` (`google_oracle_database_*`) schema "
                "and output the corrected Terraform code."
            )
            repair_resp = self._chat.send_message(repair_prompt)
            reply_text = repair_resp.text or reply_text

        return AgentTurnResponse(
            text=reply_text,
            model=self.config.model,
            auth_mode=self.config.auth_mode,
            tool_traces=list(self._current_turn_traces),
            guardrail_verified=guardrail_ok,
            auto_repairs_triggered=repairs,
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
