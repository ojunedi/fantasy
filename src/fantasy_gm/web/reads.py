"""Cached adapter reads.

The adapter already disk-caches for an hour, so what these save is not network
but repeated JSON parsing and model construction: one page with three HTMX
partials would otherwise re-parse the same file three times. The TTL is 60s,
far below the adapter's, so `fresh=True` can never be masked by this layer.

Signal collection is the one genuinely slow call (nflverse parquet), so it is
cached the same way and is always optional — every page renders without it.
"""
from __future__ import annotations

from typing import Any

from fantasy_gm.web.deps import ReadCache, league_settings_for


def current_week(adapter: Any, settings: Any, reads: ReadCache) -> int:
    if settings.week is not None:
        return settings.week
    try:
        return reads.get(("week", settings.season),
                         lambda: adapter.get_current_week(settings.season))
    except Exception:
        return 1


def league_settings(adapter: Any, season: int):
    return league_settings_for(adapter, season)


def roster(adapter: Any, reads: ReadCache, team_id: str, week: int, season: int,
           fresh: bool = False):
    if fresh:
        return adapter.get_roster(team_id, week, season, fresh=True)
    return reads.get(("roster", team_id, week, season),
                     lambda: adapter.get_roster(team_id, week, season))


def projections(adapter: Any, reads: ReadCache, week: int, season: int) -> dict[str, float]:
    return reads.get(("projections", week, season),
                     lambda: adapter.get_projections(week, season))


def standings(adapter: Any, reads: ReadCache, season: int):
    return reads.get(("standings", season), lambda: adapter.get_standings(season))


def all_rosters(adapter: Any, reads: ReadCache, week: int, season: int):
    return reads.get(("all_rosters", week, season),
                     lambda: adapter.get_all_rosters(week, season))


# Lock state and banked points both change at kickoff, so the in-week roster is
# read past the adapter's 1h disk cache. The 60s memo still stops one page with
# three partials from fetching it three times.
LIVE_ROSTER_TTL = 30.0


def live_rosters(adapter: Any, cache: ReadCache, week: int, season: int,
                 fresh: bool = False) -> list:
    """Every team's roster, fresh off ESPN rather than from the disk cache.

    `get_all_rosters(fresh=True)` is one request and yields the opponent's
    lineup too, which is what the live matchup total needs.
    """
    if fresh:
        return adapter.get_all_rosters(week, season, fresh=True)
    return cache.get(("live_rosters", week, season),
                     lambda: adapter.get_all_rosters(week, season, fresh=True))


def matchup(adapter: Any, reads: ReadCache, team_id: str, week: int, season: int):
    """None rather than an exception: a bye or an unscheduled week is normal,
    and the rest of the page is still worth rendering."""
    try:
        return reads.get(("matchup", team_id, week, season),
                         lambda: adapter.get_matchup(team_id, week, season))
    except Exception:
        return None


def all_matchups(adapter: Any, reads: ReadCache, week: int, season: int,
                 standings_rows: list) -> list:
    """Every game this week, assembled from the per-team matchup read."""
    def compute():
        seen: set[frozenset[str]] = set()
        out = []
        for row in standings_rows:
            try:
                m = adapter.get_matchup(row.team_id, week, season)
            except Exception:
                continue
            key = frozenset({m.home.team_id, m.away.team_id})
            if key in seen:
                continue
            seen.add(key)
            out.append(m)
        return out

    return reads.get(("all_matchups", week, season), compute)


def signals(adapter: Any, reads: ReadCache, roster_obj: Any, week: int, season: int):
    """SignalBundle, or None when collection fails — never fatal to a page."""
    def compute():
        from fantasy_gm.signals.collector import collect_signals
        return collect_signals(adapter, week, season, roster_obj.players)

    try:
        return reads.get(("signals", roster_obj.team_id, week, season), compute)
    except Exception:
        return None


def raw_lineup_slots(adapter: Any, team_id: str, week: int, season: int) -> dict[str, int]:
    """Deliberately uncached — this one feeds the write path, where a stale
    'current slot' would produce a plan that ESPN rejects."""
    return adapter.get_raw_lineup_slots(team_id, week, season)


# ------------------------------------------------------------------ trades

def trade_value_map(
    adapter: Any, cache: ReadCache, week: int, season: int, team_id: str
) -> tuple[dict, float | None]:
    """FantasyCalc-backed value map for this team's league + epoch of build.

    FantasyCalc is a network call that can fail. Any exception degrades to an
    empty dict with a None timestamp so the page still renders without values.
    """
    def compute():
        from fantasy_gm.agent.trade.tools import TradeToolContext
        settings = league_settings_for(adapter, season)
        ctx = TradeToolContext(
            adapter=adapter, settings=settings,
            team_id=team_id, week=week, season=season,
        )
        import time as _t
        vm = ctx.value_map()
        return vm, _t.time()

    try:
        return cache.get(("trade_value_map", week, season, team_id), compute)
    except Exception:
        return {}, None


def league_player_index(
    adapter: Any, cache: ReadCache, week: int, season: int
) -> dict:
    """pid -> {player, position, team, name, owner_team_id, owner_name}.

    Built from all rosters via TradeToolContext so the join is identical to
    what the trade agent sees. Returns {} on any exception.
    """
    def compute():
        from fantasy_gm.agent.trade.tools import TradeToolContext
        # Use a placeholder team_id; player_index spans all rosters.
        settings = league_settings_for(adapter, season)
        all_r = adapter.get_all_rosters(week, season)
        ctx = TradeToolContext(
            adapter=adapter, settings=settings,
            team_id=(all_r[0].team_id if all_r else "1"),
            week=week, season=season,
            _all_rosters=all_r,
        )
        return ctx.player_index()

    try:
        return cache.get(("league_player_index", week, season), compute)
    except Exception:
        return {}


def my_trade_needs(
    adapter: Any, cache: ReadCache, week: int, season: int, team_id: str
) -> tuple[dict, list]:
    """(roster_needs dict, trade_chips list) for *my* team.

    roster_needs keys: count/startable/required/surplus/unfilled/best/bar/need/thin.
    trade_chips: [(RosterPlayer, AssetValue)] sorted value-desc.
    Returns ({}, []) on any exception.
    """
    def compute():
        from fantasy_gm.agent.trade.tools import TradeToolContext
        settings = league_settings_for(adapter, season)
        roster_obj = adapter.get_roster(team_id, week, season)
        ctx = TradeToolContext(
            adapter=adapter, settings=settings,
            team_id=team_id, week=week, season=season,
            _roster=roster_obj,
        )
        needs = ctx.roster_needs(roster_obj)
        chips = ctx.trade_chips(roster_obj)
        return needs, chips

    try:
        return cache.get(("my_trade_needs", week, season, team_id), compute)
    except Exception:
        return {}, []
