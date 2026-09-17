"""
nflverse data source (via nflreadpy).

The analytics engine for the deterministic core tools: weekly player stats,
snap counts, opportunity, schedules (incl. Vegas lines + roof), injuries,
FantasyPros-derived rankings, and the cross-platform player-ID map.

Design:
  - Each loader is a thin wrapper over an `nflreadpy` loader, cached to
    `data/cache/nflverse/*.parquet` with a TTL so the deterministic tools are
    reproducible within a session and work offline once warmed.
  - This module returns Polars DataFrames from the raw loaders and *normalized
    Python dicts/lists* from the higher-level helpers. The `core/` tools consume
    the normalized structures only — they never import Polars — so they stay
    pure and unit-testable against fixtures.
  - ID bridge: ESPN player IDs ↔ nflverse `gsis_id` (the `player_id` in
    player_stats/injuries) via `load_ff_playerids`, which also carries Sleeper
    and FantasyPros IDs.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

CACHE_DIR = Path("data/cache/nflverse")
DEFAULT_TTL = 6 * 3600  # 6 hours — nflverse data updates at most a few times/day


def _cache_path(name: str) -> Path:
    return CACHE_DIR / f"{name}.parquet"


def _cached(name: str, loader: Callable[[], Any], ttl: int = DEFAULT_TTL):
    """Load a Polars DataFrame, caching it as parquet under CACHE_DIR.

    Returns a fresh cached copy when present and younger than ttl; otherwise
    calls `loader`, writes the result, and returns it. On a loader failure with
    a stale cache present, the stale cache is returned rather than raising.
    """
    import polars as pl

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(name)
    if path.exists() and (time.time() - path.stat().st_mtime) < ttl:
        return pl.read_parquet(path)
    try:
        df = loader()
    except Exception:
        if path.exists():
            return pl.read_parquet(path)
        raise
    try:
        df.write_parquet(path)
    except Exception:
        pass
    return df


# ---------------------------------------------------------------------------
# Raw loaders (Polars DataFrames)
# ---------------------------------------------------------------------------

def _nfl():
    """Import `nflreadpy` on first use.

    It is a heavy import (and pulls the network on a cache miss), so the loaders
    below call this from inside their `_cached` lambda — a warm cache therefore
    never imports it at all.
    """
    import nflreadpy as nfl
    return nfl


def load_player_stats(season: int):
    return _cached(f"player_stats_{season}", lambda: _nfl().load_player_stats(season))


def load_snap_counts(season: int):
    return _cached(f"snap_counts_{season}", lambda: _nfl().load_snap_counts(season))


def load_ff_opportunity(season: int):
    return _cached(f"ff_opportunity_{season}", lambda: _nfl().load_ff_opportunity(season))


def load_schedules(season: int):
    return _cached(f"schedules_{season}", lambda: _nfl().load_schedules(season))


def load_injuries(season: int):
    return _cached(f"injuries_{season}", lambda: _nfl().load_injuries(season))


def load_ff_rankings():
    return _cached("ff_rankings_week", lambda: _nfl().load_ff_rankings(type="week"), ttl=3600)


def load_players():
    return _cached("players", lambda: _nfl().load_players())


def load_ff_playerids():
    # ID map changes rarely; cache for a week.
    return _cached("ff_playerids", lambda: _nfl().load_ff_playerids(), ttl=7 * 24 * 3600)


# ---------------------------------------------------------------------------
# ID mapping (ESPN ↔ nflverse gsis ↔ Sleeper)
# ---------------------------------------------------------------------------

class IdMap:
    """Bidirectional map between ESPN player IDs and nflverse gsis_ids.

    Also exposes Sleeper IDs and display names, keyed by gsis_id, so the
    projection engine can join Sleeper's weekly projections.
    """

    def __init__(self, espn_to_gsis: dict[str, str], gsis_to_sleeper: dict[str, str],
                 gsis_to_name: dict[str, str]):
        self.espn_to_gsis = espn_to_gsis
        self.gsis_to_espn = {v: k for k, v in espn_to_gsis.items()}
        self.gsis_to_sleeper = gsis_to_sleeper
        self.gsis_to_name = gsis_to_name

    def gsis(self, espn_id: str) -> str | None:
        return self.espn_to_gsis.get(str(espn_id))

    def espn(self, gsis_id: str) -> str | None:
        return self.gsis_to_espn.get(gsis_id)

    def sleeper(self, gsis_id: str) -> str | None:
        return self.gsis_to_sleeper.get(gsis_id)


def build_id_map() -> IdMap:
    df = load_ff_playerids()
    espn_to_gsis: dict[str, str] = {}
    gsis_to_sleeper: dict[str, str] = {}
    gsis_to_name: dict[str, str] = {}
    for row in df.iter_rows(named=True):
        gsis = row.get("gsis_id")
        espn = row.get("espn_id")
        if gsis is None:
            continue
        gsis = str(gsis)
        if espn is not None and str(espn) != "":
            espn_to_gsis[str(int(espn)) if _is_intlike(espn) else str(espn)] = gsis
        sleeper = row.get("sleeper_id")
        if sleeper is not None and str(sleeper) != "":
            gsis_to_sleeper[gsis] = str(int(sleeper)) if _is_intlike(sleeper) else str(sleeper)
        if row.get("name"):
            gsis_to_name[gsis] = row["name"]
    return IdMap(espn_to_gsis, gsis_to_sleeper, gsis_to_name)


def _is_intlike(v: Any) -> bool:
    try:
        return float(v) == int(float(v))
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------------------
# Normalized helpers (Polars → plain dicts for the core tools)
# ---------------------------------------------------------------------------

# Columns the core tools care about, kept small on purpose.
_STAT_COLS = [
    "player_id", "player_display_name", "position", "team", "opponent_team",
    "week", "season", "fantasy_points_ppr",
    "carries", "targets", "receptions", "receiving_air_yards",
    "target_share", "air_yards_share", "rushing_tds", "receiving_tds",
]


def player_stat_rows(season: int, through_week: int | None = None) -> list[dict]:
    """Normalized weekly stat rows (regular + post season), one per player-week.

    Keys mirror `_STAT_COLS`; missing numeric values are coerced to 0.0. If
    `through_week` is given, rows with week > through_week are dropped (so the
    tools never peek at the future when analyzing a given week).
    """
    df = load_player_stats(season)
    have = [c for c in _STAT_COLS if c in df.columns]
    rows: list[dict] = []
    for r in df.select(have).iter_rows(named=True):
        wk = r.get("week")
        if through_week is not None and wk is not None and wk > through_week:
            continue
        out = dict(r)
        out["player_id"] = str(out.get("player_id") or "")
        for c in ("carries", "targets", "receptions", "receiving_air_yards",
                  "target_share", "air_yards_share", "rushing_tds", "receiving_tds",
                  "fantasy_points_ppr"):
            out[c] = float(out.get(c) or 0.0)
        rows.append(out)
    return rows


def schedule_rows(season: int) -> list[dict]:
    """Normalized schedule rows with Vegas lines + roof, one per game."""
    df = load_schedules(season)
    cols = ["game_id", "season", "week", "game_type", "away_team", "home_team",
            "spread_line", "total_line", "roof", "stadium", "gameday"]
    have = [c for c in cols if c in df.columns]
    out: list[dict] = []
    for r in df.select(have).iter_rows(named=True):
        out.append(dict(r))
    return out
