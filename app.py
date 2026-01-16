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
import pandas as pd
from utils.helper import save_img
from google import genai

logger = get_logger(__name__)

# Page configuration
st.set_page_config(
    page_title="Metric Mind",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for Sky branding and styling
st.markdown("""
<style>
    /* Sky Broadband color scheme */
    :root {
        --sky-blue: #003D7A;
        --sky-cyan: #0099CC;
        --sky-light: #E8F4FF;
        --sky-white: #F5F5F5;
    }
    
    /* Main page background */
    .stApp {
        background: linear-gradient(135deg, #FFFFFF 0%, #F0F7FF 100%);
    }
    
    /* Sidebar background */
    .stSidebar {
        background-color: #F5F5F5 !important;
    }
    
    /* Header styling */
    h1 {
        color: #003D7A !important;
        font-weight: 800 !important;
        letter-spacing: -0.5px;
    }
    
    /* Bio text styling */
    .bio-text {
        color: #003D7A;
        font-size: 15px;
        font-weight: 600;
        margin-bottom: 24px;
        padding: 14px 16px;
        background: linear-gradient(90deg, #E8F4FF 0%, #F0F8FF 100%);
        border-left: 5px solid #0099CC;
        border-radius: 6px;
    }
    
    /* Expander styling */
    .streamlit-expanderHeader {
        background-color: #E8F4FF !important;
        color: #003D7A !important;
        border-radius: 6px !important;
    }
    
    /* Button styling */
    .stButton > button {
        background: linear-gradient(135deg, #0099CC 0%, #0077AA 100%) !important;
        color: white !important;
        border: none !important;
        border-radius: 6px !important;
        font-weight: 700 !important;
        box-shadow: 0 2px 8px rgba(0, 153, 204, 0.3) !important;
    }
    
    .stButton > button:hover {
        background: linear-gradient(135deg, #0077AA 0%, #005580 100%) !important;
        box-shadow: 0 4px 12px rgba(0, 153, 204, 0.4) !important;
    }
    
    /* Divider styling */
    hr {
        border-color: #0099CC !important;
        margin: 20px 0 !important;
    }
    
    /* Text styling */
    body {
        color: #003D7A !important;
    }
</style>
""", unsafe_allow_html=True)

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

        # Define defs schema to be passed as initial_state
        defs_schema = json_to_dict(DEFS_SCHEMA_PATH)

        data_schema = json_to_dict(DATA_SCHEMA_PATH)

        initial_state_formatted = {
            'projects': "uk-dta-gsmanalytics-poc",
            'datasets': "metricmind",
            'tables': "GSM_KPI_DATA_TEST_V5",
            'schema_structure': defs_schema,
            'schema_context': data_schema
        }

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
        
        # Call Starter Agent Sequence
        await starter_agent_sequence(app_name, user_id, session_service, artifact_service, session_id, user_query)
        
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
        
    state = session.state
    
    # Always display greeting
    greeting = state.get('greeting', '')
    if greeting:
        st.markdown(f"**{greeting}**")
        st.divider()
    
    # Handle SQL sequence output
    if state.get('sql_required'):
        st.subheader("SQL Analysis")
        
        sql_outcome = state.get('latest_sql_sequence_outcome')
        
        if sql_outcome == 'SUCCESS':
            # Display both SQL response and output
            sql_response = state.get('latest_sql_response', '')
            sql_output_reasoning = state.get('latest_sql_output_reasoning', '')
            
            if sql_output_reasoning:
                with st.expander("**SQL Analysis**", expanded=True):
                    st.markdown(sql_output_reasoning, unsafe_allow_html=True)

            if sql_response:
                st.markdown('**SQL Response:**')
                df = pd.DataFrame(sql_response)
                st.dataframe(df, width='stretch')
            
        else:
            # Display only reasoning
            sql_output_reasoning = state.get('latest_sql_output_reasoning', 'SQL sequence encountered an error.')
            st.markdown("**SQL Status:**")
            st.warning(sql_output_reasoning)
    
    # Handle Python sequence output
    if state.get('python_required'):
        st.subheader("Visualization")
        
        python_outcome = state.get('latest_python_sequence_outcome')
        
        if python_outcome == 'SUCCESS':
            # Display Python response
            python_response = state.get('latest_python_code_output_reasoning', '')
            if python_response: 
                with st.expander("**Visualization Analysis**", expanded=False):
                    st.markdown(python_response, unsafe_allow_html=True)
            
            # Display the most recently saved image
            img_dir = Path("images")
            if img_dir.exists():
                png_files = list(img_dir.glob("img_*.png"))
                if png_files:
                    latest_img = max(png_files, key=lambda f: f.stat().st_mtime)
                    st.image(str(latest_img), caption=f"Generated Visualization ({latest_img.name})", width='content')
                else:
                    st.warning("Visualization was generated but no image files found in the directory.")
            else:
                st.warning("Visualization directory not found.")

        else:
            # Display only Python response (error case)
            python_response = state.get('latest_python_code_output_reasoning', 'Visualization generation encountered an error.')
            st.markdown("**Visualization Status:**")
            st.warning(python_response)

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
        st.code(state.get('latest_sql_output_reasoning', 'N/A'), language=None)
        
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
        st.code(state.get('latest_python_code_output_reasoning', 'N/A'), language=None)
        
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

def display_kpi_reference():
    """Display KPI reference dropdown with KPI names and definitions."""
    schema_context = json_to_dict(SCHEMA_CONTEXT_PATH)
    kpis = schema_context.get('kpis', {})
    
    # Create a dataframe with KPI information
    kpi_data = []
    for kpi_id, kpi_info in kpis.items():
        kpi_data.append({
            'KPI ID': kpi_info.get('kpi_id', ''),
            'KPI Name': kpi_info.get('kpi_name', ''),
            'Description': kpi_info.get('kpi_description', '')
        })
    
    if kpi_data:
        with st.expander("KPI Reference", expanded=False):
            df_kpis = pd.DataFrame(kpi_data)
            st.dataframe(
                df_kpis,
                width='stretch',
                hide_index=True,
                column_config={
                    "KPI ID": st.column_config.TextColumn(width="medium"),
                    "KPI Name": st.column_config.TextColumn(width="medium"),
                    "Description": st.column_config.TextColumn(width="large")
                }
            )

def main():
    """Main Streamlit application."""
    
    # Header with logo and title
    col1, col2, col3 = st.columns([0.15, 0.7, 0.15])
    
    with col1:
        # Try to load Sky logo, fallback to emoji if not found
        logo_path = Path("SKY_NEW_LOGO.png")
        if logo_path.exists():
            st.image(str(logo_path), width=120)
        else:
            st.markdown("<div style='font-size: 60px; text-align: center;'>☁️</div>", unsafe_allow_html=True)
    
    with col2:
        st.markdown("<h1 style='text-align: center; margin-top: 10px;'>Metric Mind</h1>", unsafe_allow_html=True)
    
    with col3:
        st.empty()
    
    # Bio line
    st.markdown(
        "<div class='bio-text'>Conversational AI agent for Sky TV, Broadband & Mobile Service Analytics | "
        "Fast self-service intelligence for stakeholders</div>",
        unsafe_allow_html=True
    )
    
    # Display KPI reference
    display_kpi_reference()
    
    st.markdown("---")

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
        
        # Display debug info if session exists
        if st.session_state.agent_session is not None:
            display_debug_info(st.session_state.agent_session)
        else:
            st.info("Start a conversation to see debug information")
    
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