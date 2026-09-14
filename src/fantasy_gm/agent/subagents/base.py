"""
Shared helpers for the single-shot LLM sub-agents.

The sub-agents (injury, news) are the *only* new LLM units in this phase. Each
turns unstructured English (an injury report, news blurbs) into a small
structured dict the deterministic tools can consume. They are single-shot (one
model call, no tool loop) to keep token cost bounded.

Both degrade gracefully: with no API key and no injected LLM, they return a
neutral result with a note rather than raising.
"""
from __future__ import annotations

import json
from typing import Any


def default_llm(config=None):
    """Build the configured chat model, or None if that provider has no API key.

    Goes through the shared factory so the process-wide rate limiter and retry
    bound apply here exactly as they do for the main agent loop.
    """
    from fantasy_gm.agent.config import AgentConfig
    from fantasy_gm.agent.llm import api_key_for, build_chat_model
    cfg = config or AgentConfig()
    if not api_key_for(cfg):
        return None
    return build_chat_model(cfg, max_output_tokens=1024)


def _message_text(msg: Any) -> str:
    content = getattr(msg, "content", msg)
    if isinstance(content, list):  # some LC versions wrap content in blocks
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(block.get("text", ""))
            else:
                parts.append(str(block))
        return "".join(parts)
    return str(content)


def parse_json_object(text: str) -> dict | None:
    """Extract the first JSON object from an LLM response, tolerating prose."""
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
