"""
Simple heuristics to trim conversation history and tool outputs to reduce tokens.
Usage:
  trimmed = trim_messages(messages, max_messages=6, max_tool_chars=1000)
Where messages is a list of dicts like: {"role":"user"|"system"|"assistant"|"tool", "content": "..."}
"""

from typing import List, Dict

def summarize_long_text(text: str, max_chars: int = 500) -> str:
    if not text:
        return text
    if len(text) <= max_chars:
        return text
    head = text[: int(max_chars * 0.45)]
    tail = text[-int(max_chars * 0.45):]
    return head + "\n...[truncated]...\n" + tail

def trim_messages(messages: List[Dict[str, str]], max_messages: int = 6, max_tool_chars: int = 800) -> List[Dict[str, str]]:
    """
    Keeps the last max_messages messages. For tool outputs or long assistant outputs, summarize/truncate them.
    """
    if not messages:
        return []

    trimmed = messages[-max_messages:]
    cleaned = []
    for msg in trimmed:
        role = msg.get("role", "assistant")
        content = msg.get("content", "") or ""
        if role in ("tool",):
            content = summarize_long_text(content, max_chars=max_tool_chars)
        else:
            content = summarize_long_text(content, max_chars=1200)
        cleaned.append({"role": role, "content": content})
    return cleaned