"""
Trade agent graph test with a fake chat model — no live API, no nflverse.

Proves the trade loop, tool execution, terminal routing (propose_trades /
abstain), and DecisionRecord(TRADE) construction. Heavy analytics inputs are
injected so the test runs fully offline.
"""
import tempfile
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from fantasy_gm.agent.config import AgentConfig
from fantasy_gm.agent.trade.graph import TradeGraphAgent
from fantasy_gm.agent.trade.tools import TradeToolContext
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


class FakeChatModel:
    def __init__(self, script):
        self._script = list(script)
        self.i = 0

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        msg = self._script[self.i]
        self.i += 1
        return msg


def _p(pid, pos, team=None):
    return Player(platform_id=pid, name=f"P{pid}", position=pos,
                  eligible_positions=[pos], nfl_team=team, status=PlayerStatus.ACTIVE)


def _rp(pid, pos, starter):
    return RosterPlayer(player=_p(pid, pos), slot=pos if starter else Position.BENCH,
                        is_starter=starter)


class FakeAdapter:
    def __init__(self, rosters):
        self._rosters = {r.team_id: r for r in rosters}
        self.league_id = "test"

    def get_all_rosters(self, week, season, fresh=False):
        return list(self._rosters.values())

    def get_roster(self, team_id, week, season, fresh=False):
        return self._rosters[team_id]

    def get_projections(self, week, season):
        return {}


@pytest.fixture
def settings():
    slots = [
        RosterSlot(slot_id="qb", position=Position.QB, is_starter=True),
        RosterSlot(slot_id="rb1", position=Position.RB, is_starter=True),
        RosterSlot(slot_id="wr1", position=Position.WR, is_starter=True),
        RosterSlot(slot_id="te1", position=Position.TE, is_starter=True),
        RosterSlot(slot_id="be0", position=Position.BENCH, is_starter=False),
        RosterSlot(slot_id="be1", position=Position.BENCH, is_starter=False),
    ]
    return LeagueSettings(
        platform=Platform.ESPN, league_id="test", season=2026, team_count=2,
        roster_slots=slots, scoring_rules=ScoringRules(rules=[]),
        waiver_type=WaiverType.SNAKE, faab_budget=None, playoff_start_week=15,
        playoff_weeks=[15, 16, 17], regular_season_weeks=list(range(1, 15)),
    )


@pytest.fixture
def ctx(settings):
    mine = Roster(team_id="8", team_name="Me", owner_name="Me", week=1, season=2026, players=[
        _rp("qb1", Position.QB, True),
        _rp("rb_weak", Position.RB, True),
        _rp("wr1", Position.WR, True),
        _rp("te1", Position.TE, True),
        _rp("wr_spare", Position.WR, False),
        _rp("wr_spare2", Position.WR, False),
    ])
    other = Roster(team_id="3", team_name="Them", owner_name="Rival", week=1, season=2026, players=[
        _rp("qb2", Position.QB, True),
        _rp("rb_strong", Position.RB, True),
        _rp("rb_strong2", Position.RB, False),
        _rp("wr3", Position.WR, True),
        _rp("te2", Position.TE, True),
    ])
    adapter = FakeAdapter([mine, other])
    weekly = {"qb1": 20, "rb_weak": 5, "wr1": 15, "te1": 8, "wr_spare": 9, "wr_spare2": 7,
              "qb2": 18, "rb_strong": 22, "rb_strong2": 12, "wr3": 10, "te2": 6}
    return TradeToolContext(
        adapter=adapter, settings=settings, team_id="8", week=1, season=2026,
        _weekly_proj={k: float(v) for k, v in weekly.items()},
    )


def _agent_with(script):
    tmp = Path(tempfile.mkdtemp()) / "cp.db"
    return TradeGraphAgent(AgentConfig(), llm=FakeChatModel(script), checkpoint_path=tmp)


def test_trade_agent_proposes(ctx):
    script = [
        AIMessage(content="", tool_calls=[
            {"name": "get_all_rosters", "args": {}, "id": "t1"},
            {"name": "get_roster_needs", "args": {}, "id": "t2"},
        ]),
        AIMessage(content="", tool_calls=[
            {"name": "get_trade_value", "args": {"player_ids": ["wr_spare", "rb_strong"]}, "id": "t3"},
            {"name": "evaluate_trade", "args": {
                "send_player_ids": ["wr_spare", "wr_spare2"],
                "receive_player_ids": ["rb_strong"],
                "counterparty_team_id": "3"}, "id": "t4"},
        ]),
        AIMessage(content="Proposing.", tool_calls=[
            {"name": "propose_trades", "args": {
                "trades": [{
                    "counterparty_team_id": "3",
                    "send_player_ids": ["wr_spare", "wr_spare2"],
                    "receive_player_ids": ["rb_strong"],
                    "rationale": "Consolidates WR surplus into a scarce RB1; upgrades my RB starter.",
                    "counterparty_pitch": "They have RB depth and start only one WR-worthy option.",
                    "confidence": 0.7,
                }],
                "memo": "Consolidate WR depth for RB1.",
                "what_would_change_this": "A wr_spare injury.",
            }, "id": "t5"},
        ]),
    ]
    record = _agent_with(script).decide(ctx)
    assert record.decision_type == DecisionType.TRADE
    assert not record.recommendation.get("abstained")
    trades = record.recommendation["trades"]
    assert trades[0]["receive_player_ids"] == ["rb_strong"]
    assert trades[0]["send_names"] == ["Pwr_spare", "Pwr_spare2"]  # enriched
    assert record.confidence == 0.7
    tools_used = [c["tool"] for c in record.inputs_snapshot["tool_calls"]]
    assert "evaluate_trade" in tools_used and "propose_trades" in tools_used


def test_trade_agent_abstains(ctx):
    script = [
        AIMessage(content="", tool_calls=[
            {"name": "abstain", "args": {
                "missing_information": ["no clear surplus/need fit"],
                "what_you_would_need": "A team willing to move an RB1.",
                "memo": "No favorable trade available.",
            }, "id": "t1"},
        ]),
    ]
    record = _agent_with(script).decide(ctx)
    assert record.recommendation.get("abstained") is True
    assert record.confidence == 0.0


def test_evaluate_trade_tool_reports_roster_impact(ctx):
    out, terminal = ctx.dispatch("evaluate_trade", {
        "send_player_ids": ["wr_spare", "wr_spare2"],
        "receive_player_ids": ["rb_strong"],
    })
    assert not terminal
    assert "EV delta" in out
    assert "Starting-lineup impact" in out
    # Receiving a 22-pt RB for bench WRs should raise the optimized starter total.
    assert "→" in out


def test_get_trade_value_tool(ctx):
    out, _ = ctx.dispatch("get_trade_value", {"player_ids": ["rb_strong", "wr_spare"]})
    assert "rb_strong" in out and "value" in out
