"""
Projection engine — blends multiple projection sources into one number.

Combines ESPN (league-scored), Sleeper, and FantasyPros/nflverse projections
into a mean per player-week, with a rough floor/ceiling derived from how much
the sources disagree (wide disagreement → wider band). This is the single
source of truth the downstream tools (trade value, lineup adjustments) read.

All sources must be keyed by the *same* player id (the caller maps Sleeper /
gsis ids into our ESPN-id space first). Pure functions — no I/O.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BlendedProjection:
    player_id: str
    mean: float
    floor: float
    ceiling: float
    n_sources: int
    per_source: dict[str, float] = field(default_factory=dict)

    @property
    def sources(self) -> list[str]:
        return sorted(self.per_source.keys())


def blend_player(per_source: dict[str, float], weights: dict[str, float] | None = None,
                 player_id: str = "") -> BlendedProjection:
    """Blend one player's per-source projections into mean/floor/ceiling."""
    items = [(s, v) for s, v in per_source.items() if v is not None]
    if not items:
        return BlendedProjection(player_id=player_id, mean=0.0, floor=0.0,
                                 ceiling=0.0, n_sources=0, per_source={})
    values = [v for _s, v in items]
    if weights:
        w = [weights.get(s, 1.0) for s, _v in items]
        total_w = sum(w) or 1.0
        mean = sum(v * wi for (_s, v), wi in zip(items, w)) / total_w
    else:
        mean = sum(values) / len(values)

    # Dispersion band: half the source spread, plus a base volatility term.
    half_range = (max(values) - min(values)) / 2.0 if len(values) >= 2 else 0.30 * mean
    floor = max(0.0, round(mean - half_range - 0.15 * mean, 2))
    ceiling = round(mean + half_range + 0.20 * mean, 2)
    return BlendedProjection(
        player_id=player_id, mean=round(mean, 2), floor=floor, ceiling=ceiling,
        n_sources=len(values), per_source={s: round(v, 2) for s, v in items},
    )


def blend_projections(
    sources: dict[str, dict[str, float]],
    weights: dict[str, float] | None = None,
) -> dict[str, BlendedProjection]:
    """Blend a set of projection sources.

    `sources` maps source_name -> {player_id: projected_points}. Returns one
    BlendedProjection per player id seen in any source.
    """
    all_ids: set[str] = set()
    for src_map in sources.values():
        all_ids.update(src_map.keys())

    out: dict[str, BlendedProjection] = {}
    for pid in all_ids:
        per_source = {
            src: src_map[pid]
            for src, src_map in sources.items()
            if pid in src_map and src_map[pid] is not None
        }
        out[pid] = blend_player(per_source, weights=weights, player_id=pid)
    return out
