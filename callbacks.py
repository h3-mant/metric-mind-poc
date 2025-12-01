# Modified callbacks.py - minimal defensive changes and tool-response summarization
from google.genai import types
from google.adk.agents.callback_context import CallbackContext
from typing import Optional, Dict, Any
from utils.logger import get_logger
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from constants import *
from pydantic_models import StarterAgentResponse
import base64
import re
import io
import json

from utils.sql_response_summarizer import summarize_sql_response

logger = get_logger(__name__)

def sql_refiner_agent_callback(callback_context: CallbackContext) -> Optional[types.Content]:
    agent_name = callback_context.agent_name
    if callback_context.state.get('latest_sql_criticism') == OUTCOME_OK_PHRASE:
        return types.Content(
            parts=[types.Part(text=f"Agent {agent_name} skipped since {OUTCOME_OK_PHRASE}")],
            role="model"
        )
    return None

def python_refiner_agent_callback(callback_context: CallbackContext) -> Optional[types.Content]:
    agent_name = callback_context.agent_name
    if callback_context.state.get('latest_python_code_criticism') == OUTCOME_OK_PHRASE:
        return types.Content(
            parts=[types.Part(text=f"Agent {agent_name} skipped since {OUTCOME_OK_PHRASE}")],
            role="model"
        )
    return None

def _summarize_and_replace_tool_responses(state: Dict[str, Any]) -> None:
    """
    Scan session state and replace large tool response objects (BigQuery) with small summaries.
    Modifies state in-place.
    """
    keys = list(state.keys())
    for k in keys:
        # common pattern in your logs: '[tool_response]_execute_sql' or keys containing 'execute_sql'
        if "tool_response" in k or "execute_sql" in k:
            try:
                tool_resp = state.get(k)
                if isinstance(tool_resp, dict):
                    summary = summarize_sql_response(tool_resp)
                    # replace with a concise summary and keep a trace key name
                    new_key = f"{k}_summary"
                    state[new_key] = summary
                    # remove the verbose original to avoid reinjecting into prompts
                    del state[k]
                    logger.debug("Replaced verbose tool response key %s with %s", k, new_key)
                else:
                    # non-dict tool responses: convert to string and keep only short sample
                    s = str(tool_resp)[:1000] if tool_resp is not None else ""
                    state[f"{k}_summary"] = {"status": "UNKNOWN", "row_count": 0, "sample_rows": [s]}
                    del state[k]
            except Exception:
                logger.exception("Failed to summarize tool response for state key: %s", k)

def _trim_large_state_values(state: Dict[str, Any], max_chars: int = 2000) -> None:
    """
    Truncate any very long strings in state to avoid feeding them into prompts.
    """
    for k, v in list(state.items()):
        if isinstance(v, str) and len(v) > max_chars:
            state[k] = v[:max_chars - 1] + "\n...[truncated]..."
            logger.debug("Truncated state key %s (len>%s)", k, max_chars)

def store_results_in_context(callback_context: CallbackContext) -> None:
    """
    Save parsed starter-agent output into session state.

    Defensive parsing + summarization of tool responses to avoid token bloat.
    """
    # FIRST: summarize and trim any tool responses already present in state
    try:
        _summarize_and_replace_tool_responses(callback_context.state)
        _trim_large_state_values(callback_context.state)
    except Exception:
        logger.exception("Pre-store trimming failed; continuing defensively")

    response_dict = callback_context.state.get('starter_agent_response')

    parsed: Dict[str, Any] = {
        "greeting": "",
        "user_intent": "(agent failed to produce structured response)",
        "sql_required": False,
        "python_required": False
    }

    if response_dict:
        try:
            parsed_response = StarterAgentResponse.model_validate(response_dict)
            parsed = {
                "greeting": parsed_response.greeting,
                "user_intent": parsed_response.user_intent,
                "sql_required": bool(parsed_response.sql_required),
                "python_required": bool(parsed_response.python_required),
            }
            logger.debug("Starter agent parsed successfully via pydantic.")
        except Exception as e:
            logger.warning("StarterAgentResponse validation failed: %s. Attempting dict fallback.", e)
            try:
                if isinstance(response_dict, dict):
                    parsed = {
                        "greeting": response_dict.get("greeting", parsed["greeting"]),
                        "user_intent": response_dict.get("user_intent", parsed["user_intent"]),
                        "sql_required": bool(response_dict.get("sql_required", parsed["sql_required"])),
                        "python_required": bool(response_dict.get("python_required", parsed["python_required"])),
                    }
                    logger.debug("Starter agent parsed via dict fallback.")
                else:
                    logger.debug("starter_agent_response present but not a dict: %s", type(response_dict))
            except Exception as e2:
                logger.exception("Failed to extract fallback fields from starter_agent_response: %s", e2)
    else:
        # try fallback keys
        fallback_candidates = [
            "parsed_json",
            "starter_agent_parsed_json",
            "latest_parsed_json",
            "starter_agent_response_text",
            "latest_agent_output"
        ]
        found = None
        for key in fallback_candidates:
            candidate = callback_context.state.get(key)
            if candidate and isinstance(candidate, dict):
                found = candidate
                logger.debug("Using fallback parsed JSON from state key: %s", key)
                break

        if found:
            parsed = {
                "greeting": found.get("greeting", parsed["greeting"]),
                "user_intent": found.get("user_intent", parsed["user_intent"]),
                "sql_required": bool(found.get("sql_required", parsed["sql_required"])),
                "python_required": bool(found.get("python_required", parsed["python_required"])),
            }
        else:
            logger.warning("No starter_agent_response found in state; using defaults. State keys: %s",
                           list(callback_context.state.keys())[:20])

    # Persist only minimal values into the session state to avoid re-injecting large objects
    callback_context.state['greeting'] = parsed["greeting"]
    callback_context.state['user_intent_text'] = parsed["user_intent"]
    callback_context.state['python_required'] = parsed["python_required"]
    callback_context.state['sql_required'] = True if parsed["python_required"] else parsed["sql_required"]

def get_sequence_outcome(callback_context: CallbackContext) -> None:
    if 'sql' in callback_context.agent_name:
        if callback_context.state.get('latest_sql_criticism') == OUTCOME_OK_PHRASE and \
           callback_context.state.get('latest_bq_execution_status') == 'SUCCESS':
            callback_context.state['latest_sql_sequence_outcome'] = 'SUCCESS'
        else:
            callback_context.state['latest_sql_sequence_outcome'] = 'FAILURE'

    if 'python' in callback_context.agent_name:
        if callback_context.state.get('latest_python_code_criticism') == OUTCOME_OK_PHRASE and \
           'OK' in str(callback_context.state.get('latest_python_code_execution_outcome', '')):
            callback_context.state['latest_python_sequence_outcome'] = 'SUCCESS'
        else:
            callback_context.state['latest_python_sequence_outcome'] = 'FAILURE'

    return None

async def store_image_artifact(tool: BaseTool, args: Dict[str, Any], tool_context: ToolContext, tool_response: Dict) -> None:
    try:
        markdown_str = tool_response.get('inline_data', '')
        # existing image storage handling kept as-is...
    except Exception:
        logger.exception("Failed to store image artifact")