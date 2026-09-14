"""
Unit tests for tool_get_opponent_injuries.

Mocks all httpx calls; exercises the scoreboard → injury pipeline, the
plain-text output format, and graceful degradation on API failures.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from fantasy_gm.agent.tools_ext.opponent_injuries import tool_get_opponent_injuries
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

# Week 1: KC (12) hosts BUF (2); MIA (15) is away @ NE (17)
FAKE_SCOREBOARD_RESPONSE = {
    "events": [
        {
            "competitions": [
                {
                    "competitors": [
                        {"team": {"id": "12", "abbreviation": "KC"},  "homeAway": "home"},
                        {"team": {"id": "2",  "abbreviation": "BUF"}, "homeAway": "away"},
                    ]
                }
            ]
        },
        {
            "competitions": [
                {
                    "competitors": [
                        {"team": {"id": "17", "abbreviation": "NE"},  "homeAway": "home"},
                        {"team": {"id": "15", "abbreviation": "MIA"}, "homeAway": "away"},
                    ]
                }
            ]
        },
    ]
}

# BUF has two injuries: one significant (Out), one not (Probable → filtered)
BUF_INJURIES_RESPONSE = {
    "injuries": [
        {
            "athlete": {
                "displayName": "Tre'Davious White",
                "position": {"abbreviation": "CB"},
            },
            "type": {"description": "Knee"},
            "status": "Out",
        },
        {
            "athlete": {
                "displayName": "Keon Coleman",
                "position": {"abbreviation": "WR"},
            },
            "type": {"description": "Ankle"},
            "status": "Questionable",
        },
        {
            "athlete": {
                "displayName": "Josh Allen",
                "position": {"abbreviation": "QB"},
            },
            "type": {"description": "Shoulder"},
            "status": "Probable",  # should be filtered out
        },
    ]
}

NE_INJURIES_RESPONSE: dict = {"injuries": []}


# ---------------------------------------------------------------------------
# Helpers
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
    """Minimal fake context for tool_get_opponent_injuries."""

    def __init__(self, roster: Roster, week: int = 1, season: int = 2026):
        self._roster = roster
        self.week = week
        self.season = season

    def roster(self) -> Roster:
        return self._roster


def _mock_response(data: dict, status_code: int = 200) -> MagicMock:
    m = MagicMock()
    m.status_code = status_code
    m.json.return_value = data
    m.raise_for_status = MagicMock()
    return m


def _dispatch_get(url: str, **kwargs):
    """Route httpx.get calls to the appropriate fixture response."""
    if "scoreboard" in url:
        return _mock_response(FAKE_SCOREBOARD_RESPONSE)
    if "/buf/" in url:
        return _mock_response(BUF_INJURIES_RESPONSE)
    if "/ne/" in url:
        return _mock_response(NE_INJURIES_RESPONSE)
    # Unknown team URL → 404
    return _mock_response({}, status_code=404)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@patch("fantasy_gm.agent.tools_ext.opponent_injuries.httpx.get")
def test_shows_injured_player_name_and_status(mock_get):
    """Output includes significant injuries (Out/Questionable) from opponent."""
    mock_get.side_effect = _dispatch_get

    players = [
        # Tyreek Hill plays for MIA (id=15), faces NE
        RosterPlayer(
            player=_make_player("1", "Tyreek Hill", Position.WR, "15"),
            slot=Position.WR,
            is_starter=True,
        ),
        # Patrick Mahomes plays for KC (id=12), faces BUF
        RosterPlayer(
            player=_make_player("2", "Patrick Mahomes", Position.QB, "12"),
            slot=Position.QB,
            is_starter=True,
        ),
    ]
    ctx = FakeCtx(_make_roster(players))
    result = tool_get_opponent_injuries(ctx)

    # BUF has injured players — Mahomes faces BUF
    assert "Tre'Davious White" in result
    assert "Out" in result
    assert "Keon Coleman" in result
    assert "Questionable" in result

    # Probable should be filtered out
    assert "Josh Allen" not in result

    # Tyreek Hill section should reference MIA and NE
    assert "Tyreek Hill" in result
    assert "MIA" in result
    assert "NE" in result


@patch("fantasy_gm.agent.tools_ext.opponent_injuries.httpx.get")
def test_no_injuries_message_when_empty(mock_get):
    """Shows 'No significant injuries' when the opponent has a clean bill of health."""
    mock_get.side_effect = _dispatch_get

    players = [
        # Tyreek Hill plays for MIA (id=15), faces NE which has no injuries in fixture
        RosterPlayer(
            player=_make_player("1", "Tyreek Hill", Position.WR, "15"),
            slot=Position.WR,
            is_starter=True,
        ),
    ]
    ctx = FakeCtx(_make_roster(players))
    result = tool_get_opponent_injuries(ctx)

    assert "Tyreek Hill" in result
    assert "No significant injuries" in result
    assert "NE" in result


@patch("fantasy_gm.agent.tools_ext.opponent_injuries.httpx.get")
def test_graceful_404_on_injury_endpoint(mock_get):
    """When the injuries API returns 404, output notes no injuries instead of crashing."""
    def side_effect(url: str, **kwargs):
        if "scoreboard" in url:
            return _mock_response(FAKE_SCOREBOARD_RESPONSE)
        # All injury endpoints return 404
        m = MagicMock()
        m.status_code = 404
        return m

    mock_get.side_effect = side_effect

    players = [
        RosterPlayer(
            player=_make_player("2", "Patrick Mahomes", Position.QB, "12"),
            slot=Position.QB,
            is_starter=True,
        ),
    ]
    ctx = FakeCtx(_make_roster(players))
    result = tool_get_opponent_injuries(ctx)

    # Should not raise, and should mention the player and opponent
    assert "Patrick Mahomes" in result
    assert "BUF" in result
    assert "No significant injuries" in result


@patch("fantasy_gm.agent.tools_ext.opponent_injuries.httpx.get")
def test_player_without_nfl_team(mock_get):
    """Player with no proTeamId shows 'unknown' rather than crashing."""
    mock_get.side_effect = _dispatch_get

    players = [
        RosterPlayer(
            player=_make_player("3", "Waiver Wire RB", Position.RB, None),
            slot=Position.RB,
            is_starter=False,
        ),
    ]
    ctx = FakeCtx(_make_roster(players))
    result = tool_get_opponent_injuries(ctx)

    assert "Waiver Wire RB" in result
    assert "unknown" in result.lower()


@patch("fantasy_gm.agent.tools_ext.opponent_injuries.httpx.get")
def test_player_on_bye(mock_get):
    """Player whose team has no game this week shows BYE/not scheduled note."""
    mock_get.side_effect = _dispatch_get

    players = [
        # DAL (id=6) is not in the fixture scoreboard
        RosterPlayer(
            player=_make_player("4", "CeeDee Lamb", Position.WR, "6"),
            slot=Position.WR,
            is_starter=True,
        ),
    ]
    ctx = FakeCtx(_make_roster(players))
    result = tool_get_opponent_injuries(ctx)

    assert "CeeDee Lamb" in result
    assert "BYE" in result or "not scheduled" in result


@patch("fantasy_gm.agent.tools_ext.opponent_injuries.httpx.get")
def test_injury_api_error_continues_for_other_players(mock_get):
    """If one team's injury call fails, other players still get their output."""
    call_count = {"n": 0}

    def side_effect(url: str, **kwargs):
        if "scoreboard" in url:
            return _mock_response(FAKE_SCOREBOARD_RESPONSE)
        call_count["n"] += 1
        if "/buf/" in url and call_count["n"] == 1:
            raise ConnectionError("network timeout")
        if "/ne/" in url:
            return _mock_response(NE_INJURIES_RESPONSE)
        return _mock_response({}, status_code=404)

    mock_get.side_effect = side_effect

    players = [
        RosterPlayer(
            player=_make_player("2", "Patrick Mahomes", Position.QB, "12"),  # KC → BUF
            slot=Position.QB,
            is_starter=True,
        ),
        RosterPlayer(
            player=_make_player("1", "Tyreek Hill", Position.WR, "15"),  # MIA → NE
            slot=Position.WR,
            is_starter=True,
        ),
    ]
    ctx = FakeCtx(_make_roster(players))
    result = tool_get_opponent_injuries(ctx)

    # Both players appear in output even when one API call fails
    assert "Patrick Mahomes" in result
    assert "Tyreek Hill" in result


