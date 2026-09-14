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
    # qwen over gpt-oss-120b: gpt-oss emitted JavaScript-style // comments
    # inside its JSON tool arguments, which the API rejects outright.
    "groq": "qwen/qwen3.8-27b",
}


# Per-provider defaults for the two knobs that providers meter differently.
# Groq's free tier enforces a separate output-tokens-per-minute cap (1,000) and
# charges the *reserved* max_tokens against it, so a large reservation fails the
# request outright — and only ~1 call/min fits. Gemini meters requests, not
# output, so it can afford a bigger reservation and a faster cadence.
_DEFAULT_MAX_TOKENS = {"google": 2048, "groq": 900}
_DEFAULT_MAX_RPM = {"google": 4.0, "groq": 1.0}

# Reasoning models bill their internal reasoning against max_tokens. On Groq's
# 1,000 output-tokens/minute free cap that is fatal: gpt-oss-120b spent 898 of
# 900 tokens reasoning and had none left to emit the tool call. Keep it low.
_DEFAULT_REASONING_EFFORT = {"groq": "low"}


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
    max_tokens: int = 0   # 0 = resolve per provider in __post_init__
    max_tool_iterations: int = 20  # safety cap on the agentic loop
    google_api_key: str = os.environ.get("GOOGLE_API_KEY", "")
    # Hard cap on LLM API calls per run (agent loop + LLM sub-agents share it),
    # to stay under provider rate limits. Override with FANTASY_GM_MAX_LLM_CALLS.
    max_llm_calls: int = int(os.environ.get("FANTASY_GM_MAX_LLM_CALLS", "3"))
    # Hard wall-clock cap on requests per minute, enforced process-wide by a
    # shared limiter (see `shared_rate_limiter`). Unlike `max_llm_calls` this
    # survives across runs/agents in the same process and across client
    # retries. Override with FANTASY_GM_MAX_RPM.
    max_rpm: float = 0.0  # 0 = resolve per provider in __post_init__
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
    # "", "none", "low", "medium", "high" — provider-specific; "" means unset.
    reasoning_effort: str = os.environ.get("FANTASY_GM_REASONING_EFFORT", "")
    # Extra attempts the *agent loop* makes when the provider returns a transient
    # server error (503 "high demand", 500/502/504). These go back through the
    # shared rate limiter, so unlike the client's own retries they stay inside
    # the requests/minute bound. Never applied to 429s.
    transient_retries: int = int(os.environ.get("FANTASY_GM_TRANSIENT_RETRIES", "2"))

    def __post_init__(self) -> None:
        if not self.model:
            self.model = _resolve_model(self.provider)
        if not self.max_tokens:
            env = os.environ.get("FANTASY_GM_MAX_TOKENS")
            self.max_tokens = int(env) if env else _DEFAULT_MAX_TOKENS.get(self.provider, 2048)
        if not self.max_rpm:
            env = os.environ.get("FANTASY_GM_MAX_RPM")
            self.max_rpm = float(env) if env else _DEFAULT_MAX_RPM.get(self.provider, 4.0)
        if not self.reasoning_effort:
            self.reasoning_effort = _DEFAULT_REASONING_EFFORT.get(self.provider, "")


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
    rpm = max_rpm or AgentConfig().max_rpm
    if _RATE_LIMITER is None or _RATE_LIMITER_RPM != rpm:
        from langchain_core.rate_limiters import InMemoryRateLimiter
        _RATE_LIMITER = InMemoryRateLimiter(
            requests_per_second=rpm / 60.0,
            check_every_n_seconds=0.1,
            max_bucket_size=1,
        )
        _RATE_LIMITER_RPM = rpm
    return _RATE_LIMITER
