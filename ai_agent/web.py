"""Streamlit Web Studio for the Oracle Database@Google Cloud LLM Architect Agent.

Run locally bound to localhost:
    streamlit run ai_agent/web.py --server.address=127.0.0.1 --server.port=8502
"""

from __future__ import annotations

import json
import os

import streamlit as st

from ai_agent.llm_client import (
    SUPPORTED_MODELS,
    detect_gcloud_default_project,
    resolve_llm_config,
)
from ai_agent.orchestrator import (
    ODBArchitectAgent,
    test_llm_connection,
)
from ai_agent.tools.day2_maintenance import (
    analyze_day2_terraform_diff,
    inspect_existing_terraform_workspace,
)
from ai_agent.tools.odb_live_discovery import (
    check_live_vpc_subnet_overlaps,
    discover_live_odb_regions_and_zones,
    discover_live_odb_shapes_and_versions,
)
from ai_agent.tools.terraform_registry import (
    EXACT_ODB_RESOURCE_SCHEMAS,
    get_latest_google_provider_version,
    get_odb_resource_documentation,
)


def _init_session_state() -> None:
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "agent_instance" not in st.session_state:
        st.session_state.agent_instance = None
    if "agent_config_key" not in st.session_state:
        st.session_state.agent_config_key = ""


