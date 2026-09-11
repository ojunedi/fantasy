"""Tests for game-environment (implied totals + game script)."""
import pytest

from fantasy_gm.core.game_env import from_schedule_row, game_environment


def test_implied_totals_split_by_spread():
    # Total 46, team favored by 3 (spread -3): 23 + 1.5 = 24.5 for team.
    env = game_environment("KC", "BAL", total=46.0, spread=-3.0)
    assert env.implied_team_total == pytest.approx(24.5)
    assert env.opponent_implied_total == pytest.approx(21.5)
    assert env.is_favorite


def test_big_favorite_run_leaning():
    env = game_environment("SF", "CAR", total=44.0, spread=-10.0)
    assert env.script == "run-leaning"
    assert env.pass_tilt < 0


def test_big_underdog_pass_leaning():
    env = game_environment("CAR", "SF", total=44.0, spread=10.0)
    assert env.script == "pass-leaning"
    assert env.pass_tilt > 0


def test_neutral_script_near_pick():
    env = game_environment("DAL", "PHI", total=45.0, spread=-1.0)
    assert env.script == "neutral"


def test_env_score_higher_for_higher_implied_total():
    low = game_environment("A", "B", total=36.0, spread=0.0)
    high = game_environment("A", "B", total=54.0, spread=0.0)
    assert high.env_score > low.env_score


def test_shootout_flag():
    env = game_environment("MIA", "BUF", total=52.0, spread=-1.0)
    assert env.is_shootout


def test_from_schedule_row_home_team_favored():
    row = {"home_team": "KC", "away_team": "BAL", "total_line": 46.0, "spread_line": 3.0}
    env = from_schedule_row(row, "KC")
    assert env.is_favorite  # spread_line 3 > 0 → home favored
    assert env.implied_team_total == pytest.approx(24.5)
    away = from_schedule_row(row, "BAL")
    assert not away.is_favorite
    assert away.spread == pytest.approx(3.0)


def test_from_schedule_row_missing_lines_returns_none():
    row = {"home_team": "KC", "away_team": "BAL", "total_line": None, "spread_line": None}
    assert from_schedule_row(row, "KC") is None
