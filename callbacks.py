from google.genai import types
from google.adk.agents.callback_context import CallbackContext
from typing import Optional
from utils.logger import get_logger
from google.adk.tools.base_tool import BaseTool
from typing import Dict, Any
from google.adk.tools.tool_context import ToolContext
from constants import *
from pydantic_models import StarterAgentResponse
import base64
import re
import io
import json

logger = get_logger(__name__)

def sql_refiner_agent_callback(callback_context: CallbackContext) -> Optional[types.Content]:

  agent_name = callback_context.agent_name
  #skip condition
  if callback_context.state.get('latest_sql_criticism') == OUTCOME_OK_PHRASE:
    
    return types.Content(
            parts=[types.Part(text=f"Agent {agent_name} skipped since {OUTCOME_OK_PHRASE}")],
            role="model" # Assign model role to the overriding response
        )

  return None # Return None to allow the LlmAgent's normal execution

def python_refiner_agent_callback(callback_context: CallbackContext) -> Optional[types.Content]:

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

  #pydantic parses format
  response_dict = callback_context.state.get('starter_agent_response')

  # Validate using Pydantic
  parsed_response = StarterAgentResponse.model_validate(response_dict)
  
  # Store in state for downstream agents to access
  callback_context.state['greeting'] = parsed_response.greeting
  callback_context.state['user_intent'] = parsed_response
  callback_context.state['python_required'] = parsed_response.python_required
  
  #force SQL requirement if python is required
  callback_context.state['sql_required'] = True if callback_context.state['python_required'] else parsed_response.sql_required


def get_sequence_outcome(callback_context: CallbackContext) -> None:
  """get the sequence outcome of SQL/Python Agent"""
  
  if 'sql' in callback_context.agent_name:
    if callback_context.state.get('latest_sql_criticism') == OUTCOME_OK_PHRASE and \
    callback_context.state.get('latest_bq_execution_status') == 'SUCCESS':

      callback_context.state['latest_sql_sequence_outcome'] = 'SUCCESS'
    else:
      callback_context.state['latest_sql_sequence_outcome'] = 'FAILURE'

  if 'python' in callback_context.agent_name:
    if callback_context.state.get('latest_python_code_criticism') == OUTCOME_OK_PHRASE and 'OK' in callback_context.state.get('latest_python_code_execution_outcome'):
    
      callback_context.state['latest_python_sequence_outcome'] = 'SUCCESS'
    else:
      callback_context.state['latest_python_sequence_outcome'] = 'FAILURE'

  return None


async def store_image_artifact(
    tool: BaseTool,
    args: Dict[str, Any],
    tool_context: ToolContext,
    tool_response: Dict
) -> None:
    try:
        inline_data = tool_response.get("inline_data")

        if not inline_data:
            raise ValueError("inline_data missing from tool response")

        # inline_data may be JSON string or dict
        if isinstance(inline_data, str):
            payload = json.loads(inline_data)
        else:
            payload = inline_data

        image_gcs_uri = payload.get("image_gcs_uri")
        image_signed_url = payload.get("image_signed_url")

        if not image_gcs_uri:
            raise ValueError("image_gcs_uri missing in tool response")

        # Validate bucket (optional safety check)
        if not image_gcs_uri.startswith("gs://metric-mind-images/"):
            raise ValueError("Image not stored in expected bucket")

        logger.info(f"GCS image recorded: {image_gcs_uri}")

    except Exception as e:
        logger.error(f"Error extracting GCS image URL: {e}")


# async def store_image_artifact(tool: BaseTool, args: Dict[str, Any], tool_context: ToolContext, tool_response: Dict) -> None:
#     try:
#         # The response contains a Markdown image tag — extract base64 string
#         markdown_str = tool_response.get('inline_data', '')
#         match = re.search(r"data:image/png;base64,([A-Za-z0-9+/=]+)", markdown_str)
#         if not match:
#             raise ValueError("No valid base64 image string found in response")

#         image_base64 = match.group(1)
#         image_bytes = base64.b64decode(image_base64)

#         filename = "image.png"
#         image_artifact = types.Part.from_bytes(
#             data=image_bytes,
#             mime_type="image/png"
#         )

#         version = await tool_context.save_artifact(
#             filename=filename,
#             artifact=image_artifact
#         )
#         logger.info(f"Successfully saved image artifact '{filename}' as version {version}.")

#     except Exception as e:
#         logger.error(f"Error saving image artifact: {e}")

  

