"""
Backtest runner.

Replays historical weeks using only data that was available at decision time
(as-of-date isolation). Any use of post-hoc information is a bug, not a feature.

As-of-date discipline:
  - Projections fetched as of BEFORE the week's games started.
  - Actual scores fetched AFTER the week completed (for outcome measurement only).
  - Injury reports as of the day before kickoff.

The runner produces a WeeklyScorecard per week comparing:
  - All three baselines
  - The actual historical lineup (ground truth)
  - Hindsight optimal (only used for outcome measurement, never for decisions)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

from fantasy_gm.adapters.base import FantasyPlatform
from fantasy_gm.core.optimizer import optimize_lineup
from fantasy_gm.eval.baselines import get_baseline_lineup
from fantasy_gm.eval.metrics import compute_weekly_scorecard, format_scorecard
from fantasy_gm.models import (
    BaselineType,
    LeagueSettings,
    PlayerProjection,
    Roster,
    WeeklyScorecard,
)

log = logging.getLogger(__name__)

ProjectionFetcher = Callable[[int, int], list[PlayerProjection]]  # (week, season) -> projections
ActualScoreFetcher = Callable[[int, int], dict[str, float]]  # (week, season) -> {player_id: score}


@dataclass
class BacktestResult:
    season: int
    weeks: list[WeeklyScorecard] = field(default_factory=list)

    def summary(self) -> dict:
        if not self.weeks:
            return {}
        avg_regret = sum(w.decision_regret for w in self.weeks) / len(self.weeks)
        avg_bench_pts = sum(w.points_left_on_bench for w in self.weeks) / len(self.weeks)
        baseline_avgs: dict[str, float] = {}
        for bt in BaselineType:
            scores = [w.baseline_scores.get(bt, 0.0) for w in self.weeks]
            baseline_avgs[bt.value] = sum(scores) / len(scores) if scores else 0.0
        avg_actual = sum(w.actual_score for w in self.weeks) / len(self.weeks)
        return {
            "weeks_evaluated": len(self.weeks),
            "avg_actual_score": round(avg_actual, 2),
            "avg_decision_regret": round(avg_regret, 2),
            "avg_points_left_on_bench": round(avg_bench_pts, 2),
            "baseline_avg_scores": {k: round(v, 2) for k, v in baseline_avgs.items()},
        }


class Backtester:
    """
    Replays a season week-by-week against historical data.

    Enforces as-of-date isolation: the decision inputs (projections,
    injury status) must be from BEFORE each week's games. Actual scores
    are only accessed for outcome measurement.
    """

    def __init__(
        self,
        platform: FantasyPlatform,
        team_id: str,
        settings: LeagueSettings,
        projection_fetcher: ProjectionFetcher,
        actual_score_fetcher: ActualScoreFetcher,
    ):
        self.platform = platform
        self.team_id = team_id
        self.settings = settings
        self._fetch_projections = projection_fetcher
        self._fetch_actual_scores = actual_score_fetcher

    def run_week(self, week: int, season: int) -> WeeklyScorecard:
        log.info(f"Backtesting week {week}/{season} for team {self.team_id}")

        # Decision-time data (as-of: before week's games)
        roster: Roster = self.platform.get_roster(self.team_id, week, season)
        projections: list[PlayerProjection] = self._fetch_projections(week, season)

        # Outcome data (as-of: after week completed — only for measurement)
        actual_scores: dict[str, float] = self._fetch_actual_scores(week, season)

        players = [rp.player for rp in roster.players]

        # Actual historical lineup (what the team manager actually started)
        actual_lineup = list(roster.players)

        # Hindsight optimal lineup (uses actual scores — post-hoc, for measurement only)
        optimal_lineup = optimize_lineup(players, actual_scores, self.settings)

        # Three baselines
        last_week_scores: dict[str, float] = {}
        if week > 1:
            last_week_scores = self._fetch_actual_scores(week - 1, season)

        baseline_lineups = {
            BaselineType.PLATFORM_RANK: get_baseline_lineup(
                BaselineType.PLATFORM_RANK, roster, self.settings, projections=projections
            ),
            BaselineType.LAST_WEEK_BEST: get_baseline_lineup(
                BaselineType.LAST_WEEK_BEST, roster, self.settings, last_week_scores=last_week_scores
            ) if week > 1 else get_baseline_lineup(
                BaselineType.DO_NOTHING, roster, self.settings
            ),
            BaselineType.DO_NOTHING: get_baseline_lineup(
                BaselineType.DO_NOTHING, roster, self.settings
            ),
        }

        scorecard = compute_weekly_scorecard(
            week=week,
            season=season,
            actual_lineup=actual_lineup,
            actual_scores=actual_scores,
            optimal_lineup=optimal_lineup,
            baseline_lineups=baseline_lineups,
        )
        log.info(format_scorecard(scorecard))
        return scorecard

    def run_season(self, weeks: list[int], season: int) -> BacktestResult:
        result = BacktestResult(season=season)
        for week in weeks:
            try:
                scorecard = self.run_week(week, season)
                result.weeks.append(scorecard)
            except Exception as e:
                log.error(f"Backtest failed for week {week}: {e}")
        return result
