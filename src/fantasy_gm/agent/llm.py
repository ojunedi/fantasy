"""
Single construction point for every chat model in the project.

Both the agent loop (`GraphAgent._build_llm`) and the LLM sub-agents
(`subagents.base.default_llm`) build their client here, so the shared rate
limiter and the retry bound apply whichever provider is selected. Building a
chat client anywhere else would escape both guards.

Provider is chosen with FANTASY_GM_PROVIDER (google | groq | anthropic); the model defaults
per provider and can be overridden with FANTASY_GM_MODEL.
"""
from __future__ import annotations

from typing import Any

from fantasy_gm.agent.config import AgentConfig, shared_rate_limiter


_KEY_FIELD = {"groq": "groq_api_key", "anthropic": "anthropic_api_key"}


def api_key_for(config: AgentConfig) -> str:
    """The API key that matters for the configured provider."""
    return getattr(config, _KEY_FIELD.get(config.provider, "google_api_key"))


def build_chat_model(config: AgentConfig | None = None,
                     max_output_tokens: int | None = None) -> Any:
    """Build the configured chat model with the shared rate limiter attached."""
    cfg = config or AgentConfig()
    max_out = max_output_tokens or cfg.max_tokens
    limiter = shared_rate_limiter(cfg.max_rpm)

    if cfg.provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        # An unscoped key must name its workspace explicitly; a scoped key must not.
        headers = ({"anthropic-workspace-id": cfg.anthropic_workspace_id}
                   if cfg.anthropic_workspace_id else None)
        return ChatAnthropic(
            model=cfg.model,
            anthropic_api_key=cfg.anthropic_api_key or None,
            max_tokens=max_out,
            rate_limiter=limiter,
            max_retries=cfg.max_retries,
            default_headers=headers,
        )

    if cfg.provider == "groq":
        from langchain_groq import ChatGroq
        return ChatGroq(
            model=cfg.model,
            groq_api_key=cfg.groq_api_key or None,
            max_tokens=max_out,
            rate_limiter=limiter,
            max_retries=cfg.max_retries,
            # Reasoning tokens count against max_tokens, so on a tight output
            # quota they can starve the actual tool call. See config defaults.
            reasoning_effort=cfg.reasoning_effort or None,
        )

    from langchain_google_genai import ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI(
        model=cfg.model,
        google_api_key=cfg.google_api_key or None,
        max_output_tokens=max_out,
        rate_limiter=limiter,
        max_retries=cfg.max_retries,
    )
