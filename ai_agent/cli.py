"""Interactive CLI for the Oracle Database@Google Cloud AI Architect Agent.

Commands:
- `odb-ai-agent doctor`: Verifies LLM connection (Vertex AI ADC or Gemini API Key), gcloud, and Terraform CLI.
- `odb-ai-agent inspect-provider`: Queries live Terraform Registry for latest `hashicorp/google` ODB resources.
- `odb-ai-agent ask "..."`: Runs a single-turn agentic query with live tool execution trace.
- `odb-ai-agent chat`: Launches an interactive multi-turn agentic chat session in the terminal.
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
from ai_agent.orchestrator import (
    AgentTurnResponse,
    ODBArchitectAgent,
    test_llm_connection,
)
from ai_agent.tools.terraform_registry import (
    get_latest_google_provider_version,
    get_odb_resource_documentation,
    list_odb_terraform_resources,
)

app = typer.Typer(
    name="odb-ai-agent",
    help="LLM-Powered AI Architect Agent for Oracle Database@Google Cloud (Live Docs, ODB API & Terraform Provider Discovery).",
    add_completion=False,
)
console = Console()


def _render_tool_traces(turn: AgentTurnResponse) -> None:
    """Renders a Rich table showing all live tools invoked by the LLM during the turn."""
    if not turn.tool_traces:
        return
    table = Table(
        title="Live Agent Tool Invocations",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Tool Name", style="bold green")
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
        help="Google Cloud region for Vertex AI endpoint.",
    ),
    model: str = typer.Option(
        DEFAULT_MODEL,
        "--model",
        help="Gemini model ID (default: gemini-3.8-flash).",
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
            "[bold cyan]Oracle Database@Google Cloud AI Agent — Environment Doctor[/bold cyan]",
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

    # Check live Terraform Registry
    reg_info = json.loads(get_latest_google_provider_version())
    google_ver = (
        reg_info.get("providers", {}).get("google", {}).get("latest_version")
    )
    table.add_row(
        "Terraform Registry (hashicorp/google)",
        "[green]ONLINE[/green]" if google_ver else "[yellow]OFFLINE FALLBACK[/yellow]",
        f"Latest hashicorp/google version: {google_ver or '7.0.0 (fallback)'}",
    )

    # Check LLM configuration
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
            f"{resolved_cfg.masked_credential_summary} | Model: {resolved_cfg.model}",
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
    table.add_column("Key Schema Arguments", style="yellow")

    for r_name, meta in resources_payload.get("resources", {}).items():
        table.add_row(r_name, meta.get("summary", ""), meta.get("key_arguments", ""))
    console.print(table)


@app.command("ask")
def ask(
    prompt: str = typer.Argument(..., help="Question or Terraform generation task for the AI Agent."),
    auth_mode: str = typer.Option("auto", "--auth-mode", help="'auto', 'vertex', or 'api_key'."),
    project_id: Optional[str] = typer.Option(None, "--project-id", help="GCP project ID for Vertex AI mode."),
    location: str = typer.Option("global", "--location", help="GCP region for Vertex AI."),
    model: str = typer.Option(DEFAULT_MODEL, "--model", help="Gemini model ID."),
) -> None:
    """Sends a single prompt to the LLM Architect Agent and displays the live tool trace + answer."""
    config = resolve_llm_config(
        auth_mode=auth_mode,  # type: ignore[arg-type]
        model=model,
        project_id=project_id,
        location=location,
    )
    agent = ODBArchitectAgent(config)
    with console.status("[bold cyan]Agent reasoning and querying live tools...[/bold cyan]"):
        turn = agent.send_message(prompt)

    _render_tool_traces(turn)
    console.print(
        Panel(
            Markdown(turn.text),
            title=f"[bold green]ODB@GCP AI Agent ({turn.model} via {turn.auth_mode})[/bold green]",
            border_style="green",
        )
    )


@app.command("chat")
def chat(
    auth_mode: str = typer.Option("auto", "--auth-mode", help="'auto', 'vertex', or 'api_key'."),
    project_id: Optional[str] = typer.Option(None, "--project-id", help="GCP project ID for Vertex AI mode."),
    location: str = typer.Option("global", "--location", help="GCP region for Vertex AI."),
    model: str = typer.Option(DEFAULT_MODEL, "--model", help="Gemini model ID."),
) -> None:
    """Starts an interactive multi-turn terminal chat session with the ODB@GCP AI Architect Agent."""
    config = resolve_llm_config(
        auth_mode=auth_mode,  # type: ignore[arg-type]
        model=model,
        project_id=project_id,
        location=location,
    )
    agent = ODBArchitectAgent(config)
    console.print(
        Panel.fit(
            f"[bold cyan]Oracle Database@Google Cloud — Interactive AI Architect Agent[/bold cyan]\n"
            f"Connected via: [bold green]{config.masked_credential_summary}[/bold green] | Model: [bold]{config.model}[/bold]\n"
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

        with console.status("[bold cyan]Agent thinking & calling live tools...[/bold cyan]"):
            turn = agent.send_message(user_input)

        _render_tool_traces(turn)
        console.print(
            Panel(
                Markdown(turn.text),
                title="[bold green]ODB@GCP AI Architect[/bold green]",
                border_style="green",
            )
        )


if __name__ == "__main__":
    app()
