"""Scoring bar tests for the waiver agent."""
from __future__ import annotations

import pytest

from fantasy_gm.agent.waiver_agent import score_candidates
from fantasy_gm.models import (
    LeagueSettings,
    Platform,
    Position,
    RosterSlot,
    ScoringRules,
    WaiverScanState,
    WaiverType,
)


def _settings(team_count: int = 12, wr_starters: int = 2) -> LeagueSettings:
    slots = [
        RosterSlot(slot_id="QB", position=Position.QB, is_starter=True),
        RosterSlot(slot_id="WR1", position=Position.WR, is_starter=True),
        RosterSlot(slot_id="WR2", position=Position.WR, is_starter=True),
        RosterSlot(slot_id="RB1", position=Position.RB, is_starter=True),
        RosterSlot(slot_id="BE1", position=Position.BENCH, is_starter=False),
    ]
    return LeagueSettings(
        platform=Platform.ESPN,
        league_id="test",
        season=2026,
        team_count=team_count,
        roster_slots=slots,
        scoring_rules=ScoringRules(rules=[]),
        waiver_type=WaiverType.SNAKE,
        playoff_start_week=14,
        playoff_weeks=[14, 15, 16],
        regular_season_weeks=list(range(1, 14)),
    )


def _roster(pos: str = "WR", ros_value: float = 50.0) -> list[dict]:
    return [{"name": "Worst WR", "position": pos, "ros_value": ros_value}]


# ---------------------------------------------------------------------------
# WADD-02: candidate clearing fewer than all bars is not recommended
# ---------------------------------------------------------------------------

def test_wadd02_candidate_clears_relative_but_not_absolute():
    settings = _settings(team_count=12, wr_starters=2)
    # 12 teams × 2 WR starters = 24 WRs in startable tier
    # Candidate ranked 30th — outside the absolute bar
    candidates = [{"name": "Deep WR", "position": "WR", "ros_value": 80.0,
                   "tier_rank": 30, "startable_weeks": 3}]
    roster = _roster("WR", ros_value=60.0)

    result = score_candidates(candidates, roster, settings, week=7)

    # WADD-02 THEN the candidate does not appear as a recommendation
    assert result.scan_state == WaiverScanState.NO_CANDIDATE
    assert result.candidate is None
    assert result.closest_miss == "Deep WR"
    assert result.failed_bar == "absolute"


def test_wadd02_candidate_clears_bars_but_not_startability():
    settings = _settings(team_count=12)
    candidates = [{"name": "Bye WR", "position": "WR", "ros_value": 80.0,
                   "tier_rank": 10, "startable_weeks": 0}]
    roster = _roster("WR", ros_value=60.0)

    result = score_candidates(candidates, roster, settings, week=7)

    # WADD-02 THEN the candidate does not appear as a recommendation
    assert result.scan_state == WaiverScanState.NO_CANDIDATE
    assert result.failed_bar == "startability"


def test_wadd02_candidate_below_relative_bar():
    settings = _settings(team_count=12)
    candidates = [{"name": "Weak WR", "position": "WR", "ros_value": 40.0,
                   "tier_rank": 5, "startable_weeks": 3}]
    roster = _roster("WR", ros_value=60.0)

    result = score_candidates(candidates, roster, settings, week=7)

    # WADD-02 THEN the candidate does not appear as a recommendation
    assert result.scan_state == WaiverScanState.NO_CANDIDATE
    assert result.failed_bar == "relative"


def test_wadd02_candidate_clears_all_three_is_recommended():
    settings = _settings(team_count=12)
    candidates = [{"name": "Good WR", "position": "WR", "ros_value": 80.0,
                   "tier_rank": 10, "startable_weeks": 3}]
    roster = _roster("WR", ros_value=60.0)

    result = score_candidates(candidates, roster, settings, week=7)

    assert result.scan_state == WaiverScanState.RECOMMENDATION
    assert result.candidate == "Good WR"
