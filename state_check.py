import argparse
import asyncio
import json
import uuid
from copy import deepcopy
from typing import Any

from google.adk.artifacts import InMemoryArtifactService
from google.adk.sessions import InMemorySessionService

from constants import APP_NAME, DATA_SCHEMA_PATH, DEFS_SCHEMA_PATH, USER_ID
from sequences.python_sequence import python_agent_sequence
from sequences.sql_sequence import sql_agent_sequence
from sequences.starter_sequence import starter_agent_sequence
from utils.helper import json_to_dict

#hold all token keys here for tracking usage count 
TOKEN_KEYS = [
    "app:total_token_count",
    "app:prompt_token_count",
    "app:candidates_token_count",
    "app:thoughts_token_count",
    "app:tool_use_prompt_token_count",
    "app:cached_content_token_count",
]

#internal func to decide return types
def _safe_value(value: Any, max_text_len: int) -> Any:
    if isinstance(value, bytes):
        return {
            "_type": "bytes",
            "length": len(value),
        }
    if isinstance(value, str):
        if len(value) > max_text_len:
            return {
                "_type": "string",
                "length": len(value),
                "preview": value[:max_text_len],
            }
        return value
    if isinstance(value, list):
        return [_safe_value(v, max_text_len) for v in value]
    if isinstance(value, dict):
        return {k: _safe_value(v, max_text_len) for k, v in value.items()}
    return value

#use this helper to display snapshot state 
def _snapshot_state(state: dict[str, Any], max_text_len: int) -> dict[str, Any]:
    return _safe_value(state, max_text_len)

#track changes in state keys 
def _state_diff(prev_state: dict[str, Any], curr_state: dict[str, Any]) -> dict[str, Any]:
    prev_keys = set(prev_state.keys()) 
    curr_keys = set(curr_state.keys())

    #what's added/remvoed/changed since last QnA
    added = sorted(curr_keys - prev_keys)
    removed = sorted(prev_keys - curr_keys)

    changed = []
    for key in sorted(prev_keys & curr_keys):
        if prev_state[key] != curr_state[key]:
            changed.append(key) #if values for the key don't match, add to what's changed
 
    #format to return keys 
    return {
        "added_keys": added,
        "removed_keys": removed,
        "changed_keys": changed,
        "counts": {
            "added": len(added),
            "removed": len(removed),
            "changed": len(changed),
        },
    }

#token metric helper
def _token_metrics(state: dict[str, Any]) -> dict[str, Any]:
    return {key: state.get(key) for key in TOKEN_KEYS}

# what's changed in token consumption?
def _token_delta(prev: dict[str, Any], curr: dict[str, Any]) -> dict[str, Any]:
    delta: dict[str, Any] = {}
    for key in TOKEN_KEYS:
        prev_val = prev.get(key)
        curr_val = curr.get(key)
        #type safety for token delta
        if isinstance(prev_val, (int, float)) and isinstance(curr_val, (int, float)):
            delta[key] = curr_val - prev_val
        else:
            delta[key] = None #type safety
    return delta


def _event_summary(events: list[Any]) -> dict[str, Any]:
    by_author: dict[str, int] = {}
    with_content_by_author: dict[str, int] = {}

    for event in events:
        author = getattr(event, "author", "unknown")
        by_author[author] = by_author.get(author, 0) + 1

        content = getattr(event, "content", None)
        if content is not None and getattr(content, "parts", None):
            with_content_by_author[author] = with_content_by_author.get(author, 0) + 1

    return {
        "total_events": len(events),
        "events_by_author": by_author,
        "events_with_content_by_author": with_content_by_author,
    }


def _agent_state_view(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "starter": {k: v for k, v in state.items() if k.startswith("starter_") or k in {"greeting", "user_intent", "sql_required", "python_required"}},
        "sql": {k: v for k, v in state.items() if k.startswith("latest_sql") or k.startswith("bigquery_")},
        "python": {k: v for k, v in state.items() if k.startswith("latest_python") or k.startswith("latest_img")},
        "app": {k: v for k, v in state.items() if k.startswith("app:")},
    }


async def _build_initial_state() -> dict[str, Any]:
    return {
        "projects": "uk-dta-gsmanalytics-poc",
        "datasets": "metricmind",
        "tables": "GSM_KPI_DATA_TEST_V5, GSM_KPI_DEFS_TEST_V5"
    }


