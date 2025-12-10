"""
Helpers to build combined prompts so a single model call returns both structured JSON and display text.
The template asks for a JSON block (for programmatic parsing) and a text block (for UI), separated by markers.
"""

from typing import Dict, Any

COMBINED_PROMPT_TEMPLATE = """
You are an assistant that must:
1) RETURN a JSON object under the heading ===JSON_START=== ... ===JSON_END=== containing fields:
   - greeting: short greeting for the user
   - parsed: structured fields needed by the system (e.g., sql_required: bool, python_required: bool, kpi_id: int)
   - optional: sql (if applicable) - return a single SQL statement string or empty
2) RETURN a user-facing text reply under the heading ===TEXT_START=== ... ===TEXT_END=== that is a short conversational response.

CONSTRAINTS:
- The JSON block must be valid JSON (no trailing commas).
- The JSON must be as small as possible (only keys required downstream).
- The text block should be concise (<= 200 words) and friendly.

CONTEXT:
{context_text}

KPI metadata (short):
{kpi_metadata}

User message:
{user_message}

Produce the output exactly as specified with the two markers.
"""

def build_combined_prompt(context_text: str, kpi_metadata: Dict[str, Any], user_message: str) -> str:
    if kpi_metadata:
        parts = []
        # Only keep small, non-null fields to reduce tokens
        for k, v in kpi_metadata.items():
            if v is None:
                continue
            # truncate long descriptions
            val = str(v)
            if len(val) > 300:
                val = val[:280] + "…"
            parts.append(f"{k}: {val}")
        kpi_summary = "\n".join(parts)
    else:
        kpi_summary = "No KPI metadata available."

    return COMBINED_PROMPT_TEMPLATE.format(
        context_text=context_text or "No context.",
        kpi_metadata=kpi_summary,
        user_message=user_message
    )