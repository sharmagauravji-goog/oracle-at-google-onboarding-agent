"""Streamlit Web Studio for the Oracle@Google Onboarding Agent.

Run locally bound to localhost:
    streamlit run ai_agent/web.py --server.address=127.0.0.1 --server.port=8502
Or via the CLI helper (auto-configures port 8080 & WebSocket proxy flags in Google Cloud Shell):
    odb-onboarding-agent studio [--cloud-shell]
"""

from __future__ import annotations

import json
import os
from typing import Any

import streamlit as st

from ai_agent.llm_client import (
    DEFAULT_MODEL,
    SUPPORTED_MODELS,
    detect_gcloud_default_project,
    resolve_llm_config,
)
from ai_agent.orchestrator import (
    ODBOnboardingAgent,
    test_llm_connection,
)
from ai_agent.tools.day2_maintenance import (
    analyze_day2_terraform_diff,
    inspect_existing_terraform_workspace,
)
from ai_agent.tools.diagram_generator import (
    SUPPORTED_DIAGRAM_TYPES,
    generate_odb_architecture_diagram,
)
from ai_agent.tools.golden_templates import generate_golden_odb_terraform
from ai_agent.tools.interactive_diagram import (
    INTERACTIVE_DIAGRAM_CSS,
    INTERACTIVE_DIAGRAM_HTML,
    INTERACTIVE_DIAGRAM_JS,
    build_day2_blast_radius_overlays,
    build_interactive_diagram_spec,
    build_readiness_node_overlays,
    render_standalone_interactive_html,
)
from ai_agent.tools.interactive_workflows import (
    SUPPORTED_HA_DR_TIERS,
    SUPPORTED_NETWORK_GOVERNANCE_MODES,
    SUPPORTED_WORKLOAD_PROFILES,
    build_guardrail_telemetry_summary,
    manage_onboarding_progress_tracker,
    recommend_odb_architecture_wizard,
    simulate_day2_scaling_what_if,
)
from ai_agent.tools.network_validator import (
    save_generated_terraform_bundle,
    validate_odb_network_cidrs,
)
from ai_agent.tools.odb_live_discovery import (
    check_live_vpc_subnet_overlaps,
    discover_live_odb_shapes_and_versions,
    verify_live_onboarding_and_iam_readiness,
)
from ai_agent.tools.onboarding_knowledge import (
    SUPPORTED_ONBOARDING_TOPICS,
    evaluate_customer_onboarding_readiness,
    get_odb_onboarding_and_architecture_guide,
)
from ai_agent.tools.terraform_registry import (
    EXACT_ODB_RESOURCE_SCHEMAS,
    get_latest_google_provider_version,
    get_odb_resource_documentation,
    validate_terraform_hcl,
)

# Register Streamlit Custom Component v2 once at module import time
_ODB_INTERACTIVE_TOPOLOGY = st.components.v2.component(
    "odb_interactive_topology",
    html=INTERACTIVE_DIAGRAM_HTML,
    css=INTERACTIVE_DIAGRAM_CSS,
    js=INTERACTIVE_DIAGRAM_JS,
)


def _init_session_state() -> None:
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "agent_instance" not in st.session_state:
        st.session_state.agent_instance = None
    if "agent_config_key" not in st.session_state:
        st.session_state.agent_config_key = ""
    if "latest_checklist_readiness" not in st.session_state:
        st.session_state.latest_checklist_readiness = ""
    if "latest_live_readiness" not in st.session_state:
        st.session_state.latest_live_readiness = ""
    if "latest_subnet_overlap" not in st.session_state:
        st.session_state.latest_subnet_overlap = ""
    if "latest_day2_diff" not in st.session_state:
        st.session_state.latest_day2_diff = ""
    if "latest_tracker_payload" not in st.session_state:
        st.session_state.latest_tracker_payload = None
    if "latest_wizard_payload" not in st.session_state:
        st.session_state.latest_wizard_payload = None
    if "latest_day2_simulation" not in st.session_state:
        st.session_state.latest_day2_simulation = None


def _sync_blueprint_to_golden_terraform(bp: dict[str, Any]) -> dict[str, Any]:
    """Validates edited canvas blueprint parameters and writes a Golden Terraform bundle in `./output`."""
    proj = str(bp.get("project_id") or "my-odb-project-01").strip()
    reg = str(bp.get("region") or "us-east4").strip()
    ozone = str(bp.get("gcp_oracle_zone") or f"{reg}-b-r1").strip()
    v_cidr = str(bp.get("vpc_cidr") or "10.10.0.0/16").strip()
    c_cidr = str(bp.get("client_subnet_cidr") or "10.20.1.0/24").strip()
    b_cidr = str(bp.get("backup_subnet_cidr") or "10.20.2.0/24").strip()
    wkl = str(bp.get("workload_type") or "adb").strip().lower()
    dlayer = str(bp.get("deployment_layer") or "full_stack").strip().lower()
    cpus = int(bp.get("compute_count") or 4)
    tbs = int(bp.get("storage_size_tb") or 1)

    cidr_res = json.loads(
        validate_odb_network_cidrs(
            vpc_cidr=v_cidr,
            client_subnet_cidr=c_cidr,
            backup_subnet_cidr=b_cidr,
        )
    )
    if not cidr_res.get("valid"):
        return {
            "valid": False,
            "error": "; ".join(cidr_res.get("errors", ["CIDR validation failed."])),
        }

    gen_res = json.loads(
        generate_golden_odb_terraform(
            project_id=proj,
            region=reg,
            gcp_oracle_zone=ozone,
            workload_type=wkl,
            vpc_cidr=v_cidr,
            client_subnet_cidr=c_cidr,
            backup_subnet_cidr=b_cidr,
            compute_count=cpus,
            storage_size_tb=tbs,
            deployment_layer=dlayer,
        )
    )
    if not gen_res.get("valid"):
        return {
            "valid": False,
            "error": str(gen_res.get("error", "Golden Terraform generation failed.")),
        }

    files_map: dict[str, str] = gen_res.get("files", {})
    val_res = json.loads(validate_terraform_hcl(json.dumps(files_map), fast_mode=True))
    bundle_name = f"blueprint-{wkl}-{dlayer}".replace("_", "-")
    save_res = json.loads(
        save_generated_terraform_bundle(
            files_json=json.dumps(files_map),
            bundle_name=bundle_name,
            base_output_dir="./output",
        )
    )
    return {
        "valid": bool(val_res.get("valid", True)) and bool(save_res.get("saved")),
        "bundle_dir": save_res.get("bundle_dir", f"./output/{bundle_name}"),
        "written_files": save_res.get("written_files", []),
        "files": files_map,
        "deployment_layer": dlayer,
        "workload_type": wkl,
        "validation": val_res,
        "error": save_res.get("error", ""),
    }


