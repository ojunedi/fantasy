"""The graph step limit must be a safety net, never the stop condition.

A live run died with `GraphRecursionError: Recursion limit of 12 reached`. The
cause was arithmetic, not a loop: `recursion_limit` was `max_tool_iterations * 2`
(6 * 2 = 12), while the LLM budget allows 8 calls, each of which can cost two
graph steps. So the net could fire before the budget logic — which degrades to a
truncated record — ever got the chance to run, throwing away the whole run.
"""
from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage

from fantasy_gm.agent.base import GraphAgent
from fantasy_gm.agent.config import AgentConfig
from fantasy_gm.agent.graph import LineupGraphAgent
from fantasy_gm.agent.tools import LineupToolContext
from tests.agent.test_locked_tools import _Adapter, _rp, _settings
from fantasy_gm.models import Position, Roster


# ------------------------------------------------------- the arithmetic

def test_the_step_limit_exceeds_what_the_llm_budget_can_spend():
    """Each LLM call can cost two steps (agent + tools), plus the reserved
    terminal turn. The net must sit above that or it fires on a normal run."""
    for budget in (4, 8, 12, 20):
        limit = GraphAgent._recursion_limit(6, budget)
        assert limit > 2 * budget, f"budget {budget} can outrun limit {limit}"


def test_the_regression_case_is_fixed():
    """max_tool_iterations=6 with the default budget of 8 produced 12."""
    assert GraphAgent._recursion_limit(6, 8) == 22
    assert GraphAgent._recursion_limit(6, 8) > 12


def test_a_generous_tool_iteration_cap_is_still_respected():
    assert GraphAgent._recursion_limit(20, 8) == 46


def test_the_limit_never_drops_below_the_iteration_cap():
    for max_iter in (1, 6, 10, 20):
        assert GraphAgent._recursion_limit(max_iter, 8) >= 2 * max_iter


# --------------------------------------------------- graceful degradation

class _LoopingLLM:
    """A model that never calls a terminal tool — the worst realistic case.

    It always asks for the same analysis tool, so only the LLM budget can stop
    it. If the step limit were the binding constraint this would raise.
    """

    def __init__(self, tool_name="get_my_injury_summary"):
        self.tool_name = tool_name
        self.calls = 0
        self._forced = None

    def bind_tools(self, tools, tool_choice=None):
        bound = _LoopingLLM(self.tool_name)
        bound.calls = 0
        bound._parent = self
        bound._names = [getattr(t, "name", None) for t in tools]
        bound._forced = tool_choice
        return bound

    def invoke(self, prompt):
        parent = getattr(self, "_parent", self)
        parent.calls += 1
        names = getattr(self, "_names", []) or []
        # On the final turn the analysis tools are withdrawn; keep asking for a
        # non-terminal tool anyway so nothing but the budget ends this run.
        name = self.tool_name if self.tool_name in names else (
            names[0] if names else self.tool_name)
        return AIMessage(content="still looking", tool_calls=[
            {"name": name, "args": {}, "id": f"c{parent.calls}"},
        ])


class _StubAgent(LineupGraphAgent):
    """LineupGraphAgent with the provider swapped out and prefetch disabled."""

    def __init__(self, config, llm):
        super().__init__(config)
        self._llm = llm

    def _build_llm(self):
        return self._llm

    def _llm_description(self, llm):
        return "stub"

    def user_prompt(self, ctx):
        # The real prompt pre-fetches five tools over the network.
        return "Recommend a lineup."


@pytest.fixture
def ctx(tmp_path):
    players = [
        _rp("qb", Position.QB, Position.QB, True),
        _rp("rb", Position.RB, Position.RB, True),
        _rp("w1", Position.WR, Position.WR, True),
        _rp("w2", Position.WR, Position.WR, True),
        _rp("flex", Position.RB, Position.FLEX, True),
        _rp("bench", Position.WR, Position.BENCH, False),
    ]
    roster = Roster(team_id="8", team_name="Mine", owner_name="", players=players,
                    week=2, season=2026)
    context = LineupToolContext(adapter=_Adapter(roster), settings=_settings(),
                                team_id="8", week=2, season=2026)
    context._raw_projection_map = lambda: {"qb": 20.0, "rb": 15.0, "w1": 12.0,
                                           "w2": 11.0, "flex": 9.0, "bench": 8.0}
    return context


@pytest.fixture
def agent(tmp_path, monkeypatch):
    def _make(llm, budget=4):
        config = AgentConfig()
        config.max_llm_calls = budget
        a = _StubAgent(config, llm)
        a._checkpoint_path = tmp_path / "checkpoints.db"
        return a
    return _make


def test_a_run_that_never_terminates_does_not_raise(agent, ctx):
    """The whole point: no GraphRecursionError escapes to the caller."""
    record = agent(_LoopingLLM(), budget=4).decide(ctx, verbose=False)
    assert record is not None


def test_such_a_run_is_recorded_as_truncated(agent, ctx):
    record = agent(_LoopingLLM(), budget=4).decide(ctx, verbose=False)
    assert record.recommendation["truncated"] is True
    assert record.recommendation["abstained"] is True      # executors must refuse
    assert record.confidence == 0.0


def test_the_budget_stops_it_not_the_step_limit(agent, ctx):
    """If the step limit were binding, `hit_step_limit` would be set instead."""
    record = agent(_LoopingLLM(), budget=4).decide(ctx, verbose=False)
    assert ctx.llm_calls >= ctx.llm_budget
    assert record.recommendation["hit_step_limit"] is False
    assert "budget" in record.recommendation["reason"]


def test_the_analysis_is_preserved_not_discarded(agent, ctx):
    """A crash threw away every tool result; a truncated record keeps them."""
    agent(_LoopingLLM(), budget=4).decide(ctx, verbose=False)
    assert ctx.call_log, "tool calls made during the run should still be logged"


def test_a_step_limit_hit_is_reported_honestly(agent, ctx, monkeypatch):
    """Force the net to fire and check it degrades rather than raising."""
    monkeypatch.setattr(GraphAgent, "_recursion_limit",
                        staticmethod(lambda max_iter, budget: 4))
    record = agent(_LoopingLLM(), budget=8).decide(ctx, verbose=False)
    assert record.recommendation["truncated"] is True
    assert record.recommendation["hit_step_limit"] is True
    assert "step limit" in record.recommendation["reason"]
    assert "looped" in record.memo


def test_a_step_limit_hit_emits_a_trace_event(agent, ctx, monkeypatch):
    monkeypatch.setattr(GraphAgent, "_recursion_limit",
                        staticmethod(lambda max_iter, budget: 4))
    events = []
    agent(_LoopingLLM(), budget=8).decide(ctx, emit=events.append)
    assert any(e["kind"] == "step_limit" for e in events)
