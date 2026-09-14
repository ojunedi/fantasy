"""Agent runtime configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass

_DEFAULT_MODEL = "gemini-2.5-flash"

# Per-provider default model, used when FANTASY_GM_MODEL is not set. The Groq
# pick is a large-context model documented for tool use — this agent lives or
# dies on reliable multi-tool calling, so the small/fast models are a bad fit.
_DEFAULT_MODELS = {
    "google": _DEFAULT_MODEL,
    "groq": "openai/gpt-oss-120b",
}


def _resolve_model(provider: str) -> str:
    """Pick the model for a provider. Model ids are provider-specific.

    Override per provider with FANTASY_GM_GOOGLE_MODEL / FANTASY_GM_GROQ_MODEL.
    The older generic FANTASY_GM_MODEL is honoured for google only — it has
    always held a Gemini id, so applying it to another provider just sends an
    unknown model name and 404s.
    """
    specific = os.environ.get(f"FANTASY_GM_{provider.upper()}_MODEL")
    if specific:
        return specific
    if provider == "google":
        return os.environ.get("FANTASY_GM_MODEL") or _DEFAULT_MODEL
    return _DEFAULT_MODELS.get(provider, _DEFAULT_MODEL)


@dataclass
class AgentConfig:
    # "google" (Gemini) or "groq". Override with FANTASY_GM_PROVIDER.
    provider: str = os.environ.get("FANTASY_GM_PROVIDER", "google")
    # Blank means "resolve from the provider" — see __post_init__.
    model: str = ""
    groq_api_key: str = os.environ.get("GROQ_API_KEY", "")
    # Max completion tokens per call. Providers reserve this against their
    # tokens-per-minute quota, so an oversized value fails the request outright
    # (Groq 413s on a 16k reservation). The agent only ever emits a tool call or
    # a short memo, so a few thousand is ample. Override: FANTASY_GM_MAX_TOKENS.
    max_tokens: int = int(os.environ.get("FANTASY_GM_MAX_TOKENS", "2048"))
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

    def __post_init__(self) -> None:
        if not self.model:
            self.model = _resolve_model(self.provider)


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
