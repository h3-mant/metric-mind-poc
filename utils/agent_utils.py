from google.genai import types
from google.adk.events import Event, EventActions
from google.adk.sessions import InMemorySessionService
from google.adk.artifacts import InMemoryArtifactService
from google.adk.runners import Runner
import time
from utils import EVENT_LOG_ACCUMULATOR
import json
import re

async def process_agent_response(
        event: Event, 
        app_name: str, 
        user_id: str, 
        session_id: str, 
        session_service: InMemorySessionService, 
        artifact_service: InMemoryArtifactService,
        final_response: dict
    ) -> dict:
    """Process each agent event and accumulate details into state and final_response."""
    
    state_changes = {}
    try:
        #update session
        current_session = await session_service.get_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id
        )
        
        # ---- 1. Final Text Response ----
        if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        # append final text to the accumulated response
                        final_response["text"] = final_response.get("text", "") + part.text                        

                    #for Python agents
                    if part.executable_code:
                        final_response["python_code_output"] = part.executable_code.code
                        state_changes['latest_python_code_output'] = part.executable_code.code

                    #for Python agents
                    if part.code_execution_result:
                        #was code execution successful?
                        final_response["python_code_execution_outcome"] = part.code_execution_result.outcome

                        state_changes["latest_python_code_execution_outcome"] = str(part.code_execution_result.outcome)

                        #TO DO: use artifact_service via callbacks to load image instead of state as below
                        
                        final_response["img_bytes_length"] = len(str(part.code_execution_result.output))

                        #save binary img artifact to state
                        state_changes["latest_img_bytes"] = part.code_execution_result.output

        # ---- 2. Function Calls ----
        calls = event.get_function_calls()
        if calls:
            for call in calls:
                tool_name = call.name
                arguments = call.args or {}
                final_response[f"[tool_call]_{tool_name}"] = arguments

                # for SQL agents
                if tool_name == "execute_sql":
                    state_changes["latest_sql_output"] = arguments.get("query")
                    

        # ---- 3. Function Responses ----
        responses = event.get_function_responses()
        if responses:
            for response in responses:
                tool_name = response.name
                result_dict = response.response or {}
                final_response[f"[tool_response]_{tool_name}"] = result_dict
                state_changes['latest_sql_response'] = result_dict.get("rows")
                
                state_changes['latest_bq_execution_status'] = result_dict.get("status")
                
                # track BQ API failures
                if result_dict.get("status") == "ERROR":
                    state_changes["app:bq_api_failure_count"] = (
                        current_session.state.get("app:bq_api_failure_count", 0) + 1
                    )

        # ---- 4. Usage Metadata ----
        if event.usage_metadata:
            ############ update general cache stats ############
            
            # #Number of contents stored in this cache (ONE_TIME CALL SINCE IMMUTABLE)
            # if not state_changes.get("app:cached_contents_count"):
            #     state_changes["app:cached_contents_count"] = event.cache_metadata.cached_contents_count

            ##Number of tokens in the cached part in the input (the cached content). (ONE_TIME CALL SINCE IMMUTABLE)
            state_changes['app:cached_content_token_count'] = event.usage_metadata.cached_content_token_count

            # #Number of invocations this cache has been used for
            # state_changes['app:cache_invocations_used'] = state_changes.get('app:cache_invocations_used',0) + event.cache_metadata.invocations_used

            ############ update token usage stats ############
            
            #Number of tokens in the response(s).
            n_tokens = event.usage_metadata.candidates_token_count
            state_changes['app:candidates_token_count'] = state_changes.get('app:candidates_token_count',0) + n_tokens if n_tokens else 0
            
            #Number of tokens in the request. When `cached_content` is set, this is still the total effective prompt size meaning this includes the number of tokens in the cached content.
            prompt_token_count = event.usage_metadata.prompt_token_count
            state_changes['app:prompt_token_count'] = state_changes.get('app:prompt_token_count',0) + prompt_token_count if prompt_token_count else 0

            #Number of tokens present in thoughts output.
            thoughts_token_count = event.usage_metadata.thoughts_token_count
            state_changes['app:thoughts_token_count'] = state_changes.get('app:thoughts_token_count',0) + thoughts_token_count if thoughts_token_count else 0
            
            #Number of tokens present in tool-use prompt(s).
            tool_use_prompt_token_count = event.usage_metadata.tool_use_prompt_token_count
            state_changes['app:tool_use_prompt_token_count'] = state_changes.get('app:tool_use_prompt_token_count',0) + tool_use_prompt_token_count if tool_use_prompt_token_count else 0

            #total tokens used
            total_tokens_used = event.usage_metadata.total_token_count or 0
            final_response["total_token_count"] = final_response.get("total_token_count", 0) + total_tokens_used
            state_changes["app:total_token_count"] = (
                current_session.state.get("app:total_token_count", 0) + total_tokens_used
            )
        
        #Accumulate logs for UI upstream
        EVENT_LOG_ACCUMULATOR.append(final_response)

        # --- 5. Apply State Changes ---
        if state_changes:
            actions_with_update = EventActions(state_delta=state_changes)
            system_event = Event(
                author="system",
                actions=actions_with_update,
                timestamp=time.time(),
            )

            await session_service.append_event(current_session, system_event)

    except Exception as e:
        print(f"Error in process_agent_response: {e}")
        raise

    return final_response


