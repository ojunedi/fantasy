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
import os
from typing import Any


def default_llm(config=None):
    """Build a ChatGoogleGenerativeAI, or return None if no API key is configured."""
    if not os.environ.get("GOOGLE_API_KEY"):
        return None
    from fantasy_gm.agent.config import AgentConfig
    from langchain_google_genai import ChatGoogleGenerativeAI
    cfg = config or AgentConfig()
    return ChatGoogleGenerativeAI(
        model=cfg.model,
        google_api_key=cfg.google_api_key or None,
        max_output_tokens=1024,
    )


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
