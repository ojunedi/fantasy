"""
Evaluation metrics.

All metrics are pure functions: (actual, optimal, baselines) -> numbers.
No I/O. The backtest runner collects the inputs; this module computes the scores.
"""
from __future__ import annotations

from fantasy_gm.models import BaselineType, RosterPlayer, WeeklyScorecard


def points_left_on_bench(
    actual_lineup: list[RosterPlayer],
    actual_scores: dict[str, float],  # platform_id -> actual points
) -> float:
    """Total points scored by bench players who outscored a starter at their position."""
    bench = [rp for rp in actual_lineup if not rp.is_starter]
    starters = [rp for rp in actual_lineup if rp.is_starter]

    # For each bench player, check if they outscored any same-slot-eligible starter
    left_behind = 0.0
    for bench_player in bench:
        bench_score = actual_scores.get(bench_player.player.platform_id, 0.0)
        worst_starter_score = min(
            (actual_scores.get(s.player.platform_id, 0.0) for s in starters if s.slot == bench_player.slot),
            default=None,
        )
        if worst_starter_score is not None and bench_score > worst_starter_score:
            left_behind += bench_score - worst_starter_score

    return round(left_behind, 2)


def decision_regret(
    actual_score: float,
    optimal_score: float,
) -> float:
    """How many points were left on the table vs. the hindsight-optimal lineup."""
    return round(max(0.0, optimal_score - actual_score), 2)


def compute_weekly_scorecard(
    week: int,
    season: int,
    actual_lineup: list[RosterPlayer],
    actual_scores: dict[str, float],
    optimal_lineup: list[RosterPlayer],
    baseline_lineups: dict[BaselineType, list[RosterPlayer]],
    agent_projected_score: float | None = None,
    agent_agreed_with_human: bool | None = None,
) -> WeeklyScorecard:
    actual_score = sum(
        actual_scores.get(rp.player.platform_id, 0.0)
        for rp in actual_lineup if rp.is_starter
    )
    optimal_score = sum(
        actual_scores.get(rp.player.platform_id, 0.0)
        for rp in optimal_lineup if rp.is_starter
    )
    baseline_scores = {
        bt: sum(actual_scores.get(rp.player.platform_id, 0.0) for rp in lineup if rp.is_starter)
        for bt, lineup in baseline_lineups.items()
    }

    return WeeklyScorecard(
        week=week,
        season=season,
        actual_score=round(actual_score, 2),
        optimal_score=round(optimal_score, 2),
        agent_projected_score=agent_projected_score,
        baseline_scores=baseline_scores,
        points_left_on_bench=points_left_on_bench(actual_lineup, actual_scores),
        decision_regret=decision_regret(actual_score, optimal_score),
        agent_agreement_with_human=agent_agreed_with_human,
    )


def format_scorecard(scorecard: WeeklyScorecard) -> str:
    lines = [
        f"=== Week {scorecard.week} Scorecard ===",
        f"Actual score:   {scorecard.actual_score:.2f}",
        f"Optimal score:  {scorecard.optimal_score:.2f}",
        f"Decision regret:{scorecard.decision_regret:.2f}",
        f"Points on bench:{scorecard.points_left_on_bench:.2f}",
    ]
    if scorecard.agent_projected_score is not None:
        lines.append(f"Agent projected:{scorecard.agent_projected_score:.2f}")
    lines.append("")
    lines.append("Baselines:")
    for bt, score in scorecard.baseline_scores.items():
        delta = scorecard.actual_score - score
        sign = "+" if delta >= 0 else ""
        lines.append(f"  {bt.value:<20} {score:.2f}  ({sign}{delta:.2f} vs actual)")
    return "\n".join(lines)
