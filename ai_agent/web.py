"""Streamlit Web Studio for the Oracle@Google Onboarding Agent.

Run locally bound to localhost:
    streamlit run ai_agent/web.py --server.address=127.0.0.1 --server.port=8502
"""

from __future__ import annotations

import json
import os

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
from ai_agent.tools.odb_live_discovery import (
    check_live_vpc_subnet_overlaps,
    discover_live_odb_shapes_and_versions,
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
        page_title="Oracle@Google Onboarding Agent",
        page_icon=":material/smart_toy:",
        layout="wide",
    )
    _init_session_state()

    st.title("Oracle@Google Onboarding Agent")
    st.caption(
        "End-to-End Onboarding Lifecycle, ODB Networks & Architecture Diagrams, Production Terraform Code Generator, "
        "Day-2 Maintenance Guard, and IDE MCP Server — Powered by 5-Layer Anti-Hallucination Guardrails."
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
            "1. **Onboarding & Architecture Knowledge Base**\n"
            "2. **Syntax-Verified Mermaid & ASCII Diagrams**\n"
            "3. **Golden Terraform + Exact Schema Grounding**\n"
            "4. **CIDR `/28`, Secret & Workspace Path Containment**\n"
            "5. **Compiler Auto-Repair + Day-2 `ForceNew` Guard**"
        )

    tab_chat, tab_onboarding, tab_day2, tab_explorer, tab_mcp = st.tabs(
        [
            "Oracle@Google Onboarding Agent Chat",
            "Onboarding Lifecycle, Architecture & Diagrams",
            "Day-2 Maintenance & ForceNew Guard",
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
            use_container_width=True,
        ):
            prompt_to_run = (
                "Walk me through the complete Oracle@Google onboarding process — including Prerequisites, "
                "Marketplace Private Offer vs Pay-As-You-Go, OCI Account Linking, and My Oracle Support (CSI) "
                "registration — and generate an end-to-end onboarding diagram."
            )
        if q_cols[1].button(
            "Networking: ODB Network Topologies + Diagram",
            use_container_width=True,
        ):
            prompt_to_run = (
                "Explain ODB Networks (`google_oracle_database_odb_network`), `CLIENT_SUBNET` vs `BACKUP_SUBNET` "
                "sizing rules, and the 3 Enterprise Networking Topologies (Standalone VPC, Shared VPC, and "
                "Hub-and-Spoke with NCC/Interconnect), and generate a Hub-and-Spoke networking diagram."
            )
        if q_cols[2].button(
            "Day-1: Generate Golden Autonomous DB 23ai Terraform",
            use_container_width=True,
        ):
            prompt_to_run = (
                f"Generate a production-ready Golden Terraform configuration for an Oracle 23ai "
                f"Autonomous Database in project '{project_id or 'my-odb-project-01'}', region 'us-east4', "
                "zone 'us-east4-b-r1', VPC CIDR 10.10.0.0/16, and Client Subnet 10.20.1.0/24. "
                "Validate the HCL and save it to ./output/adb-prod."
            )
        if q_cols[3].button(
            "Day-2: Backup, CMEK & Safe ECPU Scaling",
            use_container_width=True,
        ):
            prompt_to_run = (
                "Explain Backup & Recovery and CMEK encryption (`gcp-sa-oracledatabase` service agent IAM) "
                "for Oracle@Google, then inspect ./output and show how to safely scale compute_count in-place."
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
            "Ask about Prerequisites, Marketplace Private Offer/PAYG, OCI Linking, MOS Support, ODB Networks, Backup, CMEK, Monitoring, Diagrams, or Terraform..."
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

                    with st.spinner("Oracle@Google Onboarding Agent reasoning, running live tools & verifying guardrails..."):
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

    with tab_onboarding:
        st.subheader("Grounded Onboarding Lifecycle, Deep Architecture & Diagram Generator")
        col_kb, col_diag = st.columns(2)
        with col_kb:
            st.markdown("#### 1. Verified Onboarding & Architecture Knowledge Base")
            selected_topic = st.selectbox(
                "Select Onboarding or Architecture Domain",
                options=list(SUPPORTED_ONBOARDING_TOPICS),
                index=0,
            )
            if st.button("Load Verified Domain Guide", use_container_width=True):
                kb_payload = json.loads(get_odb_onboarding_and_architecture_guide(selected_topic))
                st.json(kb_payload)

            st.markdown("#### 2. Interactive Onboarding Readiness Evaluator")
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
            if st.button("Evaluate Onboarding Readiness Score", use_container_width=True):
                readiness_json = evaluate_customer_onboarding_readiness(
                    has_gcp_billing_and_org_admin=r_billing,
                    has_enabled_oracledatabase_api=r_api,
                    marketplace_procurement_mode=r_mkt,
                    has_linked_oci_tenancy=r_oci,
                    has_mos_account_and_csi=r_mos,
                    networking_topology=r_top,
                    encryption_mode=r_enc,
                    workload_type=r_wkl,
                )
                st.json(json.loads(readiness_json))

        with col_diag:
            st.markdown("#### 3. Grounded Architecture & Onboarding Diagram Generator")
            selected_diag = st.selectbox(
                "Select Diagram Type",
                options=list(SUPPORTED_DIAGRAM_TYPES),
                index=0,
            )
            save_diag_path = st.text_input(
                "Optional Workspace Output Path",
                value=f"./output/diagrams/{selected_diag}.md",
            )
            if st.button("Generate Grounded Mermaid & ASCII Diagram", use_container_width=True):
                diag_res = json.loads(
                    generate_odb_architecture_diagram(
                        diagram_type=selected_diag,
                        output_format="both",
                        save_to_file=save_diag_path,
                    )
                )
                if diag_res.get("valid"):
                    st.success(f"{diag_res.get('title')} — {diag_res.get('summary')}")
                    if diag_res.get("saved_file"):
                        st.caption(f"Saved inside workspace: `{diag_res['saved_file']}`")
                    st.markdown("**Mermaid Diagram Preview:**")
                    st.markdown(diag_res.get("mermaid_markdown", ""))
                    st.markdown("**ASCII Terminal Reference Diagram:**")
                    st.code(diag_res.get("ascii_diagram", ""), language="text")
                else:
                    st.error(diag_res.get("error", "Failed to generate diagram"))

    with tab_day2:
        st.subheader("Day-2 Maintenance & Destructive Change (`ForceNew`) Guard")
        col_w, col_d = st.columns(2)
        with col_w:
            st.markdown("#### 1. Inspect Existing Terraform Workspace (Workspace-Sandboxed)")
            ws_dir = st.text_input("Workspace Path (inside active project root)", value="./output")
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

    with tab_mcp:
        st.subheader("IDE MCP Server Integration (VS Code, Cursor, Claude Desktop, Antigravity) & Cloud Shell Setup")
        st.markdown(
            """
            ### 1. Use via Model Context Protocol (`stdio` MCP Server) in Your IDE
            Customers can attach the **Oracle@Google Onboarding Agent** directly to **VS Code (GitHub Copilot / Cline / Continue)**, **Cursor**, **Claude Desktop**, **Gemini CLI**, or **Antigravity IDE** using the built-in `odb-mcp-server` (or `odb-onboarding-agent mcp-serve`) entrypoint.

            #### Built-In MCP Safety & Reliability Guardrails
            - **Never Exposes `terraform apply` or `terraform destroy`**: Only read-only onboarding guides, diagram generation, golden HCL generation, fast schema validation, and non-destructive Day-2 workspace inspection are exposed.
            - **Strict `stdio` Stream Isolation**: All logs, warnings, and subprocess diagnostics are redirected to `stderr` so `stdout` carries exclusively JSON-RPC 2.0 protocol frames.
            - **Workspace Path Containment**: `generate_golden_terraform` and `inspect_day2_workspace` strictly enforce that all paths resolve inside `ODB_WORKSPACE_ROOT` (rejecting `../` traversal or `/etc`, `/tmp`, `~/.ssh`).
            - **Fast IDE Timeout Protection (`<50ms`)**: MCP tools run in fast validation mode and return concise summaries pointing to `./output/<bundle>` instead of blocking on multi-hundred-MB `terraform init` downloads.
            - **Configurable Model IDs**: Set `ODB_AGENT_MODEL` or `GEMINI_MODEL` in your environment so you are never locked into a retired preview model ID.

            #### VS Code (`.vscode/mcp.json`) / Cursor (`.cursor/mcp.json`) Configuration
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

            ### 2. Google Cloud Shell (Zero Local Setup, Zero API Keys)
            ```bash
            git clone https://github.com/sharmagauravji-goog/oracle-at-google-onboarding-agent.git
            cd oracle-at-google-onboarding-agent
            python3 -m venv .venv && source .venv/bin/activate
            pip install -r requirements.txt && pip install -e .

            # 1. Verify environment & Vertex AI ADC connection
            odb-onboarding-agent doctor --ping-llm

            # 2. Explore Onboarding Lifecycle & Generate Architecture Diagrams
            odb-onboarding-agent onboarding-guide --topic overview
            odb-onboarding-agent diagram --type end_to_end_onboarding --save-to ./output/diagrams/onboarding.md

            # 3. Generate Golden Day-1 Terraform or launch interactive Onboarding Chat
            odb-onboarding-agent generate-golden --project-id "$GOOGLE_CLOUD_PROJECT" --workload adb
            odb-onboarding-agent chat
            ```
            """
        )


if __name__ == "__main__":
    main()
