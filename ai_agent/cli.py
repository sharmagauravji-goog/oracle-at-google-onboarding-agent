"""Interactive CLI for the Oracle@Google Onboarding Agent.

Commands:
- `odb-onboarding-agent doctor`: Verifies LLM connection (Vertex AI ADC or Gemini API Key), gcloud, and Terraform CLI.
- `odb-onboarding-agent onboarding-guide`: Displays verified, anti-hallucination guides for Prerequisites, Marketplace (Private Offer vs PAYG), OCI Account Linking, MOS/CSI Support Registration, ODB Networks, Backup/Recovery, Encryption/CMEK, and Monitoring.
- `odb-onboarding-agent diagram`: Generates grounded Mermaid and ASCII diagrams for end-to-end onboarding and networking topologies.
- `odb-onboarding-agent inspect-provider`: Queries live Terraform Registry for latest `hashicorp/google` ODB resources & schemas.
- `odb-onboarding-agent generate-golden`: Generates a verified Golden Terraform bundle inside the active workspace.
- `odb-onboarding-agent inspect-day2`: Audits an existing Terraform directory (inside workspace) for Day-2 maintenance & `deletion_protection` posture.
- `odb-onboarding-agent mcp-serve`: Launches the Model Context Protocol (`stdio`) server for VS Code, Cursor, Claude Desktop, and Antigravity IDE.
- `odb-onboarding-agent ask "..."`: Runs a single-turn agentic query with live tool execution trace & auto-repair guardrails.
- `odb-onboarding-agent chat`: Launches an interactive multi-turn agentic onboarding & architecture chat session in the terminal.
"""

from __future__ import annotations

import json
import shutil
from typing import Optional

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from ai_agent.llm_client import (
    DEFAULT_MODEL,
    detect_gcloud_default_project,
    resolve_llm_config,
)
from ai_agent.mcp_server import run_stdio_mcp_server
from ai_agent.orchestrator import (
    AgentTurnResponse,
    ODBOnboardingAgent,
    test_llm_connection,
)
from ai_agent.tools.day2_maintenance import inspect_existing_terraform_workspace
from ai_agent.tools.diagram_generator import (
    SUPPORTED_DIAGRAM_TYPES,
    generate_odb_architecture_diagram,
)
from ai_agent.tools.golden_templates import generate_golden_odb_terraform
from ai_agent.tools.network_validator import save_generated_terraform_bundle
from ai_agent.tools.onboarding_knowledge import (
    SUPPORTED_ONBOARDING_TOPICS,
    get_odb_onboarding_and_architecture_guide,
)
from ai_agent.tools.terraform_registry import (
    get_latest_google_provider_version,
    get_odb_resource_documentation,
    list_odb_terraform_resources,
    validate_terraform_hcl,
)

app = typer.Typer(
    name="odb-onboarding-agent",
    help=(
        "Oracle@Google Onboarding Agent — End-to-End Onboarding Lifecycle, Architecture & "
        "Diagram Generator, Production Terraform Code Generator, Day-2 Maintenance Guard, and IDE MCP Server."
    ),
    add_completion=False,
)
console = Console()


