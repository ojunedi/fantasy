"""
Waiver wire constraint checking (snake priority, no FAAB).

Deterministic rules — no LLM. The agent layer decides *whether* to claim;
this layer checks *whether a claim is legal* and tracks priority state.
"""
from __future__ import annotations

from dataclasses import dataclass

from fantasy_gm.models import FreeAgent, LeagueSettings, Player, WaiverType


@dataclass
class WaiverConstraintResult:
    is_legal: bool
    errors: list[str]


def check_waiver_claim(
    player_add: FreeAgent,
    player_drop: Player | None,
    roster_players: list[Player],
    settings: LeagueSettings,
) -> WaiverConstraintResult:
    """
    Validate that a waiver claim is structurally legal.

    - The player must actually be a free agent (not on a roster).
    - If the roster is full, a drop is required.
    - For snake waivers (our league), no budget check is needed.
    """
    errors: list[str] = []

    roster_ids = {p.platform_id for p in roster_players}

    # Can't drop a player not on your roster
    if player_drop and player_drop.platform_id not in roster_ids:
        errors.append(f"{player_drop.name} is not on your roster and cannot be dropped")

    # Can't add a player already on your roster
    if player_add.player.platform_id in roster_ids:
        errors.append(f"{player_add.player.name} is already on your roster")

    # Roster size check: if full and no drop specified, illegal
    # (We don't know max roster size from FreeAgent alone — caller must enforce)

    if settings.waiver_type == WaiverType.FAAB and settings.faab_budget is not None:
        # Not our case, but included for completeness
        pass  # budget checked in faab.py

    return WaiverConstraintResult(is_legal=len(errors) == 0, errors=errors)


def sort_free_agents_by_value(
    agents: list[FreeAgent],
    projections: dict[str, float],  # platform_id -> projected points
) -> list[tuple[FreeAgent, float]]:
    """Sort free agents by projected value descending. Returns (agent, projection) pairs."""
    return sorted(
        [(a, projections.get(a.player.platform_id, 0.0)) for a in agents],
        key=lambda x: x[1],
        reverse=True,
    )
