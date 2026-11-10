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
- `odb-onboarding-agent studio`: Launches the Interactive Topology & Digital Twin Streamlit Web Studio (`127.0.0.1:8502` locally, or `127.0.0.1:8080` with Cloud Shell Web Preview proxy flags).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
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
from ai_agent.tools.interactive_diagram import render_standalone_interactive_html
from ai_agent.tools.interactive_workflows import (
    SUPPORTED_HA_DR_TIERS,
    SUPPORTED_NETWORK_GOVERNANCE_MODES,
    SUPPORTED_WORKLOAD_PROFILES,
    manage_onboarding_progress_tracker,
    recommend_odb_architecture_wizard,
    simulate_day2_scaling_what_if,
)
from ai_agent.tools.network_validator import (
    resolve_safe_workspace_path,
    save_generated_terraform_bundle,
)
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
        "Oracle@Google Onboarding Agent — End-to-End Onboarding Lifecycle, Guided Architecture Wizard, "
        "6-Phase Progress Tracker, Interactive Topology Studio, Production Terraform Generator, Day-2 Simulator, and IDE MCP Server."
    ),
    add_completion=False,
)
console = Console()


def _render_tool_traces(turn: AgentTurnResponse) -> None:
    """Renders a Rich table showing all live tools, mapped Guardrail Layer, and 5-Layer Scorecard."""
    if not turn.tool_traces:
        return
    table = Table(
        title="Live Agent Tool & 5-Layer Guardrail Telemetry",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Tool / Check", style="bold green")
    table.add_column("Guardrail Layer", style="cyan")
    table.add_column("Arguments", style="yellow")
    table.add_column("Latency", justify="right", style="magenta")

    for idx, trace in enumerate(turn.tool_traces, start=1):
        table.add_row(
            str(idx),
            trace.tool_name,
            getattr(trace, "guardrail_layer", "") or "Layer 5: Post-Gen & Day-2 Guard",
            json.dumps(trace.arguments),
            f"{trace.duration_ms:.1f} ms",
        )
    console.print(table)
    scorecard = getattr(turn, "guardrail_scorecard", None) or {}
    if scorecard:
        console.print(
            f"[bold green]5-Layer Guardrail Scorecard:[/bold green] "
            f"Status=[bold]{scorecard.get('overall_status', 'VERIFIED')}[/bold] | "
            f"Active Layers={scorecard.get('active_guardrail_layers', 1)}/5 | "
            f"Tool Calls={scorecard.get('total_tool_invocations', len(turn.tool_traces))} | "
            f"Auto-Repairs={scorecard.get('auto_repairs_triggered', 0)} | "
            f"Total Tool Time={scorecard.get('total_duration_ms', 0.0)} ms"
        )


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
        help="Format: 'mermaid', 'ascii', 'both', 'interactive_html', or 'all'.",
    ),
    save_to: Optional[str] = typer.Option(
        None,
        "--save-to",
        help="Optional relative path inside the workspace (e.g., ./output/diagrams/onboarding.md or .html) to save the diagram.",
    ),
    save_html: bool = typer.Option(
        False,
        "--save-html",
        help="Also export a standalone zero-CDN interactive HTML5 topology explorer alongside Markdown.",
    ),
) -> None:
    """Generates syntax-verified Mermaid, ASCII, and standalone HTML5 interactive diagrams for Oracle@Google topologies."""
    payload = json.loads(
        generate_odb_architecture_diagram(
            diagram_type=diagram_type,
            output_format=output_format,
            save_to_file=save_to or "",
            save_interactive_html=save_html,
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
    if payload.get("saved_html_file") and payload.get("saved_html_file") != payload.get("saved_file"):
        console.print(
            f"[bold green]Saved interactive HTML5 topology to:[/bold green] {payload['saved_html_file']}"
        )


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
    layer: str = typer.Option(
        "full_stack",
        "--layer",
        help="Separation-of-Duties layer: full_stack (default), network_only, infra_only, or database_only.",
    ),
    region: str = typer.Option("us-east4", "--region", help="Target GCP region."),
    oracle_zone: str = typer.Option("us-east4-b-r1", "--oracle-zone", help="Target gcp_oracle_zone."),
    vpc_cidr: str = typer.Option("10.10.0.0/16", "--vpc-cidr", help="Customer VPC CIDR."),
    client_cidr: str = typer.Option("10.20.1.0/24", "--client-cidr", help="ODB Client Subnet CIDR (min /28)."),
    backup_cidr: str = typer.Option("10.20.2.0/24", "--backup-cidr", help="ODB Backup Subnet CIDR (min /28)."),
    existing_odb_network: str = typer.Option("", "--existing-odb-network", help="Pre-existing ODB Network resource name (for database_only)."),
    existing_client_subnet: str = typer.Option("", "--existing-client-subnet", help="Pre-existing CLIENT_SUBNET resource name (for database_only)."),
    existing_backup_subnet: str = typer.Option("", "--existing-backup-subnet", help="Pre-existing BACKUP_SUBNET resource name (for database_only)."),
    existing_exadata_infra: str = typer.Option("", "--existing-exadata-infra", help="Pre-existing Exadata Infra / Exascale Vault resource name (for database_only)."),
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
        deployment_layer=layer,
        existing_odb_network=existing_odb_network,
        existing_client_odb_subnet=existing_client_subnet,
        existing_backup_odb_subnet=existing_backup_subnet,
        existing_exadata_infrastructure=existing_exadata_infra,
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
            f"Workload: [bold]{workload}[/bold] | Layer: [bold yellow]{payload.get('deployment_layer')}[/bold yellow] | "
            f"Output Directory: [bold cyan]{save_res.get('output_directory')}[/bold cyan]\n"
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


@app.command("wizard")
def wizard(
    project_id: str = typer.Option(
        "my-odb-project-01",
        "--project-id",
        help="Target GCP project ID.",
    ),
    region: str = typer.Option("us-east4", "--region", help="Target GCP region."),
    oracle_zone: str = typer.Option("us-east4-b-r1", "--oracle-zone", help="Target colocated gcp_oracle_zone."),
    workload_profile: str = typer.Option(
        "autonomous_ai_lakehouse",
        "--workload-profile",
        "-w",
        help="Workload profile: " + ", ".join(SUPPORTED_WORKLOAD_PROFILES),
    ),
    ha_dr_tier: str = typer.Option(
        "regional_ha",
        "--ha-dr-tier",
        help="HA/DR tier: " + ", ".join(SUPPORTED_HA_DR_TIERS),
    ),
    cores: int = typer.Option(8, "--cores", help="Estimated ECPU / OCPU compute cores needed."),
    storage_tb: int = typer.Option(2, "--storage-tb", help="Estimated data storage in TB."),
    network_governance: str = typer.Option(
        "standalone_vpc",
        "--network-governance",
        help="Networking mode: " + ", ".join(SUPPORTED_NETWORK_GOVERNANCE_MODES),
    ),
    encryption: str = typer.Option(
        "google_managed",
        "--encryption",
        help="Encryption compliance: google_managed, gcp_cmek, or oci_vault.",
    ),
    separation_of_duties: str = typer.Option(
        "full_stack",
        "--separation-of-duties",
        help="'full_stack' or 'enterprise_layered'.",
    ),
    generate_bundle: bool = typer.Option(
        False,
        "--generate-bundle",
        help="Also generate and validate the recommended Golden Terraform bundle inside ./output.",
    ),
    save_html: bool = typer.Option(
        False,
        "--save-html",
        help="Also export the recommended Interactive HTML5 Topology Explorer inside ./output/diagrams.",
    ),
    interactive: bool = typer.Option(
        False,
        "--interactive",
        "-i",
        help="Prompt interactively for workload, HA/DR, sizing, and networking choices in the terminal.",
    ),
) -> None:
    """Guided Interactive Architecture Discovery & Sizing Wizard (Part 2 Item 4)."""
    if interactive:
        project_id = typer.prompt("1. Target GCP Project ID", default=project_id)
        workload_profile = typer.prompt(
            f"2. Workload Profile ({'/'.join(SUPPORTED_WORKLOAD_PROFILES)})",
            default=workload_profile,
        )
        ha_dr_tier = typer.prompt(
            f"3. HA/DR Tier ({'/'.join(SUPPORTED_HA_DR_TIERS)})",
            default=ha_dr_tier,
        )
        cores = int(typer.prompt("4. Estimated ECPU / OCPU Cores Needed", default=str(cores)))
        storage_tb = int(typer.prompt("5. Estimated Storage Needed (TB)", default=str(storage_tb)))
        network_governance = typer.prompt(
            f"6. Network Governance ({'/'.join(SUPPORTED_NETWORK_GOVERNANCE_MODES)})",
            default=network_governance,
        )
        encryption = typer.prompt(
            "7. Encryption Compliance (google_managed/gcp_cmek/oci_vault)",
            default=encryption,
        )

    payload = json.loads(
        recommend_odb_architecture_wizard(
            project_id=project_id,
            region=region,
            gcp_oracle_zone=oracle_zone,
            workload_profile=workload_profile,
            ha_dr_tier=ha_dr_tier,
            cpu_cores_needed=cores,
            storage_tb_needed=storage_tb,
            network_governance=network_governance,
            encryption_compliance=encryption,
            separation_of_duties_mode=separation_of_duties,
            generate_artifacts=generate_bundle,
        )
    )
    if not payload.get("valid"):
        console.print_json(data=payload)
        raise typer.Exit(code=1)

    summary = payload.get("wizard_summary", {})
    table = Table(
        title="Oracle@Google Guided Architecture & Sizing Recommendation",
        show_lines=True,
        header_style="bold cyan",
    )
    table.add_column("Dimension", style="bold green")
    table.add_column("Recommended Specification", style="white")
    table.add_row("Recommended ODB Service", f"[bold]{summary.get('recommended_workload_type')}[/bold] — {summary.get('recommended_shape')}")
    table.add_row("Sizing Baseline", f"{summary.get('recommended_compute_count')} Cores (ECPU/OCPU) | {summary.get('recommended_storage_size_tb')} TB Storage")
    table.add_row("Networking & Diagram", f"{summary.get('recommended_networking_topology')} ({summary.get('recommended_diagram_type')})")
    table.add_row("HA / DR Strategy", str(summary.get("dr_strategy")))
    table.add_row("Separation-of-Duties Layers", ", ".join(summary.get("separation_of_duties_layers", [])))
    table.add_row("Terraform Resources", "\n".join(summary.get("terraform_resources", [])))
    console.print(table)

    for note in summary.get("architectural_rationale", []):
        console.print(f"• {note}")

    if payload.get("generated_bundle") and payload["generated_bundle"].get("saved"):
        gb = payload["generated_bundle"]
        console.print(
            Panel.fit(
                f"[bold green]Recommended Golden Terraform Bundle Generated![/bold green]\n"
                f"Output Directory: [bold cyan]{gb.get('output_directory')}[/bold cyan]\n"
                f"Files: {', '.join(gb.get('written_files', []))}",
                border_style="green",
            )
        )

    if save_html and isinstance(payload.get("interactive_spec"), dict):
        diag_dir = resolve_safe_workspace_path("./output/diagrams")
        diag_dir.mkdir(parents=True, exist_ok=True)
        html_file = (diag_dir / f"wizard_{summary.get('recommended_diagram_type', 'topology')}.html").resolve()
        if str(html_file).startswith(str(diag_dir) + os.sep):
            html_file.write_text(
                render_standalone_interactive_html(payload["interactive_spec"]),
                encoding="utf-8",
            )
            console.print(f"[bold green]Saved Interactive HTML5 Topology to:[/bold green] {html_file}")


@app.command("tracker")
def tracker(
    action: str = typer.Option(
        "status",
        "--action",
        "-a",
        help="Tracker action: 'status', 'auto_verify', 'update_phase', or 'reset'.",
    ),
    project_id: str = typer.Option("my-odb-project-01", "--project-id", help="Target GCP project ID."),
    region: str = typer.Option("us-east4", "--region", help="Target GCP region."),
    phase: str = typer.Option("", "--phase", "-p", help="Phase ID for update_phase (phase_1 .. phase_6 or 1 .. 6)."),
    status: str = typer.Option("", "--status", "-s", help="New status for update_phase: completed, in_progress, blocked, or pending."),
    notes: str = typer.Option("", "--notes", "-n", help="Optional phase note or blocker reason."),
    tracker_file: str = typer.Option(
        "./output/onboarding_progress.json",
        "--tracker-file",
        help="Workspace-relative path to persist onboarding tracker state.",
    ),
) -> None:
    """Stateful 6-Phase Onboarding Progress Tracker with Digital Twin auto-verification (Part 2 Item 5)."""
    payload = json.loads(
        manage_onboarding_progress_tracker(
            action=action,
            project_id=project_id,
            region=region,
            phase_id=phase,
            status=status,
            notes=notes,
            tracker_file=tracker_file,
        )
    )
    if not payload.get("valid"):
        console.print_json(data=payload)
        raise typer.Exit(code=1)

    console.print(
        Panel.fit(
            f"[bold cyan]Oracle@Google 6-Phase Onboarding Progress Tracker[/bold cyan]\n"
            f"Project: [bold]{payload.get('project_id')}[/bold] ({payload.get('region')}) | "
            f"Overall Completion: [bold green]{payload.get('completion_pct')}%[/bold green] "
            f"({payload.get('completed_phases')}/{payload.get('total_phases')} phases completed)\n"
            f"State File: [dim]{payload.get('tracker_file')}[/dim]",
            border_style="cyan",
        )
    )
    table = Table(show_lines=True, header_style="bold")
    table.add_column("Phase", style="bold cyan")
    table.add_column("Owner", style="yellow")
    table.add_column("Status")
    table.add_column("Verification Command / Notes")

    for ph in payload.get("phases", []):
        st_val = str(ph.get("status", "pending")).lower()
        if st_val == "completed":
            st_badge = "[bold green]COMPLETED[/bold green]"
        elif st_val == "blocked":
            st_badge = "[bold red]BLOCKED[/bold red]"
        elif st_val == "in_progress":
            st_badge = "[bold yellow]IN PROGRESS[/bold yellow]"
        else:
            st_badge = "[dim]PENDING[/dim]"
        note_str = f"\nNote: {ph.get('notes')}" if ph.get("notes") else ""
        table.add_row(
            str(ph.get("title")),
            str(ph.get("team_owner")).upper(),
            st_badge,
            f"{ph.get('verification_command')}{note_str}",
        )
    console.print(table)


@app.command("simulate-day2")
def simulate_day2(
    workload: str = typer.Option("adb", "--workload", "-w", help="Workload: adb, exadata_dedicated, exascale, or basedb."),
    project_id: str = typer.Option("my-odb-project-01", "--project-id", help="Target GCP project ID."),
    region: str = typer.Option("us-east4", "--region", help="Target GCP region."),
    current_compute: int = typer.Option(4, "--current-compute", help="Current ECPU/OCPU count."),
    proposed_compute: int = typer.Option(8, "--proposed-compute", help="Proposed ECPU/OCPU count."),
    current_storage_tb: int = typer.Option(1, "--current-storage-tb", help="Current storage in TB."),
    proposed_storage_tb: int = typer.Option(2, "--proposed-storage-tb", help="Proposed storage in TB."),
    current_cidr: str = typer.Option("10.20.1.0/24", "--current-cidr", help="Current CLIENT_SUBNET CIDR."),
    proposed_cidr: str = typer.Option("10.20.1.0/24", "--proposed-cidr", help="Proposed CLIENT_SUBNET CIDR (ForceNew if changed)."),
    current_zone: str = typer.Option("us-east4-b-r1", "--current-zone", help="Current gcp_oracle_zone."),
    proposed_zone: str = typer.Option("us-east4-b-r1", "--proposed-zone", help="Proposed gcp_oracle_zone (ForceNew if changed)."),
    deletion_protection: bool = typer.Option(True, "--deletion-protection/--no-deletion-protection", help="Proposed deletion_protection setting."),
    apply_to_bundle: str = typer.Option("", "--apply-to-bundle", help="Optional workspace directory to write day2_simulated_update.tf if safe."),
    save_html: bool = typer.Option(False, "--save-html", help="Export Day-2 Blast-Radius Interactive HTML5 Topology inside ./output/diagrams."),
) -> None:
    """Interactive Day-2 What-If Scaling & ForceNew Simulator (Part 2 Item 6)."""
    payload = json.loads(
        simulate_day2_scaling_what_if(
            workload_type=workload,
            project_id=project_id,
            region=region,
            current_gcp_oracle_zone=current_zone,
            proposed_gcp_oracle_zone=proposed_zone,
            current_client_subnet_cidr=current_cidr,
            proposed_client_subnet_cidr=proposed_cidr,
            current_compute_count=current_compute,
            proposed_compute_count=proposed_compute,
            current_storage_size_tb=current_storage_tb,
            proposed_storage_size_tb=proposed_storage_tb,
            proposed_deletion_protection=deletion_protection,
            apply_to_bundle_dir=apply_to_bundle,
        )
    )
    is_safe = bool(payload.get("safe_day2_change", True))
    border = "green" if is_safe else "red"
    status_str = "[bold green]SAFE ONLINE SCALING (~ update in-place)[/bold green]" if is_safe else "[bold red]CRITICAL FORCENEW HAZARD (-/+ destroy and recreate)[/bold red]"
    console.print(
        Panel.fit(
            f"Day-2 What-If Simulation: {status_str}\n"
            f"Workload: [bold]{payload.get('workload_type')}[/bold] | "
            f"Compute Delta: {payload.get('delta_summary', {}).get('compute_delta'):+d} | "
            f"Storage Delta: {payload.get('delta_summary', {}).get('storage_tb_delta'):+d} TB\n"
            f"Impact: {payload.get('downtime_impact')}",
            border_style=border,
        )
    )
    if payload.get("deletion_protection_warning"):
        console.print(f"[bold yellow]{payload['deletion_protection_warning']}[/bold yellow]")
    if payload.get("save_blocked_reason"):
        console.print(f"[bold red]{payload['save_blocked_reason']}[/bold red]")
    elif payload.get("saved_file"):
        console.print(f"[bold green]Saved safe Day-2 update to:[/bold green] {payload['saved_file']}")

    if save_html and isinstance(payload.get("interactive_spec"), dict):
        diag_dir = resolve_safe_workspace_path("./output/diagrams")
        diag_dir.mkdir(parents=True, exist_ok=True)
        html_file = (diag_dir / "day2_blast_radius_simulation.html").resolve()
        if str(html_file).startswith(str(diag_dir) + os.sep):
            html_file.write_text(
                render_standalone_interactive_html(payload["interactive_spec"]),
                encoding="utf-8",
            )
            console.print(f"[bold green]Saved Day-2 Blast-Radius Interactive HTML5 Topology to:[/bold green] {html_file}")


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
    """Sends a single prompt to the Oracle@Google Onboarding Agent and streams live 5-Layer Guardrail telemetry + answer."""
    config = resolve_llm_config(
        auth_mode=auth_mode,  # type: ignore[arg-type]
        model=model,
        project_id=project_id,
        location=location,
    )
    agent = ODBOnboardingAgent(config)
    with console.status("[bold cyan]Oracle@Google Onboarding Agent reasoning and querying live tools...[/bold cyan]") as status_spinner:
        def _on_live_event(ev: dict) -> None:
            etype = ev.get("event_type")
            if etype == "tool_start":
                status_spinner.update(
                    f"[bold cyan]Running `{ev.get('tool_name')}` ({ev.get('guardrail_layer')})...[/bold cyan]"
                )
            elif etype == "guardrail_verify":
                status_spinner.update(
                    f"[bold green]Post-Gen Compiler Verified ({ev.get('hcl_blocks_inspected', 0)} HCL block(s))...[/bold green]"
                )
            elif etype == "auto_repair":
                status_spinner.update(
                    f"[bold yellow]Auto-Repair Guardrail Self-Healing (Attempt #{ev.get('attempt')})...[/bold yellow]"
                )

        turn = agent.send_message(prompt, on_event=_on_live_event)

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
            f"Capabilities: Onboarding Lifecycle | Architecture Wizard | 6-Phase Tracker | Diagrams | Terraform | Day-2 Simulator\n"
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

        with console.status("[bold cyan]Oracle@Google Onboarding Agent thinking & calling live tools...[/bold cyan]") as status_spinner:
            def _on_live_event(ev: dict) -> None:
                etype = ev.get("event_type")
                if etype == "tool_start":
                    status_spinner.update(
                        f"[bold cyan]Running `{ev.get('tool_name')}` ({ev.get('guardrail_layer')})...[/bold cyan]"
                    )
                elif etype == "guardrail_verify":
                    status_spinner.update(
                        f"[bold green]Post-Gen Compiler Verified ({ev.get('hcl_blocks_inspected', 0)} HCL block(s))...[/bold green]"
                    )

            turn = agent.send_message(user_input, on_event=_on_live_event)

        _render_tool_traces(turn)
        console.print(
            Panel(
                Markdown(turn.text),
                title="[bold green]Oracle@Google Onboarding Agent (5-Layer Guardrails Verified)[/bold green]",
                border_style="green",
            )
        )


@app.command("studio")
def studio(
    port: Optional[int] = typer.Option(
        None,
        "--port",
        "-p",
        help="Localhost port (defaults to 8080 in Google Cloud Shell, or 8502 locally).",
    ),
    cloud_shell: bool = typer.Option(
        False,
        "--cloud-shell",
        help="Enable Google Cloud Shell Web Preview proxy compatibility flags on 127.0.0.1:8080.",
    ),
) -> None:
    """Launches the Interactive Topology, Digital Twin & Golden Terraform Web Studio (bound strictly to 127.0.0.1)."""
    is_cloud_shell = cloud_shell or os.environ.get("CLOUD_SHELL", "").lower() == "true"
    effective_port = port if port is not None else (8080 if is_cloud_shell else 8502)
    web_entry = str((Path(__file__).resolve().parent / "web.py"))

    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        web_entry,
        "--server.address=127.0.0.1",
        f"--server.port={effective_port}",
        "--browser.gatherUsageStats=false",
    ]
    if is_cloud_shell:
        cmd.extend(
            [
                "--server.enableCORS=false",
                "--server.enableXsrfProtection=false",
                "--server.headless=true",
            ]
        )
        console.print(
            Panel.fit(
                f"[bold green]Launching Interactive Studio for Google Cloud Shell Web Preview[/bold green]\n"
                f"Bound safely to [bold]127.0.0.1:{effective_port}[/bold].\n"
                f"Click [bold cyan]Web Preview -> Preview on port {effective_port}[/bold cyan] in the Cloud Shell toolbar.",
                border_style="green",
            )
        )
    else:
        console.print(
            Panel.fit(
                f"[bold green]Launching Interactive Studio on http://127.0.0.1:{effective_port}[/bold green]",
                border_style="green",
            )
        )

    proc = subprocess.run(cmd, check=False)
    raise typer.Exit(code=proc.returncode)


if __name__ == "__main__":
    app()


