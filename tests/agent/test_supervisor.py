"""Tests for the Supervisor's record-based risk posture."""
import pytest

from fantasy_gm.agent.supervisor import risk_posture
from fantasy_gm.models import (
    LeagueSettings,
    Platform,
    ScoringRules,
    TeamStanding,
    WaiverType,
)


@pytest.fixture
def settings():
    return LeagueSettings(
        platform=Platform.ESPN, league_id="t", season=2026, team_count=12,
        roster_slots=[], scoring_rules=ScoringRules(rules=[]),
        waiver_type=WaiverType.SNAKE, faab_budget=None, playoff_start_week=15,
        playoff_weeks=[15, 16, 17], regular_season_weeks=list(range(1, 15)),
    )


def _standing(team_id, seed, wins, losses):
    return TeamStanding(team_id=team_id, team_name=f"T{team_id}", wins=wins,
                        losses=losses, playoff_seed=seed)


def test_early_season_is_normal(settings):
    standings = [_standing("8", 8, 3, 3)]
    p = risk_posture(standings, "8", week=5, settings=settings)  # 10 weeks left
    assert p.posture == "normal"


def test_late_out_of_position_is_must_win(settings):
    standings = [_standing("8", 9, 5, 7)]  # seed 9, outside top 6
    p = risk_posture(standings, "8", week=13, settings=settings)  # 2 weeks left
    assert p.posture == "must_win"


def test_late_top_seed_coasts(settings):
    standings = [_standing("8", 1, 11, 1)]
    p = risk_posture(standings, "8", week=13, settings=settings)
    assert p.posture == "coast"


def test_late_middle_seed_stays_normal(settings):
    standings = [_standing("8", 5, 7, 5)]  # in position (top 6) but not top 2
    p = risk_posture(standings, "8", week=13, settings=settings)
    assert p.posture == "normal"


def test_missing_team_defaults_normal(settings):
    p = risk_posture([], "8", week=13, settings=settings)
    assert p.posture == "normal"
