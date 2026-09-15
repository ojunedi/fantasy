"""The process-wide requests-per-minute limiter.

Providers meter differently (the Gemini free tier allows 5 requests/minute;
Anthropic is far less constrained), so the ceiling is per-provider. The per-run
`max_llm_calls` budget cannot enforce a rate on its own — two runs in one minute
double the calls — so a single shared `InMemoryRateLimiter` is attached to every
chat client, whichever provider built it.
"""
import time

import pytest

from fantasy_gm.agent import config as config_mod
from fantasy_gm.agent.base import GraphAgent
from fantasy_gm.agent.config import AgentConfig, shared_rate_limiter
from fantasy_gm.agent.subagents.base import default_llm


@pytest.fixture(autouse=True)
def _reset_limiter():
    """Keep the module-level singleton from leaking between tests."""
    config_mod._RATE_LIMITER = None
    config_mod._RATE_LIMITER_RPM = None
    yield
    config_mod._RATE_LIMITER = None
    config_mod._RATE_LIMITER_RPM = None


def test_shared_rate_limiter_is_a_singleton():
    assert shared_rate_limiter(4) is shared_rate_limiter(4)


def test_google_defaults_leave_headroom_under_the_free_tier():
    """Gemini's free tier is 5 req/min, and retries sit below the limiter."""
    cfg = AgentConfig(provider="google")
    assert cfg.max_rpm == 4
    assert cfg.max_retries <= 2
    assert cfg.max_rpm * cfg.max_retries <= 5   # worst-case requests/minute


def test_each_provider_gets_its_own_ceiling():
    """A ceiling tuned for one provider must not be imposed on another."""
    rpm = {p: AgentConfig(provider=p).max_rpm for p in ("google", "groq", "anthropic")}
    assert rpm["groq"] < rpm["google"] < rpm["anthropic"]


def test_limiter_cannot_burst():
    limiter = shared_rate_limiter(4)
    assert limiter.max_bucket_size == 1
    assert limiter.requests_per_second == pytest.approx(4 / 60.0)


class _Agent(GraphAgent):
    """Minimal concrete subclass; we only exercise `_build_llm`."""
    system_prompt = ""
    terminal_tools = set()

    def build_tools(self, ctx):
        return []

    def user_prompt(self, ctx):
        return ""

    def build_record(self, ctx, messages):
        return {}

    def thread_id(self, ctx):
        return "test"


@pytest.mark.parametrize("provider,key_field", [
    ("google", "google_api_key"),
    ("anthropic", "anthropic_api_key"),
])
def test_both_construction_sites_share_one_limiter(provider, key_field):
    """The whole point: two limiters would each allow max_rpm, doubling it."""
    cfg = AgentConfig(provider=provider, **{key_field: "test-key"})

    main_llm = _Agent(config=cfg)._build_llm()
    sub_llm = default_llm(cfg)

    assert main_llm.rate_limiter is not None
    assert main_llm.rate_limiter is sub_llm.rate_limiter
    assert main_llm.rate_limiter is shared_rate_limiter(cfg.max_rpm)
    # Retries are bounded on both, so one rejection can't fan out.
    assert main_llm.max_retries == cfg.max_retries
    assert sub_llm.max_retries == cfg.max_retries


def test_limiter_spaces_calls_out():
    """Fast stand-in for the real 4/min: 600 rpm => 0.1s between calls."""
    limiter = shared_rate_limiter(600)
    limiter.acquire(blocking=True)  # drain the initial token
    start = time.monotonic()
    for _ in range(3):
        limiter.acquire(blocking=True)
    elapsed = time.monotonic() - start
    assert elapsed >= 0.25  # 3 calls at 0.1s apart, minus scheduling slack
