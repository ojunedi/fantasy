"""The player card: photo, weekly fantasy points, season stats, recent news.

Read only. Fantasy points are ESPN's league-scored actuals from the weekly
read the app already caches (I-14: never a projection); real stats are
nflverse's, labelled with the week they run through (I-01). Completed weeks
never change, so they are memoised for the life of the process (NFR-03).
"""
from __future__ import annotations

from typing import Any

PHOTO_URL = "https://a.espncdn.com/i/headshots/nfl/players/full/{id}.png"
LOGO_URL = "https://a.espncdn.com/i/teamlogos/nfl/500/{abbr}.png"

_completed_weeks: dict[tuple[int, int], dict[str, float]] = {}


def weekly_actuals(adapter, week: int, season: int) -> dict[str, float]:
    """League-scored actuals for a completed week, read once per process."""
    key = (season, week)
    if key not in _completed_weeks:
        _completed_weeks[key] = adapter.get_actual_scores(week, season)
    return _completed_weeks[key]


def _stat_lines(position: str, t: dict) -> list[tuple[str, str]]:
    def n(k):
        return int(t.get(k, 0))
    lines = []
    if position == "QB":
        lines.append(("Passing", f"{n('completions')}/{n('attempts')}, {n('passing_yards')} yds, "
                                 f"{n('passing_tds')} TD, {n('passing_interceptions')} INT"))
    if position in ("QB", "RB", "WR", "TE") and n("carries"):
        lines.append(("Rushing", f"{n('carries')} car, {n('rushing_yards')} yds, {n('rushing_tds')} TD"))
    if position in ("RB", "WR", "TE"):
        lines.append(("Receiving", f"{n('receptions')}/{n('targets')} tgt, "
                                   f"{n('receiving_yards')} yds, {n('receiving_tds')} TD"))
    if position == "K":
        lines.append(("Field goals", f"{n('fg_made')}/{n('fg_att')}"))
    return lines


def build_card(adapter, player_id: str, season: int, current_week: int) -> dict | None:
    """Everything the card shows, or None for a player the system cannot find."""
    from fantasy_gm.signals.collector import ESPN_PRO_TEAM_ABBR
    from fantasy_gm.signals.news import cached_articles
    from fantasy_gm.signals.sources import nflverse as nv

    player = next((p for p in adapter.get_player_projections(current_week, season)
                   if p.player_id == player_id), None)
    if player is None:
        return None
    position = player.position.value

    weeks = []
    for week in range(1, current_week):
        try:
            points = weekly_actuals(adapter, week, season).get(player_id)
        except Exception:
            points = None
        weeks.append({"week": week, "points": points})

    is_defense = position in ("DST", "D/ST") or player_id.startswith("-")
    stats, team = None, None
    if is_defense:
        team = ESPN_PRO_TEAM_ABBR.get(str(abs(int(player_id)) - 16000))
    else:
        try:
            gsis = nv.build_id_map().gsis(player_id)
            totals = nv.season_totals(gsis, season) if gsis else None
        except Exception:
            totals = None
        if totals:
            team = totals.get("team")
            stats = {"lines": _stat_lines(position, totals),
                     "through_week": totals["through_week"]}

    news: list[dict] = []
    try:
        from fantasy_gm.web.context import relative_time
        feeds = list(cached_articles())
        # His team's feed too: the 50-story league feed rarely holds a player's
        # own news for long. nflverse says "LA" where ESPN says "LAR".
        abbr_to_espn = {v: k for k, v in ESPN_PRO_TEAM_ABBR.items()}
        team_id = abbr_to_espn.get({"LA": "LAR"}.get(team or "", team or ""))
        if team_id:
            try:
                feeds += cached_articles(team_id)
            except Exception:
                pass
        seen = set()
        for a in feeds:
            if player_id in a["athlete_ids"] and a["id"] not in seen:
                seen.add(a["id"])
                news.append({**a, "when": relative_time(a.get("published"))})
        news = sorted(news, key=lambda a: a.get("published") or "", reverse=True)[:5]
    except Exception:
        news = []

    return {
        "player_id": player_id,
        "name": player.player_name,
        "position": position,
        "team": team,
        "photo": (LOGO_URL.format(abbr=team.lower()) if is_defense and team
                  else None if is_defense else PHOTO_URL.format(id=player_id)),
        "initials": "".join(w[0] for w in player.player_name.split()[:2]).upper(),
        "weeks": weeks,
        "stats": stats,
        "news": news,
    }