async def call_agent_async(
        *,
        runner: Runner, 
        app_name: str, 
        user_id: str, 
        session_service: InMemorySessionService,
        artifact_service: InMemoryArtifactService,
        session_id: str, 
        user_query: str, 
    ) -> dict:
    """Custom Agent Caller to aggregate the final_response payload across all events."""

    final_response = {}
    content = types.Content(role="user", parts=[types.Part(text=user_query)])
    
    #set user_query into final_response
    final_response['user_query'] = user_query
    
    try:
        async for event in runner.run_async(
            user_id=user_id, session_id=session_id, new_message=content
        ):
            await process_agent_response(event, app_name, user_id, session_id, session_service, artifact_service, final_response)
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"Error during agent call: {e}\n{tb}")
        final_response["error"] = str(e)
        final_response["traceback"] = tb

        # Attempt to update session state with a safe fallback so downstream code can continue.
        try:
            current_session = await session_service.get_session(
                app_name=app_name, user_id=user_id, session_id=session_id
            )
            # Provide conservative defaults for starter agent outputs to avoid crashes.
            state_changes = {
                "greeting": "",
                "user_intent": "(agent failed to produce structured response)",
                "sql_required": False,
                "python_required": False,
                "latest_agent_error": str(e),
            }
            actions_with_update = EventActions(state_delta=state_changes)
            system_event = Event(
                author="system",
                actions=actions_with_update,
                timestamp=time.time(),
            )
            await session_service.append_event(current_session, system_event)
            final_response["parsed_json"] = {
                "greeting": state_changes["greeting"],
                "user_intent": state_changes["user_intent"],
                "sql_required": state_changes["sql_required"],
                "python_required": state_changes["python_required"],
            }
            final_response["parsed_json_source"] = "exception_fallback"
        except Exception as exc:
            # If even this fails, ensure we still return an error payload.
            final_response["append_event_error"] = str(exc)

    # Post-process: try to parse JSON from accumulated text so downstream Pydantic parsing won't fail unexpectedly.
    # Prefer structured tool responses first (they are already dicts).
    for k, v in final_response.items():
        if isinstance(k, str) and k.startswith("[tool_response]") and isinstance(v, dict):
            final_response["parsed_json"] = v
            final_response["parsed_json_source"] = "tool_response"
            break

    text = final_response.get("text")
    if "parsed_json" not in final_response and text:
        def _extract_candidates_from_text(t: str):
            candidates = []
            # 1) ```json code fences
            for m in re.finditer(r'```json\s*(.*?)```', t, flags=re.DOTALL | re.IGNORECASE):
                candidates.append(m.group(1).strip())

            # 2) generic code fences that contain JSON
            for m in re.finditer(r'```\s*(.*?)```', t, flags=re.DOTALL):
                body = m.group(1).strip()
                if body.startswith('{') or body.startswith('['):
                    candidates.append(body)

            # 3) bracket-matching for top-level JSON objects (attempt to find balanced {...} blocks)
            stack = []
            starts = []
            for i, ch in enumerate(t):
                if ch == '{':
                    stack.append(i)
                elif ch == '}':
                    if stack:
                        start = stack.pop()
                        # if stack is empty, we closed a top-level object
                        if not stack:
                            candidate = t[start:i+1]
                            candidates.append(candidate)

            # 4) regex fallback: last {...} block
            m = re.search(r'\{[\s\S]*\}', t)
            if m:
                candidates.append(m.group(0))

            # deduplicate preserving order
            seen = set()
            uniq = []
            for c in candidates:
                s = c.strip()
                if s and s not in seen:
                    seen.add(s)
                    uniq.append(s)
            return uniq

        candidates = _extract_candidates_from_text(text)

        # Try candidates by descending length (prefer larger JSON objects)
        for candidate in sorted(candidates, key=lambda x: -len(x)):
            try:
                parsed = json.loads(candidate)
                final_response["parsed_json"] = parsed
                final_response["parsed_json_source"] = "extracted_block"
                break
            except Exception:
                continue

        # If still not found, try direct full-text parse as last attempt
        if "parsed_json" not in final_response:
            try:
                parsed = json.loads(text)
                final_response["parsed_json"] = parsed
                final_response["parsed_json_source"] = "full_text"
            except Exception:
                # Fallback: handle common short status outputs like "OUTCOME OK" or "SUCCESS" etc.
                cleaned = text.strip().upper()
                m_status = re.search(r'OUTCOME[_\s:-]*(OK|SUCCESS|FAIL|ERROR)\b', cleaned)
                if m_status:
                    val = m_status.group(1)
                    outcome = 'OK' if val in ('OK', 'SUCCESS') else 'ERROR' if val == 'ERROR' else 'FAIL'
                    final_response["parsed_json"] = {"outcome": outcome}
                    final_response["parsed_json_source"] = "status_fallback"
                else:
                    if cleaned in ("OK", "SUCCESS"):
                        final_response["parsed_json"] = {"outcome": "OK"}
                        final_response["parsed_json_source"] = "status_fallback"
                    elif cleaned in ("ERROR", "FAIL"):
                        final_response["parsed_json"] = {"outcome": "ERROR"}
                        final_response["parsed_json_source"] = "status_fallback"
                    else:
                        final_response["json_error"] = "No JSON object found in text"
                        final_response["raw_text"] = text

    # If parsing failed, attempt a single retry asking the agent to return pure JSON.
    if "parsed_json" not in final_response and not final_response.get("retried"):
        try:
            prev_text = final_response.get("raw_text") or final_response.get("text", "")
            followup = (
                "The assistant's previous response did not contain valid JSON. "
                "Please respond with ONLY a JSON object matching this schema: {\"greeting\": \"...\", \"user_intent\": \"...\", \"sql_required\": false, \"python_required\": false}. "
                "Do not include any additional commentary.\n\nPrevious response for context:\n" + prev_text
            )
            retry_response = {}
            content2 = types.Content(role="user", parts=[types.Part(text=followup)])
            async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=content2):
                await process_agent_response(event, app_name, user_id, session_id, session_service, artifact_service, retry_response)

            rtext = retry_response.get("text", "")
            parsed_retry = None
            if rtext:
                try:
                    parsed_retry = json.loads(rtext)
                except Exception:
                    m = re.search(r'\{[\s\S]*\}', rtext)
                    if m:
                        try:
                            parsed_retry = json.loads(m.group(0))
                        except Exception:
                            parsed_retry = None

            if parsed_retry:
                final_response["parsed_json"] = parsed_retry
                final_response["parsed_json_source"] = "retry"

            final_response["retried"] = True
        except Exception as exc:
            final_response["retry_error"] = str(exc)

    return final_response