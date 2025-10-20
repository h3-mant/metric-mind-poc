from google.genai import types
from google.adk.agents.callback_context import CallbackContext
from typing import Optional
from constants import *
from pydantic_models import StarterAgentResponse
import json

def sql_refiner_agent_callback(callback_context: CallbackContext) -> Optional[types.Content]:

  agent_name = callback_context.agent_name
  #skip condition
  if callback_context.state.get('latest_sql_criticism') == OUTCOME_OK_PHRASE:
    
    return types.Content(
            parts=[types.Part(text=f"Agent {agent_name} skipped since {OUTCOME_OK_PHRASE}")],
            role="model" # Assign model role to the overriding response
        )

  return None # Return None to allow the LlmAgent's normal execution

async def python_refiner_agent_callback(callback_context: CallbackContext) -> Optional[types.Content]:

  agent_name = callback_context.agent_name
  #skip condition
  if callback_context.state.get('latest_python_code_criticism') == OUTCOME_OK_PHRASE:

    return types.Content(
            parts=[types.Part(text=f"Agent {agent_name} skipped since {OUTCOME_OK_PHRASE}")],
            role="model" # Assign model role to the overriding response
        )
  return None # Return None to allow the LlmAgent's normal execution

def store_results_in_context(callback_context: CallbackContext) -> None:
  """save JSON output into state"""

  #pydantic parses to dict format
  response_dict = callback_context.state.get('starter_agent_response')

  # Validate using Pydantic
  parsed_response = StarterAgentResponse.model_validate(response_dict)
  
  # Store in state for downstream agents to access
  callback_context.state['greeting'] = parsed_response.greeting
  callback_context.state['user_intent'] = parsed_response
  callback_context.state['python_required'] = parsed_response.python_required
  
  #force SQL requirement if python is required
  callback_context.state['sql_required'] = True if callback_context.state['python_required'] else parsed_response.sql_required
  

