"""Locked players — those whose NFL game has already kicked off.

ESPN rejects any lineup transaction that touches such a player with
409 TRAN_LINEUP_LOCKED, so a recommendation that moves one is not a better
lineup, it is an impossible one. These tests pin that across the optimizer
and the plan builder.
"""
from __future__ import annotations

import pytest

from fantasy_gm.core.optimizer import (
    live_score,
    locks_from_roster,
    optimize_lineup,
    projected_score,
)
from fantasy_gm.execute.lineup_plan import (
    build_target_slots,
    locked_conflicts,
    plan_moves,
)
from fantasy_gm.models import (
    LeagueSettings,
    Platform,
    Player,
    Position,
    RosterPlayer,
    RosterSlot,
    ScoringRule,
    ScoringRules,
    WaiverType,
)

STARTERS = [(Position.QB, 1), (Position.RB, 1), (Position.WR, 2), (Position.FLEX, 1)]
FLEX_OK = {Position.RB, Position.WR, Position.TE}


@pytest.fixture
def settings() -> LeagueSettings:
    slots = [RosterSlot(slot_id=f"{p.value}_{i}", position=p, is_starter=True)
             for p, n in STARTERS for i in range(n)]
    slots += [RosterSlot(slot_id=f"BE_{i}", position=Position.BENCH, is_starter=False)
              for i in range(4)]
    return LeagueSettings(
        platform=Platform.ESPN, league_id="1", season=2026, team_count=12,
        roster_slots=slots, scoring_rules=ScoringRules(rules=[ScoringRule(stat="53", points=1.0)]),
        waiver_type=WaiverType.ROLLING, playoff_start_week=15,
        playoff_weeks=[15], regular_season_weeks=list(range(1, 15)),
    )


def _player(pid: str, position: Position) -> Player:
    eligible = [position, Position.FLEX] if position in FLEX_OK else [position]
    return Player(platform_id=pid, name=f"P{pid}", position=position,
                  eligible_positions=eligible, nfl_team="1")


def _rp(pid, position, slot, starter, locked=False, actual=None) -> RosterPlayer:
    return RosterPlayer(player=_player(pid, position), slot=slot, is_starter=starter,
                        is_locked=locked, actual_points=actual)


@pytest.fixture
def roster() -> list[RosterPlayer]:
    """WR "w_lo" starts and is locked after a bad game; "w_hi" outprojects him
    on the bench. Without lock awareness the optimizer wants to swap them."""
    return [
        _rp("qb", Position.QB, Position.QB, True),
        _rp("rb", Position.RB, Position.RB, True),
        _rp("w_lo", Position.WR, Position.WR, True, locked=True, actual=5.3),
        _rp("w_mid", Position.WR, Position.WR, True),
        _rp("flex", Position.RB, Position.FLEX, True),
        _rp("w_hi", Position.WR, Position.BENCH, False),
        _rp("bench_rb", Position.RB, Position.BENCH, False),
    ]


# w_lo projects worst of anyone: with no lock the optimizer drops him outright,
# so any test where he still starts is the lock doing the work.
PROJ = {"qb": 20.0, "rb": 15.0, "w_lo": 3.0, "w_mid": 11.0,
        "flex": 9.0, "w_hi": 18.0, "bench_rb": 8.0}


# ------------------------------------------------------------------- locks

def test_locks_from_roster_finds_only_locked_players(roster):
    assert locks_from_roster(roster) == {"w_lo": Position.WR}


def test_locks_from_roster_is_empty_before_any_game(roster):
    for rp in roster:
        rp.is_locked = False
    assert locks_from_roster(roster) == {}


# --------------------------------------------------------------- optimizer

def test_without_locks_the_optimizer_wants_the_swap(roster, settings):
    """Baseline: the higher projection wins when nobody has played."""
    lineup = optimize_lineup([rp.player for rp in roster], PROJ, settings)
    started = {rp.player.platform_id for rp in lineup if rp.is_starter}
    assert "w_hi" in started
    assert "w_lo" not in started


def test_a_locked_starter_keeps_their_slot(roster, settings):
    lineup = optimize_lineup([rp.player for rp in roster], PROJ, settings,
                             locked=locks_from_roster(roster))
    started = {rp.player.platform_id for rp in lineup if rp.is_starter}
    assert "w_lo" in started, "a player who has played cannot be benched"


def test_a_locked_starter_keeps_the_slot_they_occupied(roster, settings):
    lineup = optimize_lineup([rp.player for rp in roster], PROJ, settings,
                             locked=locks_from_roster(roster))
    slot = next(rp.slot for rp in lineup if rp.player.platform_id == "w_lo")
    assert slot == Position.WR


def test_the_optimizer_still_improves_around_a_lock(roster, settings):
    """Pinning one player must not stop it optimizing everyone else: w_hi should
    come in via FLEX, displacing the weaker flex."""
    lineup = optimize_lineup([rp.player for rp in roster], PROJ, settings,
                             locked=locks_from_roster(roster))
    started = {rp.player.platform_id for rp in lineup if rp.is_starter}
    assert "w_hi" in started
    assert "w_lo" in started


