"""
LangGraph agent test with a fake chat model.

Proves the graph loop, tool execution via ToolNode, terminal-tool routing, and
DecisionRecord construction work end-to-end — no live API call.
"""
import tempfile
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from fantasy_gm.agent.config import AgentConfig
from fantasy_gm.agent.graph import LineupGraphAgent
from fantasy_gm.agent.tools import LineupToolContext
from fantasy_gm.models import (
    DecisionType,
    LeagueSettings,
    Platform,
    Player,
    PlayerStatus,
    Position,
    Roster,
    RosterPlayer,
    RosterSlot,
    ScoringRules,
    WaiverType,
)


# ---- Fakes ---------------------------------------------------------------

class FakeChatModel:
    """Returns a scripted list of AIMessages; ignores the input messages."""
    def __init__(self, script):
        self._script = list(script)
        self.i = 0

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        msg = self._script[self.i]
        self.i += 1
        return msg


class FakeAdapter:
    def __init__(self, roster, projections):
        self._roster = roster
        self._projections = projections
        self.league_id = "test"
        from fantasy_gm.adapters.cache import DiskCache
        self._cache = DiskCache(Path(tempfile.mkdtemp()), ttl_seconds=3600)

    def get_roster(self, team_id, week, season, fresh=False):
        return self._roster

    def get_projections(self, week, season):
        return self._projections

    def get_matchup(self, team_id, week, season):
        raise Exception("no matchup in test")


def make_player(pid, pos):
    return Player(platform_id=pid, name=f"Player {pid}", position=pos,
                  eligible_positions=[pos], status=PlayerStatus.ACTIVE)


@pytest.fixture
def ctx():
    slots = [
        RosterSlot(slot_id="qb", position=Position.QB, is_starter=True),
        RosterSlot(slot_id="rb1", position=Position.RB, is_starter=True),
        RosterSlot(slot_id="wr1", position=Position.WR, is_starter=True),
        RosterSlot(slot_id="be0", position=Position.BENCH, is_starter=False),
    ]
    settings = LeagueSettings(
        platform=Platform.ESPN, league_id="test", season=2025, team_count=12,
        roster_slots=slots, scoring_rules=ScoringRules(rules=[]),
        waiver_type=WaiverType.SNAKE, faab_budget=None,
        playoff_start_week=15, playoff_weeks=[15, 16, 17],
        regular_season_weeks=list(range(1, 15)),
    )
    players = [
        RosterPlayer(player=make_player("qb1", Position.QB), slot=Position.QB, is_starter=True),
        RosterPlayer(player=make_player("rb1", Position.RB), slot=Position.RB, is_starter=True),
        RosterPlayer(player=make_player("wr1", Position.WR), slot=Position.WR, is_starter=True),
        RosterPlayer(player=make_player("wr2", Position.WR), slot=Position.BENCH, is_starter=False),
    ]
    roster = Roster(team_id="8", team_name="Test", owner_name="Me",
                    players=players, week=1, season=2025)
    adapter = FakeAdapter(roster, {"qb1": 20.0, "rb1": 15.0, "wr1": 8.0, "wr2": 14.0})
    return LineupToolContext(adapter=adapter, settings=settings,
                             team_id="8", week=1, season=2025)


def _agent_with(script):
    tmp = Path(tempfile.mkdtemp()) / "cp.db"
    return LineupGraphAgent(AgentConfig(), llm=FakeChatModel(script), checkpoint_path=tmp)


# ---- Tests ---------------------------------------------------------------

def test_graph_proposes_lineup(ctx):
    # Read tools are pre-fetched before the LLM runs; the model goes straight
    # to optimize_lineup / propose_lineup without calling the read tools.
    script = [
        AIMessage(content="Starting wr2 over wr1.", tool_calls=[
            {"name": "propose_lineup", "args": {
                "starter_player_ids": ["qb1", "rb1", "wr2"],
                "changes_from_current": [
                    {"start_in_player_id": "wr2", "bench_out_player_id": "wr1",
                     "reason": "wr2 projects 14 vs wr1's 8."}
                ],
                "memo": "Swap wr1 for wr2 on a clear projection edge.",
                "confidence": 0.8,
                "what_would_change_this": "A late injury to wr2.",
            }, "id": "t1"},
        ]),
    ]
    record = _agent_with(script).decide(ctx)

    assert record.decision_type == DecisionType.LINEUP
    assert record.confidence == 0.8
    assert not record.recommendation.get("abstained")
    assert record.recommendation["starter_player_ids"] == ["qb1", "rb1", "wr2"]
    assert record.inputs_snapshot["projections"]["wr2"] == 14.0
    # prefetch logs: get_roster, get_projections, get_signals, get_league_context
    # (get_matchup raises in FakeAdapter → not logged); plus propose_lineup = 5 total.
    tool_names = [c["tool"] for c in record.inputs_snapshot["tool_calls"]]
    assert "propose_lineup" in tool_names
    assert "get_roster" in tool_names
    assert "get_projections" in tool_names


def test_graph_abstains(ctx):
    script = [
        AIMessage(content="", tool_calls=[
            {"name": "abstain", "args": {
                "missing_information": ["wr1 injury status unclear"],
                "what_you_would_need": "Final injury report.",
                "memo": "Too much uncertainty.",
            }, "id": "t1"},
        ]),
    ]
    record = _agent_with(script).decide(ctx)
    assert record.recommendation.get("abstained") is True
    assert record.confidence == 0.0
    assert "wr1 injury status unclear" in record.recommendation["missing_information"]


def test_graph_uses_news_tool(ctx, monkeypatch):
    """The nfl_news tool is wired and logged."""
    import fantasy_gm.signals.news as news
    monkeypatch.setattr(news, "get_nfl_news", lambda limit=10: "FAKE NEWS: nothing new.")
    script = [
        AIMessage(content="", tool_calls=[{"name": "nfl_news", "args": {"limit": 5}, "id": "n1"}]),
        AIMessage(content="", tool_calls=[
            {"name": "abstain", "args": {
                "missing_information": ["still unclear"],
                "what_you_would_need": "more",
                "memo": "abstaining",
            }, "id": "t2"},
        ]),
    ]
    record = _agent_with(script).decide(ctx)
    tools_used = [c["tool"] for c in record.inputs_snapshot["tool_calls"]]
    assert "nfl_news" in tools_used


def test_optimize_lineup_tool_uses_adjusted_projections(ctx):
    out_raw, _ = ctx.dispatch("optimize_lineup", {})
    assert "Player wr2" in out_raw
    out_adj, _ = ctx.dispatch("optimize_lineup", {"projections": {"wr1": 25.0}})
    assert "Player wr1" in out_adj


def test_llm_call_budget_caps_the_loop(ctx):
    """A model that never terminates is stopped after max_llm_calls LLM calls."""
    class LoopingModel:
        def __init__(self):
            self.calls = 0

        def bind_tools(self, tools):
            return self

        def invoke(self, messages):
            self.calls += 1
            return AIMessage(content="", tool_calls=[
                {"name": "get_my_injury_summary", "args": {}, "id": f"t{self.calls}"}])

    model = LoopingModel()
    tmp = Path(tempfile.mkdtemp()) / "cp.db"
    agent = LineupGraphAgent(AgentConfig(max_llm_calls=3), llm=model, checkpoint_path=tmp)
    record = agent.decide(ctx, verbose=False)

    assert model.calls == 3            # capped — did not loop until recursion limit
    assert ctx.llm_calls == 3
    assert record.recommendation.get("abstained")  # no terminal tool → abstain fallback
