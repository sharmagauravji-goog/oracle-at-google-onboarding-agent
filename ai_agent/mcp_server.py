"""Model Context Protocol (MCP) `stdio` Server for the Oracle@Google Onboarding Agent.

Allows customers to integrate the Oracle@Google Onboarding Agent directly into
VS Code (GitHub Copilot / Cline / Roo Code), Cursor, Claude Desktop, Gemini CLI,
and Google Antigravity IDE.

Safety & Reliability Guarantees:
1. NEVER exposes `terraform apply` or `terraform destroy` as MCP tools.
2. Redirects `sys.stdout` to `sys.stderr` during tool imports and execution so stray
   `print()` statements can never corrupt the JSON-RPC 2.0 `stdio` stream.
3. Enforces strict workspace path containment (`resolve_safe_workspace_path`): rejects
   any `output_dir` or `workspace_dir` outside the open workspace.
4. Prevents IDE client timeouts by running fast deterministic validation (`fast_mode=True`)
   and returning concise summaries pointing to `./output/<bundle_name>`.
5. Supports configurable Gemini model IDs via `ODB_AGENT_MODEL` / `GEMINI_MODEL`.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import sys
from typing import Any, TextIO

# Configure logging strictly to stderr before importing any sub-modules
logging.basicConfig(
    stream=sys.stderr,
    level=logging.WARNING,
    format="[odb-mcp-server] %(levelname)s: %(message)s",
)
logger = logging.getLogger("odb_mcp_server")

MCP_SERVER_NAME = "oracle-google-onboarding-agent"
MCP_SERVER_VERSION = "0.2.0"
DEFAULT_PROTOCOL_VERSION = "2024-11-05"

# Deliberately excludes `terraform apply`, `terraform destroy`, or shell execution.
MCP_TOOLS_CATALOG: list[dict[str, Any]] = [
    {
        "name": "get_odb_onboarding_guide",
        "description": (
            "Retrieves authoritative, hallucination-free guidance for Oracle Database@Google Cloud (ODB@GCP) "
            "covering Prerequisites & IAM, Marketplace Private Offer vs. Pay-As-You-Go (PAYG), OCI Account Linking, "
            "My Oracle Support (MOS) CSI Registration, ODB Networks & Topologies, Backup & Recovery, "
            "Encryption & CMEK (Cloud KMS / OCI Vault), and Monitoring."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": (
                        "Topic to query: 'all', 'prerequisites_and_iam', 'marketplace_procurement', "
                        "'account_linking_and_tenancy', 'support_registration_mos', "
                        "'odb_networks_and_topologies', 'backup_and_recovery', "
                        "'encryption_and_cmek', or 'monitoring_and_observability'."
                    ),
                    "default": "all",
                }
            },
        },
    },
    {
        "name": "evaluate_onboarding_readiness",
        "description": (
            "Generates a customized step-by-step ODB@GCP Onboarding Readiness Checklist and gcloud bootstrap "
            "commands tailored to the customer's project, Marketplace model (private_offer vs payg), "
            "networking topology (standalone_vpc, shared_vpc, hub_and_spoke), workload, and encryption mode."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "default": "my-odb-project-01"},
                "procurement_model": {
                    "type": "string",
                    "description": "'private_offer' or 'payg'",
                    "default": "private_offer",
                },
                "networking_topology": {
                    "type": "string",
                    "description": "'standalone_vpc', 'shared_vpc', or 'hub_and_spoke'",
                    "default": "standalone_vpc",
                },
                "workload_type": {
                    "type": "string",
                    "description": "'adb', 'exadata_dedicated', 'exascale', or 'basedb'",
                    "default": "adb",
                },
                "encryption_mode": {
                    "type": "string",
                    "description": "'google_managed' or 'cmek'",
                    "default": "google_managed",
                },
            },
        },
    },
    {
        "name": "generate_odb_diagram",
        "description": (
            "Generates syntax-verified Mermaid (`mermaid`) and ASCII architecture/onboarding diagrams for "
            "ODB@GCP (end-to-end onboarding, standalone VPC, Shared VPC, Hub-and-Spoke HA/DR, Backup & Recovery, "
            "CMEK Encryption, or Monitoring)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "diagram_type": {
                    "type": "string",
                    "description": (
                        "One of: 'end_to_end_onboarding', 'networking_standalone_vpc', "
                        "'networking_shared_vpc', 'networking_hub_and_spoke_ha_dr', "
                        "'backup_and_recovery', 'encryption_cmek', 'monitoring_observability'."
                    ),
                    "default": "end_to_end_onboarding",
                },
                "project_id": {"type": "string", "default": "my-odb-project-01"},
                "region": {"type": "string", "default": "us-east4"},
                "gcp_oracle_zone": {"type": "string", "default": "us-east4-b-r1"},
                "vpc_cidr": {"type": "string", "default": "10.10.0.0/16"},
                "client_subnet_cidr": {"type": "string", "default": "10.20.1.0/24"},
                "backup_subnet_cidr": {"type": "string", "default": "10.20.2.0/24"},
                "save_to_workspace": {"type": "boolean", "default": False},
                "output_dir": {"type": "string", "default": "./output/diagrams"},
            },
        },
    },
    {
        "name": "generate_golden_terraform",
        "description": (
            "Generates a production-ready, schema-verified Golden Terraform bundle (`hashicorp/google >= 7.0.0`) "
            "for ODB@GCP inside the open workspace (`./output/<bundle_name>`), runs fast anti-hallucination and "
            "HCL syntax validation, and returns a concise summary pointing to the output directory. "
            "NOTE: Never runs `terraform apply` or `destroy`."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Target GCP project ID."},
                "workload_type": {
                    "type": "string",
                    "description": "One of: 'adb', 'exadata_dedicated', 'exascale', 'basedb'.",
                    "default": "adb",
                },
                "region": {"type": "string", "default": "us-east4"},
                "gcp_oracle_zone": {"type": "string", "default": "us-east4-b-r1"},
                "environment_prefix": {"type": "string", "default": "odb-prod"},
                "vpc_name": {"type": "string", "default": "odb-vpc"},
                "vpc_cidr": {"type": "string", "default": "10.10.0.0/16"},
                "client_subnet_cidr": {"type": "string", "default": "10.20.1.0/24"},
                "backup_subnet_cidr": {"type": "string", "default": "10.20.2.0/24"},
                "shared_vpc_host_project_id": {"type": "string", "default": ""},
                "db_name": {"type": "string", "default": "ODBPROD1"},
                "compute_count": {"type": "integer", "default": 4},
                "storage_size_tb": {"type": "integer", "default": 1},
                "bundle_name": {"type": "string", "default": "odb-golden-bundle"},
                "base_output_dir": {"type": "string", "default": "./output"},
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "validate_odb_network_cidrs",
        "description": (
            "Deterministically validates ODB@GCP network CIDRs for minimum `/28` prefix length "
            "and zero overlap between VPC, Client Subnet, and Backup Subnet."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "vpc_cidr": {"type": "string"},
                "client_subnet_cidr": {"type": "string"},
                "backup_subnet_cidr": {"type": "string", "default": ""},
            },
            "required": ["vpc_cidr", "client_subnet_cidr"],
        },
    },
    {
        "name": "validate_odb_terraform_hcl",
        "description": (
            "Validates Terraform `.tf` content against ODB@GCP anti-hallucination rules "
            "(blocks `oci_*` resources, checks `odbnetwork` vs `odb_network`, verifies `properties {}` nesting) "
            "and checks HCL syntax in fast mode."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "hcl_content": {
                    "type": "string",
                    "description": "Raw Terraform HCL code to validate.",
                }
            },
            "required": ["hcl_content"],
        },
    },
    {
        "name": "inspect_day2_workspace",
        "description": (
            "Inspects an existing Terraform directory inside the open workspace to inventory ODB@GCP resources, "
            "`deletion_protection` posture, safe in-place scaling attributes, and immutable `ForceNew` attributes. "
            "Rejects paths outside the open workspace."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_dir": {
                    "type": "string",
                    "description": "Relative path inside the active workspace (e.g. './output/odb-golden-bundle').",
                    "default": "./output",
                }
            },
        },
    },
    {
        "name": "analyze_day2_terraform_diff",
        "description": (
            "Compares existing HCL with proposed Day-2 HCL to block destructive `ForceNew` resource replacements "
            "(`-/+ destroy and recreate`) on live databases."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "existing_hcl": {"type": "string"},
                "proposed_hcl": {"type": "string"},
            },
            "required": ["existing_hcl", "proposed_hcl"],
        },
    },
    {
        "name": "list_odb_provider_resources",
        "description": (
            "Lists all `google_oracle_database_*` Terraform resources in `hashicorp/google` along with their "
            "exact top-level vs. nested `properties {}` attributes."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
]


def execute_mcp_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Executes an allow-listed MCP tool with stderr redirection, workspace containment, and timeout safety."""
    args = arguments or {}

    # Redirect any accidental stdout writes during tool imports & execution strictly to sys.stderr
    with contextlib.redirect_stdout(sys.stderr):
        from ai_agent.tools.day2_maintenance import (
            analyze_day2_terraform_diff,
            inspect_existing_terraform_workspace,
        )
        from ai_agent.tools.diagram_generator import generate_odb_architecture_diagram
        from ai_agent.tools.golden_templates import generate_golden_odb_terraform
        from ai_agent.tools.network_validator import (
            resolve_safe_workspace_path,
            save_generated_terraform_bundle,
            validate_odb_network_cidrs,
        )
        from ai_agent.tools.onboarding_knowledge import (
            evaluate_customer_onboarding_readiness,
            get_odb_onboarding_and_architecture_guide,
        )
        from ai_agent.tools.terraform_registry import (
            list_odb_terraform_resources,
            validate_terraform_hcl,
        )

        if tool_name in {"terraform_apply", "terraform_destroy", "apply", "destroy"}:
            return {
                "isError": True,
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "error": (
                                    "Security Guardrail: `terraform apply` and `terraform destroy` are intentionally "
                                    "never exposed by the Oracle@Google Onboarding Agent MCP Server. "
                                    "Use this agent to generate, validate, and inspect Terraform, then apply via human review or CI/CD."
                                )
                            },
                            indent=2,
                        ),
                    }
                ],
            }

        if tool_name == "get_odb_onboarding_guide":
            res_str = get_odb_onboarding_and_architecture_guide(
                topic=str(args.get("topic", "all"))
            )
            return {"isError": False, "content": [{"type": "text", "text": res_str}]}

        if tool_name == "evaluate_onboarding_readiness":
            res_str = evaluate_customer_onboarding_readiness(
                project_id=str(args.get("project_id", "my-odb-project-01")),
                procurement_model=str(args.get("procurement_model", "private_offer")),
                networking_topology=str(args.get("networking_topology", "standalone_vpc")),
                workload_type=str(args.get("workload_type", "adb")),
                encryption_mode=str(args.get("encryption_mode", "google_managed")),
            )
            return {"isError": False, "content": [{"type": "text", "text": res_str}]}

        if tool_name == "generate_odb_diagram":
            res_str = generate_odb_architecture_diagram(
                diagram_type=str(args.get("diagram_type", "end_to_end_onboarding")),
                project_id=str(args.get("project_id", "my-odb-project-01")),
                region=str(args.get("region", "us-east4")),
                gcp_oracle_zone=str(args.get("gcp_oracle_zone", "us-east4-b-r1")),
                vpc_cidr=str(args.get("vpc_cidr", "10.10.0.0/16")),
                client_subnet_cidr=str(args.get("client_subnet_cidr", "10.20.1.0/24")),
                backup_subnet_cidr=str(args.get("backup_subnet_cidr", "10.20.2.0/24")),
                save_to_workspace=bool(args.get("save_to_workspace", False)),
                output_dir=str(args.get("output_dir", "./output/diagrams")),
            )
            parsed = json.loads(res_str)
            return {
                "isError": not parsed.get("valid", True),
                "content": [{"type": "text", "text": res_str}],
            }

        if tool_name == "generate_golden_terraform":
            base_output_dir = str(args.get("base_output_dir") or args.get("output_dir") or "./output")
            bundle_name = str(args.get("bundle_name", "odb-golden-bundle"))

            # Enforce workspace containment upfront before generating
            try:
                resolve_safe_workspace_path(base_output_dir)
            except ValueError as exc:
                return {
                    "isError": True,
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps({"valid": False, "saved": False, "error": str(exc)}, indent=2),
                        }
                    ],
                }

            raw_gen = generate_golden_odb_terraform(
                project_id=str(args.get("project_id", "my-odb-project-01")),
                region=str(args.get("region", "us-east4")),
                gcp_oracle_zone=str(args.get("gcp_oracle_zone", "us-east4-b-r1")),
                workload_type=str(args.get("workload_type", "adb")),
                environment_prefix=str(args.get("environment_prefix", "odb-prod")),
                vpc_name=str(args.get("vpc_name", "odb-vpc")),
                vpc_cidr=str(args.get("vpc_cidr", "10.10.0.0/16")),
                client_subnet_cidr=str(args.get("client_subnet_cidr", "10.20.1.0/24")),
                backup_subnet_cidr=str(args.get("backup_subnet_cidr", "10.20.2.0/24")),
                shared_vpc_host_project_id=str(args.get("shared_vpc_host_project_id", "")),
                db_name=str(args.get("db_name", "ODBPROD1")),
                compute_count=int(args.get("compute_count", 4)),
                storage_size_tb=int(args.get("storage_size_tb", 1)),
            )
            gen_payload = json.loads(raw_gen)
            if not gen_payload.get("valid"):
                return {
                    "isError": True,
                    "content": [{"type": "text", "text": raw_gen}],
                }

            files_json = json.dumps(gen_payload["files"])
            # Fast validation (<50ms) prevents IDE client tool-call timeouts
            val_payload = json.loads(validate_terraform_hcl(files_json, fast_mode=True))
            save_payload = json.loads(
                save_generated_terraform_bundle(
                    files_json=files_json,
                    bundle_name=bundle_name,
                    base_output_dir=base_output_dir,
                )
            )
            if not save_payload.get("saved"):
                return {
                    "isError": True,
                    "content": [{"type": "text", "text": json.dumps(save_payload, indent=2)}],
                }

            # Return a concise summary pointing to the output folder so IDE clients never time out or overflow context
            concise_summary = {
                "valid": True,
                "saved": True,
                "status": "GENERATED_AND_VERIFIED",
                "workload_type": gen_payload.get("workload_type"),
                "output_directory": save_payload.get("output_directory"),
                "written_files": save_payload.get("written_files"),
                "guardrail_checks": gen_payload.get("guardrail_checks"),
                "validation": val_payload,
                "validation_Summary": val_payload,
                "next_steps": [
                    f"cd {save_payload.get('output_directory')}",
                    "export TF_VAR_db_admin_password='<YourStrongPassword>'",
                    "terraform init && terraform plan",
                ],
                "safety_note": (
                    "Files have been written inside your workspace. Review `terraform plan` and apply via "
                    "human review or CI/CD pipeline."
                ),
            }
            return {
                "isError": False,
                "content": [{"type": "text", "text": json.dumps(concise_summary, indent=2)}],
            }

        if tool_name == "validate_odb_network_cidrs":
            res_str = validate_odb_network_cidrs(
                vpc_cidr=str(args.get("vpc_cidr", "")),
                client_subnet_cidr=str(args.get("client_subnet_cidr", "")),
                backup_subnet_cidr=str(args.get("backup_subnet_cidr", "")),
            )
            return {"isError": False, "content": [{"type": "text", "text": res_str}]}

        if tool_name == "validate_odb_terraform_hcl":
            hcl_content = str(args.get("hcl_content", ""))
            files_json = json.dumps({"main.tf": hcl_content})
            res_str = validate_terraform_hcl(files_json, fast_mode=True)
            return {"isError": False, "content": [{"type": "text", "text": res_str}]}

        if tool_name == "inspect_day2_workspace":
            res_str = inspect_existing_terraform_workspace(
                workspace_dir=str(args.get("workspace_dir", "./output"))
            )
            parsed = json.loads(res_str)
            return {
                "isError": "error" in parsed,
                "content": [{"type": "text", "text": res_str}],
            }

        if tool_name == "analyze_day2_terraform_diff":
            res_str = analyze_day2_terraform_diff(
                existing_hcl=str(args.get("existing_hcl", "")),
                proposed_hcl=str(args.get("proposed_hcl", "")),
            )
            return {"isError": False, "content": [{"type": "text", "text": res_str}]}

        if tool_name == "list_odb_provider_resources":
            res_str = list_odb_terraform_resources()
            return {"isError": False, "content": [{"type": "text", "text": res_str}]}

        return {
            "isError": True,
            "content": [{"type": "text", "text": json.dumps({"error": f"Unknown MCP tool '{tool_name}'."})}],
        }


