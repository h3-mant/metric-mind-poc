from google.genai import types
from google.adk.events import Event, EventActions
from google.adk.sessions import InMemorySessionService
from google.adk.artifacts import InMemoryArtifactService
from google.adk.runners import Runner
import time
from utils import EVENT_LOG_ACCUMULATOR 

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

                        #save img artifact URL to state
                        state_changes["latest_img_url"] = part.code_execution_result.output

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
        print(f"Error during agent call: {e}")
    
    return final_response