async def _run_single_query(
    *,
    app_name: str,
    user_id: str,
    session_id: str,
    query: str,
    session_service: InMemorySessionService,
    artifact_service: InMemoryArtifactService,
) -> None:
    await starter_agent_sequence(app_name, user_id, session_service, artifact_service, session_id, query)

    session = await session_service.get_session(app_name=app_name, user_id=user_id, session_id=session_id)

    if session.state.get("sql_required"):
        await sql_agent_sequence(app_name, user_id, session_service, artifact_service, session_id, query)
        session = await session_service.get_session(app_name=app_name, user_id=user_id, session_id=session_id)

    if session.state.get("python_required") and session.state.get("latest_sql_sequence_outcome") == "SUCCESS":
        await python_agent_sequence(app_name, user_id, session_service, artifact_service, session_id, query)

#MAIN RUNNER
async def _run(args: argparse.Namespace) -> dict[str, Any]:
    #INITIATE STUFF HERE
    app_name = APP_NAME
    user_id = USER_ID
    session_id = str(uuid.uuid4())
    
    session_service = InMemorySessionService()
    artifact_service = InMemoryArtifactService()

    initial_state = await _build_initial_state()
    
    #create a session first
    await session_service.create_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
        state=initial_state,
    )

    #initialize whats held for dumping into report 
    query_reports: list[dict[str, Any]] = []
    prev_state: dict[str, Any] = deepcopy(initial_state)
    prev_tokens = _token_metrics(prev_state)
    prev_event_count = 0

    #run query by query 
    for idx, query in enumerate(args.queries, start=1):
        await _run_single_query(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
            query=query,
            session_service=session_service,
            artifact_service=artifact_service,
        )

        #fetch state info
        session = await session_service.get_session(app_name=app_name, user_id=user_id, session_id=session_id)
        curr_state = deepcopy(session.state) #replace shallow with deepcopy!!!
        curr_tokens = _token_metrics(curr_state)

        event_count = len(session.events)

        #custom turn-based report 
        report = {
            "turn": idx,
            "query": query,
            "state_key_count": len(curr_state),
            "state_diff_from_previous_turn": _state_diff(prev_state, curr_state),
            "token_metrics": {
                "current": curr_tokens,
                "delta_from_previous_turn": _token_delta(prev_tokens, curr_tokens),
            },
            "events": {
                "total_events": event_count,
                "delta_events_from_previous_turn": event_count - prev_event_count,
                "summary": _event_summary(session.events),
            },
            "agent_state_view": _snapshot_state(_agent_state_view(curr_state), args.max_text_len),
            "full_state_snapshot": _snapshot_state(curr_state, args.max_text_len),
        }

        #append to final query report
        query_reports.append(report)

        #modify state at end of turn 
        prev_state = curr_state
        prev_tokens = curr_tokens
        prev_event_count = event_count

    #fetch final state
    final_session = await session_service.get_session(app_name=app_name, user_id=user_id, session_id=session_id)

    #return a summary of events, tokens etc
    return {
        "session_id": session_id,
        "query_count": len(args.queries),
        "notes": {
            "same_session_used_for_all_queries": True,
            "include_contents_default_agents": ["starter_agent", "sql_writer_agent", "python_writer_agent"],
            "include_contents_none_agents": ["sql_critic_agent", "sql_refiner_agent", "python_critic_agent", "python_refiner_agent"],
        },
        "per_query": query_reports,
        "final": {
            "event_count": len(final_session.events),
            "token_metrics": _token_metrics(final_session.state),
        },
    }

#fetch all queries post processing
def _load_queries(args: argparse.Namespace) -> list[str]:
    queries: list[str] = []

    if args.query:
        queries.extend(args.query)

    if args.queries_file:
        with open(args.queries_file, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip() 
                if stripped:
                    queries.append(stripped)
    
    if not queries:
        raise ValueError("Provide at least one query via --query or --queries-file")

    return queries

#process multiple QnA under main 
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run multiple user queries in one session and dump cross-agent state/token/event growth."
    )
    parser.add_argument(
        "--query",
        action="append",
        help="One query. Repeat this flag for multiple questions.",
    )
    parser.add_argument(
        "--queries-file",
        default=None,
        help="Optional text file with one query per line",
    )
    parser.add_argument(
        "--out",
        default="session_state_growth_dump.json",
        help="Output JSON path",
    )
    parser.add_argument(
        "--max-text-len",
        type=int,
        default=2000,
        help="Maximum stored text length per value in snapshots (longer strings are summarized)",
    )

    #parse then load arguments
    args = parser.parse_args()
    args.queries = _load_queries(args)
    
    #run it through the event loop
    report = asyncio.run(_run(args))

    # dump report as JSON to debug
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"Saved session report to {args.out}")


if __name__ == "__main__":
    main()
