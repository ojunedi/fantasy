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