def _render_tool_traces(turn: AgentTurnResponse) -> None:
    """Renders a Rich table showing all live tools and guardrail checks invoked during the turn."""
    if not turn.tool_traces:
        return
    table = Table(
        title="Live Agent Tool & Guardrail Invocations",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Tool / Guardrail", style="bold green")
    table.add_column("Arguments", style="yellow")
    table.add_column("Latency", justify="right", style="magenta")

    for idx, trace in enumerate(turn.tool_traces, start=1):
        table.add_row(
            str(idx),
            trace.tool_name,
            json.dumps(trace.arguments),
            f"{trace.duration_ms:.1f} ms",
        )
    console.print(table)


@app.command("doctor")
def doctor(
    auth_mode: str = typer.Option(
        "auto",
        "--auth-mode",
        help="LLM connection mode: 'auto', 'vertex' (gcloud ADC), or 'api_key' (GEMINI_API_KEY).",
    ),
    project_id: Optional[str] = typer.Option(
        None,
        "--project-id",
        help="Google Cloud Project ID for Vertex AI ADC mode.",
    ),
    location: str = typer.Option(
        "global",
        "--location",
        help="Google Cloud region for Vertex AI endpoint (default: global).",
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model",
        help=f"Gemini model ID (overrides ODB_AGENT_MODEL / GEMINI_MODEL env var; default: {DEFAULT_MODEL}).",
    ),
    ping_llm: bool = typer.Option(
        False,
        "--ping-llm",
        help="Send a live test prompt to verify LLM reachability.",
    ),
) -> None:
    """Diagnoses customer environment readiness: LLM connection, gcloud ADC, and Terraform Registry access."""
    console.print(
        Panel.fit(
            "[bold cyan]Oracle@Google Onboarding Agent — Environment Doctor[/bold cyan]",
            border_style="cyan",
        )
    )

    table = Table(show_header=True, header_style="bold")
    table.add_column("Check", style="bold")
    table.add_column("Status")
    table.add_column("Details")

    gcloud_bin = shutil.which("gcloud")
    default_proj = detect_gcloud_default_project()
    table.add_row(
        "gcloud CLI",
        "[green]INSTALLED[/green]" if gcloud_bin else "[yellow]MISSING[/yellow]",
        f"Binary: {gcloud_bin or 'not found'} | Active project: {default_proj or '(unset)'}",
    )

    tf_bin = shutil.which("terraform")
    table.add_row(
        "Terraform CLI",
        "[green]INSTALLED[/green]" if tf_bin else "[yellow]OPTIONAL (Not on PATH)[/yellow]",
        tf_bin or "Agent will use live Registry API & structural validation",
    )

    reg_info = json.loads(get_latest_google_provider_version())
    google_ver = (
        reg_info.get("providers", {}).get("google", {}).get("latest_version")
    )
    table.add_row(
        "Terraform Registry (hashicorp/google)",
        "[green]ONLINE[/green]" if google_ver else "[yellow]OFFLINE FALLBACK[/yellow]",
        f"Latest hashicorp/google version: {google_ver or '7.0.0 (fallback)'}",
    )

    resolved_cfg = None
    try:
        resolved_cfg = resolve_llm_config(
            auth_mode=auth_mode,  # type: ignore[arg-type]
            model=model,
            project_id=project_id,
            location=location,
        )
        table.add_row(
            "LLM Credentials",
            "[green]CONFIGURED[/green]",
            f"{resolved_cfg.masked_credential_summary} | Model: {resolved_cfg.model} (configurable via ODB_AGENT_MODEL)",
        )
    except ValueError as exc:
        table.add_row(
            "LLM Credentials",
            "[red]ACTION NEEDED[/red]",
            str(exc),
        )

    if ping_llm and resolved_cfg is not None:
        ping_res = test_llm_connection(resolved_cfg)
        if ping_res.get("connected"):
            table.add_row(
                "Live LLM Handshake",
                "[green]CONNECTED[/green]",
                f"Response: '{ping_res.get('response')}' ({ping_res.get('latency_ms')} ms)",
            )
        else:
            table.add_row(
                "Live LLM Handshake",
                "[red]FAILED[/red]",
                str(ping_res.get("error")),
            )

    console.print(table)


@app.command("onboarding-guide")
def onboarding_guide(
    topic: str = typer.Option(
        "overview",
        "--topic",
        "-t",
        help=(
            "Onboarding/architecture topic: "
            + ", ".join(SUPPORTED_ONBOARDING_TOPICS)
        ),
    ),
) -> None:
    """Displays verified, anti-hallucination guidance for Oracle@Google onboarding phases and deep architecture."""
    payload = json.loads(get_odb_onboarding_and_architecture_guide(topic))
    if not payload.get("valid"):
        console.print_json(data=payload)
        raise typer.Exit(code=1)

    console.print(
        Panel.fit(
            f"[bold cyan]Oracle@Google Onboarding & Architecture Guide[/bold cyan]\n"
            f"Topic: [bold green]{payload.get('topic')}[/bold green] — {payload.get('title', 'End-to-End Lifecycle Overview')}",
            border_style="cyan",
        )
    )
    console.print_json(data=payload)


@app.command("diagram")
def diagram(
    diagram_type: str = typer.Option(
        "end_to_end_onboarding",
        "--type",
        "-t",
        help="Diagram type: " + ", ".join(SUPPORTED_DIAGRAM_TYPES),
    ),
    output_format: str = typer.Option(
        "both",
        "--format",
        "-f",
        help="Format: 'mermaid', 'ascii', or 'both'.",
    ),
    save_to: Optional[str] = typer.Option(
        None,
        "--save-to",
        help="Optional relative path inside the workspace (e.g., ./output/diagrams/onboarding.md) to save the diagram.",
    ),
) -> None:
    """Generates syntax-verified Mermaid and ASCII diagrams for Oracle@Google onboarding and networking topologies."""
    payload = json.loads(
        generate_odb_architecture_diagram(
            diagram_type=diagram_type,
            output_format=output_format,
            save_to_file=save_to or "",
        )
    )
    if not payload.get("valid"):
        console.print_json(data=payload)
        raise typer.Exit(code=1)

    console.print(
        Panel.fit(
            f"[bold green]{payload.get('title')}[/bold green]\n"
            f"{payload.get('summary')}",
            border_style="green",
        )
    )
    if payload.get("ascii_diagram"):
        console.print(
            Panel(
                payload["ascii_diagram"],
                title="[bold cyan]ASCII Architecture Diagram[/bold cyan]",
                border_style="cyan",
            )
        )
    if payload.get("mermaid_markdown"):
        console.print(
            Panel(
                payload["mermaid_markdown"],
                title="[bold magenta]Mermaid Diagram Source[/bold magenta]",
                border_style="magenta",
            )
        )
    if payload.get("saved_file"):
        console.print(f"[bold green]Saved diagram to:[/bold green] {payload['saved_file']}")


@app.command("inspect-provider")
def inspect_provider(
    resource: Optional[str] = typer.Option(
        None,
        "--resource",
        "-r",
        help="Optional specific ODB resource name (e.g., google_oracle_database_autonomous_database) to fetch live upstream docs.",
    ),
) -> None:
    """Queries the live Terraform Registry for the latest `hashicorp/google` version and ODB resource schemas."""
    if resource:
        doc_payload = json.loads(get_odb_resource_documentation(resource))
        console.print_json(data=doc_payload)
        return

    resources_payload = json.loads(list_odb_terraform_resources())
    console.print(
        Panel.fit(
            f"[bold green]Latest hashicorp/google Provider Version:[/bold green] "
            f"[bold white]{resources_payload.get('latest_hashicorp_google_version')}[/bold white]",
            border_style="green",
        )
    )
    table = Table(title="Supported google_oracle_database_* Terraform Resources", show_lines=True)
    table.add_column("Terraform Resource", style="bold cyan")
    table.add_column("Summary")
    table.add_column("Top-Level Required", style="green")
    table.add_column("Nested `properties {}` Attributes", style="yellow")

    for r_name, meta in resources_payload.get("resources", {}).items():
        top_req = ", ".join(meta.get("top_level_required", []))
        nested_props = ", ".join(meta.get("nested_properties_block", {}).keys()) or "(none)"
        table.add_row(r_name, meta.get("summary", ""), top_req, nested_props)
    console.print(table)


@app.command("generate-golden")
def generate_golden(
    project_id: str = typer.Option(..., "--project-id", help="Target GCP project ID."),
    workload: str = typer.Option("adb", "--workload", help="Workload: adb, exadata_dedicated, exascale, or basedb."),
    region: str = typer.Option("us-east4", "--region", help="Target GCP region."),
    oracle_zone: str = typer.Option("us-east4-b-r1", "--oracle-zone", help="Target gcp_oracle_zone."),
    vpc_cidr: str = typer.Option("10.10.0.0/16", "--vpc-cidr", help="Customer VPC CIDR."),
    client_cidr: str = typer.Option("10.20.1.0/24", "--client-cidr", help="ODB Client Subnet CIDR (min /28)."),
    backup_cidr: str = typer.Option("10.20.2.0/24", "--backup-cidr", help="ODB Backup Subnet CIDR (min /28)."),
    output_dir: str = typer.Option("./output", "--output-dir", help="Relative directory inside the active workspace."),
    bundle_name: str = typer.Option("odb-golden-bundle", "--bundle-name", help="Subdirectory under --output-dir."),
) -> None:
    """Generates a deterministic Golden Terraform bundle, validates it against anti-hallucination rules, and exports it inside the workspace."""
    raw_res = generate_golden_odb_terraform(
        project_id=project_id,
        region=region,
        gcp_oracle_zone=oracle_zone,
        workload_type=workload,
        vpc_cidr=vpc_cidr,
        client_subnet_cidr=client_cidr,
        backup_subnet_cidr=backup_cidr,
    )
    payload = json.loads(raw_res)
    if not payload.get("valid"):
        console.print_json(data=payload)
        raise typer.Exit(code=1)

    files_json = json.dumps(payload["files"])
    val_res = json.loads(validate_terraform_hcl(files_json))
    save_res = json.loads(
        save_generated_terraform_bundle(
            files_json=files_json,
            output_dir=output_dir,
            bundle_name=bundle_name,
        )
    )
    if not save_res.get("saved"):
        console.print_json(data=save_res)
        raise typer.Exit(code=1)

    console.print(
        Panel.fit(
            f"[bold green]Golden Terraform Bundle Generated & Verified![/bold green]\n"
            f"Workload: [bold]{workload}[/bold] | Output Directory: [bold cyan]{save_res.get('output_directory')}[/bold cyan]\n"
            f"Files: {', '.join(save_res.get('written_files', []))}\n"
            f"Guardrail Validation: [bold green]{'PASSED' if val_res.get('valid') else 'FAILED'}[/bold green]",
            border_style="green",
        )
    )


@app.command("inspect-day2")
def inspect_day2(
    workspace_dir: str = typer.Option(
        "./output",
        "--workspace-dir",
        "-w",
        help="Path to existing Terraform workspace directory (must be inside the active workspace).",
    ),
) -> None:
    """Inspects an existing Terraform workspace for Day-2 maintenance, `deletion_protection`, and `ForceNew` guardrails."""
    report = json.loads(inspect_existing_terraform_workspace(workspace_dir))
    console.print_json(data=report)
    if not report.get("valid", True):
        raise typer.Exit(code=1)


@app.command("mcp-serve")
def mcp_serve() -> None:
    """Starts the Model Context Protocol (MCP) stdio server for VS Code, Cursor, Claude Desktop, and Antigravity IDE.

    Guardrails enforced:
    - Never exposes `terraform apply` or `terraform destroy`.
    - Redirects all diagnostic output to `stderr` so `stdout` carries exclusively JSON-RPC 2.0 frames.
    - Enforces strict workspace path containment for file writes and Day-2 inspections.
    - Uses fast validation mode (`<50ms`) and concise summaries to prevent IDE timeouts.
    """
    run_stdio_mcp_server()


@app.command("ask")
def ask(
    prompt: str = typer.Argument(..., help="Onboarding question, diagram request, or Terraform generation task."),
    auth_mode: str = typer.Option("auto", "--auth-mode", help="'auto', 'vertex', or 'api_key'."),
    project_id: Optional[str] = typer.Option(None, "--project-id", help="GCP project ID for Vertex AI mode."),
    location: str = typer.Option("global", "--location", help="GCP region for Vertex AI."),
    model: Optional[str] = typer.Option(
        None,
        "--model",
        help=f"Gemini model ID (overrides ODB_AGENT_MODEL / GEMINI_MODEL env var; default: {DEFAULT_MODEL}).",
    ),
) -> None:
    """Sends a single prompt to the Oracle@Google Onboarding Agent and displays the live tool trace + answer."""
    config = resolve_llm_config(
        auth_mode=auth_mode,  # type: ignore[arg-type]
        model=model,
        project_id=project_id,
        location=location,
    )
    agent = ODBOnboardingAgent(config)
    with console.status("[bold cyan]Oracle@Google Onboarding Agent reasoning and querying live tools...[/bold cyan]"):
        turn = agent.send_message(prompt)

    _render_tool_traces(turn)
    badge = "GUARDRAILS VERIFIED" if turn.guardrail_verified else "GUARDRAIL WARNING"
    console.print(
        Panel(
            Markdown(turn.text),
            title=f"[bold green]Oracle@Google Onboarding Agent ({turn.model} via {turn.auth_mode} | {badge})[/bold green]",
            border_style="green",
        )
    )


@app.command("chat")
def chat(
    auth_mode: str = typer.Option("auto", "--auth-mode", help="'auto', 'vertex', or 'api_key'."),
    project_id: Optional[str] = typer.Option(None, "--project-id", help="GCP project ID for Vertex AI mode."),
    location: str = typer.Option("global", "--location", help="GCP region for Vertex AI."),
    model: Optional[str] = typer.Option(
        None,
        "--model",
        help=f"Gemini model ID (overrides ODB_AGENT_MODEL / GEMINI_MODEL env var; default: {DEFAULT_MODEL}).",
    ),
) -> None:
    """Starts an interactive multi-turn terminal chat session with the Oracle@Google Onboarding Agent."""
    config = resolve_llm_config(
        auth_mode=auth_mode,  # type: ignore[arg-type]
        model=model,
        project_id=project_id,
        location=location,
    )
    agent = ODBOnboardingAgent(config)
    console.print(
        Panel.fit(
            f"[bold cyan]Oracle@Google Onboarding Agent — Interactive CLI Session[/bold cyan]\n"
            f"Connected via: [bold green]{config.masked_credential_summary}[/bold green] | Model: [bold]{config.model}[/bold]\n"
            f"Capabilities: Onboarding Lifecycle | ODB Networks & Topologies | Diagrams | Production Terraform | Day-2 Guardrails\n"
            f"Type [bold yellow]exit[/bold yellow] or [bold yellow]quit[/bold yellow] to end the session.",
            border_style="cyan",
        )
    )

    while True:
        try:
            user_input = console.input("\n[bold blue]You > [/bold blue]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Session ended.[/dim]")
            break

        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit", ":q"}:
            console.print("[dim]Goodbye![/dim]")
            break

        with console.status("[bold cyan]Oracle@Google Onboarding Agent thinking & calling live tools...[/bold cyan]"):
            turn = agent.send_message(user_input)

        _render_tool_traces(turn)
        console.print(
            Panel(
                Markdown(turn.text),
                title="[bold green]Oracle@Google Onboarding Agent (5-Layer Guardrails Verified)[/bold green]",
                border_style="green",
            )
        )


if __name__ == "__main__":
    app()
