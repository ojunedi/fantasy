"""The agent must not propose moving a player whose game has been played.

The optimizer already refuses to, and the plan builder drops such a move, but
the model can still *write* "bench Williams" in its memo unless the tools tell
it plainly. These tests cover the tool surface the model reads.
"""
from __future__ import annotations

import pytest

from fantasy_gm.agent.tools import LineupToolContext
from fantasy_gm.models import (
    LeagueSettings,
    Platform,
    Player,
    Position,
    Roster,
    RosterPlayer,
    RosterSlot,
    ScoringRule,
    ScoringRules,
    WaiverType,
)

FLEX_OK = {Position.RB, Position.WR, Position.TE}


def _settings() -> LeagueSettings:
    spec = [(Position.QB, 1), (Position.RB, 1), (Position.WR, 2), (Position.FLEX, 1)]
    slots = [RosterSlot(slot_id=f"{p.value}_{i}", position=p, is_starter=True)
             for p, n in spec for i in range(n)]
    slots += [RosterSlot(slot_id=f"BE_{i}", position=Position.BENCH, is_starter=False)
              for i in range(3)]
    return LeagueSettings(
        platform=Platform.ESPN, league_id="1", season=2026, team_count=12,
        roster_slots=slots, scoring_rules=ScoringRules(rules=[ScoringRule(stat="53", points=1.0)]),
        waiver_type=WaiverType.ROLLING, playoff_start_week=15, playoff_weeks=[15],
        regular_season_weeks=list(range(1, 15)),
    )


def _rp(pid, position, slot, starter, locked=False, actual=None):
    eligible = [position, Position.FLEX] if position in FLEX_OK else [position]
    return RosterPlayer(
        player=Player(platform_id=pid, name=f"Player {pid}", position=position,
                      eligible_positions=eligible, nfl_team="1"),
        slot=slot, is_starter=starter, is_locked=locked, actual_points=actual)


PROJ = {"qb": 20.0, "rb": 15.0, "w_lo": 3.0, "w_mid": 11.0,
        "flex": 9.0, "w_hi": 18.0}


class _Adapter:
    """Minimal stand-in: the lineup tools only need these three reads."""

    def __init__(self, roster):
        self._roster = roster
        self.league_id = "1"

    def get_roster(self, team_id, week, season, fresh=False):
        return self._roster

    def get_projections(self, week, season):
        return dict(PROJ)

    def get_league_settings(self, season):
        return _settings()


@pytest.fixture
def ctx():
    players = [
        _rp("qb", Position.QB, Position.QB, True),
        _rp("rb", Position.RB, Position.RB, True),
        _rp("w_lo", Position.WR, Position.WR, True, locked=True, actual=5.3),
        _rp("w_mid", Position.WR, Position.WR, True),
        _rp("flex", Position.RB, Position.FLEX, True),
        _rp("w_hi", Position.WR, Position.BENCH, False),
    ]
    roster = Roster(team_id="8", team_name="Mine", owner_name="", players=players,
                    week=2, season=2026)
    adapter = _Adapter(roster)
    context = LineupToolContext(adapter=adapter, settings=_settings(), team_id="8",
                               week=2, season=2026)
    # Projections normally arrive via the signal bundle (nflverse + ESPN); these
    # tests are about lock handling, so the map is supplied directly.
    context._raw_projection_map = lambda: dict(PROJ)
    return context


# ----------------------------------------------------------- get_roster

def test_the_roster_tool_marks_a_locked_player(ctx):
    out = ctx.dispatch("get_roster", {})[0]
    assert "LOCKED" in out
    assert "scored 5.3" in out
    assert "CANNOT be moved" in out


def test_the_roster_tool_spells_out_the_instruction(ctx):
    """The model needs to be told not to write about moving them, not just that
    a flag exists."""
    out = ctx.dispatch("get_roster", {})[0]
    assert "already played" in out
    assert "Do not mention" in out


def test_the_roster_tool_is_quiet_when_nothing_is_locked(ctx):
    for rp in ctx.roster().players:
        rp.is_locked = False
    out = ctx.dispatch("get_roster", {})[0]
    assert "LOCKED" not in out
    assert "already played" not in out


# ------------------------------------------------------ optimize_lineup

def test_optimize_keeps_a_locked_starter_in_place(ctx):
    out = ctx.dispatch("optimize_lineup", {})[0]
    started = [l for l in out.splitlines() if l.strip().startswith("START")]
    assert any("Player w_lo" in l for l in started), \
        "the locked starter must remain a starter"


def test_optimize_lists_the_locked_players(ctx):
    out = ctx.dispatch("optimize_lineup", {})[0]
    assert "LOCKED" in out
    assert "do not propose changing them" in out


def test_optimize_still_improves_the_movable_slots(ctx):
    """w_hi (18.0) should still be brought in over the weaker flex."""
    out = ctx.dispatch("optimize_lineup", {})[0]
    started = [l for l in out.splitlines() if l.strip().startswith("START")]
    assert any("Player w_hi" in l for l in started)


# ------------------------------------------------- check_lineup_legality

def test_legality_rejects_benching_a_locked_player(ctx):
    """The tool the model uses to self-check must catch this, or it will happily
    propose an impossible lineup."""
    out = ctx.dispatch("check_lineup_legality",
                       {"starter_player_ids": ["qb", "rb", "w_hi", "w_mid", "flex"]})[0]
    assert out.startswith("Illegal")
    assert "cannot be benched" in out


def test_legality_accepts_a_lineup_that_respects_locks(ctx):
    out = ctx.dispatch("check_lineup_legality",
                       {"starter_player_ids": ["qb", "rb", "w_lo", "w_mid", "w_hi"]})[0]
    assert out.startswith("Legal")


def test_legality_still_catches_ordinary_position_errors(ctx):
    """The lock check must not have displaced the existing validation."""
    out = ctx.dispatch("check_lineup_legality",
                       {"starter_player_ids": ["qb", "rb", "w_lo"]})[0]
    assert out.startswith("Illegal")


def test_legality_hands_back_a_corrected_lineup(ctx):
    """Saying only "illegal" costs another guess-and-recheck round against a
    hard step cap; the fix is returned so a correction takes one turn."""
    out = ctx.dispatch("check_lineup_legality",
                       {"starter_player_ids": ["qb", "rb", "w_hi", "w_mid", "flex"]})[0]
    assert out.startswith("Illegal")
    assert "Correct starter_player_ids:" in out
    assert "w_lo" in out.split("Correct starter_player_ids:")[1]


def test_the_suggested_correction_is_itself_legal(ctx):
    import ast
    out = ctx.dispatch("check_lineup_legality",
                       {"starter_player_ids": ["qb", "rb", "w_hi", "w_mid", "flex"]})[0]
    fixed = ast.literal_eval(out.split("Correct starter_player_ids:")[1].strip().rstrip("."))
    recheck = ctx.dispatch("check_lineup_legality", {"starter_player_ids": fixed})[0]
    assert recheck.startswith("Legal"), recheck


def test_the_correction_names_the_slot_to_keep(ctx):
    out = ctx.dispatch("check_lineup_legality",
                       {"starter_player_ids": ["qb", "rb", "w_hi", "w_mid", "flex"]})[0]
    assert "slot WR" in out
