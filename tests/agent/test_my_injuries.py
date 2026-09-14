"""
Unit tests for tool_get_my_injury_summary.

Uses a minimal fake context that provides roster() and signals()
directly — no live adapter or network calls.
"""
from __future__ import annotations

from fantasy_gm.agent.tools_ext.my_injuries import tool_get_my_injury_summary
from fantasy_gm.models import (
    InjuryReport,
    Player,
    PlayerStatus,
    Position,
    Roster,
    RosterPlayer,
)
from fantasy_gm.signals.base import SignalBundle


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_player(
    pid: str,
    pos: Position,
    status: PlayerStatus = PlayerStatus.ACTIVE,
    name: str | None = None,
) -> Player:
    return Player(
        platform_id=pid,
        name=name or f"Player {pid}",
        position=pos,
        eligible_positions=[pos],
        status=status,
    )


def _make_roster(players: list[RosterPlayer], week: int = 1, season: int = 2026) -> Roster:
    return Roster(
        team_id="8",
        team_name="Test",
        owner_name="Me",
        players=players,
        week=week,
        season=season,
    )


class FakeCtx:
    """Minimal fake context for tool_get_my_injury_summary."""

    def __init__(
        self,
        roster: Roster,
        signals: SignalBundle | None = None,
        week: int = 1,
        season: int = 2026,
    ) -> None:
        self._roster = roster
        self._signals = signals or SignalBundle(week=week, season=season)
        self.week = week
        self.season = season

    def roster(self) -> Roster:
        return self._roster

    def signals(self) -> SignalBundle:
        return self._signals


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_all_active_returns_brief_message():
    """When every player is ACTIVE, the tool returns the brief short-circuit message."""
    players = [
        RosterPlayer(player=_make_player("qb1", Position.QB), slot=Position.QB, is_starter=True),
        RosterPlayer(player=_make_player("rb1", Position.RB), slot=Position.RB, is_starter=True),
        RosterPlayer(player=_make_player("wr1", Position.WR), slot=Position.WR, is_starter=True),
        RosterPlayer(player=_make_player("wr2", Position.WR), slot=Position.BENCH, is_starter=False),
    ]
    ctx = FakeCtx(_make_roster(players))
    result = tool_get_my_injury_summary(ctx)

    assert "All players ACTIVE" in result
    # Should be a single short line, not a full table
    assert "\n" not in result


def test_starter_out_contains_urgent_language():
    """When a starting player is OUT, output includes the player name and DO NOT START."""
    injured_qb = _make_player("qb1", Position.QB, status=PlayerStatus.OUT, name="Injured QB")
    players = [
        RosterPlayer(player=injured_qb, slot=Position.QB, is_starter=True),
        RosterPlayer(player=_make_player("rb1", Position.RB), slot=Position.RB, is_starter=True),
        RosterPlayer(player=_make_player("wr1", Position.WR), slot=Position.WR, is_starter=True),
        RosterPlayer(player=_make_player("wr2", Position.WR), slot=Position.BENCH, is_starter=False),
    ]
    ctx = FakeCtx(_make_roster(players))
    result = tool_get_my_injury_summary(ctx)

    assert "Injured QB" in result
    assert "DO NOT START" in result
    # Must appear in the starters section (case-insensitive check for "STARTER")
    assert "STARTER" in result


def test_starter_ir_contains_urgent_language():
    """IR players on IR slot should also trigger DO NOT START."""
    ir_te = _make_player("te1", Position.TE, status=PlayerStatus.IR, name="IR Tight End")
    players = [
        RosterPlayer(player=ir_te, slot=Position.IR, is_starter=True),
        RosterPlayer(player=_make_player("qb1", Position.QB), slot=Position.QB, is_starter=True),
    ]
    ctx = FakeCtx(_make_roster(players))
    result = tool_get_my_injury_summary(ctx)

    assert "IR Tight End" in result
    assert "DO NOT START" in result


def test_bench_questionable_contains_name_and_position():
    """A bench player who is QUESTIONABLE appears with their name and position."""
    hurt_wr = _make_player("wr2", Position.WR, status=PlayerStatus.QUESTIONABLE, name="Hurt WR")
    players = [
        RosterPlayer(player=_make_player("qb1", Position.QB), slot=Position.QB, is_starter=True),
        RosterPlayer(player=_make_player("rb1", Position.RB), slot=Position.RB, is_starter=True),
        RosterPlayer(player=_make_player("wr1", Position.WR), slot=Position.WR, is_starter=True),
        RosterPlayer(player=hurt_wr, slot=Position.BENCH, is_starter=False),
    ]
    ctx = FakeCtx(_make_roster(players))
    result = tool_get_my_injury_summary(ctx)

    assert "Hurt WR" in result
    assert "WR" in result
    assert "BENCH" in result
    assert "Monitor final report" in result


