from google.genai import types
from google.adk.agents.callback_context import CallbackContext
from typing import Optional
from constants import *

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
