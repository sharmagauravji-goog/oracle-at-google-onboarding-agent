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
from ai_agent.tools.odb_live_discovery import (
    discover_live_odb_regions_and_zones,
    discover_live_odb_shapes_and_versions,
)
from ai_agent.tools.terraform_registry import (
     KNOWN_ODB_RESOURCES,
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
        "Autonomous LLM Agent powered by Gemini (`google-genai`) with live Terraform Registry schema inspection, "
        "live `oracledatabase.googleapis.com` capability discovery, and official documentation lookup."
    )

    # ------------------------------------------------------------------
    # Sidebar: Customer LLM Connection Configuration
    # ------------------------------------------------------------------
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
                value=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
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
            location = "us-central1"

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
        st.subheader("Active Live Tools")
        st.markdown(
            "- `get_latest_google_provider_version`\n"
            "- `list_odb_terraform_resources`\n"
            "- `get_odb_resource_documentation`\n"
            "- `discover_live_odb_regions_and_zones`\n"
            "- `discover_live_odb_shapes_and_versions`\n"
            "- `check_customer_gcp_readiness`\n"
            "- `fetch_official_odb_documentation`\n"
            "- `validate_odb_network_cidrs`\n"
            "- `validate_terraform_hcl`\n"
            "- `save_generated_terraform_bundle`"
        )

    # ------------------------------------------------------------------
    # Main Tabs
    # ------------------------------------------------------------------
    tab_chat, tab_explorer, tab_guide = st.tabs(
        [
            "AI Architect Agent (Chat + Live Tools)",
            "Live Terraform & ODB API Inspector",
            "Customer LLM Connection Guide",
        ]
    )

    with tab_chat:
        st.markdown("##### Quick Discovery Prompts")
        q_cols = st.columns(3)
        prompt_to_run: str | None = None
        if q_cols[0].button(
            "Check latest hashicorp/google version & ODB resources",
            use_container_width=True,
        ):
            prompt_to_run = (
                "Check the latest released version of the hashicorp/google Terraform provider "
                "and list all supported google_oracle_database_* resources."
            )
        if q_cols[1].button(
            "Inspect live Exascale VM Cluster Terraform schema",
            use_container_width=True,
        ):
            prompt_to_run = (
                "Fetch the latest upstream Terraform documentation for "
                "google_oracle_database_exadb_vm_cluster and show me a production example."
            )
        if q_cols[2].button(
            "Validate CIDRs & design Autonomous DB 23ai in us-east4",
            use_container_width=True,
        ):
            prompt_to_run = (
                "Validate VPC CIDR 10.10.0.0/16 and Client Subnet 10.20.1.0/24, check the latest "
                "google_oracle_database_autonomous_database schema, and generate Terraform for an "
                "Oracle 23ai OLTP Autonomous Database in us-east4."
            )

        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                if msg.get("tool_traces"):
                    with st.expander(
                        f"Executed {len(msg['tool_traces'])} live tool call(s)",
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
            "Ask about latest ODB@GCP features, live Terraform schemas, or request custom infrastructure code..."
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

                    with st.spinner("Agent reasoning & querying live tools..."):
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
                            f"Executed {len(serialized_traces)} live tool call(s)",
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

    with tab_explorer:
        st.subheader("Live Terraform Registry & ODB@GCP API Inspector")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("#### 1. Latest `hashicorp/google` Provider Release")
            if st.button("Query Terraform Registry Live"):
                st.code(get_latest_google_provider_version(), language="json")

            selected_res = st.selectbox(
                "Inspect Upstream Terraform Resource Schema",
                options=list(KNOWN_ODB_RESOURCES.keys()),
            )
            if st.button("Fetch Upstream Resource Docs"):
                doc_data = json.loads(get_odb_resource_documentation(selected_res))
                st.json(doc_data)

        with col2:
            st.markdown("#### 2. Live ODB@GCP Cloud Capability Probe")
            probe_project = st.text_input(
                "Target GCP Project for Live API Probe",
                value=project_id or "my-odb-project-01",
            )
            probe_region = st.text_input("Target Region", value="us-east4")
            if st.button("Discover Live Regions & Shapes"):
                st.markdown("**Regions & Oracle Zones:**")
                st.code(discover_live_odb_regions_and_zones(probe_project), language="json")
                st.markdown("**Shapes, GI Versions & ADB Versions:**")
                st.code(
                    discover_live_odb_shapes_and_versions(probe_project, probe_region),
                    language="json",
                )

    with tab_guide:
        st.subheader("How Customers Connect the Downloaded Agent to LLMs")
        st.markdown(
            """
            ### Option 1: Vertex AI via Google Cloud ADC (Recommended for Enterprise Customers)
            Customers onboarding to Oracle Database@Google Cloud already have a GCP project and `gcloud` CLI.
            No separate API keys are required:
            ```bash
            # 1. Authenticate with Google Cloud Application Default Credentials
            gcloud auth application-default login

            # 2. Enable the Vertex AI API in your project
            gcloud services enable aiplatform.googleapis.com --project=YOUR_PROJECT_ID

            # 3. Export your project ID and run the agent
            export GOOGLE_CLOUD_PROJECT="YOUR_PROJECT_ID"
            export GOOGLE_CLOUD_LOCATION="us-central1"
            odb-ai-agent doctor --ping-llm
            odb-ai-agent chat
            ```

            ---

            ### Option 2: Gemini Developer API Key (Fastest for Local Evaluation)
            For quick sandbox testing without enabling Vertex AI on a GCP project:
            ```bash
            export GEMINI_API_KEY="your-google-ai-studio-key"
            odb-ai-agent doctor --ping-llm
            odb-ai-agent chat
            ```
            """
        )


if __name__ == "__main__":
    main()