def test_a_locked_bench_player_is_never_started(roster, settings):
    """The mirror case: a benched player who has played cannot be promoted,
    however well he did."""
    for rp in roster:
        if rp.player.platform_id == "w_hi":
            rp.is_locked = True
            rp.actual_points = 30.0
    lineup = optimize_lineup([rp.player for rp in roster], PROJ, settings,
                             locked=locks_from_roster(roster))
    started = {rp.player.platform_id for rp in lineup if rp.is_starter}
    assert "w_hi" not in started


def test_locking_everyone_returns_the_current_lineup(roster, settings):
    for rp in roster:
        rp.is_locked = True
    lineup = optimize_lineup([rp.player for rp in roster], PROJ, settings,
                             locked=locks_from_roster(roster))
    started = {rp.player.platform_id for rp in lineup if rp.is_starter}
    assert started == {rp.player.platform_id for rp in roster if rp.is_starter}


def test_optimizer_signature_stays_backwards_compatible(roster, settings):
    """The CLI and every existing caller pass no locks at all."""
    lineup = optimize_lineup([rp.player for rp in roster], PROJ, settings)
    assert sum(1 for rp in lineup if rp.is_starter) == 5


# ------------------------------------------------------------- live_score

def test_live_score_banks_actuals_and_projects_the_rest(roster):
    """A played starter's actual is a fact; his projection is no longer relevant."""
    starters = [rp for rp in roster if rp.is_starter]
    # w_lo actually scored 5.3; his 3.0 projection is now irrelevant
    assert live_score(starters, PROJ) == pytest.approx(20.0 + 15.0 + 5.3 + 11.0 + 9.0)
    assert projected_score(starters, PROJ) == pytest.approx(20.0 + 15.0 + 3.0 + 11.0 + 9.0)


def test_live_score_equals_projected_before_anyone_plays(roster):
    for rp in roster:
        rp.actual_points = None
    starters = [rp for rp in roster if rp.is_starter]
    assert live_score(starters, PROJ) == pytest.approx(projected_score(starters, PROJ))


def test_live_score_counts_a_zero_actual_as_zero_not_missing(roster):
    """A player who played and scored nothing must not fall back to his projection."""
    for rp in roster:
        if rp.player.platform_id == "w_lo":
            rp.actual_points = 0.0
    starters = [rp for rp in roster if rp.is_starter]
    assert live_score(starters, PROJ) == pytest.approx(20.0 + 15.0 + 0.0 + 11.0 + 9.0)
    assert live_score(starters, PROJ) < projected_score(starters, PROJ)


# ------------------------------------------------------------ plan builder

def test_target_slots_omit_locked_players(roster, settings):
    """Omission is the guarantee: plan_moves only moves what it finds here."""
    target = build_target_slots(roster, ["qb", "rb", "w_hi", "w_mid", "flex"], settings)
    assert "w_lo" not in target


def test_no_move_is_planned_for_a_locked_player(roster, settings):
    """The regression for the live 409: benching a locked player emits nothing."""
    requested = ["qb", "rb", "w_hi", "w_mid", "flex"]      # w_lo dropped
    target = build_target_slots(roster, requested, settings)
    current = {"qb": 0, "rb": 2, "w_lo": 4, "w_mid": 4, "flex": 23,
               "w_hi": 20, "bench_rb": 20}
    names = {rp.player.platform_id: rp.player.name for rp in roster}
    moves = plan_moves(current, target, names)
    assert "w_lo" not in {m.player_id for m in moves}


def test_legitimate_moves_still_planned_alongside_a_lock(roster, settings):
    target = build_target_slots(roster, ["qb", "rb", "w_lo", "w_mid", "w_hi"], settings)
    current = {"qb": 0, "rb": 2, "w_lo": 4, "w_mid": 4, "flex": 23,
               "w_hi": 20, "bench_rb": 20}
    names = {rp.player.platform_id: rp.player.name for rp in roster}
    moves = plan_moves(current, target, names)
    assert "w_hi" in {m.player_id for m in moves}


def test_locked_conflicts_explains_an_impossible_bench(roster):
    problems = locked_conflicts(roster, ["qb", "rb", "w_hi", "w_mid", "flex"])
    assert len(problems) == 1
    assert "cannot be benched" in problems[0]
    assert "Pw_lo" in problems[0]


def test_locked_conflicts_explains_an_impossible_start(roster):
    for rp in roster:
        if rp.player.platform_id == "w_hi":
            rp.is_locked = True
    problems = locked_conflicts(roster, ["qb", "rb", "w_lo", "w_mid", "w_hi"])
    assert any("cannot be started" in p for p in problems)


def test_no_conflicts_when_the_request_respects_locks(roster):
    assert locked_conflicts(roster, ["qb", "rb", "w_lo", "w_mid", "w_hi"]) == []
