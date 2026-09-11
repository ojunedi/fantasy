"""Tests for trade valuation and evaluation."""
import pytest

from fantasy_gm.core.trade_value import (
    asset_value,
    build_value_map,
    evaluate_trade,
    evaluate_trade_for_roster,
)
from fantasy_gm.models import (
    LeagueSettings,
    Platform,
    Player,
    PlayerStatus,
    Position,
    RosterSlot,
    ScoringRules,
    WaiverType,
)


def _player(pid, pos):
    return Player(platform_id=pid, name=f"P{pid}", position=pos,
                  eligible_positions=[pos], status=PlayerStatus.ACTIVE)


def test_scarcity_premium_for_rb_over_wr():
    rb = asset_value("r", Position.RB, 100.0)
    wr = asset_value("w", Position.WR, 100.0)
    assert rb.value > wr.value  # same points, RB scarcer


def test_evaluate_trade_even_is_fair():
    vm = build_value_map({"a": 100.0, "b": 100.0}, {"a": Position.WR, "b": Position.WR})
    ev = evaluate_trade(["a"], ["b"], vm)
    assert ev.verdict == "fair"
    assert ev.fairness == pytest.approx(1.0)


def test_evaluate_trade_winning_side():
    vm = build_value_map({"a": 50.0, "b": 100.0}, {"a": Position.WR, "b": Position.WR})
    ev = evaluate_trade(["a"], ["b"], vm)  # send 50, receive 100
    assert ev.ev_delta > 0
    assert ev.verdict == "win"
    assert ev.fairness < 1.0


def test_evaluate_trade_losing_side():
    vm = build_value_map({"a": 100.0, "b": 50.0}, {"a": Position.WR, "b": Position.WR})
    ev = evaluate_trade(["a"], ["b"], vm)
    assert ev.verdict == "lose"


def test_two_for_one_consolidation():
    vm = build_value_map({"a": 60.0, "b": 40.0, "star": 110.0},
                         {"a": Position.WR, "b": Position.WR, "star": Position.RB})
    ev = evaluate_trade(["a", "b"], ["star"], vm)
    # send 100 value of WRs, receive 110*1.12 scarcity RB → clear win
    assert ev.verdict == "win"


@pytest.fixture
def settings():
    slots = [
        RosterSlot(slot_id="qb", position=Position.QB, is_starter=True),
        RosterSlot(slot_id="rb1", position=Position.RB, is_starter=True),
        RosterSlot(slot_id="wr1", position=Position.WR, is_starter=True),
        RosterSlot(slot_id="be0", position=Position.BENCH, is_starter=False),
        RosterSlot(slot_id="be1", position=Position.BENCH, is_starter=False),
    ]
    return LeagueSettings(
        platform=Platform.ESPN, league_id="t", season=2026, team_count=12,
        roster_slots=slots, scoring_rules=ScoringRules(rules=[]),
        waiver_type=WaiverType.SNAKE, faab_budget=None, playoff_start_week=15,
        playoff_weeks=[15, 16, 17], regular_season_weeks=list(range(1, 15)),
    )


def test_roster_impact_improves_starting_total(settings):
    # I roster a weak RB; trade a spare WR for a strong RB → starters improve.
    my_players = [
        _player("qb1", Position.QB),
        _player("rb_weak", Position.RB),
        _player("wr1", Position.WR),
        _player("wr_spare", Position.WR),
    ]
    incoming = [_player("rb_strong", Position.RB)]
    projections = {"qb1": 20.0, "rb_weak": 5.0, "wr1": 15.0,
                   "wr_spare": 6.0, "rb_strong": 22.0}
    vm = build_value_map(
        {"wr_spare": 40.0, "rb_strong": 90.0},
        {"wr_spare": Position.WR, "rb_strong": Position.RB},
    )
    ev = evaluate_trade_for_roster(
        my_players, incoming, ["wr_spare"], ["rb_strong"], vm, projections, settings)
    assert ev.roster_impact is not None
    # Before starters: qb20 + rb_weak5 + best WR15 = 40. After: rb_strong starts.
    assert ev.roster_impact.after_total > ev.roster_impact.before_total
    assert ev.roster_impact.delta > 0