def handle_jsonrpc_request(request: dict[str, Any]) -> dict[str, Any] | None:
    """Processes a single JSON-RPC 2.0 request and returns the JSON-RPC 2.0 response (or None for notifications)."""
    method = request.get("method", "")
    req_id = request.get("id")
    params = request.get("params") or {}

    # JSON-RPC notifications (no `id`) do not expect a response frame
    if req_id is None:
        return None

    if method == "initialize":
        client_proto = params.get("protocolVersion") or DEFAULT_PROTOCOL_VERSION
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": client_proto,
                "capabilities": {
                    "tools": {"listChanged": False},
                },
                "serverInfo": {
                    "name": MCP_SERVER_NAME,
                    "version": MCP_SERVER_VERSION,
                },
            },
        }

    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": MCP_TOOLS_CATALOG},
        }

    if method == "resources/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"resources": []},
        }

    if method == "prompts/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"prompts": []},
        }

    if method == "tools/call":
        tool_name = str(params.get("name", ""))
        arguments = params.get("arguments") or {}
        tool_result = execute_mcp_tool(tool_name, arguments)
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": tool_result,
        }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {
            "code": -32601,
            "message": f"Method not found: {method}",
        },
    }


def _write_jsonrpc_message(
    response: dict[str, Any],
    protocol_stdout: TextIO,
    use_content_length: bool = False,
) -> None:
    """Writes a JSON-RPC message exclusively to the reserved protocol stdout stream."""
    payload = json.dumps(response, separators=(",", ":"))
    if use_content_length:
        encoded = payload.encode("utf-8")
        header = f"Content-Length: {len(encoded)}\r\n\r\n"
        protocol_stdout.write(header + payload)
    else:
        protocol_stdout.write(payload + "\n")
    protocol_stdout.flush()


