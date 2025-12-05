import streamlit as st
import asyncio
import uuid
from pathlib import Path
from google.adk.sessions import InMemorySessionService
from google.adk.artifacts import InMemoryArtifactService
from utils import EVENT_LOG_ACCUMULATOR
from utils.helper import json_to_dict
from constants import *
from utils.logger import get_logger
from sequences.sql_sequence import sql_agent_sequence
from sequences.python_sequence import python_agent_sequence
from sequences.starter_sequence import starter_agent_sequence
from utils import semantic_layer
import pandas as pd
from utils.helper import save_img
from google import genai
from utils.visuals import display_image_gallery, apply_sky_style

logger = get_logger(__name__)


def _render_with_semantic_names(text, session=None):
    """Compatibility shim: previously we post-processed agent text to
    replace physical column tokens with semantic names. That feature was
    reverted — keep a no-op shim so older call sites don't crash.

    Returns the original text unchanged (safe for None inputs).
    """
    try:
        if text is None:
            return ""
        return text
    except Exception:
        return text

# Page configuration
st.set_page_config(
    page_title="Metric Mind",
    layout="wide"
)

# Initialize session state
if 'messages' not in st.session_state:
    st.session_state.messages = []
if 'session_id' not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if 'agent_session' not in st.session_state:
    st.session_state.agent_session = None
if 'session_service' not in st.session_state:
    st.session_state.session_service = InMemorySessionService()
if 'artifact_service' not in st.session_state:
    st.session_state.artifact_service = InMemoryArtifactService()

async def process_query(user_query: str, session_id: str):
    """Process user query through the agent pipeline."""
    
    try:
        # Define APP NAME AND USER NAME
        app_name = APP_NAME
        user_id = USER_ID

        #Use session service
        session_service = st.session_state.session_service
        
        #Define Artifact service
        artifact_service = st.session_state.artifact_service

        # Define data schema to be passed as initial_state
        initial_state = json_to_dict(DATA_SCHEMA_PATH)
        initial_state_formatted = {
            'projects': initial_state.get('project_id'),
            'datasets': initial_state.get('dataset_id'),
            'tables': initial_state.get('tables')
        }

        #TO DO: try to pass data schema to be cached instead of cluttering session state

        # Create or get existing session
        if st.session_state.agent_session is None:
            session = await session_service.create_session(
                app_name=app_name,
                user_id=user_id,
                session_id=session_id,
                state=initial_state_formatted
            )
            logger.info(f"Created new session: {session.id}")
        else:
            session = await session_service.get_session(
                app_name=app_name,
                user_id=user_id,
                session_id=session_id
            )
        
        # If the UI has a selected KPI, include a short, explicit KPI context
        # in the user query so agents don't need to re-query the defs table when
        # the KPI is already chosen by the user.
        try:
            ui_selected = st.session_state.get('selected_kpi_meta') or {}
            if ui_selected:
                kpi_ctx = f"[KPI_CONTEXT] KPI_NAME={ui_selected.get('kpi_name')} KPI_ID={ui_selected.get('kpi_id')} AVAILABLE_DIMS={','.join(ui_selected.get('available_dimensions',[]))} -- "
                augmented_query = kpi_ctx + (user_query or "")
            else:
                augmented_query = user_query
        except Exception:
            augmented_query = user_query

        # Call Starter Agent Sequence
        await starter_agent_sequence(app_name, user_id, session_service, artifact_service, session_id, augmented_query)
        
        # Refresh session to get updated state
        session = await session_service.get_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id
        )

        # Decide if SQL sequence is required
        if session.state.get('sql_required'):
            # Call SQL Sequence
            await sql_agent_sequence(app_name, user_id, session_service, artifact_service, session_id, user_query)
            
            # Update session
            session = await session_service.get_session(
                app_name=app_name,
                user_id=user_id,
                session_id=session_id
            )

        # Decide if Python sequence is required
        if session.state.get('python_required'):
            
            # Note: If python_required is True, sql_required is ALWAYS True
            if session.state.get('latest_sql_sequence_outcome') == 'SUCCESS':
                
                # Call Python Sequence
                await python_agent_sequence(app_name, user_id, session_service, artifact_service, session_id, user_query)
                
                # Update session
                session = await session_service.get_session(
                    app_name=app_name,
                    user_id=user_id,
                    session_id=session_id
                )
                
                # Save image artifact from Python sequence
                img_bytes = session.state.get('latest_img_bytes')                
                save_img(img_bytes)                
            else:
                logger.error('SQL sequence failed')

        #update again?
        session = await session_service.get_session(
                app_name=app_name,
                user_id=user_id,
                session_id=session_id
            )

        #Store session for future use
        st.session_state.agent_session = session
        
        return session

    except Exception as e:
        logger.error(f"Error in process_query: {e}", exc_info=True)
        raise e

