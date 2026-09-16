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
    DecisionRecord,
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


# ---- Batched injury / news tools ------------------------------------------

def _hurt(pid, status):
    """A roster player with a non-ACTIVE status, so the injury LLM is engaged."""
    p = Player(platform_id=pid, name=f"P{pid}", position=Position.WR,
               eligible_positions=[Position.WR], status=status)
    return RosterPlayer(player=p, slot=Position.BENCH, is_starter=False)


@pytest.fixture
def hurt_ctx(settings):
    mine = Roster(team_id="8", team_name="Me", owner_name="Me", week=1, season=2026, players=[
        _rp("qb1", Position.QB, True),
        _rp("rb1", Position.RB, True),
        _rp("wr_ok", Position.WR, True),
        _rp("te1", Position.TE, True),
        _hurt("wr_out", PlayerStatus.OUT),
        _hurt("wr_quest", PlayerStatus.QUESTIONABLE),
    ])
    return TradeToolContext(
        adapter=FakeAdapter([mine]), settings=settings, team_id="8", week=1, season=2026,
        _weekly_proj={"qb1": 20.0, "rb1": 10.0, "wr_ok": 12.0, "te1": 8.0,
                      "wr_out": 0.0, "wr_quest": 6.0},
    )


def test_injury_tool_makes_one_subagent_call_for_the_batch(hurt_ctx):
    calls = []

    def fake_injury(players):
        calls.append([p["player_name"] for p in players])
        return {p["player_name"]: {"availability_pct": 25, "role_change_flag": True,
                                   "note": "Limited."} for p in players}

    hurt_ctx.injury_fn = fake_injury
    hurt_ctx.llm_budget = 8
    out, _ = hurt_ctx.dispatch("get_injury_report",
                               {"player_ids": ["wr_out", "wr_quest"]})

    assert len(calls) == 1                      # ONE call, not one per player
    assert calls[0] == ["Pwr_out", "Pwr_quest"]
    assert hurt_ctx.llm_calls == 1
    assert out.count("availability_pct=25") == 2


def test_injury_tool_answers_active_players_without_an_llm(hurt_ctx):
    def fake_injury(players):
        raise AssertionError("ACTIVE players must not reach the LLM")

    hurt_ctx.injury_fn = fake_injury
    hurt_ctx.llm_budget = 8
    out, _ = hurt_ctx.dispatch("get_injury_report", {"player_ids": ["wr_ok"]})
    assert "ACTIVE" in out
    assert hurt_ctx.llm_calls == 0


def test_injury_tool_mixes_active_and_hurt_in_one_call(hurt_ctx):
    calls = []

    def fake_injury(players):
        calls.append([p["player_name"] for p in players])
        return {p["player_name"]: {"availability_pct": 50} for p in players}

    hurt_ctx.injury_fn = fake_injury
    hurt_ctx.llm_budget = 8
    out, _ = hurt_ctx.dispatch("get_injury_report",
                               {"player_ids": ["wr_ok", "wr_out", "nope"]})
    assert calls == [["Pwr_out"]]               # only the hurt player was sent
    assert "ACTIVE" in out and "not found" in out
    assert hurt_ctx.llm_calls == 1


def test_news_tool_makes_one_subagent_call_for_the_batch(hurt_ctx):
    calls = []

    def fake_news(names):
        calls.append(list(names))
        return {n: {"events": [{"type": "usage_trend", "impact": "up",
                                "summary": "More targets."}],
                    "net_outlook": "up", "note": "Trending."} for n in names}

    hurt_ctx.news_fn = fake_news
    hurt_ctx.llm_budget = 8
    out, _ = hurt_ctx.dispatch("get_player_news",
                               {"player_ids": ["wr_ok", "wr_out", "qb1"]})

    assert len(calls) == 1                      # ONE call for all three
    assert calls[0] == ["Pwr_ok", "Pwr_out", "Pqb1"]
    assert hurt_ctx.llm_calls == 1
    assert out.count("net outlook up") == 3


def test_batched_tools_respect_the_remaining_budget(hurt_ctx):
    """A batch that would overrun the budget is skipped, not half-charged."""
    def fake_news(names):
        raise AssertionError("must not call the LLM with no budget left")

    hurt_ctx.news_fn = fake_news
    hurt_ctx.llm_budget = 2
    hurt_ctx.llm_calls = 2
    out, _ = hurt_ctx.dispatch("get_player_news", {"player_ids": ["wr_ok"]})
    assert "budget reached" in out
    assert hurt_ctx.llm_calls == 2


