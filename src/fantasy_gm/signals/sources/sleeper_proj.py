"""
Sleeper weekly projections — a second, keyless projection source.

Sleeper publishes per-player weekly projections at
`api.sleeper.com/projections/nfl/{season}/{week}`. We pull PPR points
(`stats.pts_ppr`) keyed by Sleeper player_id, which the projection engine joins
to our players via the nflverse ID map (gsis → sleeper_id).

Keyless and public. Returns an empty map (never raises) on any failure, so a
missing source degrades gracefully in the signal-availability model.
"""
from __future__ import annotations

import httpx

SLEEPER_PROJ_URL = "https://api.sleeper.com/projections/nfl/{season}/{week}"


def get_sleeper_projections(season: int, week: int) -> dict[str, float]:
    """Map Sleeper player_id -> projected PPR points for the given week.

    PPR is used as the common denominator; the projection engine rescales/blends
    against ESPN's league-scored projection. Returns {} on any error.
    """
    try:
        resp = httpx.get(
            SLEEPER_PROJ_URL.format(season=season, week=week),
            params={"season_type": "regular",
                    "position[]": ["QB", "RB", "WR", "TE", "K", "DEF"]},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return {}

    out: dict[str, float] = {}
    if not isinstance(data, list):
        return out
    for entry in data:
        pid = entry.get("player_id")
        stats = entry.get("stats") or {}
        pts = stats.get("pts_ppr")
        if pid is None or pts is None:
            continue
        out[str(pid)] = float(pts)
    return out