def display_agent_response(session):
    """Display agent response based on state variables."""
    if session is None:
        st.error("No session available to display")
        return


    # Show only user-facing information by default: greeting, insights,
    # recommendations, and the main result tables/visuals. Internal agent
    # diagnostics and event logs are hidden behind the clickable
    # "What I did" expander for analysts.
    state = session.state

    # User-facing header/greeting
    greeting = state.get('greeting', '')
    if greeting:
        st.markdown(f"**{greeting}**")
        st.divider()

    # Collate a lightweight user-facing summary
    user_insights = state.get('latest_sql_output_reasoning') or ''
    user_visual_insights = state.get('latest_python_code_output_reasoning') or ''
    recommendations = state.get('latest_recommendations') or ''

    # Present SQL-derived insights first (concise)
    if state.get('sql_required'):
        st.subheader("Results & Insights")
        # Prefer a human-readable reasoning block if present
        if user_insights:
            st.markdown(user_insights, unsafe_allow_html=True)

        # Show result table (if available) as a clean dataframe
        sql_rows = state.get('latest_sql_response')
        if sql_rows:
            st.markdown('**Result table:**')
            try:
                df = pd.DataFrame(sql_rows)
                st.dataframe(df, use_container_width=True)
            except Exception:
                st.code(str(sql_rows))

    # Present visualization insights
    if state.get('python_required'):
        if user_visual_insights:
            st.subheader("Visualization Insights")
            st.markdown(user_visual_insights, unsafe_allow_html=True)

        # Show the latest image for the session (if saved)
        img_path = None
        try:
            img_path = state.get('latest_img_path')
        except Exception:
            img_path = None

        if img_path:
            st.image(img_path, use_container_width=True)

    # Recommendations block (if any)
    if recommendations:
        st.subheader("Recommendations")
        st.markdown(recommendations, unsafe_allow_html=True)

    # Clickable diagnostics for analysts: show the internal events, tool calls
    # and raw agent outputs when explicitly requested.
    with st.expander("What I did (click to expand)", expanded=False):
        st.markdown("**Event Log / Agent Internals**")
        # Event accumulator (shows tool responses, parsed json, token counts)
        try:
            st.json(EVENT_LOG_ACCUMULATOR)
        except Exception:
            st.text(str(EVENT_LOG_ACCUMULATOR))

        st.markdown("**Session State (sanitised)**")
        try:
            # don't attempt to render enormous binary blobs
            safe_state = {k: (v if not isinstance(v, (bytes, bytearray)) else f"<binary {len(v)} bytes>") for k, v in state.items()}
            st.json(safe_state)
        except Exception:
            st.text(str(state))

        st.markdown("**Latest Tool Calls / Responses**")
        try:
            # show recent tool call/response entries from the last final_response
            recent_tools = {}
            for k, v in state.items():
                if isinstance(k, str) and (k.startswith('[tool_call]') or k.startswith('[tool_response]')):
                    recent_tools[k] = v
            if recent_tools:
                st.json(recent_tools)
            else:
                st.text('No explicit tool call/response entries found in session state')
        except Exception:
            st.text('Could not extract tool call/response info')