def main() -> None:
    st.set_page_config(
        page_title="ODB@GCP AI Architect Agent",
        page_icon=":material/smart_toy:",
        layout="wide",
    )
    _init_session_state()

    st.title("Oracle Database@Google Cloud — AI Architect Agent")
    st.caption(
        "Production Terraform Generator & Day-2 Maintenance Agent with 5-Layer Anti-Hallucination Guardrails."
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
        selected_model = st.selectbox(
            "Gemini Model",
            options=list(SUPPORTED_MODELS),
            index=0,
        )

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
            verify_clicked = st.button("Test LLM", use_container_width=True)
        with col_b:
            reset_clicked = st.button("Reset Chat", use_container_width=True)

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
            "1. **Golden Baseline (`generate_golden_odb_terraform`)**\n"
            "2. **Exact Provider Schema (`EXACT_ODB_RESOURCE_SCHEMAS`)**\n"
            "3. **CIDR `/28` + Secret Leak Guard**\n"
            "4. **Compiler Auto-Repair (`terraform validate`)**\n"
            "5. **Day-2 `ForceNew` Destroy Protection**"
        )

    tab_chat, tab_day2, tab_explorer, tab_guide = st.tabs(
        [
            "AI Architect Agent (Day-1 & Day-2)",
            "Day-2 Maintenance & ForceNew Guard",
            "Live Terraform & GCP VPC Inspector",
            "Customer Setup & Cloud Shell Guide",
        ]
    )

    with tab_chat:
        st.markdown("##### Quick Production Workflows")
        q_cols = st.columns(3)
        prompt_to_run: str | None = None
        if q_cols[0].button(
            "Day-1: Generate Golden Autonomous DB 23ai Terraform",
            use_container_width=True,
        ):
            prompt_to_run = (
                f"Generate a production-ready Golden Terraform configuration for an Oracle 23ai "
                f"Autonomous Database in project '{project_id or 'my-odb-project-01'}', region 'us-east4', "
                "zone 'us-east4-b-r1', VPC CIDR 10.10.0.0/16, and Client Subnet 10.20.1.0/24. "
                "Validate the HCL and save it to ./output/adb-prod."
            )
        if q_cols[1].button(
            "Day-1: Generate Golden Exascale Cluster Terraform",
            use_container_width=True,
        ):
            prompt_to_run = (
                f"Generate a Golden Terraform bundle for an Exadata Exascale cluster in project "
                f"'{project_id or 'my-odb-project-01'}' in us-east4 (zone us-east4-b-r1) with Client Subnet "
                "10.20.1.0/24 and Backup Subnet 10.20.2.0/24, and validate the generated HCL."
            )
        if q_cols[2].button(
            "Day-2: Inspect Workspace & Safely Scale ECPUs",
            use_container_width=True,
        ):
            prompt_to_run = (
                "Inspect the existing Terraform workspace in ./output, check if deletion_protection is enabled, "
                "and show me how to safely scale compute_count in-place without triggering a ForceNew replacement."
            )

        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                if msg.get("tool_traces"):
                    with st.expander(
                        f"Executed {len(msg['tool_traces'])} live tool / guardrail check(s)",
                        expanded=False,
                    ):
                        for trace in msg["tool_traces"]:
                            st.markdown(
                                f"**`{trace['tool_name']}`** ({trace['duration_ms']} ms) — "
                                f"Args: `{json.dumps(trace['arguments'])}`"
                            )
                            st.code(trace["result_preview"], language="json")
                st.markdown(msg["content"])

        chat_input = st.chat_input(
            "Ask to generate Day-1 Terraform, inspect live schemas, or perform safe Day-2 maintenance..."
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
                        st.session_state.agent_instance = ODBArchitectAgent(cfg)
                        st.session_state.agent_config_key = config_fingerprint

                    with st.spinner("Agent reasoning, running live tools & verifying HCL guardrails..."):
                        turn = st.session_state.agent_instance.send_message(active_prompt)

                    serialized_traces = [
                        {
                            "tool_name": t.tool_name,
                            "arguments": t.arguments,
                            "result_preview": t.result_preview,
                            "duration_ms": t.duration_ms,
                        }
                        for t in turn.tool_traces
                    ]
                    if serialized_traces:
                        with st.expander(
                            f"Executed {len(serialized_traces)} live tool / guardrail check(s)",
                            expanded=True,
                        ):
                            for trace in serialized_traces:
                                st.markdown(
                                    f"**`{trace['tool_name']}`** ({trace['duration_ms']} ms) — "
                                    f"Args: `{json.dumps(trace['arguments'])}`"
                                )
                                st.code(trace["result_preview"], language="json")

                    st.markdown(turn.text)
                    st.session_state.messages.append(
                        {
                            "role": "assistant",
                            "content": turn.text,
                            "tool_traces": serialized_traces,
                        }
                    )
                except Exception as exc:
                    st.error(f"LLM Agent Error: {exc}")

    with tab_day2:
        st.subheader("Day-2 Maintenance & Destructive Change (`ForceNew`) Guard")
        col_w, col_d = st.columns(2)
        with col_w:
            st.markdown("#### 1. Inspect Existing Terraform Workspace")
            ws_dir = st.text_input("Workspace Path", value="./output")
            if st.button("Audit Workspace Resources & Deletion Protection"):
                st.code(inspect_existing_terraform_workspace(ws_dir), language="json")

        with col_d:
            st.markdown("#### 2. Verify Day-2 Diff for Destructive Replacements")
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
            existing_hcl = st.text_area("Current HCL (Before)", value=sample_before, height=160)
            proposed_hcl = st.text_area("Proposed HCL (After)", value=sample_after, height=160)
            if st.button("Analyze Day-2 Change Safety"):
                st.code(analyze_day2_terraform_diff(existing_hcl, proposed_hcl), language="json")

    with tab_explorer:
        st.subheader("Live Terraform Registry, Exact Schema & GCP VPC Overlap Inspector")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("#### 1. Latest `hashicorp/google` Provider & Exact Schema")
            if st.button("Query Terraform Registry Live"):
                st.code(get_latest_google_provider_version(), language="json")

            selected_res = st.selectbox(
                "Inspect Exact Resource Schema (`top_level` vs `properties {}`)",
                options=list(EXACT_ODB_RESOURCE_SCHEMAS.keys()),
            )
            if st.button("Fetch Exact Schema & Upstream Docs"):
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
            if st.button("Check Live GCP Subnets & ODB Shapes"):
                st.markdown("**Live GCP VPC Subnet Collision Check:**")
                st.code(
                    check_live_vpc_subnet_overlaps(probe_project, probe_client_cidr),
                    language="json",
                )
                st.markdown("**Regions, Shapes, GI Versions & ADB Versions:**")
                st.code(
                    discover_live_odb_shapes_and_versions(probe_project, probe_region),
                    language="json",
                )

    with tab_guide:
        st.subheader("Customer Deployment & Zero-Setup Cloud Shell Guide")
        st.markdown(
            """
            ### Recommended Path 1: Google Cloud Shell (Zero Local Setup, Zero API Keys)
            Google Cloud Shell comes pre-installed with `gcloud` (already logged in), `terraform`, `python3`, and `git`.
            ```bash
            git clone <YOUR_REPO_URL>
            cd oracle-google-ai-agent
            python3 -m venv .venv && source .venv/bin/activate
            pip install -r requirements.txt && pip install -e .

            # Verify Vertex AI ADC connection (uses active Cloud Shell project)
            odb-ai-agent doctor --ping-llm

            # Generate a Golden Day-1 Terraform bundle directly or launch interactive chat
            odb-ai-agent generate-golden --project-id $(gcloud config get-value project) --workload adb
            odb-ai-agent chat
            ```

            ---

            ### Recommended Path 2: Docker Container (For Corporate Laptops / Jump Hosts)
            ```bash
            docker compose up --build odb-ai-agent-web
            # Open http://127.0.0.1:8502
            ```
            """
        )


if __name__ == "__main__":
    main()
