"""
Unit tests for tool_get_opponent_defense (enhanced version).

Mocks all httpx calls and nflreadpy; exercises team/opponent resolution,
DvP stats, team offense stats, and plain-text output format.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from fantasy_gm.agent.tools_ext.opponent_defense import tool_get_opponent_defense
from fantasy_gm.models import (
    Player,
    PlayerStatus,
    Position,
    Roster,
    RosterPlayer,
)


# ---------------------------------------------------------------------------
# Fixture data (mimics ESPN public API responses)
# ---------------------------------------------------------------------------

FAKE_TEAMS_RESPONSE = {
    "sports": [
        {
            "leagues": [
                {
                    "teams": [
                        {"team": {"id": "22", "abbreviation": "ARI", "displayName": "Arizona Cardinals"}},
                        {"team": {"id": "1",  "abbreviation": "ATL", "displayName": "Atlanta Falcons"}},
                        {"team": {"id": "33", "abbreviation": "BAL", "displayName": "Baltimore Ravens"}},
                        {"team": {"id": "2",  "abbreviation": "BUF", "displayName": "Buffalo Bills"}},
                        {"team": {"id": "29", "abbreviation": "CAR", "displayName": "Carolina Panthers"}},
                        {"team": {"id": "3",  "abbreviation": "CHI", "displayName": "Chicago Bears"}},
                        {"team": {"id": "4",  "abbreviation": "CIN", "displayName": "Cincinnati Bengals"}},
                        {"team": {"id": "5",  "abbreviation": "CLE", "displayName": "Cleveland Browns"}},
                        {"team": {"id": "6",  "abbreviation": "DAL", "displayName": "Dallas Cowboys"}},
                        {"team": {"id": "7",  "abbreviation": "DEN", "displayName": "Denver Broncos"}},
                        {"team": {"id": "8",  "abbreviation": "DET", "displayName": "Detroit Lions"}},
                        {"team": {"id": "9",  "abbreviation": "GB",  "displayName": "Green Bay Packers"}},
                        {"team": {"id": "34", "abbreviation": "HOU", "displayName": "Houston Texans"}},
                        {"team": {"id": "11", "abbreviation": "IND", "displayName": "Indianapolis Colts"}},
                        {"team": {"id": "30", "abbreviation": "JAX", "displayName": "Jacksonville Jaguars"}},
                        {"team": {"id": "12", "abbreviation": "KC",  "displayName": "Kansas City Chiefs"}},
                        {"team": {"id": "13", "abbreviation": "LV",  "displayName": "Las Vegas Raiders"}},
                        {"team": {"id": "24", "abbreviation": "LAC", "displayName": "Los Angeles Chargers"}},
                        {"team": {"id": "14", "abbreviation": "LAR", "displayName": "Los Angeles Rams"}},
                        {"team": {"id": "15", "abbreviation": "MIA", "displayName": "Miami Dolphins"}},
                        {"team": {"id": "16", "abbreviation": "MIN", "displayName": "Minnesota Vikings"}},
                        {"team": {"id": "17", "abbreviation": "NE",  "displayName": "New England Patriots"}},
                        {"team": {"id": "18", "abbreviation": "NO",  "displayName": "New Orleans Saints"}},
                        {"team": {"id": "19", "abbreviation": "NYG", "displayName": "New York Giants"}},
                        {"team": {"id": "20", "abbreviation": "NYJ", "displayName": "New York Jets"}},
                        {"team": {"id": "21", "abbreviation": "PHI", "displayName": "Philadelphia Eagles"}},
                        {"team": {"id": "23", "abbreviation": "PIT", "displayName": "Pittsburgh Steelers"}},
                        {"team": {"id": "25", "abbreviation": "SF",  "displayName": "San Francisco 49ers"}},
                        {"team": {"id": "26", "abbreviation": "SEA", "displayName": "Seattle Seahawks"}},
                        {"team": {"id": "27", "abbreviation": "TB",  "displayName": "Tampa Bay Buccaneers"}},
                        {"team": {"id": "10", "abbreviation": "TEN", "displayName": "Tennessee Titans"}},
                        {"team": {"id": "28", "abbreviation": "WSH", "displayName": "Washington Commanders"}},
                    ]
                }
            ]
        }
    ]
}

# Week 1 2026: SEA (26) is away @ SF (25); KC (12) hosts BUF (2)
FAKE_SCOREBOARD_RESPONSE = {
    "events": [
        {
            "id": "401671234",
            "competitions": [
                {
                    "date": "2026-09-07T17:00Z",
                    "competitors": [
                        {"team": {"id": "25", "abbreviation": "SF"},  "homeAway": "home"},
                        {"team": {"id": "26", "abbreviation": "SEA"}, "homeAway": "away"},
                    ],
                }
            ],
        },
        {
            "id": "401671235",
            "competitions": [
                {
                    "date": "2026-09-07T20:25Z",
                    "competitors": [
                        {"team": {"id": "12", "abbreviation": "KC"},  "homeAway": "home"},
                        {"team": {"id": "2",  "abbreviation": "BUF"}, "homeAway": "away"},
                    ],
                }
            ],
        },
    ]
}

# Fake ESPN team stats response (for KC passing offense)
FAKE_TEAM_STATS_RESPONSE = {
    "results": {
        "stats": {
            "categories": [
                {
                    "name": "passing",
                    "stats": [
                        {"name": "passingYardsPerGame", "value": 312.4},
                        {"name": "passingTouchdowns", "value": 36.0},
                        {"name": "yardsPerPassAttempt", "value": 8.3},
                    ],
                },
                {
                    "name": "general",
                    "stats": [
                        {"name": "gamesPlayed", "value": 17.0},
                    ],
                },
                {
                    "name": "rushing",
                    "stats": [
                        {"name": "rushingYardsPerGame", "value": 120.5},
                        {"name": "rushingTouchdowns", "value": 18.0},
                        {"name": "yardsPerRushAttempt", "value": 4.8},
                    ],
                },
            ]
        }
    }
}


# ---------------------------------------------------------------------------
# Fake player stats DataFrame (nflreadpy replacement)
# ---------------------------------------------------------------------------

def _make_empty_stats_df() -> pl.DataFrame:
    """Minimal empty DataFrame matching nflreadpy schema (< 4 weeks → fallback)."""
    return pl.DataFrame({
        "season_type": pl.Series([], dtype=pl.Utf8),
        "position": pl.Series([], dtype=pl.Utf8),
        "opponent_team": pl.Series([], dtype=pl.Utf8),
        "week": pl.Series([], dtype=pl.Int64),
        "fantasy_points_ppr": pl.Series([], dtype=pl.Float64),
        "targets": pl.Series([], dtype=pl.Float64),
        "receiving_yards": pl.Series([], dtype=pl.Float64),
        "receiving_tds": pl.Series([], dtype=pl.Float64),
        "receiving_air_yards": pl.Series([], dtype=pl.Float64),
        "passing_yards": pl.Series([], dtype=pl.Float64),
        "passing_tds": pl.Series([], dtype=pl.Float64),
        "sacks": pl.Series([], dtype=pl.Float64),
        "carries": pl.Series([], dtype=pl.Float64),
        "rushing_yards": pl.Series([], dtype=pl.Float64),
        "rushing_tds": pl.Series([], dtype=pl.Float64),
    })


def _make_wr_stats_df() -> pl.DataFrame:
    """Fake WR stats across 8 weeks with BUF as the most favorable defense."""
    # 32 teams as defense opponents
    defenses = [
        "BUF", "KC",  "MIA", "DAL", "PHI", "NE",  "SF",  "LAR",
        "TB",  "ATL", "CAR", "NO",  "DET", "GB",  "MIN", "CHI",
        "IND", "HOU", "JAX", "TEN", "DEN", "LV",  "LAC", "ARI",
        "SEA", "LA",  "CLE", "PIT", "BAL", "CIN", "NYG", "NYJ",
    ]
    records = []
    for week in range(1, 9):  # 8 regular-season weeks
        for i, opp in enumerate(defenses):
            # BUF (i=0) allows 30 FP/g → rank 1 → FAVORABLE
            records.append({
                "season_type": "REG",
                "position": "WR",
                "opponent_team": opp,
                "week": week,
                "fantasy_points_ppr": float(30 - i),
                "targets": 8.0,
                "receiving_yards": float(80 - i),
                "receiving_tds": 0.6,
                "receiving_air_yards": 100.0,
                "passing_yards": 0.0,
                "passing_tds": 0.0,
                "sacks": 0.0,
                "carries": 0.0,
                "rushing_yards": 0.0,
                "rushing_tds": 0.0,
            })
    return pl.DataFrame(records)


def _make_qb_stats_df() -> pl.DataFrame:
    """Fake QB stats across 4 weeks with BUF as a favorable defense."""
    records = []
    for week in range(1, 5):
        records.append({
            "season_type": "REG",
            "position": "QB",
            "opponent_team": "BUF",
            "week": week,
            "fantasy_points_ppr": 28.0,
            "passing_yards": 320.0,
            "passing_tds": 3.0,
            "sacks": 2.0,
            "targets": 0.0,
            "receiving_yards": 0.0,
            "receiving_tds": 0.0,
            "receiving_air_yards": 0.0,
            "carries": 5.0,
            "rushing_yards": 30.0,
            "rushing_tds": 0.0,
        })
    return pl.DataFrame(records)


# ---------------------------------------------------------------------------
# Fake context helpers
# ---------------------------------------------------------------------------

def _make_player(pid: str, name: str, pos: Position, nfl_team: str | None) -> Player:
    return Player(
        platform_id=pid,
        name=name,
        position=pos,
        eligible_positions=[pos],
        status=PlayerStatus.ACTIVE,
        nfl_team=nfl_team,
    )


def _make_roster(players: list[RosterPlayer], week: int = 1, season: int = 2026) -> Roster:
    return Roster(
        team_id="8",
        team_name="Test Team",
        owner_name="Omer",
        players=players,
        week=week,
        season=season,
    )


class FakeCtx:
    """Minimal fake context for tool_get_opponent_defense."""
    def __init__(self, roster: Roster, week: int = 1, season: int = 2026):
        self._roster = roster
        self.week = week
        self.season = season

    def roster(self) -> Roster:
        return self._roster


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(data: dict) -> MagicMock:
    m = MagicMock()
    m.json.return_value = data
    m.raise_for_status = MagicMock()
    return m


def _make_get_side_effect(
    teams_resp: dict,
    scoreboard_resp: dict,
    team_stats_resp: dict | None = None,
):
    """Return a side_effect function that dispatches by URL."""
    _default_stats = {"results": {"stats": {"categories": []}}}

    def side_effect(url: str, **kwargs):
        # Check statistics before teams (statistics URL also contains "teams")
        if "statistics" in url:
            return _mock_response(team_stats_resp if team_stats_resp is not None else _default_stats)
        if "scoreboard" in url:
            return _mock_response(scoreboard_resp)
        if "teams" in url:
            return _mock_response(teams_resp)
        raise ValueError(f"Unexpected URL: {url}")

    return side_effect


# ---------------------------------------------------------------------------
# autouse fixture — clear module-level caches and stub nflreadpy
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_caches_and_stub_nfl(monkeypatch):
    """Clear module caches between tests and stub nflreadpy with empty data."""
    from fantasy_gm.agent.tools_ext import opponent_defense as mod

    mod._STATS_CACHE.clear()
    mod._TEAM_STATS_CACHE.clear()

    # Default stub: return an empty DataFrame (< 4 weeks → season fallback also empty)
    empty = _make_empty_stats_df()
    monkeypatch.setattr("nflreadpy.load_player_stats", lambda seasons=None, **kw: empty)

    yield

    mod._STATS_CACHE.clear()
    mod._TEAM_STATS_CACHE.clear()


# ---------------------------------------------------------------------------
# Existing tests (updated to pass with the enhanced output format)
# ---------------------------------------------------------------------------

@patch("fantasy_gm.agent.tools_ext.opponent_defense.httpx.get")
def test_basic_matchup(mock_get):
    """Players on teams with scheduled games show team abbr and opponent."""
    mock_get.side_effect = _make_get_side_effect(FAKE_TEAMS_RESPONSE, FAKE_SCOREBOARD_RESPONSE)

    players = [
        # SEA is away @ SF (proTeamId = "26")
        RosterPlayer(player=_make_player("1", "DK Metcalf", Position.WR, "26"),
                     slot=Position.WR, is_starter=True),
        # KC is home vs BUF (proTeamId = "12")
        RosterPlayer(player=_make_player("2", "Patrick Mahomes", Position.QB, "12"),
                     slot=Position.QB, is_starter=True),
    ]
    roster = _make_roster(players)
    ctx = FakeCtx(roster, week=1, season=2026)

    result = tool_get_opponent_defense(ctx)

    assert "DK Metcalf" in result
    assert "SEA" in result
    # SEA is away, so opponent should show as "@ SF"
    assert "@ SF" in result or "SF" in result

    assert "Patrick Mahomes" in result
    assert "KC" in result
    # KC is home, so should show "vs BUF"
    assert "vs BUF" in result or "BUF" in result


@patch("fantasy_gm.agent.tools_ext.opponent_defense.httpx.get")
def test_player_without_nfl_team(mock_get):
    """Player with no proTeamId shows 'unknown' rather than crashing."""
    mock_get.side_effect = _make_get_side_effect(FAKE_TEAMS_RESPONSE, FAKE_SCOREBOARD_RESPONSE)

    players = [
        RosterPlayer(player=_make_player("3", "No Team Player", Position.RB, None),
                     slot=Position.RB, is_starter=False),
    ]
    roster = _make_roster(players)
    ctx = FakeCtx(roster)

    result = tool_get_opponent_defense(ctx)
    assert "No Team Player" in result
    assert "unknown" in result.lower()


@patch("fantasy_gm.agent.tools_ext.opponent_defense.httpx.get")
def test_player_on_bye(mock_get):
    """Player whose team has no game this week shows BYE note."""
    mock_get.side_effect = _make_get_side_effect(FAKE_TEAMS_RESPONSE, FAKE_SCOREBOARD_RESPONSE)

    players = [
        # DAL (id=6) has no game in the fixture scoreboard
        RosterPlayer(player=_make_player("4", "CeeDee Lamb", Position.WR, "6"),
                     slot=Position.WR, is_starter=True),
    ]
    roster = _make_roster(players)
    ctx = FakeCtx(roster)

    result = tool_get_opponent_defense(ctx)
    assert "CeeDee Lamb" in result
    assert "BYE" in result or "not scheduled" in result


@patch("fantasy_gm.agent.tools_ext.opponent_defense.httpx.get")
def test_scoreboard_error_is_graceful(mock_get):
    """If the scoreboard call fails, output still lists roster with a warning."""
    import httpx as _httpx

    def side_effect(url: str, **kwargs):
        if "statistics" in url:
            return _mock_response({"results": {"stats": {"categories": []}}})
        if "teams" in url:
            return _mock_response(FAKE_TEAMS_RESPONSE)
        raise _httpx.HTTPError("connection timeout")

    mock_get.side_effect = side_effect

    players = [
        RosterPlayer(player=_make_player("5", "Lamar Jackson", Position.QB, "33"),
                     slot=Position.QB, is_starter=True),
    ]
    roster = _make_roster(players)
    ctx = FakeCtx(roster)

    result = tool_get_opponent_defense(ctx)
    assert "Lamar Jackson" in result
    # Should warn about scoreboard being unavailable
    assert "WARNING" in result or "unavailable" in result.lower()


@patch("fantasy_gm.agent.tools_ext.opponent_defense.httpx.get")
def test_header_contains_week_and_season(mock_get):
    """Output header mentions the correct week and season."""
    mock_get.side_effect = _make_get_side_effect(FAKE_TEAMS_RESPONSE, FAKE_SCOREBOARD_RESPONSE)

    roster = _make_roster([], week=3, season=2026)
    ctx = FakeCtx(roster, week=3, season=2026)

    result = tool_get_opponent_defense(ctx)
    assert "Week 3" in result
    assert "2026" in result


@patch("fantasy_gm.agent.tools_ext.opponent_defense.httpx.get")
def test_starter_bench_tag(mock_get):
    """Players are tagged STARTER or bench in output."""
    mock_get.side_effect = _make_get_side_effect(FAKE_TEAMS_RESPONSE, FAKE_SCOREBOARD_RESPONSE)

    players = [
        RosterPlayer(player=_make_player("6", "Travis Kelce", Position.TE, "12"),
                     slot=Position.TE, is_starter=True),
        RosterPlayer(player=_make_player("7", "Sam LaPorta", Position.TE, "8"),
                     slot=Position.BENCH, is_starter=False),
    ]
    roster = _make_roster(players)
    ctx = FakeCtx(roster)

    result = tool_get_opponent_defense(ctx)
    assert "STARTER" in result
    assert "bench" in result


# ---------------------------------------------------------------------------
# New tests — DvP stats and team offense stats
# ---------------------------------------------------------------------------

@patch("fantasy_gm.agent.tools_ext.opponent_defense.httpx.get")
@patch("nflreadpy.load_player_stats")
def test_dvp_stats_appear_for_wr(mock_nfl, mock_get):
    """DvP stats (fantasy pts allowed/g, targets, etc.) appear for a WR player."""
    mock_nfl.return_value = _make_wr_stats_df()
    mock_get.side_effect = _make_get_side_effect(
        FAKE_TEAMS_RESPONSE, FAKE_SCOREBOARD_RESPONSE
    )

    # KC (12) hosts BUF (2) → WR on KC faces BUF defense
    # BUF is rank 1 (most favorable) in our fake data
    players = [
        RosterPlayer(
            player=_make_player("10", "Rashee Rice", Position.WR, "12"),
            slot=Position.WR,
            is_starter=True,
        ),
    ]
    roster = _make_roster(players, season=2026)
    ctx = FakeCtx(roster, season=2026)

    result = tool_get_opponent_defense(ctx, detail=True)

    # Player and team should appear
    assert "Rashee Rice" in result
    assert "KC" in result

    # DvP section should be present
    assert "Defense vs WR" in result
    assert "Fantasy pts allowed/g" in result
    assert "rank" in result

    # BUF is the most favorable defense (rank 1) in our fake data
    assert "FAVORABLE" in result

    # Per-game receiving stats should be shown
    assert "Targets allowed/g" in result
    assert "Rec yards allowed/g" in result


@patch("fantasy_gm.agent.tools_ext.opponent_defense.httpx.get")
@patch("nflreadpy.load_player_stats")
def test_team_offense_stats_appear_for_passing_position(mock_nfl, mock_get):
    """Passing offense stats appear for a QB player when ESPN stats are available."""
    mock_nfl.return_value = _make_qb_stats_df()
    mock_get.side_effect = _make_get_side_effect(
        FAKE_TEAMS_RESPONSE,
        FAKE_SCOREBOARD_RESPONSE,
        team_stats_resp=FAKE_TEAM_STATS_RESPONSE,
    )

    # KC (12) hosts BUF (2) → QB on KC
    players = [
        RosterPlayer(
            player=_make_player("11", "Patrick Mahomes", Position.QB, "12"),
            slot=Position.QB,
            is_starter=True,
        ),
    ]
    roster = _make_roster(players, season=2026)
    ctx = FakeCtx(roster, season=2026)

    result = tool_get_opponent_defense(ctx, detail=True)

    assert "Patrick Mahomes" in result
    assert "KC" in result

    # Team offense section should appear
    assert "Passing Offense" in result
    assert "Pass yards/g" in result

    # Values from FAKE_TEAM_STATS_RESPONSE should appear
    assert "312.4" in result  # passingYardsPerGame
    assert "8.3" in result    # yardsPerPassAttempt


@patch("fantasy_gm.agent.tools_ext.opponent_defense.httpx.get")
def test_kicker_shows_no_dvp(mock_get):
    """K position shows no DvP section (not meaningful for kickers)."""
    mock_get.side_effect = _make_get_side_effect(FAKE_TEAMS_RESPONSE, FAKE_SCOREBOARD_RESPONSE)

    players = [
        RosterPlayer(
            player=_make_player("20", "Justin Tucker", Position.K, "33"),
            slot=Position.K,
            is_starter=True,
        ),
    ]
    roster = _make_roster(players)
    ctx = FakeCtx(roster)

    result = tool_get_opponent_defense(ctx)

    assert "Justin Tucker" in result
    # Should mention DvP not shown, but not show actual DvP stats
    assert "Defense vs K" not in result
    assert "Fantasy pts allowed/g" not in result


@patch("fantasy_gm.agent.tools_ext.opponent_defense.httpx.get")
@patch("nflreadpy.load_player_stats")
def test_dvp_unavailable_when_no_data_for_opponent(mock_nfl, mock_get):
    """When nflreadpy has no data for the opponent, shows graceful fallback."""
    # Return WR stats but only for a different defense (not SF)
    records = []
    for week in range(1, 5):
        records.append({
            "season_type": "REG",
            "position": "WR",
            "opponent_team": "BUF",  # only BUF data, no SF data
            "week": week,
            "fantasy_points_ppr": 25.0,
            "targets": 7.0,
            "receiving_yards": 70.0,
            "receiving_tds": 0.5,
            "receiving_air_yards": 90.0,
            "passing_yards": 0.0,
            "passing_tds": 0.0,
            "sacks": 0.0,
            "carries": 0.0,
            "rushing_yards": 0.0,
            "rushing_tds": 0.0,
        })
    mock_nfl.return_value = pl.DataFrame(records)
    mock_get.side_effect = _make_get_side_effect(FAKE_TEAMS_RESPONSE, FAKE_SCOREBOARD_RESPONSE)

    # SEA (26) plays @ SF (25) → WR on SEA faces SF defense (no data in fake)
    players = [
        RosterPlayer(
            player=_make_player("30", "DK Metcalf", Position.WR, "26"),
            slot=Position.WR,
            is_starter=True,
        ),
    ]
    roster = _make_roster(players)
    ctx = FakeCtx(roster)

    result = tool_get_opponent_defense(ctx)

    assert "DK Metcalf" in result
    # SF DvP data is missing → should show graceful fallback
    assert "unavailable" in result.lower() or "DvP data" in result
