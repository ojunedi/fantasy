"""Tests for strength-of-schedule (rest-of-season and playoff window)."""
import pytest

from fantasy_gm.core.matchup import compute_dvp
from fantasy_gm.core.schedule import (
    playoff_sos,
    rest_of_season_sos,
    strength_of_schedule,
    team_schedule,
)
from fantasy_gm.models import Position


def _game(week, home, away):
    return {"week": week, "home_team": home, "away_team": away}


def _dvp_row(defense, pos, week, pts):
    return {"opponent_team": defense, "position": pos, "week": week,
            "fantasy_points_ppr": pts}


@pytest.fixture
def schedule():
    # BUF plays soft DEN in wk15, tough SF in wk16, soft DEN again wk17.
    return [
        _game(15, "BUF", "DEN"),
        _game(16, "SF", "BUF"),
        _game(17, "DEN", "BUF"),
        _game(1, "BUF", "SF"),
    ]


@pytest.fixture
def dvp():
    rows = [
        _dvp_row("DEN", "WR", 1, 30.0),  # DEN soft vs WR
        _dvp_row("SF", "WR", 1, 4.0),    # SF tough vs WR
    ]
    return compute_dvp(rows)


def test_team_schedule_resolves_opponents(schedule):
    sched = team_schedule(schedule, "BUF")
    assert sched[15] == "DEN"
    assert sched[16] == "SF"
    assert sched[17] == "DEN"


def test_playoff_sos_favorable_for_soft_slate(schedule, dvp):
    sos = playoff_sos(schedule, dvp, "BUF", Position.WR)
    # 2 of 3 playoff opponents are soft DEN → avg ratio > 1
    assert sos.avg_ratio > 1.0
    assert sos.grade in ("A", "B")
    assert len(sos.weeks) == 3


def test_rest_of_season_from_week(schedule, dvp):
    sos = rest_of_season_sos(schedule, dvp, "BUF", Position.WR, from_week=16)
    weeks = [w.week for w in sos.weeks]
    assert weeks == [16, 17]  # wk1 and wk15 excluded


def test_bye_week_skipped(dvp):
    # BUF has no game in the requested week → skipped, not errored.
    sos = strength_of_schedule([_game(15, "BUF", "DEN")], dvp, "BUF",
                               Position.WR, weeks=[15, 16])
    assert len(sos.weeks) == 1
    assert sos.weeks[0].week == 15


def test_unknown_opponent_defense_marked(dvp):
    # Opponent with no DvP data → grade "?", excluded from avg.
    sched = [_game(15, "BUF", "MIA")]
    sos = strength_of_schedule(sched, dvp, "BUF", Position.WR, weeks=[15])
    assert sos.weeks[0].grade == "?"
    assert sos.avg_ratio == 1.0  # no graded weeks → neutral
