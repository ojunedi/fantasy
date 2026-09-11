"""
Strength-of-schedule from the NFL schedule + the DvP table.

For a player (team + position), grades the remaining slate — and, critically,
the fantasy-playoff window (NFL weeks 15–17) — by how favorable each opponent's
defense is to that position. Built on `core/matchup.py`'s DvP ratios.

Higher scores = an easier schedule (opponents that bleed points to the position).

Pure functions — no I/O.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from fantasy_gm.core.matchup import DvpCell, league_average, matchup_grade
from fantasy_gm.models import Position

# The fantasy-playoff window most ESPN leagues use (14-week regular season).
PLAYOFF_WEEKS: tuple[int, ...] = (15, 16, 17)


@dataclass(frozen=True)
class WeekMatchup:
    week: int
    opponent: str
    ratio: float          # opponent DvP ratio for the position (>1 = favorable)
    grade: str            # A/B/C/D/F, or "?" if no DvP data for the opponent


@dataclass(frozen=True)
class ScheduleStrength:
    team: str
    position: Position
    weeks: list[WeekMatchup] = field(default_factory=list)

    @property
    def graded_weeks(self) -> list[WeekMatchup]:
        return [w for w in self.weeks if w.grade != "?"]

    @property
    def avg_ratio(self) -> float:
        graded = self.graded_weeks
        if not graded:
            return 1.0
        return round(sum(w.ratio for w in graded) / len(graded), 3)

    @property
    def score(self) -> float:
        """0–100, higher = easier schedule. Same scale as MatchupGrade.score."""
        return round(max(0.0, min(100.0, 50.0 + (self.avg_ratio - 1.0) * 100.0 / 0.6)), 1)

    @property
    def grade(self) -> str:
        r = self.avg_ratio
        if r >= 1.10:
            return "A"
        if r >= 1.03:
            return "B"
        if r >= 0.97:
            return "C"
        if r >= 0.90:
            return "D"
        return "F"


def team_schedule(schedule_rows: list[dict], team: str) -> dict[int, str]:
    """Map week -> opponent abbreviation for a team (NFL regular-season weeks)."""
    out: dict[int, str] = {}
    for r in schedule_rows:
        home, away, week = r.get("home_team"), r.get("away_team"), r.get("week")
        if week is None:
            continue
        if home == team:
            out[week] = away
        elif away == team:
            out[week] = home
    return out


def strength_of_schedule(
    schedule_rows: list[dict],
    dvp_table: dict[tuple[str, Position], DvpCell],
    team: str,
    position: Position,
    weeks: list[int] | tuple[int, ...],
) -> ScheduleStrength:
    """Grade a team/position's schedule over the given weeks using DvP ratios."""
    sched = team_schedule(schedule_rows, team)
    league = league_average(dvp_table, position)
    week_matchups: list[WeekMatchup] = []
    for wk in sorted(weeks):
        opp = sched.get(wk)
        if opp is None:  # bye week or no game scheduled
            continue
        grade = matchup_grade(dvp_table, opp, position)
        if grade is None:
            week_matchups.append(WeekMatchup(week=wk, opponent=opp, ratio=1.0, grade="?"))
        else:
            week_matchups.append(WeekMatchup(
                week=wk, opponent=opp, ratio=grade.ratio, grade=grade.grade))
    _ = league  # league avg is embedded in each ratio; kept for clarity/debug
    return ScheduleStrength(team=team, position=position, weeks=week_matchups)


def rest_of_season_sos(
    schedule_rows: list[dict],
    dvp_table: dict[tuple[str, Position], DvpCell],
    team: str,
    position: Position,
    from_week: int,
) -> ScheduleStrength:
    """SoS across all remaining NFL weeks (from_week through the last scheduled)."""
    all_weeks = {r.get("week") for r in schedule_rows if r.get("week") is not None}
    weeks = [w for w in all_weeks if w >= from_week]
    return strength_of_schedule(schedule_rows, dvp_table, team, position, weeks)


def playoff_sos(
    schedule_rows: list[dict],
    dvp_table: dict[tuple[str, Position], DvpCell],
    team: str,
    position: Position,
    playoff_weeks: tuple[int, ...] = PLAYOFF_WEEKS,
) -> ScheduleStrength:
    """SoS across the fantasy-playoff window (default NFL weeks 15–17)."""
    return strength_of_schedule(schedule_rows, dvp_table, team, position, playoff_weeks)
