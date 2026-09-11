"""
ESPN unofficial odds — live spread/total for the game-environment tool.

ESPN's public scoreboard embeds betting odds for upcoming games. We convert
each game's spread + over/under into per-team implied point totals, which the
`core/game_env.py` tool turns into a pass/run script tilt.

Keyless and best-effort: odds are only present for games that haven't kicked
off, so historical weeks return {}. The game-environment tool falls back to the
closing lines carried in nflverse `load_schedules` when live odds are absent.
"""
from __future__ import annotations

import re

import httpx

ESPN_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"

_SPREAD_RE = re.compile(r"([A-Z]{2,4})\s+(-?\d+(?:\.\d+)?)")


def implied_team_total(over_under: float, team_spread: float) -> float:
    """Implied points for a team given the game total and that team's spread.

    A favorite has a negative spread and the higher implied total:
        implied = over_under/2 - team_spread/2
    e.g. total 46, favorite spread -3  → 23 + 1.5 = 24.5.
    """
    return round(over_under / 2.0 - team_spread / 2.0, 2)


def get_espn_odds(season: int, week: int) -> dict[str, dict]:
    """Map NFL team abbrev -> {spread, over_under, implied_team_total, opponent}.

    `spread` is that team's spread (negative = favorite). Returns {} when odds
    are unavailable (past games, no lines posted, or any request error).
    """
    try:
        resp = httpx.get(
            ESPN_SCOREBOARD_URL,
            params={"week": week, "seasontype": 2, "dates": season},
            timeout=20,
        )
        resp.raise_for_status()
        events = resp.json().get("events", [])
    except Exception:
        return {}

    out: dict[str, dict] = {}
    for event in events:
        comps = event.get("competitions", [])
        if not comps:
            continue
        comp = comps[0]
        competitors = comp.get("competitors", [])
        abbrevs = {c.get("homeAway"): c.get("team", {}).get("abbreviation") for c in competitors}
        home, away = abbrevs.get("home"), abbrevs.get("away")
        odds_list = comp.get("odds", [])
        if not odds_list or not home or not away:
            continue
        odds = odds_list[0]
        over_under = odds.get("overUnder")
        # `spread` in ESPN's payload is the home team's line; `details` is a
        # string like "KC -3.5" naming the favorite.
        home_spread = odds.get("spread")
        details = odds.get("details") or ""
        if home_spread is None:
            m = _SPREAD_RE.search(details)
            if m:
                fav_abbrev, line = m.group(1), float(m.group(2))
                home_spread = line if fav_abbrev == home else -line
        if over_under is None or home_spread is None:
            continue
        home_spread = float(home_spread)
        over_under = float(over_under)
        out[home] = {
            "spread": home_spread,
            "over_under": over_under,
            "implied_team_total": implied_team_total(over_under, home_spread),
            "opponent": away,
        }
        out[away] = {
            "spread": -home_spread,
            "over_under": over_under,
            "implied_team_total": implied_team_total(over_under, -home_spread),
            "opponent": home,
        }
    return out
