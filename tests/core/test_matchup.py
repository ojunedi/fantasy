"""Tests for Defense-vs-Position matchup grading."""
import pytest

from fantasy_gm.core.matchup import (
    compute_dvp,
    league_average,
    matchup_grade,
)
from fantasy_gm.models import Position


def _row(defense, pos, week, pts):
    return {"opponent_team": defense, "position": pos, "week": week,
            "fantasy_points_ppr": pts}


@pytest.fixture
def rows():
    # Two defenses, WR position, two weeks each.
    # DEN allows a lot to WRs; SF allows little.
    return [
        _row("DEN", "WR", 1, 20.0), _row("DEN", "WR", 1, 10.0),   # wk1: 30 allowed
        _row("DEN", "WR", 2, 20.0),                                # wk2: 20 allowed
        _row("SF", "WR", 1, 4.0), _row("SF", "WR", 1, 2.0),        # wk1: 6 allowed
        _row("SF", "WR", 2, 8.0),                                  # wk2: 8 allowed
    ]


def test_dvp_averages_points_allowed_per_week(rows):
    table = compute_dvp(rows)
    den = table[("DEN", Position.WR)]
    assert den.ppg_allowed == pytest.approx(25.0)  # (30 + 20) / 2
    assert den.games == 2
    sf = table[("SF", Position.WR)]
    assert sf.ppg_allowed == pytest.approx(7.0)     # (6 + 8) / 2


def test_league_average(rows):
    table = compute_dvp(rows)
    # mean of 25.0 and 7.0
    assert league_average(table, Position.WR) == pytest.approx(16.0)


def test_favorable_matchup_grades_high(rows):
    table = compute_dvp(rows)
    grade = matchup_grade(table, "DEN", Position.WR)
    assert grade is not None
    assert grade.ratio > 1.0
    assert grade.is_favorable
    assert grade.grade == "A"
    assert grade.score > 50


def test_tough_matchup_grades_low(rows):
    table = compute_dvp(rows)
    grade = matchup_grade(table, "SF", Position.WR)
    assert grade.ratio < 1.0
    assert not grade.is_favorable
    assert grade.grade == "F"
    assert grade.score < 50


def test_missing_pair_returns_none(rows):
    table = compute_dvp(rows)
    assert matchup_grade(table, "DEN", Position.QB) is None


def test_ignores_non_dvp_positions():
    rows = [_row("DEN", "K", 1, 12.0), {"opponent_team": "DEN", "position": "OL",
            "week": 1, "fantasy_points_ppr": 0.0}]
    table = compute_dvp(rows)
    assert table == {}


def test_points_fn_override(rows):
    # Score every row as a flat 1.0 → all defenses equal → ratio 1.0, grade C.
    table = compute_dvp(rows, points_fn=lambda r: 1.0)
    grade = matchup_grade(table, "DEN", Position.WR)
    assert grade.grade == "C"
