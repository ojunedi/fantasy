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
    # Hard cap on LLM API calls per run (agent loop + LLM sub-agents share it),
    # to stay under provider rate limits. Override with FANTASY_GM_MAX_LLM_CALLS.
    max_llm_calls: int = int(os.environ.get("FANTASY_GM_MAX_LLM_CALLS", "3"))
    # Hard wall-clock cap on requests per minute, enforced process-wide by a
    # shared limiter (see `shared_rate_limiter`). Unlike `max_llm_calls` this
    # survives across runs/agents in the same process and across client
    # retries. Override with FANTASY_GM_MAX_RPM.
    max_rpm: float = float(os.environ.get("FANTASY_GM_MAX_RPM", "4"))
    # Attempts (not extra retries) the underlying google.genai HTTP client makes
    # per call; the library default of 6 was the 429-burst source. Retries happen
    # BELOW the rate limiter, so they are not themselves spaced: worst-case
    # requests/minute is max_rpm * max_retries. Keep this at 1 so the bound stays
    # strictly under the 5/min free-tier quota (4 * 1 = 4). Raising it to 2 buys
    # a transient retry but doubles the worst case to 8/min.
    max_retries: int = int(os.environ.get("FANTASY_GM_MAX_RETRIES", "1"))
    # "compact" (default, one-line tool results) or "full" (untruncated outputs,
    # model reasoning, and empty-response diagnostics). Set FANTASY_GM_TRACE=full.
    trace: str = os.environ.get("FANTASY_GM_TRACE", "compact")


_RATE_LIMITER = None
_RATE_LIMITER_RPM: float | None = None


def shared_rate_limiter(max_rpm: float | None = None):
    """Process-wide `InMemoryRateLimiter` shared by every chat client.

    Both construction sites (`GraphAgent._build_llm` and the sub-agents'
    `default_llm`) must pass *this same object* as `rate_limiter=`; two
    limiters would each allow `max_rpm` and double the real rate.

    `max_bucket_size=1` means no bursting: tokens do not accumulate while
    idle, so the limiter can never release several calls back to back.
    """
    global _RATE_LIMITER, _RATE_LIMITER_RPM
    rpm = AgentConfig.max_rpm if max_rpm is None else max_rpm
    if _RATE_LIMITER is None or _RATE_LIMITER_RPM != rpm:
        from langchain_core.rate_limiters import InMemoryRateLimiter
        _RATE_LIMITER = InMemoryRateLimiter(
            requests_per_second=rpm / 60.0,
            check_every_n_seconds=0.1,
            max_bucket_size=1,
        )
        _RATE_LIMITER_RPM = rpm
    return _RATE_LIMITER