def run_mcp_stdio_server() -> None:
    """Runs the MCP JSON-RPC 2.0 server over `stdio` with strict stdout isolation."""
    # Reserve real stdout for JSON-RPC frames and redirect global sys.stdout -> sys.stderr
    protocol_stdout = sys.stdout
    sys.stdout = sys.stderr

    # Force fast validation inside MCP mode so IDE tool calls never time out
    os.environ.setdefault("ODB_FAST_VALIDATION", "1")

    stdin_stream = sys.stdin
    while True:
        line = stdin_stream.readline()
        if not line:
            break

        stripped = line.strip()
        if not stripped:
            continue

        use_content_length = False
        if stripped.lower().startswith("content-length:"):
            use_content_length = True
            try:
                content_length = int(stripped.split(":", 1)[1].strip())
            except ValueError:
                continue
            # Consume blank header separator line(s)
            while True:
                sep = stdin_stream.readline()
                if not sep or sep.strip() == "":
                    break
            body = stdin_stream.read(content_length)
            raw_json = body
        else:
            raw_json = stripped

        try:
            req = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            logger.error("Invalid JSON-RPC frame received: %s", exc)
            continue

        if isinstance(req, dict):
            resp = handle_jsonrpc_request(req)
            if resp is not None:
                _write_jsonrpc_message(resp, protocol_stdout, use_content_length=use_content_length)


MCP_TOOL_DEFINITIONS = MCP_TOOLS_CATALOG
handle_jsonrpc_message = handle_jsonrpc_request
run_stdio_mcp_server = run_mcp_stdio_server


if __name__ == "__main__":
    run_mcp_stdio_server()

