"""
Summarize BigQuery tool responses to a small representation to avoid re-injecting huge payloads into prompts.
"""

from typing import Any, Dict, List

MAX_SAMPLE_ROWS = 3
MAX_CELL_CHARS = 200

def _truncate_value(v: Any) -> Any:
    if v is None:
        return None
    s = str(v)
    if len(s) > MAX_CELL_CHARS:
        return s[: MAX_CELL_CHARS - 1] + "…"
    return s

def summarize_sql_response(tool_response: Dict[str, Any], max_rows: int = MAX_SAMPLE_ROWS) -> Dict[str, Any]:
    """
    tool_response is expected in the shape returned by the BigQuery tool in your logs, e.g.:
      {'status':'SUCCESS', 'rows':[ {col: val, ...}, ... ]}
    Returns a small dict: {status, row_count, sample_rows}
    """
    if not tool_response or not isinstance(tool_response, dict):
        return {"status": "UNKNOWN", "row_count": 0, "sample_rows": []}

    status = tool_response.get("status", "UNKNOWN")
    rows = tool_response.get("rows", [])
    if rows is None:
        rows = []

    row_count = len(rows)
    sample = []
    for r in rows[:max_rows]:
        if isinstance(r, dict):
            sample.append({k: _truncate_value(v) for k, v in r.items()})
        else:
            # fallback if row is list/tuple
            try:
                sample.append([_truncate_value(x) for x in list(r)])
            except Exception:
                sample.append(str(r)[:200])

    return {"status": status, "row_count": row_count, "sample_rows": sample}