def test_batched_tool_charges_once_per_chunk(hurt_ctx):
    """Beyond the chunk cap the budget must be charged per model call."""
    from fantasy_gm.agent.subagents.news import _BATCH_SIZE

    hurt_ctx.news_fn = lambda names: {n: {"net_outlook": "neutral"} for n in names}
    hurt_ctx.llm_budget = 8
    pids = ["qb1", "rb1", "wr_ok", "te1", "wr_out", "wr_quest"]
    assert len(pids) <= _BATCH_SIZE
    hurt_ctx.dispatch("get_player_news", {"player_ids": pids})
    assert hurt_ctx.llm_calls == 1              # 6 players, one chunk, one charge


# ---- Truncated runs are not abstentions -----------------------------------

class _LoopingModel:
    """Never calls a terminal tool — it just keeps evaluating trades."""
    def __init__(self):
        self.calls = 0

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        self.calls += 1
        return AIMessage(content="", tool_calls=[{
            "name": "evaluate_trade",
            "args": {"send_player_ids": ["wr_spare"],
                     "receive_player_ids": ["rb_strong"],
                     "counterparty_team_id": "3"},
            "id": f"t{self.calls}"}])


def _looping_agent(budget):
    tmp = Path(tempfile.mkdtemp()) / "cp.db"
    return TradeGraphAgent(AgentConfig(max_llm_calls=budget), llm=_LoopingModel(),
                           checkpoint_path=tmp)


def test_budget_exhaustion_is_reported_as_truncated_not_abstained(ctx):
    record = _looping_agent(2).decide(ctx, verbose=False)
    rec = record.recommendation
    assert rec["truncated"] is True
    assert "budget exhausted" in rec["reason"]
    assert rec["llm_calls"] == rec["llm_budget"] == 2
    assert "cut off" in record.memo
    # Still flagged abstained so executors refuse to act on a truncated run.
    assert rec["abstained"] is True


def test_truncated_run_salvages_the_packages_it_already_priced(ctx):
    """The work that used to be silently discarded must survive the cut-off."""
    record = _looping_agent(2).decide(ctx, verbose=False)
    packages = record.recommendation["evaluated_packages"]
    assert packages, "evaluated trades were dropped on truncation"
    assert packages[0]["send_player_ids"] == ["wr_spare"]
    assert packages[0]["receive_player_ids"] == ["rb_strong"]
    assert "EV delta" in packages[0]["evaluation"]


def test_a_real_abstain_is_not_marked_truncated(ctx):
    script = [AIMessage(content="", tool_calls=[{
        "name": "abstain",
        "args": {"missing_information": ["no fits"], "what_you_would_need": "more depth",
                 "memo": "Nothing available."},
        "id": "t1"}])]
    record = _agent_with(script).decide(ctx, verbose=False)
    assert record.recommendation["abstained"] is True
    assert not record.recommendation.get("truncated")
    assert record.memo == "Nothing available."


def _record_with(rec: dict, memo: str) -> DecisionRecord:
    return DecisionRecord(week=1, season=2026, decision_type=DecisionType.TRADE,
                          inputs_snapshot={}, signals_staleness={},
                          recommendation=rec, memo=memo, confidence=0.0)


def test_renderer_distinguishes_truncation_from_abstention(capsys):
    from fantasy_gm.memo.cli import _render_no_recommendation

    truncated = _record_with(
        {"abstained": True, "truncated": True, "llm_calls": 8, "llm_budget": 8,
         "evaluated_packages": [{"send_player_ids": ["A"], "receive_player_ids": ["B"],
                                 "counterparty_team_id": "3",
                                 "evaluation": "EV delta: +997.0 | verdict: WIN"}]},
        "Run was cut off before a recommendation.")
    _render_no_recommendation(truncated, truncated.recommendation)
    out = capsys.readouterr().out
    assert "RUN TRUNCATED" in out and "ABSTAINED" not in out
    assert "8 of 8" in out
    assert "+997.0" in out          # salvaged work is shown to the human

    abstained = _record_with(
        {"abstained": True, "missing_information": ["no fits"],
         "what_you_would_need": "more depth"}, "Nothing available.")
    _render_no_recommendation(abstained, abstained.recommendation)
    out = capsys.readouterr().out
    assert "AGENT ABSTAINED" in out and "TRUNCATED" not in out
    assert "no fits" in out
