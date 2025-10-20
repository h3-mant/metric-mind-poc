import streamlit as st
import asyncio
import uuid
from pathlib import Path
from google.adk.sessions import InMemorySessionService
from utils import EVENT_LOG_ACCUMULATOR
from utils.helper import json_to_dict
from constants import *
from utils.logger import get_logger
from sequences.sql_sequence import sql_agent_sequence
from sequences.python_sequence import python_agent_sequence
from sequences.starter_sequence import starter_agent_sequence
import pandas as pd
from google import genai

logger = get_logger(__name__)

# Page configuration
st.set_page_config(
    page_title="Metric Mind",
    page_icon="🤖",
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

async def process_query(user_query: str, session_id: str):
    """Process user query through the agent pipeline."""
    try:
        # Define APP NAME AND USER NAME
        app_name = APP_NAME
        user_id = USER_ID

        #Use session service
        session_service = st.session_state.session_service
        
        # Define data schema to be passed as initial_state
        initial_state = json_to_dict(DATA_SCHEMA_PATH)
        initial_state_formatted = {
            'projects': initial_state.get('project_id'),
            'datasets': initial_state.get('dataset_id'),
            'tables': initial_state.get('tables')
        }

        #try to pass data schema to be cached instead of cluttering session state
        #this is now defined within agent definitions

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

        #Ensure session has state
        if session is None:
            logger.error("Session is None after creation/retrieval")
            raise ValueError("Failed to create or retrieve session")

        #reset outcome variables for new query
        session.state['sql_sequence_outcome'] = None
        session.state['python_sequence_outcome'] = None
        
        # Call Starter Agent Sequence
        await starter_agent_sequence(app_name, user_id, session_service, session_id, user_query)
        
        # Refresh session to get updated state
        session = await session_service.get_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id
        )

        if session is None:
            raise ValueError("Session became None after starter sequence")

        # Decide if SQL sequence is required
        if session.state.get('sql_required'):
            # Call SQL Sequence
            await sql_agent_sequence(app_name, user_id, session_service, session_id, user_query)
            
            # Update session
            session = await session_service.get_session(
                app_name=app_name,
                user_id=user_id,
                session_id=session_id
            )

        # Decide if Python sequence is required
        # Note: If python_required is True, sql_required is ALWAYS True
        if session.state.get('python_required'):
            # Check if SQL sequence was successful
            sql_success = (
                session.state.get('latest_sql_criticism') == OUTCOME_OK_PHRASE and
                session.state.get('latest_bq_execution_status', '').upper() == 'SUCCESS'
            )
            
            if sql_success:
                session.state['sql_sequence_outcome'] = 'SUCCESS'
                
                # Call Python Sequence
                await python_agent_sequence(app_name, user_id, session_service, session_id, user_query)
                
                # Update session
                session = await session_service.get_session(
                    app_name=app_name,
                    user_id=user_id,
                    session_id=session_id
                )
                
                # Save image artifact from Python sequence
                img_bytes = session.state.get('latest_img_bytes')
                if img_bytes:
                    from utils.helper import save_img
                    result = save_img(img_bytes)
                    session.state['python_sequence_outcome'] = result
                else:
                    session.state['python_sequence_outcome'] = 'FAILURE'
            else:
                session.state['sql_sequence_outcome'] = 'FAILURE'
        
        #Handle SQL-only case
        elif session.state.get('sql_required') and not session.state.get('python_required'):
            # Set SQL outcome based on execution status
            sql_success = (
                session.state.get('latest_sql_criticism') == OUTCOME_OK_PHRASE and
                session.state.get('latest_bq_execution_status', '').upper() == 'SUCCESS'
            )
            session.state['sql_sequence_outcome'] = 'SUCCESS' if sql_success else 'FAILURE'

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
        st.markdown("---")
    
    # Handle SQL sequence output
    if state.get('sql_required'):
        st.subheader("📊 SQL Analysis")
        
        sql_outcome = state.get('sql_sequence_outcome')
        
        if sql_outcome == 'SUCCESS':
            # Display both SQL response and output
            sql_response = state.get('latest_sql_response', '')
            sql_output_reasoning = state.get('latest_sql_output_reasoning', '')
            
            if sql_response:
                st.markdown('**SQL Response:**')
                df = pd.DataFrame(sql_response)
                st.dataframe(df)
            
            if sql_output_reasoning:
                st.markdown("**Analysis:**")
                st.success(sql_output_reasoning)
        else:
            # Display only reasoning
            sql_output_reasoning = state.get('latest_sql_output_reasoning', 'SQL sequence encountered an error.')
            st.markdown("**SQL Status:**")
            st.warning(sql_output_reasoning)
    
    # Handle Python sequence output
    if state.get('python_required'):
        st.subheader("📈 Visualization")
        
        python_outcome = state.get('python_sequence_outcome')
        
        if python_outcome == 'SUCCESS':
            # Display Python response
            python_response = state.get('latest_python_response', '')
            if python_response:
                st.markdown("**Visualization Insight:**")
                st.info(python_response)
            
            # Display the saved image
            img_path = Path('images/img.png')
            if img_path.exists():
                st.image(str(img_path), caption="Generated Visualization", use_container_width=True)
            else:
                st.warning("Visualization was generated but image file not found.")
        else:
            # Display only Python response (error case)
            python_response = state.get('latest_python_response', 'Visualization generation encountered an error.')
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
        st.text("Output Reasoning:")
        st.code(state.get('latest_sql_output_reasoning', 'N/A'), language=None)
        
        st.text("SQL Criticism:")
        st.code(state.get('latest_sql_criticism', 'N/A'), language=None)
        
        st.text("SQL Output:")
        sql_output = state.get('latest_sql_output', 'N/A')
        if isinstance(sql_output, (list, dict)):
            st.json(sql_output)
        else:
            st.code(str(sql_output), language=None)
        
        st.text("BQ Execution Status:")
        st.code(state.get('latest_bq_execution_status', 'N/A'), language=None)
    
    # Python Code Details
    with st.expander("Python Code Details", expanded=False):
        st.text("Code Output Reasoning:")
        st.code(state.get('latest_python_code_output_reasoning', 'N/A'), language=None)
        
        st.text("Code Criticism:")
        st.code(state.get('latest_python_code_criticism', 'N/A'), language=None)
        
        st.text("Code Output:")
        st.code(state.get('latest_python_code_output', 'N/A'), language='python')
        
        st.text("Code Execution Outcome:")
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
    with st.expander("Metrics", expanded=True):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric(
                label="BQ API Failures",
                value=state.get('app:bq_api_failure_count', 0)
            )
            st.metric(
                label="Total Tokens",
                value=state.get('app:total_token_count', 0)
            )
            st.metric(
                label="Prompt Tokens",
                value=state.get('app:prompt_token_count', 0)
            )
        
        with col2:
            st.metric(
                label="Tool Use Prompt Tokens",
                value=state.get('app:tool_use_prompt_token_count', 0)
            )
            st.metric(
                label="Thoughts Tokens",
                value=state.get('app:thoughts_token_count', 0)
            )
            st.metric(
                label="Candidates Tokens",
                value=state.get('app:candidates_token_count', 0)
            )
    
    with col3:
        st.metric(
            label="Cached Content Tokens",
            value=state.get('app:cached_content_token_count', 0)
        )
        st.metric(
            label="Cache Invocations",
            value=state.get('app:cache_invocations_used', 0)
        )
        st.metric(
            label="Cached Contents Count",
            value=state.get('app:cached_contents_count', 0)
        )

def main():
    """Main Streamlit application."""
    
    # Header
    st.title("🤖 Data Analysis Agent")
    st.markdown("Ask questions about your BigQuery data and get SQL analysis with visualizations.")
    
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