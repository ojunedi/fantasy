"""Expert disagreement reaches the agent; the optimizer stays on ESPN's points."""
from __future__ import annotations

import json
from datetime import datetime

from langchain_core.messages import ToolMessage

from fantasy_gm.agent.graph import LineupGraphAgent
from fantasy_gm.agent.tools import LineupToolContext, disagreements
from fantasy_gm.models import ExpertRanking, PlayerProjection, Position, Roster
from fantasy_gm.signals.base import SignalAvailability, SignalBundle


def _rank(pid, pos, ecr, sd, espn):
    return ExpertRanking(player_id=pid, position=pos, ecr=ecr, sd=sd, pos_rank=f"{pos}{round(ecr)}",
                         scrape_date="2026-10-30", espn_pos_rank=espn)


def _ctx(rankings) -> LineupToolContext:
    bundle = SignalBundle(week=9, season=2026, availability=[
        SignalAvailability(name="projections", available=True, as_of=datetime.utcnow())])
    bundle.expert_rankings = rankings
    bundle.projections = {"1": PlayerProjection(player_id="1", player_name="Back", position=Position.RB,
                                                projected_points=9.4, week=9, season=2026)}
    ctx = LineupToolContext(adapter=None, settings=None, team_id="8", week=9, season=2026)
    ctx._signals = bundle
    ctx._roster = Roster(team_id="8", team_name="Me", owner_name="", players=[], week=9, season=2026)
    return ctx


def test_fprank02_a_sharp_disagreement_is_flagged_with_both_ranks():
    ctx = _ctx({"1": _rank("1", "RB", ecr=7.0, sd=2.0, espn=18)})

    summary = ctx._tool_get_signals({})

    # FPRANK-02 THEN the summary flags him with ESPN's rank and the experts' rank
    assert "Experts and ESPN disagree sharply on:" in summary
    assert "ESPN ranks him RB18, the experts RB7" in summary


def test_fprank03_a_small_difference_is_not_flagged():
    rankings = {"2": _rank("2", "WR", ecr=9.0, sd=1.5, espn=12)}

    # FPRANK-03 THEN he is not flagged
    assert disagreements(rankings) == []
    assert "disagree sharply" not in _ctx(rankings)._tool_get_signals({})


def test_fprank05_the_decision_records_the_rankings_it_saw_and_the_optimizer_is_unchanged():
    ctx = _ctx({"1": _rank("1", "RB", ecr=7.0, sd=2.0, espn=18)})
    result = {"starter_player_ids": ["1"], "changes_from_current": [], "memo": "Start him.",
              "confidence": 0.7}

    record = LineupGraphAgent().build_record(
        ctx, [ToolMessage(content=json.dumps(result), name="propose_lineup", tool_call_id="t")])

    # FPRANK-05 THEN it records each ranked player's expert rank and the scrape date
    assert record.inputs_snapshot["expert_rankings"]["1"] == {
        "ecr": 7.0, "sd": 2.0, "pos_rank": "RB7", "espn_pos_rank": 18, "scrape_date": "2026-10-30"}
    # FPRANK-05 AND the projections the optimizer used are ESPN's
    assert record.inputs_snapshot["projections"] == {"1": 9.4}
