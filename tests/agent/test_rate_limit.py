"""The process-wide requests-per-minute limiter.

The Gemini free tier allows 5 requests/minute. The per-run `max_llm_calls`
budget cannot enforce that (two runs in one minute double the calls), so a
single shared `InMemoryRateLimiter` is attached to every chat client.
"""
import os
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


def test_defaults_leave_headroom_under_the_free_tier():
    cfg = AgentConfig()
    assert cfg.max_rpm == 4        # under the 5/min quota
    assert cfg.max_llm_calls == 3  # per-run budget, lowered for headroom
    assert cfg.max_retries <= 2    # a 429 must not become a burst


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


def test_both_construction_sites_share_one_limiter(monkeypatch):
    """The whole point: two limiters would each allow max_rpm, doubling it."""
    monkeypatch.setitem(os.environ, "GOOGLE_API_KEY", "test-key")
    cfg = AgentConfig(google_api_key="test-key")

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
