"""
Deterministic lineup-move planner (no LLM, no I/O).

Given the current ESPN slot of each player and the desired set of starters,
compute the minimal list of slot moves and the exact ESPN transaction body.

This is the pure core of the write path — fully unit tested — so the executors
(API and browser) only have to carry out a validated plan.
"""
from __future__ import annotations

from fantasy_gm.core.optimizer import optimize_lineup
from fantasy_gm.execute.base import LineupMove
from fantasy_gm.models import LeagueSettings, Player, Position

# Position -> ESPN starter lineup slot ID
POSITION_TO_ESPN_SLOT: dict[Position, int] = {
    Position.QB: 0,
    Position.RB: 2,
    Position.WR: 4,
    Position.TE: 6,
    Position.DST: 16,
    Position.K: 17,
    Position.FLEX: 23,
    Position.SUPER_FLEX: 24,
}
BENCH_SLOT = 20

ESPN_SLOT_NAMES: dict[int, str] = {
    0: "QB", 2: "RB", 4: "WR", 6: "TE", 16: "D/ST", 17: "K",
    20: "BENCH", 21: "IR", 23: "FLEX", 24: "SUPERFLEX",
}


def slot_name(slot_id: int) -> str:
    return ESPN_SLOT_NAMES.get(slot_id, f"slot{slot_id}")


def build_target_slots(
    roster_players: list,          # list[RosterPlayer]
    starter_player_ids: list[str],
    settings: LeagueSettings,
) -> dict[str, int]:
    """
    Assign each rostered player a target ESPN slot ID such that exactly the
    requested starters occupy starter slots. Reuses the tested optimizer to find
    a legal slot assignment (proposed starters get weight 1.0, everyone else 0).
    """
    players: list[Player] = [rp.player for rp in roster_players]
    starter_set = set(starter_player_ids)
    proj = {p.platform_id: (1.0 if p.platform_id in starter_set else 0.0) for p in players}

    lineup = optimize_lineup(players, proj, settings)

    target: dict[str, int] = {}
    for rp in lineup:
        pid = rp.player.platform_id
        if rp.is_starter and pid in starter_set:
            target[pid] = POSITION_TO_ESPN_SLOT.get(rp.slot, BENCH_SLOT)
        else:
            target[pid] = BENCH_SLOT
    return target


def plan_moves(
    current_slots: dict[str, int],       # player_id -> current ESPN slot ID
    target_slots: dict[str, int],        # player_id -> desired ESPN slot ID
    names: dict[str, str],               # player_id -> name (for readability)
) -> list[LineupMove]:
    """Emit a move for every player whose slot changes."""
    moves: list[LineupMove] = []
    for pid, tslot in target_slots.items():
        cslot = current_slots.get(pid)
        if cslot is None or cslot == tslot:
            continue
        moves.append(LineupMove(
            player_id=pid,
            player_name=names.get(pid, pid),
            from_slot=cslot,
            to_slot=tslot,
        ))
    return moves


def build_espn_transaction(
    team_id: str, week: int, season: int, moves: list[LineupMove], swid: str,
) -> dict:
    """Build the ESPN 'ROSTER' transaction body for a set of lineup moves."""
    return {
        "isLeagueManager": False,
        "teamId": int(team_id),
        "type": "ROSTER",
        "memberId": swid,
        "scoringPeriodId": week,
        "executionType": "EXECUTE",
        "items": [
            {
                "playerId": int(m.player_id),
                "type": "LINEUP",
                "fromLineupSlotId": m.from_slot,
                "toLineupSlotId": m.to_slot,
            }
            for m in moves
        ],
    }