def display_debug_info(session):
    """Display debug information in the sidebar."""
    if session is None or not hasattr(session, 'state'):
        st.warning("No session data available")
        return
    
    state = session.state
    
    st.markdown("### Debugger")
    
    #COMPLETE FLOW
    with st.expander("Event Log",expanded=False):
        st.json(EVENT_LOG_ACCUMULATOR)
        
    # Starter Agent Response
    with st.expander("Starter Agent Response", expanded=False):
        starter_response = state.get('starter_agent_response', 'N/A')
        st.json(starter_response if isinstance(starter_response, dict) else str(starter_response))

    # SQL Analysis
    with st.expander("SQL Analysis Details", expanded=False):
        st.text("Latest Output Reasoning:")
        st.code(_render_with_semantic_names(state.get('latest_sql_output_reasoning', 'N/A'), session), language=None)
        
        st.text("Latest SQL Criticism:")
        st.code(state.get('latest_sql_criticism', 'N/A'), language=None)
        
        st.text("Latest SQL Output:")
        sql_output = state.get('latest_sql_output', 'N/A')
        if isinstance(sql_output, (list, dict)):
            st.json(sql_output)
        else:
            st.code(str(sql_output), language=None)
        
        st.text("Latest BQ Execution Status:")
        st.code(state.get('latest_bq_execution_status', 'N/A'), language=None)
    
    # Python Code Details
    with st.expander("Python Code Details", expanded=False):
        st.text("Latest Code Output Reasoning:")
        st.code(_render_with_semantic_names(state.get('latest_python_code_output_reasoning', 'N/A'), session), language=None)
        
        st.text("Latest Code Criticism:")
        st.code(state.get('latest_python_code_criticism', 'N/A'), language=None)
        
        st.text("Latest Code Output:")
        st.code(state.get('latest_python_code_output', 'N/A'), language='python')
        
        st.text("Latest Code Execution Outcome:")
        st.code(state.get('latest_python_code_execution_outcome', 'N/A'), language=None)
    
    # Image Bytes Info
    with st.expander("Image Info", expanded=False):
        img_bytes = state.get('latest_img_bytes')
        if img_bytes:
            st.text(f"Image size: {len(img_bytes)} bytes")
            st.text(f"Type: {type(img_bytes)}")
        else:
            st.text("No image bytes available")
    
    # Metrics
    with st.expander("Metrics", expanded=False):
        # col1, col2, col3 = st.columns(3)
        col1, col2 = st.columns(2)

        with col1:
            # st.metric(
            #     label="BQ API Failures",
            #     value=state.get('app:bq_api_failure_count', 0)
            # )
            st.metric(
                label="Total Tokens",
                value=state.get('app:total_token_count', 0)
            )
            # st.metric(
            #     label="Prompt Tokens",
            #     value=state.get('app:prompt_token_count', 0)
            # )
        
        with col2:
            st.metric(
            label="Cached Content Tokens",
            value=state.get('app:cached_content_token_count', 0)
            )
            # st.metric(
            #     label="Tool Use Prompt Tokens",
            #     value=state.get('app:tool_use_prompt_token_count', 0)
            # )
            # st.metric(
            #     label="Thoughts Tokens",
            #     value=state.get('app:thoughts_token_count', 0)
            # )
            # st.metric(
            #     label="Candidates Tokens",
            #     value=state.get('app:candidates_token_count', 0)
            # )
    
    # with col3:
    #     st.metric(
    #         label="Cached Content Tokens",
    #         value=state.get('app:cached_content_token_count', 0)
    #     )
    #     st.metric(
    #         label="Cache Invocations",
    #         value=state.get('app:cache_invocations_used', 0)
    #     )
    #     st.metric(
    #         label="Cached Contents Count",
    #         value=state.get('app:cached_contents_count', 0)
    #     )

