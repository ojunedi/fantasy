"""
Defense-vs-Position (DvP) matchup analysis.

Computes, from nflverse weekly player stats, how many fantasy points each
defense allows to each offensive position per game, then grades an individual
matchup relative to the league average for that position.

The grade is *relative* (a ratio vs. the league mean), so it is scoring-system
agnostic — a top-5 matchup is a top-5 matchup whether the league is PPR or not.
Points are taken from the PPR column by default; pass a `points_fn` to score a
row under different rules (reusing `scoring.calculate_score` upstream).

Pure functions — no I/O, no LLM. Given the same rows, always the same table.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Callable

from fantasy_gm.models import Position

# The offensive positions DvP is meaningful for.
DVP_POSITIONS: tuple[Position, ...] = (Position.QB, Position.RB, Position.WR, Position.TE)


@dataclass(frozen=True)
class DvpCell:
    """One defense's average fantasy points allowed to one position."""
    defense: str
    position: Position
    ppg_allowed: float
    games: int


@dataclass(frozen=True)
class MatchupGrade:
    """A single player-week matchup, graded vs. the league average."""
    defense: str
    position: Position
    ppg_allowed: float          # what this defense allows to this position
    league_avg: float           # league-wide average allowed to this position
    ratio: float                # ppg_allowed / league_avg (>1 = favorable)
    grade: str                  # A/B/C/D/F
    score: float                # 0–100, higher = better matchup for the offense

    @property
    def is_favorable(self) -> bool:
        return self.ratio >= 1.05


def _position_of(raw: str) -> Position | None:
    try:
        return Position(raw)
    except (ValueError, TypeError):
        return None


def compute_dvp(
    stat_rows: list[dict],
    points_fn: Callable[[dict], float] | None = None,
) -> dict[tuple[str, Position], DvpCell]:
    """Build the DvP table: (defense, position) -> DvpCell.

    Each row must carry `opponent_team` (the defense faced), `position`,
    `week`, and a points value (default `fantasy_points_ppr`). Points are
    summed per (defense, position, week) to get points-allowed that week, then
    averaged across weeks.
    """
    pts = points_fn or (lambda r: float(r.get("fantasy_points_ppr", 0.0) or 0.0))
    # (defense, position, week) -> points allowed that week
    weekly: dict[tuple[str, Position, int], float] = defaultdict(float)
    for r in stat_rows:
        defense = r.get("opponent_team")
        pos = _position_of(r.get("position"))
        week = r.get("week")
        if not defense or pos is None or pos not in DVP_POSITIONS or week is None:
            continue
        weekly[(defense, pos, week)] += pts(r)

    grouped: dict[tuple[str, Position], list[float]] = defaultdict(list)
    for (defense, pos, _week), allowed in weekly.items():
        grouped[(defense, pos)].append(allowed)

    table: dict[tuple[str, Position], DvpCell] = {}
    for (defense, pos), vals in grouped.items():
        table[(defense, pos)] = DvpCell(
            defense=defense, position=pos,
            ppg_allowed=round(sum(vals) / len(vals), 2), games=len(vals),
        )
    return table


def league_average(
    table: dict[tuple[str, Position], DvpCell], position: Position
) -> float:
    """League-wide mean fantasy points allowed to a position."""
    cells = [c.ppg_allowed for (_d, p), c in table.items() if p == position]
    return round(sum(cells) / len(cells), 2) if cells else 0.0


def _grade_letter(ratio: float) -> str:
    if ratio >= 1.15:
        return "A"
    if ratio >= 1.05:
        return "B"
    if ratio >= 0.95:
        return "C"
    if ratio >= 0.85:
        return "D"
    return "F"


def matchup_grade(
    table: dict[tuple[str, Position], DvpCell],
    defense: str,
    position: Position,
) -> MatchupGrade | None:
    """Grade a position's matchup against a defense, relative to league average.

    Returns None if the defense/position pair isn't in the table (e.g. no data
    yet this season).
    """
    cell = table.get((defense, position))
    if cell is None:
        return None
    league = league_average(table, position)
    if league <= 0:
        ratio = 1.0
    else:
        ratio = round(cell.ppg_allowed / league, 3)
    # Map ratio → 0–100. A ±30% swing spans the scale, clamped.
    score = round(max(0.0, min(100.0, 50.0 + (ratio - 1.0) * 100.0 / 0.6)), 1)
    return MatchupGrade(
        defense=defense, position=position,
        ppg_allowed=cell.ppg_allowed, league_avg=league,
        ratio=ratio, grade=_grade_letter(ratio), score=score,
    )