def render_interactive_odb_diagram(spec: dict[str, Any], *, key: str) -> None:
    """Renders the CCv2 interactive SVG topology canvas and handles bidirectional Blueprint -> Terraform sync."""
    comp_result = _ODB_INTERACTIVE_TOPOLOGY(
        key=key,
        data={"spec": spec, "is_streamlit": True},
        width="stretch",
        on_blueprint_change=lambda: None,
        on_sync_terraform_change=lambda: None,
    )

    live_bp = getattr(comp_result, "blueprint", None)
    if isinstance(live_bp, dict) and live_bp:
        st.session_state[f"{key}_blueprint"] = dict(live_bp)

    sync_req = getattr(comp_result, "sync_terraform", None)
    if isinstance(sync_req, dict) and sync_req:
        st.session_state[f"{key}_synced_bundle"] = _sync_blueprint_to_golden_terraform(dict(sync_req))

    synced = st.session_state.get(f"{key}_synced_bundle")
    if isinstance(synced, dict):
        if synced.get("valid"):
            st.success(
                f"Blueprint synced to Golden Terraform (`{synced.get('workload_type')}` • `{synced.get('deployment_layer')}`) "
                f"in `{synced.get('bundle_dir')}` — HCL & anti-hallucination guardrails verified!"
            )
            files_dict = synced.get("files", {})
            if isinstance(files_dict, dict) and files_dict:
                with st.expander("Inspect Generated Golden Terraform Files (Synced from Blueprint Canvas)", expanded=False):
                    file_tabs = st.tabs(list(files_dict.keys()))
                    for f_tab, (fname, fcontent) in zip(file_tabs, files_dict.items()):
                        with f_tab:
                            st.code(fcontent, language="hcl")
        else:
            st.error(f"Blueprint Sync Guardrail Blocked: {synced.get('error', 'Validation error')}")


def _render_guardrail_scorecard(scorecard: dict[str, Any]) -> None:
    """Renders the 5-Layer Guardrail Telemetry Scorecard (Part 2 Item 7)."""
    if not isinstance(scorecard, dict) or not scorecard.get("layers"):
        return
    status_badge = scorecard.get("overall_status", "VERIFIED")
    total_ms = scorecard.get("total_duration_ms", 0.0)
    active_layers = scorecard.get("active_guardrail_layers", 1)
    repairs = scorecard.get("auto_repairs_triggered", 0)
    st.caption(
        f"**5-Layer Guardrail Telemetry Scorecard:** `{status_badge}` • "
        f"`{active_layers}/5` Guardrail Layers Active • "
        f"`{scorecard.get('total_tool_invocations', 0)}` Tool Invocations (`{total_ms} ms`) • "
        f"`{repairs}` Compiler Auto-Repairs"
    )
    cols = st.columns(5)
    for col, lyr in zip(cols, scorecard["layers"]):
        inv = int(lyr.get("invocations", 0))
        st_val = lyr.get("status", "standby")
        marker = "VERIFIED" if (inv > 0 or st_val == "verified") else "STANDBY"
        col.markdown(
            f"**{lyr['title'].split(':')[0]}**\n\n"
            f"`{marker}` ({inv} call{'s' if inv != 1 else ''}, {lyr.get('duration_ms', 0.0)} ms)"
        )


def _extract_chat_diagram_specs(traces: list[dict[str, Any]], default_project: str) -> list[dict[str, Any]]:
    """Builds interactive topology specs for diagram, wizard, or Day-2 simulation tool calls in a chat turn."""
    specs: list[dict[str, Any]] = []
    overlays = build_readiness_node_overlays(
        live_readiness_json=st.session_state.get("latest_live_readiness", ""),
        checklist_readiness_json=st.session_state.get("latest_checklist_readiness", ""),
        live_subnet_overlap_json=st.session_state.get("latest_subnet_overlap", ""),
    )
    overlays.update(build_day2_blast_radius_overlays(st.session_state.get("latest_day2_diff", "")))
    for tr in traces:
        tname = tr.get("tool_name")
        args = tr.get("arguments") or {}
        if tname == "generate_odb_architecture_diagram":
            specs.append(
                build_interactive_diagram_spec(
                    diagram_type=str(args.get("diagram_type", "end_to_end_onboarding")),
                    project_id=str(args.get("project_id") or default_project or "my-odb-project-01"),
                    region=str(args.get("region", "us-east4")),
                    gcp_oracle_zone=str(args.get("gcp_oracle_zone", "us-east4-b-r1")),
                    vpc_cidr=str(args.get("vpc_cidr", "10.10.0.0/16")),
                    client_subnet_cidr=str(args.get("client_subnet_cidr", "10.20.1.0/24")),
                    backup_subnet_cidr=str(args.get("backup_subnet_cidr", "10.20.2.0/24")),
                    node_overlays=overlays,
                )
            )
    return specs


