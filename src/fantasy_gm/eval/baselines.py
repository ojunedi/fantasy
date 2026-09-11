"""
Three baselines for the evaluation harness.

Each baseline takes a roster and (optionally) prior-week data and returns
a lineup decision using a fixed, non-LLM strategy. They set the floor the
agent must beat to be worth using.

All baselines are as-of-safe: they only use information available at
decision time. The backtest runner is responsible for enforcing this.
"""
from __future__ import annotations

from fantasy_gm.core.optimizer import optimize_lineup
from fantasy_gm.models import (
    BaselineType,
    LeagueSettings,
    Player,
    PlayerProjection,
    Position,
    Roster,
    RosterPlayer,
)


def baseline_platform_rank(
    roster: Roster,
    projections: list[PlayerProjection],
    settings: LeagueSettings,
) -> list[RosterPlayer]:
    """
    Start whoever the platform's default projections rank highest.

    This mirrors what a casual manager does: accept the platform's
    suggested lineup. Uses the projections source passed in (FantasyPros
    in our case) as a stand-in for platform projections.
    """
    proj_map: dict[str, float] = {p.player_id: p.projected_points for p in projections}
    players = [rp.player for rp in roster.players]
    return optimize_lineup(players, proj_map, settings)


def baseline_last_week_best(
    roster: Roster,
    last_week_scores: dict[str, float],  # platform_id -> actual points scored last week
    settings: LeagueSettings,
) -> list[RosterPlayer]:
    """
    Start whoever scored the most points last week.

    Represents the "hot hand" / recency bias strategy. No projection
    data required — pure backward-looking.
    """
    players = [rp.player for rp in roster.players]
    return optimize_lineup(players, last_week_scores, settings)


def baseline_do_nothing(
    roster: Roster,
) -> list[RosterPlayer]:
    """
    Never change the lineup from the season-opening configuration.

    The weakest possible baseline. If the agent can't beat this, it is
    actively harmful. Implemented by returning the current roster state
    (the incumbents) unchanged.
    """
    return list(roster.players)


def get_baseline_lineup(
    baseline_type: BaselineType,
    roster: Roster,
    settings: LeagueSettings,
    projections: list[PlayerProjection] | None = None,
    last_week_scores: dict[str, float] | None = None,
) -> list[RosterPlayer]:
    """Dispatch to the correct baseline function."""
    if baseline_type == BaselineType.PLATFORM_RANK:
        if projections is None:
            raise ValueError("PLATFORM_RANK baseline requires projections")
        return baseline_platform_rank(roster, projections, settings)
    elif baseline_type == BaselineType.LAST_WEEK_BEST:
        if last_week_scores is None:
            raise ValueError("LAST_WEEK_BEST baseline requires last_week_scores")
        return baseline_last_week_best(roster, last_week_scores, settings)
    elif baseline_type == BaselineType.DO_NOTHING:
        return baseline_do_nothing(roster)
    else:
        raise ValueError(f"Unknown baseline type: {baseline_type}")
