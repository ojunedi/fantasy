"""Lineup and trade briefs: computed numbers only, or withheld."""
from __future__ import annotations

import json
from datetime import datetime

from langchain_core.messages import ToolMessage

from fantasy_gm.agent.graph import LineupGraphAgent
from fantasy_gm.agent.tools import LineupToolContext
from fantasy_gm.agent.trade.graph import TradeGraphAgent
from fantasy_gm.models import Roster
from fantasy_gm.signals.base import SignalAvailability, SignalBundle
from fantasy_gm.models import PlayerProjection, Position

WEEK, SEASON = 9, 2026


def _lineup_ctx() -> LineupToolContext:
    now = datetime.utcnow()
    bundle = SignalBundle(week=WEEK, season=SEASON, availability=[
        SignalAvailability(name="projections", available=True, as_of=now)])
    bundle.projections = {"100": PlayerProjection(
        player_id="100", player_name="Bijan Robinson", projected_points=23.09,
        position=Position.RB, week=WEEK, season=SEASON)}
    ctx = LineupToolContext(adapter=None, settings=None, team_id="8", week=WEEK, season=SEASON)
    ctx._signals = bundle
    ctx._roster = Roster(team_id="8", team_name="Me", owner_name="", players=[],
                         week=WEEK, season=SEASON)
    ctx.call_log = [{"tool": "get_opponent_defense", "input": {},
                     "output": "Bijan Robinson vs CHI: run DEF rank #26, allows 18.4"}]
    return ctx


def _proposal(name: str, result: dict) -> list:
    return [ToolMessage(content=json.dumps(result), name=name, tool_call_id="t1")]


def _lineup_record(memo: str):
    result = {"starter_player_ids": ["100", "101"], "changes_from_current": [],
              "memo": memo, "confidence": 0.8, "what_would_change_this": "A late scratch."}
    return LineupGraphAgent().build_record(_lineup_ctx(), _proposal("propose_lineup", result))


def test_brief01_a_lineup_brief_that_only_restates_computed_numbers_is_shown_as_written():
    memo = "Week 9: start Bijan (23.1 projected) against the #26 run defense; 80% confident."

    record = _lineup_record(memo)

    # BRIEF-01 THEN the brief is shown unchanged
    assert record.memo == memo
    assert record.recommendation["memo"] == memo
    assert "withheld" not in record.recommendation


def test_brief02_one_invented_number_among_many_withholds_the_lineup_brief():
    memo = "Week 9: Bijan 23.1 projected vs the #26 defense allowing 18.4 — expect 31.5."

    record = _lineup_record(memo)

    # BRIEF-02 THEN the brief is replaced by a notice naming 31.5
    assert record.memo == "Brief withheld — it quoted numbers the analysis never computed: 31.5."
    # BRIEF-02 AND the original brief is kept on the record
    assert record.recommendation["withheld"]["memo"]["original"] == memo
    # BRIEF-02 AND the recommended starters are unchanged
    assert record.recommendation["starter_player_ids"] == ["100", "101"]


def test_brief03_an_invented_number_in_a_counterparty_pitch_withholds_that_pitch_only():
    from fantasy_gm.agent.trade.graph import _screen_trade_texts

    ctx = _lineup_ctx()
    ctx.call_log = [{"tool": "evaluate_trade", "input": {},
                     "output": "Package EV +4.2 for me, fairness 0.91, their RB depth 2"}]
    package = {"counterparty_team_id": "6", "send_player_ids": ["100"],
               "receive_player_ids": ["200"], "confidence": 0.7,
               "rationale": "EV +4.2 and fairness 0.91.",
               "counterparty_pitch": "You'd gain 12 points a week at RB."}

    out = _screen_trade_texts({"trades": [package], "memo": "One offer."}, ctx)
    [trade] = out["trades"]

    # BRIEF-03 THEN the pitch is replaced by a notice naming the number
    assert trade["counterparty_pitch"] == ("Pitch withheld — it quoted numbers the analysis "
                                           "never computed: 12.")
    # BRIEF-03 AND the rationale is shown as written
    assert trade["rationale"] == "EV +4.2 and fairness 0.91."
    # BRIEF-03 AND the trade package is unchanged
    assert {k: trade[k] for k in ("counterparty_team_id", "send_player_ids",
                                  "receive_player_ids")} == {
        "counterparty_team_id": "6", "send_player_ids": ["100"], "receive_player_ids": ["200"]}
    assert out["withheld"]["0"]["counterparty_pitch"]["untraced"] == ["12"]