def main():
    """Main Streamlit application."""
    import os

    # Log working directory and effective semantic schema path for debugging
    try:
        schema_env = os.environ.get("SEMANTIC_SCHEMA_PATH", "metricmind_schema.json")
        resolved = os.path.abspath(schema_env)
        logger.info("App starting. CWD=%s SEMANTIC_SCHEMA_PATH=%s (resolved=%s)", os.getcwd(), schema_env, resolved)
        # also log whether the file exists at the resolved location
        try:
            logger.info("Schema file exists at resolved path: %s", os.path.exists(resolved))
        except Exception:
            logger.debug("Could not stat resolved schema path: %s", resolved)
    except Exception:
        logger.debug("Failed to log startup filesystem info")

    # Header
    st.title("Metric Mind")

    # Initialize semantic layer (load file or build if necessary)
    try:
        semantic_layer.initialize()
    except Exception:
        logger.exception("Failed to initialize semantic layer")

    # Apply a Sky-inspired plotting style for any local plotting we do
    try:
        apply_sky_style()
    except Exception:
        logger.debug("Could not apply sky style")

    # Intro from the assistant about its purpose
    st.markdown("**Hey, I'm Metric Mind.** I hold information on various business metrics that I can slice and dice for you. Use the controls in the sidebar to pick a KPI, see its description and available dimensions, and insert it into the chat to ask questions about it.")
    # st.markdown("Ask questions about your BigQuery data and get SQL analysis with visualizations.")
    
    # Sidebar
    with st.sidebar:
        st.header("Session Info")
        st.text(f"Session ID: {st.session_state.session_id}")
        
        if st.button("Create New Session"):
            st.session_state.messages = []
            st.session_state.session_id = str(uuid.uuid4())
            st.session_state.agent_session = None
            st.session_state.session_service = InMemorySessionService()
            st.rerun()
        
        st.markdown("---")
        
        # (Sidebar restored to original layout) a divider separates session info from debug
        
        # Display debug info if session exists
        if st.session_state.agent_session is not None:
            display_debug_info(st.session_state.agent_session)
        else:
            st.info("Start a conversation to see debug information")

    # KPI selector in main area (inserts into main chat window)
    try:
        kpi_names_main = semantic_layer.get_kpi_list(limit=500, sort=True)
    except Exception:
        kpi_names_main = []

    # Handler: when a KPI is selected from the main selectbox, create a session
    # and insert the assistant guidance immediately (avoids needing to click
    # multiple times). We use a simple last-selected guard to avoid duplicates.
    def _on_kpi_select_main():
        sel = st.session_state.get("kpi_select_main", "-- none --")
        logger.info("KPI select handler triggered; sel=%s", sel)
        if not sel or sel == "-- none --":
            return

        last = st.session_state.get("_last_kpi_inserted", None)
        if last == sel:
            return

        try:
            selected_def = semantic_layer.get_kpi_def_by_name(sel)
        except Exception:
            logger.exception("Failed to lookup KPI definition in on_change handler")
            return

        if not selected_def:
            return

        kpi_id = selected_def.get('kpi_id')
        kpi_name = selected_def.get('kpi_name')

        # derive available dimensions defensively
        raw_dims = selected_def.get('dimensions')
        dims_list = []
        try:
            if isinstance(raw_dims, dict):
                dims_list = list(raw_dims.keys())
            elif isinstance(raw_dims, list):
                dims_list = raw_dims
        except Exception:
            dims_list = []

        # Build a short assistant guidance message (similar to the button behavior)
        ints = selected_def.get('indicators_int') or []
        floats = selected_def.get('indicators_float') or []

        def _fmt_indicators(lst):
            out = []
            for ind in lst:
                nm = ind.get('name') or ''
                phys = ind.get('physical_column') or ''
                agg = ind.get('aggregation') or ''
                if agg:
                    out.append(f"{nm} ({phys}) - agg: {agg}")
                else:
                    out.append(f"{nm} ({phys})")
            return out

        ints_list = _fmt_indicators(ints)
        floats_list = _fmt_indicators(floats)

        lines = [
            f"Okay — you're interested in **{kpi_name}** (KPI_ID={kpi_id}). I can help you query this KPI, but first I need a little more detail so I build the correct SQL.",
            "\nPlease tell me:",
            " - The time window (e.g. a single date, 'last 7 days', 'this month', '2025-01-01 to 2025-03-31', 'last 90 days').",
            " - The aggregation level you want (e.g. daily, weekly, monthly) and the measure aggregation (sum, avg, count).",
            " - Any dimension(s) to split or filter by (e.g. Country, Product, TV Service).",
        ]

        if ints_list:
            lines.append("\n**Available integer measures:**")
            for s in ints_list:
                lines.append(f" - {s}")
        if floats_list:
            lines.append("\n**Available float measures:**")
            for s in floats_list:
                lines.append(f" - {s}")

        if dims_list:
            lines.append("\n**Available dimensions:**")
            for d in dims_list:
                lines.append(f" - {d}")

        lines.append("\nExample questions you can ask:")
        top_dim = dims_list[0] if dims_list else 'dimension'
        example_prompts = [
            f"What is the current value of '{kpi_name}' as of today?",
            f"Show the trend for '{kpi_name}' over the last 30 days (daily totals).",
            f"Compare monthly totals of '{kpi_name}' for the last 3 months.",
            f"Give the top 5 {top_dim} by '{kpi_name}' for the last 90 days.",
            f"Show '{kpi_name}' broken down by TV Service for last month (monthly averages).",
        ]
        for p in example_prompts:
            lines.append(f" - {p}")

        lines.append("\nReply with one of the example prompts or describe the exact time window, aggregation and any filters you want.")

        assistant_text = "\n".join(lines)

        # Store lightweight selected KPI metadata in Streamlit session state
        # (avoid storing complex session objects which can cause Streamlit to hang)
        try:
            st.session_state['selected_kpi_meta'] = {
                'kpi_id': kpi_id,
                'kpi_name': kpi_name,
                'available_dimensions': dims_list
            }
        except Exception:
            logger.exception('Failed to write selected_kpi_meta to session_state')

        # Append assistant guidance and mark as inserted
        st.session_state.messages.append({"role": "assistant", "content": assistant_text})
        st.session_state._last_kpi_inserted = sel
        # Do not call experimental_rerun or st.stop here; allow Streamlit to
        # naturally re-render. For debugging, log that the handler completed.
        logger.info("KPI select handler completed for %s", sel)
    with st.expander("Available KPIs", expanded=False):
        selected_kpi_name_main = st.selectbox("Choose a KPI:", options=["-- none --"] + kpi_names_main, index=0, key="kpi_select_main", on_change=_on_kpi_select_main)
        selected_kpi_def_main = None
        if selected_kpi_name_main and selected_kpi_name_main != "-- none --":
            selected_kpi_def_main = semantic_layer.get_kpi_def_by_name(selected_kpi_name_main)

        if selected_kpi_def_main:
            st.markdown(f"**{selected_kpi_def_main.get('kpi_name')}**")
            desc = selected_kpi_def_main.get('kpi_description') or "(no description)"
            st.caption(desc)

            # Always fetch available dimensions from the semantic layer definition.
            raw_dims = selected_kpi_def_main.get('dimensions')
            dims_main = []
            try:
                if isinstance(raw_dims, dict):
                    dims_main = list(raw_dims.keys())
                elif isinstance(raw_dims, list):
                    dims_main = raw_dims
            except Exception:
                dims_main = []

            if dims_main:
                # Show the available dimension names (agent will ask for selections)
                st.text(f"Available dimensions: {', '.join(dims_main)}")
            else:
                st.text("No dimensions available for this KPI")

            if st.button("Insert KPI into chat", key="insert_kpi_main"):
                # Build a conversational assistant acknowledgement instead of auto-running SQL
                kpi_id = selected_kpi_def_main.get('kpi_id')
                kpi_name = selected_kpi_def_main.get('kpi_name')
                ints = selected_kpi_def_main.get('indicators_int') or []
                floats = selected_kpi_def_main.get('indicators_float') or []

                def fmt_indicators(lst):
                    out = []
                    for ind in lst:
                        nm = ind.get('name') or ''
                        phys = ind.get('physical_column') or ''
                        agg = ind.get('aggregation') or ''
                        if agg:
                            out.append(f"{nm} ({phys}) - agg: {agg}")
                        else:
                            out.append(f"{nm} ({phys})")
                    return out

                ints_list = fmt_indicators(ints)
                floats_list = fmt_indicators(floats)

                # Assistant guidance text with time-dependency and aggregation examples
                lines = [
                    f"Okay — you're interested in **{kpi_name}** (KPI_ID={kpi_id}). I can help you query this KPI, but first I need a little more detail so I build the correct SQL.",
                    "\nPlease tell me:",
                    " - The time window (e.g. a single date, 'last 7 days', 'this month', '2025-01-01 to 2025-03-31', 'last 90 days').",
                    " - The aggregation level you want (e.g. daily, weekly, monthly) and the measure aggregation (sum, avg, count).",
                    " - Any dimension(s) to split or filter by (e.g. Country, Product, TV Service).",
                ]

                if ints_list:
                    lines.append("\n**Available integer measures:**")
                    for s in ints_list:
                        lines.append(f" - {s}")
                if floats_list:
                    lines.append("\n**Available float measures:**")
                    for s in floats_list:
                        lines.append(f" - {s}")

                lines.append("\nExample questions you can ask:")

                # Determine a safe representative dimension name for examples.
                # `selected_kpi_def_main.get('dimensions')` may be a dict (mapping name->meta)
                # or a simple list of dimension names. Use the already computed `dims_main`
                # (which is a list of names) where possible; otherwise fall back to a generic label.
                top_dim = None
                try:
                    if isinstance(dims_main, list) and len(dims_main) > 0:
                        top_dim = dims_main[0]
                except Exception:
                    top_dim = None

                if not top_dim:
                    # Try to derive from the raw definition defensively
                    raw_dims = selected_kpi_def_main.get('dimensions')
                    if isinstance(raw_dims, dict):
                        keys = list(raw_dims.keys())
                        top_dim = keys[0] if keys else 'dimension'
                    elif isinstance(raw_dims, list):
                        top_dim = raw_dims[0] if raw_dims else 'dimension'
                    else:
                        top_dim = 'dimension'

                example_prompts = [
                    f"What is the current value of '{kpi_name}' as of today?",
                    f"Show the trend for '{kpi_name}' over the last 30 days (daily totals).",
                    f"Compare monthly totals of '{kpi_name}' for the last 3 months.",
                    f"Give the top 5 {top_dim} by '{kpi_name}' for the last 90 days.",
                    f"Show '{kpi_name}' broken down by TV Service for last month (monthly averages).",
                ]
                for p in example_prompts:
                    lines.append(f" - {p}")

                lines.append("\nReply with one of the example prompts or describe the exact time window, aggregation and any filters you want.")

                assistant_text = "\n".join(lines)

                # Ensure an agent session exists and attach the selected KPI to it so
                # the UI and debug sidebar reflect an active session.
                try:
                    session_service = st.session_state.session_service
                    artifact_service = st.session_state.artifact_service
                    app_name = APP_NAME
                    user_id = USER_ID
                    session_id = st.session_state.session_id

                    # Build the initial state payload (same as process_query)
                    init_schema = json_to_dict(DATA_SCHEMA_PATH)
                    initial_state_formatted = {
                        'projects': init_schema.get('project_id'),
                        'datasets': init_schema.get('dataset_id'),
                        'tables': init_schema.get('tables')
                    }

                    if st.session_state.agent_session is None:
                        # Create a session synchronously so Streamlit UI can show debug info
                        session = asyncio.run(session_service.create_session(
                            app_name=app_name,
                            user_id=user_id,
                            session_id=session_id,
                            state=initial_state_formatted
                        ))

                        # Attach selected KPI metadata to the session state for later use
                        try:
                            session.state['selected_kpi'] = {
                                'kpi_id': kpi_id,
                                'kpi_name': kpi_name,
                                'available_dimensions': dims_main
                            }
                        except Exception:
                            # If session.state is not a plain dict-like, ignore safely
                            logger.debug('Could not attach selected_kpi to session.state')

                        st.session_state.agent_session = session
                except Exception:
                    logger.exception('Failed to create session on KPI insert')

                # Append assistant guidance into the chat (user can then reply and trigger the pipeline)
                st.session_state.messages.append({"role": "assistant", "content": assistant_text})

                # show the inserted assistant text immediately
                # Let Streamlit naturally re-render; no forced rerun here.
                pass
    
    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            if message["role"] == "user":
                st.markdown(message["content"])
            else:
                # For assistant, display structured response
                if "session" in message:
                    display_agent_response(message["session"])
                else:
                    st.markdown(message["content"])
    
    # Chat input
    if prompt := st.chat_input("Ask a question about your data..."):
        # Add user message
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        # Display user message
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # Display assistant response
        with st.chat_message("assistant"):
            with st.spinner("Analyzing your query..."):
                try:
                    # Process the query
                    session = asyncio.run(process_query(prompt, st.session_state.session_id))
                    
                    if session is None:
                        raise ValueError("Session is None after processing")
                    
                    # Display response
                    display_agent_response(session)
                    
                    # Save to message history
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": "Response generated",
                        "session": session
                    })
                    
                    # Force sidebar refresh
                    st.rerun()
                    
                except Exception as e:
                    error_msg = f"An error occurred: {str(e)}"
                    st.error(error_msg)
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": error_msg
                    })
                    logger.error(f"Error processing query: {e}", exc_info=True)

if __name__ == "__main__":
    main()