@patch("fantasy_gm.agent.tools_ext.opponent_injuries.httpx.get")
def test_deduplicates_opponent_injury_calls(mock_get):
    """Two players on the same NFL team trigger only one injury API call."""
    mock_get.side_effect = _dispatch_get

    players = [
        # Two KC players both face BUF — only one /buf/ call should happen
        RosterPlayer(
            player=_make_player("2", "Patrick Mahomes", Position.QB, "12"),
            slot=Position.QB,
            is_starter=True,
        ),
        RosterPlayer(
            player=_make_player("5", "Travis Kelce", Position.TE, "12"),
            slot=Position.TE,
            is_starter=True,
        ),
    ]
    ctx = FakeCtx(_make_roster(players))
    result = tool_get_opponent_injuries(ctx)

    buf_calls = [
        call for call in mock_get.call_args_list
        if "/buf/" in call.args[0]
    ]
    assert len(buf_calls) == 1, "Expected exactly one BUF injury API call"
    assert "Patrick Mahomes" in result
    assert "Travis Kelce" in result


@patch("fantasy_gm.agent.tools_ext.opponent_injuries.httpx.get")
def test_header_contains_week_and_season(mock_get):
    """Output header mentions the correct week and season."""
    mock_get.side_effect = _dispatch_get

    ctx = FakeCtx(_make_roster([], week=3, season=2026), week=3, season=2026)
    result = tool_get_opponent_injuries(ctx)

    assert "Week 3" in result
    assert "2026" in result