def test_doubtful_bench_shows_unlikely_to_play():
    """A bench player who is DOUBTFUL shows the 'Unlikely to play (25%)' action note."""
    doubtful_rb = _make_player("rb2", Position.RB, status=PlayerStatus.DOUBTFUL, name="Doubtful RB")
    players = [
        RosterPlayer(player=_make_player("qb1", Position.QB), slot=Position.QB, is_starter=True),
        RosterPlayer(player=_make_player("rb1", Position.RB), slot=Position.RB, is_starter=True),
        RosterPlayer(player=doubtful_rb, slot=Position.BENCH, is_starter=False),
    ]
    ctx = FakeCtx(_make_roster(players))
    result = tool_get_my_injury_summary(ctx)

    assert "Doubtful RB" in result
    assert "Unlikely to play (25%)" in result


def test_signal_bundle_enriches_injury_description():
    """When the signal bundle has an InjuryReport, the injury description is shown."""
    player = _make_player("wr1", Position.WR, status=PlayerStatus.QUESTIONABLE, name="Hamstring WR")
    players = [
        RosterPlayer(player=player, slot=Position.WR, is_starter=True),
        RosterPlayer(player=_make_player("qb1", Position.QB), slot=Position.QB, is_starter=True),
    ]

    injury_report = InjuryReport(
        player_id="wr1",
        player_name="Hamstring WR",
        status=PlayerStatus.QUESTIONABLE,
        injury_description="Hamstring",
        week=1,
    )
    signals = SignalBundle(week=1, season=2026, injuries={"wr1": injury_report})

    ctx = FakeCtx(_make_roster(players), signals=signals)
    result = tool_get_my_injury_summary(ctx)

    assert "Hamstring WR" in result
    assert "Hamstring" in result


def test_signal_status_overrides_roster_status():
    """The signal bundle status takes precedence over the ESPN roster status."""
    # ESPN says QUESTIONABLE, signals say OUT
    player = _make_player("rb1", Position.RB, status=PlayerStatus.QUESTIONABLE, name="Updated RB")
    players = [
        RosterPlayer(player=player, slot=Position.RB, is_starter=True),
        RosterPlayer(player=_make_player("qb1", Position.QB), slot=Position.QB, is_starter=True),
    ]

    injury_report = InjuryReport(
        player_id="rb1",
        player_name="Updated RB",
        status=PlayerStatus.OUT,  # more authoritative
        week=1,
    )
    signals = SignalBundle(week=1, season=2026, injuries={"rb1": injury_report})

    ctx = FakeCtx(_make_roster(players), signals=signals)
    result = tool_get_my_injury_summary(ctx)

    # Should be treated as OUT (DO NOT START), not QUESTIONABLE
    assert "DO NOT START" in result
    assert "Updated RB" in result


def test_header_contains_week_and_season():
    """Output header mentions the correct week and season when there are injuries."""
    injured = _make_player("qb1", Position.QB, status=PlayerStatus.OUT, name="Any QB")
    players = [
        RosterPlayer(player=injured, slot=Position.QB, is_starter=True),
    ]
    ctx = FakeCtx(_make_roster(players, week=5, season=2026), week=5, season=2026)
    result = tool_get_my_injury_summary(ctx)

    assert "Week 5" in result
    assert "2026" in result


def test_active_players_summary_at_bottom():
    """Healthy (ACTIVE) players are summarized by position at the bottom."""
    players = [
        RosterPlayer(
            player=_make_player("qb1", Position.QB, status=PlayerStatus.OUT, name="Out QB"),
            slot=Position.QB, is_starter=True,
        ),
        RosterPlayer(
            player=_make_player("rb1", Position.RB, name="Healthy RB"),
            slot=Position.RB, is_starter=True,
        ),
        RosterPlayer(
            player=_make_player("wr1", Position.WR, name="Healthy WR"),
            slot=Position.WR, is_starter=True,
        ),
    ]
    ctx = FakeCtx(_make_roster(players))
    result = tool_get_my_injury_summary(ctx)

    # Active players should appear in the summary
    assert "Healthy RB" in result
    assert "Healthy WR" in result
    assert "All other players ACTIVE" in result


def test_urgency_ordering_out_before_questionable():
    """OUT players appear before QUESTIONABLE players in the output."""
    players = [
        RosterPlayer(
            player=_make_player("wr1", Position.WR, status=PlayerStatus.QUESTIONABLE, name="Questionable WR"),
            slot=Position.WR, is_starter=True,
        ),
        RosterPlayer(
            player=_make_player("rb1", Position.RB, status=PlayerStatus.OUT, name="Out RB"),
            slot=Position.RB, is_starter=True,
        ),
    ]
    ctx = FakeCtx(_make_roster(players))
    result = tool_get_my_injury_summary(ctx)

    pos_out = result.index("Out RB")
    pos_q = result.index("Questionable WR")
    assert pos_out < pos_q, "OUT player should appear before QUESTIONABLE player"
