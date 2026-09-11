"""
Usage / opportunity analysis — "volume trumps talent."

From a player's recent weekly rows, computes trailing-window averages of the
inputs that drive fantasy scoring opportunity (targets, carries, target share,
air-yards share, snap share, red-zone touches) and a composite opportunity
score, plus a breakout flag when recent usage is rising sharply off a lower
baseline.

Pure functions — no I/O. Rows are plain dicts (from the nflverse source),
already filtered to one player and not peeking past the analysis week.
"""
from __future__ import annotations

from dataclasses import dataclass

DEFAULT_WINDOWS: tuple[int, ...] = (3, 5, 10)


@dataclass(frozen=True)
class UsageWindow:
    """Per-game averages over the most recent `window` games."""
    window: int
    games: int
    targets: float
    carries: float
    target_share: float        # 0–1
    air_yards_share: float     # 0–1
    snap_share: float          # 0–1 (0 if unavailable)
    rz_touches: float
    opportunity_score: float   # 0–100


@dataclass(frozen=True)
class UsageProfile:
    player_id: str
    windows: dict[int, UsageWindow]
    trend: str        # "rising" | "steady" | "falling"
    breakout: bool

    def window(self, n: int) -> UsageWindow | None:
        return self.windows.get(n)


def _avg(vals: list[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def opportunity_score(
    targets: float, carries: float, target_share: float,
    air_yards_share: float, snap_share: float,
) -> float:
    """Composite 0–100 opportunity score, monotone increasing in every input."""
    raw = (
        (targets + carries) * 3.5      # ~28 opportunities/game → ~98
        + target_share * 30.0
        + air_yards_share * 20.0
        + snap_share * 20.0
    )
    return round(min(100.0, raw), 1)


def _window_stats(rows: list[dict], n: int) -> UsageWindow:
    recent = rows[-n:] if n else rows
    targets = _avg([float(r.get("targets") or 0.0) for r in recent])
    carries = _avg([float(r.get("carries") or 0.0) for r in recent])
    target_share = _avg([float(r.get("target_share") or 0.0) for r in recent])
    ay_share = _avg([float(r.get("air_yards_share") or 0.0) for r in recent])
    snap_share = _avg([float(r.get("snap_share") or 0.0) for r in recent])
    rz = _avg([float(r.get("rz_touches") or 0.0) for r in recent])
    return UsageWindow(
        window=n, games=len(recent),
        targets=round(targets, 2), carries=round(carries, 2),
        target_share=round(target_share, 3), air_yards_share=round(ay_share, 3),
        snap_share=round(snap_share, 3), rz_touches=round(rz, 2),
        opportunity_score=opportunity_score(targets, carries, target_share, ay_share, snap_share),
    )


def usage_summary(
    rows: list[dict],
    windows: tuple[int, ...] = DEFAULT_WINDOWS,
    player_id: str = "",
) -> UsageProfile:
    """Build a UsageProfile from a player's chronologically-sorted weekly rows."""
    ordered = sorted(rows, key=lambda r: r.get("week", 0))
    win_stats = {n: _window_stats(ordered, n) for n in windows}

    # Trend: last-3 opportunity vs. the games before it (the earlier baseline).
    last3 = _window_stats(ordered, 3).opportunity_score
    prior_rows = ordered[:-3] if len(ordered) > 3 else []
    prior = _window_stats(prior_rows, len(prior_rows)).opportunity_score if prior_rows else last3

    if prior <= 0:
        ratio = 1.0 if last3 <= 0 else 2.0
    else:
        ratio = last3 / prior
    if ratio >= 1.15:
        trend = "rising"
    elif ratio <= 0.85:
        trend = "falling"
    else:
        trend = "steady"

    # Breakout: recent usage both rising and at a meaningful absolute level.
    breakout = ratio >= 1.25 and last3 >= 40.0

    return UsageProfile(
        player_id=player_id or (ordered[0].get("player_id", "") if ordered else ""),
        windows=win_stats, trend=trend, breakout=breakout,
    )