def main() -> None:
    st.set_page_config(
        page_title="Oracle@Google Onboarding Agent",
        page_icon=":material/smart_toy:",
        layout="wide",
    )
    _init_session_state()

    st.title("Oracle@Google Onboarding Agent")
    st.caption(
        "End-to-End Onboarding Lifecycle, Guided Architecture Wizard, 6-Phase Progress Tracker, Interactive Digital Twin Topology Studio, "
        "Production Terraform Generator, Day-2 What-If Simulator, and IDE MCP Server — Powered by 5-Layer Anti-Hallucination Guardrails."
    )

    with st.sidebar:
        st.header("1. Connect to LLM")
        auth_choice = st.radio(
            "Authentication Method",
            options=["Vertex AI (gcloud ADC)", "Gemini API Key"],
            help=(
                "Enterprise GCP customers can use their existing `gcloud auth application-default login` "
                "with Vertex AI (zero API keys needed). For quick local testing, use a Gemini API Key."
            ),
        )
        env_model = (
            os.environ.get("ODB_AGENT_MODEL")
            or os.environ.get("GEMINI_MODEL")
            or DEFAULT_MODEL
        )
        preset_options = list(SUPPORTED_MODELS) + ["Custom Model ID (Env / Override)"]
        selected_preset = st.selectbox(
            "Gemini Model Preset",
            options=preset_options,
            index=preset_options.index(env_model) if env_model in SUPPORTED_MODELS else 0,
            help="Model IDs can also be configured via ODB_AGENT_MODEL or GEMINI_MODEL environment variables.",
        )
        if selected_preset == "Custom Model ID (Env / Override)":
            selected_model = st.text_input(
                "Custom Gemini Model ID",
                value=env_model,
                placeholder="gemini-2.5-flash",
            )
        else:
            selected_model = selected_preset

        default_gcp_project = (
            os.environ.get("GOOGLE_CLOUD_PROJECT")
            or detect_gcloud_default_project()
            or ""
        )

        if auth_choice == "Vertex AI (gcloud ADC)":
            auth_mode = "vertex"
            project_id = st.text_input(
                "Google Cloud Project ID",
                value=default_gcp_project,
                placeholder="my-odb-project-01",
            )
            location = st.text_input(
                "Vertex AI Region",
                value=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
            )
            api_key = ""
        else:
            auth_mode = "api_key"
            api_key = st.text_input(
                "Gemini API Key",
                value="",
                type="password",
                placeholder="Paste GEMINI_API_KEY or set in env",
                help="If left blank, reads GEMINI_API_KEY from environment.",
            )
            project_id = default_gcp_project
            location = "global"

        col_a, col_b = st.columns(2)
        with col_a:
            verify_clicked = st.button("Test LLM", width="stretch")
        with col_b:
            reset_clicked = st.button("Reset Chat", width="stretch")

        if reset_clicked:
            st.session_state.messages = []
            st.session_state.agent_instance = None
            st.rerun()

        if verify_clicked:
            try:
                cfg = resolve_llm_config(
                    auth_mode=auth_mode,  # type: ignore[arg-type]
                    model=selected_model,
                    project_id=project_id or None,
                    location=location,
                    api_key=api_key or None,
                )
                status = test_llm_connection(cfg)
                if status.get("connected"):
                    st.success(
                        f"Connected! ({status.get('latency_ms')} ms)\n\n"
                        f"`{cfg.masked_credential_summary}`"
                    )
                else:
                    st.error(f"Connection failed: {status.get('error')}")
            except ValueError as exc:
                st.error(str(exc))

        st.divider()
        st.subheader("5-Layer Anti-Hallucination Guardrails")
        st.markdown(
            "1. **Onboarding & SoD Knowledge + 6-Phase Tracker**\n"
            "2. **Architecture Wizard + Interactive SVG/Mermaid/ASCII**\n"
            "3. **Golden Terraform + Exact Schema Grounding**\n"
            "4. **CIDR `/28`, Secret & Workspace Path Containment**\n"
            "5. **Compiler Auto-Repair + Day-2 What-If Simulator**"
        )

    tab_chat, tab_wizard, tab_onboarding, tab_day2, tab_explorer, tab_mcp = st.tabs(
        [
            "Oracle@Google Onboarding Agent Chat",
            "Guided Architecture & Sizing Wizard",
            "6-Phase Progress Tracker & Digital Twin Studio",
            "Day-2 What-If Simulator & ForceNew Guard",
            "Live Terraform & GCP VPC Inspector",
            "IDE MCP Server & Cloud Shell Setup",
        ]
    )

    with tab_chat:
        st.markdown("##### Quick Onboarding, Architecture & Terraform Workflows")
        q_cols = st.columns(4)
        prompt_to_run: str | None = None
        if q_cols[0].button(
            "Onboarding: End-to-End Flow + Diagram",
            width="stretch",
        ):
            prompt_to_run = (
                "Walk me through the complete Oracle@Google onboarding process — including Prerequisites, "
                "Marketplace Private Offer vs Pay-As-You-Go, OCI Account Linking, and My Oracle Support (CSI) "
                "registration — and generate an end-to-end onboarding diagram."
            )
        if q_cols[1].button(
            "Wizard: Size Mission-Critical OLTP + HA/DR",
            width="stretch",
        ):
            prompt_to_run = (
                f"Run the Guided Architecture Wizard for a mission-critical OLTP workload needing 16 cores and 4 TB "
                f"storage with cross-zone Data Guard DR in project '{project_id or 'my-odb-project-01'}', "
                "and show me the recommended architecture diagram."
            )
        if q_cols[2].button(
            "Day-1: Generate Golden Autonomous DB 23ai Terraform",
            width="stretch",
        ):
            prompt_to_run = (
                f"Generate a production-ready Golden Terraform configuration for an Oracle 23ai "
                f"Autonomous Database in project '{project_id or 'my-odb-project-01'}', region 'us-east4', "
                "zone 'us-east4-b-r1', VPC CIDR 10.10.0.0/16, and Client Subnet 10.20.1.0/24. "
                "Validate the HCL and save it to ./output/adb-prod."
            )
        if q_cols[3].button(
            "Day-2: Simulate Online ECPU Scaling vs ForceNew",
            width="stretch",
        ):
            prompt_to_run = (
                "Simulate scaling Autonomous Database compute_count from 4 to 12 ECPUs and storage from 1 TB to 4 TB "
                "in-place, and explain which attributes are ForceNew hazards."
            )

        for m_idx, msg in enumerate(st.session_state.messages):
            with st.chat_message(msg["role"]):
                if msg.get("scorecard"):
                    _render_guardrail_scorecard(msg["scorecard"])
                if msg.get("tool_traces"):
                    with st.expander(
                        f"Executed {len(msg['tool_traces'])} live tool / guardrail check(s)",
                        expanded=False,
                    ):
                        for trace in msg["tool_traces"]:
                            st.markdown(
                                f"**`{trace['tool_name']}`** ({trace['duration_ms']} ms) — "
                                f"`{trace.get('guardrail_layer', 'Guardrail Check')}` — "
                                f"Args: `{json.dumps(trace['arguments'])}`"
                            )
                            st.code(trace["result_preview"], language="json")
                for d_idx, d_spec in enumerate(msg.get("diagram_specs") or []):
                    render_interactive_odb_diagram(d_spec, key=f"chat_diag_{m_idx}_{d_idx}")
                st.markdown(msg["content"])

        chat_input = st.chat_input(
            "Ask about Prerequisites, Architecture Wizard, 6-Phase Tracker, ODB Networks, Backup, CMEK, Diagrams, Terraform, or Day-2 Simulation..."
        )
        active_prompt = prompt_to_run or chat_input

        if active_prompt:
            st.session_state.messages.append({"role": "user", "content": active_prompt})
            with st.chat_message("user"):
                st.markdown(active_prompt)

            with st.chat_message("assistant"):
                try:
                    cfg = resolve_llm_config(
                        auth_mode=auth_mode,  # type: ignore[arg-type]
                        model=selected_model,
                        project_id=project_id or None,
                        location=location,
                        api_key=api_key or None,
                    )
                    config_fingerprint = (
                        f"{cfg.auth_mode}:{cfg.model}:{cfg.project_id}:{cfg.location}:{cfg.masked_credential_summary}"
                    )
                    if (
                        st.session_state.agent_instance is None
                        or st.session_state.agent_config_key != config_fingerprint
                    ):
                        st.session_state.agent_instance = ODBOnboardingAgent(cfg)
                        st.session_state.agent_config_key = config_fingerprint

                    # Item 7: Live Streaming 5-Layer Guardrail & Tool-Execution Telemetry
                    with st.status(
                        "Oracle@Google Onboarding Agent — Streaming Live 5-Layer Guardrail Telemetry...",
                        expanded=True,
                    ) as live_status:
                        def _on_stream_event(ev: dict[str, Any]) -> None:
                            etype = ev.get("event_type")
                            if etype == "tool_start":
                                live_status.write(
                                    f"▶ Invoking **`{ev.get('tool_name')}`** — *{ev.get('guardrail_layer')}*"
                                )
                            elif etype == "tool_complete":
                                live_status.write(
                                    f"✓ Completed **`{ev.get('tool_name')}`** in `{ev.get('duration_ms')} ms`"
                                )
                            elif etype == "guardrail_verify":
                                passed = ev.get("passed", True)
                                icon = "✓" if passed else "⚠"
                                live_status.write(
                                    f"{icon} Post-Generation HCL & Onboarding Compiler Verified "
                                    f"(`{ev.get('hcl_blocks_inspected', 0)}` HCL block(s), `{ev.get('duration_ms')} ms`)"
                                )
                            elif etype == "auto_repair":
                                live_status.write(
                                    f"⟳ Auto-Repair Guardrail Self-Healing Triggered (Attempt #{ev.get('attempt')})"
                                )

                        turn = st.session_state.agent_instance.send_message(
                            active_prompt,
                            on_event=_on_stream_event,
                        )
                        live_status.update(
                            label=(
                                f"5-Layer Guardrails Verified — {len(turn.tool_traces)} tool/check(s) executed"
                                if turn.guardrail_verified
                                else "Guardrail Auto-Repair Completed"
                            ),
                            state="complete",
                            expanded=False,
                        )

                    serialized_traces = [
                        {
                            "tool_name": t.tool_name,
                            "arguments": t.arguments,
                            "result_preview": t.result_preview,
                            "duration_ms": t.duration_ms,
                            "guardrail_layer": getattr(t, "guardrail_layer", ""),
                        }
                        for t in turn.tool_traces
                    ]
                    scorecard = turn.guardrail_scorecard or build_guardrail_telemetry_summary(
                        serialized_traces,
                        guardrail_verified=turn.guardrail_verified,
                        auto_repairs_triggered=turn.auto_repairs_triggered,
                    )
                    _render_guardrail_scorecard(scorecard)

                    if serialized_traces:
                        with st.expander(
                            f"Inspect {len(serialized_traces)} live tool / guardrail payload(s)",
                            expanded=False,
                        ):
                            for trace in serialized_traces:
                                st.markdown(
                                    f"**`{trace['tool_name']}`** ({trace['duration_ms']} ms) — "
                                    f"`{trace.get('guardrail_layer', '')}` — "
                                    f"Args: `{json.dumps(trace['arguments'])}`"
                                )
                                st.code(trace["result_preview"], language="json")

                    chat_diag_specs = _extract_chat_diagram_specs(
                        serialized_traces,
                        project_id or "my-odb-project-01",
                    )
                    msg_slot = len(st.session_state.messages)
                    for d_idx, d_spec in enumerate(chat_diag_specs):
                        render_interactive_odb_diagram(d_spec, key=f"chat_diag_{msg_slot}_{d_idx}")

                    st.markdown(turn.text)
                    st.session_state.messages.append(
                        {
                            "role": "assistant",
                            "content": turn.text,
                            "tool_traces": serialized_traces,
                            "diagram_specs": chat_diag_specs,
                            "scorecard": scorecard,
                        }
                    )
                except Exception as exc:
                    st.error(f"LLM Agent Error: {exc}")

    # ========================================================================
    # TAB 2 (Part 2 Item 4): Guided Architecture Discovery & Sizing Wizard
    # ========================================================================
    with tab_wizard:
        st.subheader("Guided Interactive Architecture Discovery & Sizing Wizard")
        st.caption(
            "Answer 4 architectural questions (Workload Profile, HA/DR SLA Tier, Sizing, and Network/Security Governance) "
            "to receive a deterministic ODB@GCP service & shape recommendation, interactive topology blueprint, and "
            "1-click schema-verified Golden Terraform bundle."
        )

        wz_c1, wz_c2, wz_c3 = st.columns(3)
        with wz_c1:
            st.markdown("##### 1. Workload & Sizing")
            wz_profile = st.selectbox(
                "Workload Profile",
                options=list(SUPPORTED_WORKLOAD_PROFILES),
                index=0,
                help=(
                    "autonomous_ai_lakehouse -> Autonomous DB 23ai; "
                    "oltp_mission_critical / elastic_rac_cloud_native -> Exascale or Exadata Dedicated; "
                    "consolidated_erp_rac -> Exadata Dedicated; "
                    "single_instance_dev_test -> Base Database Service."
                ),
            )
            wz_cores = st.slider("Estimated ECPU / OCPU Cores", min_value=2, max_value=128, value=8, step=2)
            wz_storage = st.slider("Estimated Storage Capacity (TB)", min_value=1, max_value=64, value=2, step=1)
        with wz_c2:
            st.markdown("##### 2. High Availability, DR & Networking")
            wz_hadr = st.selectbox(
                "Target HA / DR Availability Tier",
                options=list(SUPPORTED_HA_DR_TIERS),
                index=0,
            )
            wz_net = st.selectbox(
                "GCP Network Governance Model",
                options=list(SUPPORTED_NETWORK_GOVERNANCE_MODES),
                index=0,
            )
            wz_sod = st.selectbox(
                "Enterprise Separation-of-Duties Mode",
                options=["full_stack", "enterprise_layered"],
                index=0,
            )
        with wz_c3:
            st.markdown("##### 3. Target Environment & Compliance")
            wz_proj = st.text_input("Target GCP Project ID", value=project_id or "my-odb-project-01", key="wz_proj")
            wz_region = st.text_input("Target GCP Region", value="us-east4", key="wz_reg")
            wz_zone = st.text_input("Colocated Oracle Zone", value="us-east4-b-r1", key="wz_zone")
            wz_enc = st.selectbox(
                "Encryption & Key Management",
                options=["google_managed", "gcp_cmek", "oci_vault"],
                index=0,
            )

        wz_btn_c1, wz_btn_c2 = st.columns(2)
        run_wz = wz_btn_c1.button("Evaluate & Recommend Architecture Blueprint", width="stretch")
        gen_wz_tf = wz_btn_c2.button(
            "Recommend & Generate Golden Terraform Bundle in ./output",
            width="stretch",
        )

        if run_wz or gen_wz_tf or st.session_state.latest_wizard_payload is None:
            st.session_state.latest_wizard_payload = json.loads(
                recommend_odb_architecture_wizard(
                    project_id=wz_proj,
                    region=wz_region,
                    gcp_oracle_zone=wz_zone,
                    workload_profile=wz_profile,
                    ha_dr_tier=wz_hadr,
                    cpu_cores_needed=wz_cores,
                    storage_tb_needed=wz_storage,
                    network_governance=wz_net,
                    encryption_compliance=wz_enc,
                    separation_of_duties_mode=wz_sod,
                    generate_artifacts=bool(gen_wz_tf),
                )
            )

        wz_data = st.session_state.latest_wizard_payload
        if isinstance(wz_data, dict) and wz_data.get("valid"):
            wsum = wz_data.get("wizard_summary", {})
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Recommended ODB Service", str(wsum.get("recommended_workload_type", "adb")).upper())
            m2.metric(
                "Recommended Sizing",
                f"{wsum.get('recommended_compute_count')} Cores / {wsum.get('recommended_storage_size_tb')} TB",
            )
            m3.metric("Networking Topology", str(wsum.get("recommended_networking_topology")))
            m4.metric(
                "Separation-of-Duties Layers",
                " -> ".join(wsum.get("separation_of_duties_layers", ["full_stack"])),
            )

            st.info(
                f"**Hardware Shape:** `{wsum.get('recommended_shape')}`  \n"
                f"**HA / DR Strategy:** {wsum.get('dr_strategy')}  \n"
                f"**Terraform Resources:** `{', '.join(wsum.get('terraform_resources', []))}`"
            )
            for item in wsum.get("architectural_rationale", []):
                st.markdown(f"- {item}")

            if isinstance(wz_data.get("generated_bundle"), dict) and wz_data["generated_bundle"].get("saved"):
                gb = wz_data["generated_bundle"]
                st.success(
                    f"Generated & Validated Golden Terraform Bundle in `{gb.get('output_directory')}` "
                    f"({', '.join(gb.get('written_files', []))})"
                )

            if isinstance(wz_data.get("interactive_spec"), dict):
                st.markdown("##### Recommended Interactive Topology Blueprint")
                render_interactive_odb_diagram(wz_data["interactive_spec"], key="wizard_recommended_canvas")

    # ========================================================================
    # TAB 3 (Part 1 + Part 2 Item 5): 6-Phase Progress Tracker & Digital Twin Studio
    # ========================================================================
    with tab_onboarding:
        st.subheader("Stateful 6-Phase Onboarding Progress Tracker & Digital Twin Topology Studio")

        # Part 2 Item 5: Stateful 6-Phase Onboarding Progress Tracker
        with st.expander("Stateful 6-Phase Onboarding Progress Tracker (Persisted in ./output/onboarding_progress.json)", expanded=True):
            trk_c1, trk_c2, trk_c3 = st.columns([2, 1, 1])
            target_proj_for_diag = project_id or "my-odb-project-01"
            with trk_c1:
                st.caption(
                    "Track your enterprise onboarding across Procurement, Network, Infrastructure, and Database teams. "
                    "Phase statuses automatically sync onto the **Interactive Digital Twin Topology Canvas** below."
                )
            with trk_c2:
                if st.button("Auto-Verify from Live GCP & Workspace", width="stretch"):
                    st.session_state.latest_tracker_payload = json.loads(
                        manage_onboarding_progress_tracker(
                            action="auto_verify",
                            project_id=target_proj_for_diag,
                            region="us-east4",
                        )
                    )
            with trk_c3:
                if st.button("Reset 6-Phase Tracker", width="stretch"):
                    st.session_state.latest_tracker_payload = json.loads(
                        manage_onboarding_progress_tracker(
                            action="reset",
                            project_id=target_proj_for_diag,
                            region="us-east4",
                        )
                    )

            if st.session_state.latest_tracker_payload is None:
                st.session_state.latest_tracker_payload = json.loads(
                    manage_onboarding_progress_tracker(
                        action="status",
                        project_id=target_proj_for_diag,
                        region="us-east4",
                    )
                )

            trk_data = st.session_state.latest_tracker_payload or {}
            pct = int(trk_data.get("completion_pct", 0))
            st.progress(
                pct / 100.0,
                text=(
                    f"Overall Onboarding Progress: {pct}% "
                    f"({trk_data.get('completed_phases', 0)}/{trk_data.get('total_phases', 6)} phases completed)"
                ),
            )

            phases_list = trk_data.get("phases", [])
            if phases_list:
                ph_cols = st.columns(3)
                status_options = ["pending", "in_progress", "completed", "blocked"]
                for idx, ph in enumerate(phases_list):
                    col_slot = ph_cols[idx % 3]
                    with col_slot:
                        pid = str(ph.get("phase_id"))
                        cur_st = str(ph.get("status", "pending"))
                        new_st = st.selectbox(
                            f"{ph.get('title')} [{str(ph.get('team_owner', '')).upper()}]",
                            options=status_options,
                            index=status_options.index(cur_st) if cur_st in status_options else 0,
                            key=f"trk_select_{pid}",
                        )
                        if new_st != cur_st:
                            st.session_state.latest_tracker_payload = json.loads(
                                manage_onboarding_progress_tracker(
                                    action="update_phase",
                                    project_id=target_proj_for_diag,
                                    phase_id=pid,
                                    status=new_st,
                                )
                            )
                            st.rerun()
                        st.code(str(ph.get("verification_command", "")), language="bash")

        st.divider()
        st.markdown("#### Interactive Architecture & Digital Twin Topology Canvas")
        st.caption(
            "Pan/zoom, search resources, click any node to inspect exact `hashicorp/google` HCL & least-privilege IAM, "
            "toggle Separation-of-Duties / CMEK / Data Guard DR / Animated Packet Flows, overlay live GCP or 6-Phase Tracker readiness, "
            "or edit parameters in the **Blueprint Editor** tab to sync Golden Terraform in 1 click."
        )

        ctrl_c1, ctrl_c2, ctrl_c3 = st.columns([1.8, 2.4, 1.3])
        with ctrl_c1:
            selected_diag = st.selectbox(
                "Select Topology / Lifecycle Diagram",
                options=list(SUPPORTED_DIAGRAM_TYPES),
                index=0,
            )
        with ctrl_c2:
            overlay_mode = st.segmented_control(
                "Canvas Overlay Mode",
                options=[
                    "Architecture & Blueprint",
                    "6-Phase Progress Tracker",
                    "Live Digital Twin Readiness",
                    "Day-2 Blast-Radius Map",
                ],
                default="Architecture & Blueprint",
            )
        with ctrl_c3:
            if st.button("Probe Live GCP Readiness", width="stretch"):
                st.session_state.latest_live_readiness = verify_live_onboarding_and_iam_readiness(
                    project_id=target_proj_for_diag,
                    workload_type="adb",
                    team_role="full_stack",
                )
                st.session_state.latest_subnet_overlap = check_live_vpc_subnet_overlaps(
                    project_id=target_proj_for_diag,
                    client_subnet_cidr="10.20.1.0/24",
                    backup_subnet_cidr="10.20.2.0/24",
                )

        saved_bp = st.session_state.get(f"studio_topology_{selected_diag}_blueprint", {})
        active_live_json = (
            st.session_state.latest_live_readiness
            if overlay_mode == "Live Digital Twin Readiness"
            else ""
        )
        active_chk_json = (
            st.session_state.latest_checklist_readiness
            if overlay_mode == "Live Digital Twin Readiness"
            else ""
        )
        active_sub_json = (
            st.session_state.latest_subnet_overlap
            if overlay_mode == "Live Digital Twin Readiness"
            else ""
        )
        active_d2_json = (
            st.session_state.latest_day2_diff
            if overlay_mode == "Day-2 Blast-Radius Map"
            else ""
        )

        diag_res = json.loads(
            generate_odb_architecture_diagram(
                diagram_type=selected_diag,
                project_id=str(saved_bp.get("project_id") or target_proj_for_diag),
                region=str(saved_bp.get("region") or "us-east4"),
                gcp_oracle_zone=str(saved_bp.get("gcp_oracle_zone") or "us-east4-b-r1"),
                vpc_cidr=str(saved_bp.get("vpc_cidr") or "10.10.0.0/16"),
                client_subnet_cidr=str(saved_bp.get("client_subnet_cidr") or "10.20.1.0/24"),
                backup_subnet_cidr=str(saved_bp.get("backup_subnet_cidr") or "10.20.2.0/24"),
                workload_type=str(saved_bp.get("workload_type") or "adb"),
                deployment_layer=str(saved_bp.get("deployment_layer") or "full_stack"),
                compute_count=int(saved_bp.get("compute_count") or 4),
                storage_size_tb=int(saved_bp.get("storage_size_tb") or 1),
                live_readiness_json=active_live_json,
                checklist_readiness_json=active_chk_json,
                live_subnet_overlap_json=active_sub_json,
                day2_diff_json=active_d2_json,
                output_format="both",
            )
        )

        if diag_res.get("valid") and isinstance(diag_res.get("interactive_spec"), dict):
            spec_to_render = diag_res["interactive_spec"]
            if overlay_mode == "6-Phase Progress Tracker" and isinstance(st.session_state.latest_tracker_payload, dict):
                trk_overlays = st.session_state.latest_tracker_payload.get("digital_twin_node_overlays", {}) or {}
                for node in spec_to_render.get("nodes", []):
                    nid = str(node.get("id", ""))
                    if nid in trk_overlays:
                        ov = trk_overlays[nid]
                        node["status"] = ov.get("status", "verified")
                        node["status_badge_label"] = ov.get("badge_label", "")
                        node["status_detail"] = ov.get("detail", "")
                        node["remediation_command"] = ov.get("remediation_command", "")
            elif overlay_mode == "Live Digital Twin Readiness" and not (
                active_live_json or active_chk_json or active_sub_json
            ):
                st.info(
                    "Click **Probe Live GCP Readiness** above or **Evaluate Onboarding Readiness Score** below "
                    "to populate live Verified / Warning / Blocker badges and 1-click `gcloud` fix commands onto diagram nodes."
                )
            elif overlay_mode == "Day-2 Blast-Radius Map" and not active_d2_json:
                st.info(
                    "Run the **Day-2 What-If Simulator** in the **Day-2 What-If Simulator & ForceNew Guard** tab to overlay "
                    "online scaling (`~ SAFE ONLINE`) vs. destructive replacement (`-/+ FORCENEW RISK`) badges here."
                )

            render_interactive_odb_diagram(
                spec_to_render,
                key=f"studio_topology_{selected_diag}",
            )

            exp_c1, exp_c2, exp_c3 = st.columns([2, 1, 1])
            with exp_c1:
                save_diag_path = st.text_input(
                    "Workspace Export Path (`.html` for standalone interactive explorer or `.md` for Mermaid/ASCII)",
                    value=f"./output/diagrams/{selected_diag}.html",
                )
            with exp_c2:
                st.write("")
                if st.button("Save Diagram to Workspace", width="stretch"):
                    saved_out = json.loads(
                        generate_odb_architecture_diagram(
                            diagram_type=selected_diag,
                            project_id=str(saved_bp.get("project_id") or target_proj_for_diag),
                            save_to_file=save_diag_path,
                            live_readiness_json=active_live_json,
                            checklist_readiness_json=active_chk_json,
                            live_subnet_overlap_json=active_sub_json,
                            day2_diff_json=active_d2_json,
                        )
                    )
                    if saved_out.get("valid"):
                        st.success(f"Saved: `{saved_out.get('saved_file')}`")
                    else:
                        st.error(saved_out.get("error", "Failed to save diagram"))
            with exp_c3:
                st.write("")
                standalone_html_bytes = render_standalone_interactive_html(
                    spec_to_render
                ).encode("utf-8")
                st.download_button(
                    label="Download Interactive .html",
                    data=standalone_html_bytes,
                    file_name=f"{selected_diag}.html",
                    mime="text/html",
                    width="stretch",
                )

            with st.expander("View Syntax-Verified Mermaid & Terminal ASCII Diagram Source", expanded=False):
                st.markdown("**Mermaid Diagram Preview:**")
                st.markdown(diag_res.get("mermaid_markdown", ""))
                st.markdown("**ASCII Terminal Reference Diagram:**")
                st.code(diag_res.get("ascii_diagram", ""), language="text")

        st.divider()
        col_kb, col_eval = st.columns(2)
        with col_kb:
            st.markdown("#### 1. Verified Onboarding & Architecture Knowledge Base")
            selected_topic = st.selectbox(
                "Select Onboarding or Architecture Domain",
                options=list(SUPPORTED_ONBOARDING_TOPICS),
                index=0,
            )
            if st.button("Load Verified Domain Guide", width="stretch"):
                kb_payload = json.loads(get_odb_onboarding_and_architecture_guide(selected_topic))
                st.json(kb_payload)

        with col_eval:
            st.markdown("#### 2. Interactive Onboarding Readiness Evaluator (Feeds Digital Twin Map)")
            r_c1, r_c2 = st.columns(2)
            with r_c1:
                r_billing = st.checkbox("Active GCP Billing + Org Admin", value=True)
                r_api = st.checkbox("oracledatabase.googleapis.com Enabled", value=True)
                r_mkt = st.selectbox("Marketplace Mode", ["private_offer", "payg", "none"])
                r_oci = st.checkbox("OCI Tenancy Linked", value=True)
            with r_c2:
                r_mos = st.checkbox("MOS Linked with CSI", value=False)
                r_top = st.selectbox("Networking Topology", ["standalone_vpc", "shared_vpc", "hub_and_spoke_ncc"])
                r_enc = st.selectbox("Encryption Mode", ["google_managed", "gcp_cmek", "oci_vault"])
                r_wkl = st.selectbox("Target Workload", ["adb", "exadata_dedicated", "exascale", "basedb"])
            if st.button("Evaluate Onboarding Readiness Score", width="stretch"):
                readiness_json = evaluate_customer_onboarding_readiness(
                    project_id=project_id or "my-odb-project-01",
                    has_gcp_billing_and_org_admin=r_billing,
                    has_enabled_oracledatabase_api=r_api,
                    marketplace_procurement_mode=r_mkt,
                    has_linked_oci_tenancy=r_oci,
                    has_mos_account_and_csi=r_mos,
                    networking_topology=r_top,
                    encryption_mode=r_enc,
                    workload_type=r_wkl,
                )
                st.session_state.latest_checklist_readiness = readiness_json
                st.json(json.loads(readiness_json))

    # ========================================================================
    # TAB 4 (Part 2 Item 6): Day-2 What-If Simulator & ForceNew Guard
    # ========================================================================
    with tab_day2:
        st.subheader("Interactive Day-2 What-If Scaling Simulator & `ForceNew` Guard")
        st.caption(
            "Simulate Day-2 ECPU/OCPU and storage scaling sliders alongside what-if mutations of immutable `ForceNew` "
            "attributes (`cidr_range`, `gcp_oracle_zone`, `database`) before touching production `.tf` files."
        )

        sim_c1, sim_c2, sim_c3 = st.columns(3)
        with sim_c1:
            st.markdown("##### 1. Baseline Day-1 Configuration")
            sim_wkl = st.selectbox(
                "Workload Type",
                options=["adb", "exadata_dedicated", "exascale", "basedb"],
                index=0,
                key="sim_wkl",
            )
            cur_cpus = st.slider("Current ECPU / OCPU Cores", min_value=2, max_value=64, value=4, step=2, key="cur_cpus")
            cur_tb = st.slider("Current Storage (TB)", min_value=1, max_value=32, value=1, step=1, key="cur_tb")
        with sim_c2:
            st.markdown("##### 2. Proposed Safe Online Scaling (`~ update in-place`)")
            prop_cpus = st.slider("Proposed ECPU / OCPU Cores", min_value=2, max_value=128, value=8, step=2, key="prop_cpus")
            prop_tb = st.slider("Proposed Storage (TB)", min_value=1, max_value=64, value=2, step=1, key="prop_tb")
            prop_auto = st.checkbox("Enable Auto-Scaling (`is_auto_scaling_enabled`)", value=True, key="prop_auto")
            prop_del_prot = st.checkbox("Enforce `deletion_protection = true`", value=True, key="prop_del_prot")
        with sim_c3:
            st.markdown("##### 3. What-If Immutable `ForceNew` Probes (`-/+ destroy`)")
            prop_cidr = st.text_input(
                "Proposed Client Subnet CIDR (Baseline: `10.20.1.0/24`)",
                value="10.20.1.0/24",
                key="prop_cidr",
            )
            prop_zone = st.text_input(
                "Proposed Colocated Oracle Zone (Baseline: `us-east4-b-r1`)",
                value="us-east4-b-r1",
                key="prop_zone",
            )
            prop_dbname = st.text_input(
                "Proposed Database Name (Baseline: `ODBPROD1`)",
                value="ODBPROD1",
                key="prop_dbname",
            )

        sim_b1, sim_b2 = st.columns(2)
        run_sim = sim_b1.button("Simulate Day-2 Impact & Blast Radius", width="stretch")
        save_sim = sim_b2.button(
            "Write Safe Day-2 Update to ./output/day2-simulated (Blocked if ForceNew)",
            width="stretch",
        )

        if run_sim or save_sim or st.session_state.latest_day2_simulation is None:
            sim_res_str = simulate_day2_scaling_what_if(
                workload_type=sim_wkl,
                project_id=project_id or "my-odb-project-01",
                region="us-east4",
                current_gcp_oracle_zone="us-east4-b-r1",
                proposed_gcp_oracle_zone=prop_zone,
                current_client_subnet_cidr="10.20.1.0/24",
                proposed_client_subnet_cidr=prop_cidr,
                current_db_name="ODBPROD1",
                proposed_db_name=prop_dbname,
                current_compute_count=cur_cpus,
                proposed_compute_count=prop_cpus,
                current_storage_size_tb=cur_tb,
                proposed_storage_size_tb=prop_tb,
                current_auto_scaling=True,
                proposed_auto_scaling=prop_auto,
                current_deletion_protection=True,
                proposed_deletion_protection=prop_del_prot,
                apply_to_bundle_dir="./output/day2-simulated" if save_sim else "",
            )
            sim_parsed = json.loads(sim_res_str)
            st.session_state.latest_day2_simulation = sim_parsed
            st.session_state.latest_day2_diff = json.dumps(sim_parsed.get("diff_analysis", {}), indent=2)

        sim_data = st.session_state.latest_day2_simulation
        if isinstance(sim_data, dict):
            if sim_data.get("safe_day2_change"):
                st.success(f"**SAFE DAY-2 CHANGE:** {sim_data.get('downtime_impact')}")
            else:
                st.error(f"**DESTRUCTIVE FORCENEW REPLACEMENT DETECTED:** {sim_data.get('downtime_impact')}")

            if sim_data.get("deletion_protection_warning"):
                st.warning(sim_data["deletion_protection_warning"])
            if sim_data.get("save_blocked_reason"):
                st.error(sim_data["save_blocked_reason"])
            elif sim_data.get("saved_file"):
                st.success(f"Saved safe Day-2 Terraform update to `{sim_data['saved_file']}`")

            with st.expander("View Simulated Before vs. After HCL & Diff Analysis", expanded=False):
                hc1, hc2 = st.columns(2)
                with hc1:
                    st.markdown("**Day-1 Baseline HCL:**")
                    st.code(sim_data.get("before_hcl", ""), language="hcl")
                with hc2:
                    st.markdown("**Proposed Day-2 HCL:**")
                    st.code(sim_data.get("after_hcl", ""), language="hcl")
                st.markdown("**`analyze_day2_terraform_diff` Report:**")
                st.json(sim_data.get("diff_analysis", {}))

            if isinstance(sim_data.get("interactive_spec"), dict):
                st.markdown("#### Interactive Day-2 Blast-Radius Topology Overlay")
                st.caption(
                    "Nodes with safe online scaling (`~ SAFE ONLINE`) glow blue, while any immutable `ForceNew` change "
                    "triggers a pulsing red `-/+ FORCENEW RISK` hazard badge with non-destructive migration guidance."
                )
                render_interactive_odb_diagram(sim_data["interactive_spec"], key="day2_blast_radius_canvas")

        st.divider()
        col_w, col_d = st.columns(2)
        with col_w:
            st.markdown("#### Inspect Existing Terraform Workspace (Workspace-Sandboxed)")
            ws_dir = st.text_input("Workspace Path (inside active project root)", value="./output")
            if st.button("Audit Workspace Resources & Deletion Protection", width="stretch"):
                st.code(inspect_existing_terraform_workspace(ws_dir), language="json")

        with col_d:
            st.markdown("#### Custom HCL Diff Analyzer")
            sample_before = (
                'resource "google_oracle_database_autonomous_database" "adb" {\n'
                '  autonomous_database_id = "odb-prod-adb"\n'
                '  database               = "ODBPROD1"\n'
                '  location               = "us-east4"\n'
                '  deletion_protection    = true\n'
                '  properties {\n'
                '    compute_count = 4\n'
                '  }\n'
                '}'
            )
            sample_after = (
                'resource "google_oracle_database_autonomous_database" "adb" {\n'
                '  autonomous_database_id = "odb-prod-adb"\n'
                '  database               = "ODBPROD1"\n'
                '  location               = "us-east4"\n'
                '  deletion_protection    = true\n'
                '  properties {\n'
                '    compute_count = 8\n'
                '  }\n'
                '}'
            )
            existing_hcl = st.text_area("Current HCL (Before)", value=sample_before, height=140)
            proposed_hcl = st.text_area("Proposed HCL (After)", value=sample_after, height=140)
            if st.button("Analyze Custom HCL Diff Safety", width="stretch"):
                st.session_state.latest_day2_diff = analyze_day2_terraform_diff(existing_hcl, proposed_hcl)
                st.code(st.session_state.latest_day2_diff, language="json")

    with tab_explorer:
        st.subheader("Live Terraform Registry, Exact Schema & GCP VPC Overlap Inspector")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("#### 1. Latest `hashicorp/google` Provider & Exact Schema")
            if st.button("Query Terraform Registry Live", width="stretch"):
                st.code(get_latest_google_provider_version(), language="json")

            selected_res = st.selectbox(
                "Inspect Exact Resource Schema (`top_level` vs `properties {}`)",
                options=list(EXACT_ODB_RESOURCE_SCHEMAS.keys()),
            )
            if st.button("Fetch Exact Schema & Upstream Docs", width="stretch"):
                doc_data = json.loads(get_odb_resource_documentation(selected_res))
                st.json(doc_data)

        with col2:
            st.markdown("#### 2. Live GCP VPC Subnet Overlap & ODB Capability Probe")
            probe_project = st.text_input(
                "Target GCP Project",
                value=project_id or "my-odb-project-01",
            )
            probe_region = st.text_input("Target Region", value="us-east4")
            probe_client_cidr = st.text_input("Proposed ODB Client CIDR", value="10.20.1.0/24")
            if st.button("Check Live GCP Subnets & ODB Shapes", width="stretch"):
                sub_json = check_live_vpc_subnet_overlaps(probe_project, probe_client_cidr)
                st.session_state.latest_subnet_overlap = sub_json
                st.markdown("**Live GCP VPC Subnet Collision Check:**")
                st.code(sub_json, language="json")
                st.markdown("**Regions, Shapes, GI Versions & ADB Versions:**")
                st.code(
                    discover_live_odb_shapes_and_versions(probe_project, probe_region),
                    language="json",
                )

    with tab_mcp:
        st.subheader("IDE MCP Server Integration (VS Code, Cursor, Claude Code, Antigravity) & Cloud Shell Setup")
        st.markdown(
            """
            ### 1. Use via Model Context Protocol (`stdio` MCP Server) in Your IDE
            Customers can attach the **Oracle@Google Onboarding Agent** directly to **VS Code (GitHub Copilot / Cline / Continue)**, **Cursor**, **Claude Code / Claude Desktop**, **Gemini CLI**, or **Antigravity IDE** using the built-in `odb-mcp-server` (or `odb-onboarding-agent mcp-serve`) entrypoint.

            #### 14 Allow-Listed MCP Tools (Part 1 + Part 2)
            - `get_odb_onboarding_guide` — Grounded onboarding & Separation-of-Duties documentation
            - `evaluate_onboarding_readiness` — Readiness checklist & `gcloud` bootstrap commands
            - `run_odb_architecture_wizard` — **Part 2 Item 4:** Guided Architecture Discovery & Sizing Wizard
            - `manage_onboarding_progress_tracker` — **Part 2 Item 5:** Stateful 6-Phase Onboarding Progress Tracker (`status`, `update_phase`, `auto_verify`, `reset`)
            - `generate_odb_diagram` — **Part 1:** Interactive HTML5, Mermaid, and ASCII topology generator
            - `generate_golden_terraform` — Schema-verified Golden Terraform generator (`full_stack`, `network_only`, `infra_only`, `database_only`)
            - `validate_odb_network_cidrs` — Deterministic `/28` minimum prefix & RFC1918 overlap check
            - `validate_odb_terraform_hcl` — Fast anti-hallucination HCL validator
            - `inspect_day2_workspace` — Day-2 workspace inventory & `deletion_protection` posture
            - `analyze_day2_terraform_diff` — `ForceNew` destructive replacement blocker
            - `simulate_day2_scaling_what_if` — **Part 2 Item 6:** Day-2 What-If Scaling & `ForceNew` Blast-Radius Simulator
            - `get_guardrail_telemetry_report` — **Part 2 Item 7:** 5-Layer Guardrail Telemetry & Compliance Scorecard
            - `list_odb_provider_resources` — Exact `hashicorp/google` (`google_oracle_database_*`) resource catalog
            - `verify_live_onboarding_and_iam_readiness` — Live GCP API & least-privilege IAM readiness check

            #### VS Code (`.vscode/mcp.json`) / Cursor (`.cursor/mcp.json`) / Antigravity Configuration
            ```json
            {
              "servers": {
                "oracle-google-onboarding-agent": {
                  "type": "stdio",
                  "command": "/ABSOLUTE/PATH/TO/oracle-at-google-onboarding-agent/.venv/bin/odb-mcp-server",
                  "args": [],
                  "env": {
                    "ODB_WORKSPACE_ROOT": "${workspaceFolder}",
                    "ODB_AGENT_MODEL": "gemini-3.8-flash",
                    "ODB_FAST_VALIDATION": "1"
                  }
                }
              }
            }
            ```

            ---

            ### 2. Google Cloud Shell (Web Preview Studio + Interactive CLI)
            ```bash
            git clone https://github.com/sharmagauravji-goog/oracle-at-google-onboarding-agent.git
            cd oracle-at-google-onboarding-agent
            python3 -m venv .venv && source .venv/bin/activate
            pip install -r requirements.txt && pip install -e .

            # Option A: Launch Full Interactive Web Studio in Cloud Shell Web Preview (Port 8080)
            odb-onboarding-agent studio --cloud-shell

            # Option B: Run Guided Architecture Wizard, 6-Phase Tracker & Day-2 Simulator in Terminal
            odb-onboarding-agent wizard --project-id "$GOOGLE_CLOUD_PROJECT" --workload-profile oltp_mission_critical --generate-bundle --save-html
            odb-onboarding-agent tracker --action auto_verify --project-id "$GOOGLE_CLOUD_PROJECT"
            odb-onboarding-agent simulate-day2 --workload adb --current-compute 4 --proposed-compute 12 --save-html
            ```
            """
        )


if __name__ == "__main__":
    main()
