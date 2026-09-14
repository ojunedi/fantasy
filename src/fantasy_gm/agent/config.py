"""Agent runtime configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass

_DEFAULT_MODEL = "gemini-2.5-flash"


@dataclass
class AgentConfig:
    model: str = os.environ.get("FANTASY_GM_MODEL", _DEFAULT_MODEL)
    max_tokens: int = 16000
    max_tool_iterations: int = 20  # safety cap on the agentic loop
    google_api_key: str = os.environ.get("GOOGLE_API_KEY", "")
    # "compact" (default, one-line tool results) or "full" (untruncated outputs,
    # model reasoning, and empty-response diagnostics). Set FANTASY_GM_TRACE=full.
    trace: str = os.environ.get("FANTASY_GM_TRACE", "compact")
