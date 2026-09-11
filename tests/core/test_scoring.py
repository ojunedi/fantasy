"""Tests for deterministic PPR scoring calculator."""
import pytest
from fantasy_gm.core.scoring import calculate_score, ppr_rules


@pytest.fixture
def rules():
    return ppr_rules()


def test_empty_stats_returns_zero(rules):
    assert calculate_score({}, rules) == 0.0


def test_passing_yards_only(rules):
    # 300 pass yards * 0.04 = 12.0
    score = calculate_score({"3": 300}, rules)
    assert score == pytest.approx(12.0)


def test_passing_td(rules):
    # 1 TD * 4.0 = 4.0
    score = calculate_score({"4": 1}, rules)
    assert score == pytest.approx(4.0)


def test_interception_negative(rules):
    # 1 INT * -2.0 = -2.0
    score = calculate_score({"20": 1}, rules)
    assert score == pytest.approx(-2.0)


def test_rush_yards(rules):
    # 100 rush yards * 0.1 = 10.0
    score = calculate_score({"24": 100}, rules)
    assert score == pytest.approx(10.0)


def test_rush_td(rules):
    score = calculate_score({"25": 1}, rules)
    assert score == pytest.approx(6.0)


def test_ppr_reception(rules):
    # 1 reception * 1.0 = 1.0
    score = calculate_score({"53": 1}, rules)
    assert score == pytest.approx(1.0)


def test_receiving_yards_and_td(rules):
    # 80 rec yards * 0.1 + 1 rec TD * 6.0 = 8.0 + 6.0 = 14.0
    score = calculate_score({"41": 80, "42": 1}, rules)
    assert score == pytest.approx(14.0)


def test_full_ppr_wr_game(rules):
    # 7 rec, 95 yards, 1 TD = 7.0 + 9.5 + 6.0 = 22.5
    score = calculate_score({"53": 7, "41": 95, "42": 1}, rules)
    assert score == pytest.approx(22.5)


def test_full_ppr_qb_game(rules):
    # 280 pass yds, 3 TDs, 1 INT = 11.2 + 12.0 - 2.0 = 21.2
    score = calculate_score({"3": 280, "4": 3, "20": 1}, rules)
    assert score == pytest.approx(21.2)


def test_fumble_lost_negative(rules):
    score = calculate_score({"72": 1}, rules)
    assert score == pytest.approx(-2.0)


def test_two_point_conversion(rules):
    score = calculate_score({"74": 1}, rules)
    assert score == pytest.approx(2.0)


def test_unknown_stat_id_ignored(rules):
    # Unknown stat ID should contribute 0 (not crash)
    score = calculate_score({"9999": 100}, rules)
    assert score == 0.0


def test_fractional_stats(rules):
    # 0.5 receptions shouldn't happen in practice, but math should hold
    score = calculate_score({"53": 0.5}, rules)
    assert score == pytest.approx(0.5)
