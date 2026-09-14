"""
Availability-flag reconciliation in get_projections.

A ~0 projection is an availability flag, not a score. These tests pin the
deterministic reconciliation against injury status (no LLM, no network) by
injecting a hand-built SignalBundle:
  - ACTIVE  + 0.0  -> SUSPECT (contradiction; must corroborate with news)
  - OUT     + 0.0  -> consistent (do not start; no research needed)
  - MISSING + ACTIVE -> SUSPECT
  - normal non-zero projection -> no flag
"""
from fantasy_gm.agent.tools import LineupToolContext
from fantasy_gm.models import (
    InjuryReport,
    LeagueSettings,
    Platform,
    Player,
    PlayerProjection,
    PlayerStatus,
    Position,
    Roster,
    RosterPlayer,
    RosterSlot,
    ScoringRules,
    WaiverType,
)
from fantasy_gm.signals.base import SignalAvailability, SignalBundle


def _player(pid, pos, status=PlayerStatus.ACTIVE):
    return Player(platform_id=pid, name=f"Player {pid}", position=pos,
                  eligible_positions=[pos], status=status)


def _proj(pid, pos, pts):
    return PlayerProjection(player_id=pid, player_name=f"Player {pid}",
                            projected_points=pts, position=pos, week=1, season=2025)


def _ctx_with(players, projections, injuries):
    slots = [RosterSlot(slot_id="qb", position=Position.QB, is_starter=True)]
    settings = LeagueSettings(
        platform=Platform.ESPN, league_id="test", season=2025, team_count=12,
        roster_slots=slots, scoring_rules=ScoringRules(rules=[]),
        waiver_type=WaiverType.SNAKE, faab_budget=None,
        playoff_start_week=15, playoff_weeks=[15, 16, 17],
        regular_season_weeks=list(range(1, 15)),
    )
    roster = Roster(team_id="8", team_name="T", owner_name="Me",
                    players=players, week=1, season=2025)
    ctx = LineupToolContext(adapter=None, settings=settings, team_id="8",
                            week=1, season=2025)
    # Inject caches directly so signals()/roster() never touch the network.
    ctx._roster = roster
    ctx._signals = SignalBundle(
        week=1, season=2025, projections=projections, injuries=injuries,
        availability=[SignalAvailability(name="projections", available=True,
                                         source="ESPN", note="test")],
    )
    return ctx


def test_active_zero_projection_is_flagged_suspect():
    p = RosterPlayer(player=_player("burrow", Position.QB), slot=Position.QB, is_starter=True)
    ctx = _ctx_with(
        players=[p],
        projections={"burrow": _proj("burrow", Position.QB, 0.0)},
        injuries={"burrow": InjuryReport(player_id="burrow", player_name="Player burrow",
                                         status=PlayerStatus.ACTIVE, week=1)},
    )
    out, _ = ctx.dispatch("get_projections", {})
    assert "AVAILABILITY FLAGS" in out
    assert "SUSPECT" in out
    assert "CONTRADICTION" in out
    # The model is told to corroborate, not to bench on the zero alone.
    assert "nfl_news" in out or "search_web" in out


def test_out_zero_projection_is_benign():
    p = RosterPlayer(player=_player("hurt", Position.QB, PlayerStatus.OUT),
                     slot=Position.QB, is_starter=True)
    ctx = _ctx_with(
        players=[p],
        projections={"hurt": _proj("hurt", Position.QB, 0.0)},
        injuries={"hurt": InjuryReport(player_id="hurt", player_name="Player hurt",
                                       status=PlayerStatus.OUT, week=1)},
    )
    out, _ = ctx.dispatch("get_projections", {})
    assert "consistent with status OUT" in out
    assert "do not start" in out.lower()
    assert "SUSPECT" not in out


def test_missing_projection_active_is_suspect():
    p = RosterPlayer(player=_player("ghost", Position.QB), slot=Position.QB, is_starter=True)
    ctx = _ctx_with(players=[p], projections={}, injuries={})
    out, _ = ctx.dispatch("get_projections", {})
    assert "MISSING" in out
    assert "SUSPECT" in out


def test_normal_projection_has_no_flag():
    p = RosterPlayer(player=_player("stroud", Position.QB), slot=Position.QB, is_starter=True)
    ctx = _ctx_with(
        players=[p],
        projections={"stroud": _proj("stroud", Position.QB, 16.86)},
        injuries={},
    )
    out, _ = ctx.dispatch("get_projections", {})
    assert "AVAILABILITY FLAGS" not in out
    assert "SUSPECT" not in out
