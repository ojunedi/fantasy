"""
Deterministic lineup-move planner (no LLM, no I/O).

Given the current ESPN slot of each player and the desired set of starters,
compute the minimal list of slot moves and the exact ESPN transaction body.

This is the pure core of the write path — fully unit tested — so the executors
(API and browser) only have to carry out a validated plan.
"""
from __future__ import annotations

from fantasy_gm.core.optimizer import locks_from_roster, optimize_lineup
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


def locked_conflicts(
    roster_players: list,          # list[RosterPlayer]
    starter_player_ids: list[str],
) -> list[str]:
    """Requested changes that ESPN will refuse because the player has played.

    Returned as human-readable strings for the plan's notes, so a request that
    cannot be honoured says so up front instead of failing with a 409.
    """
    requested = set(starter_player_ids)
    problems: list[str] = []
    for rp in roster_players:
        if not rp.is_locked:
            continue
        pid = rp.player.platform_id
        # State the correction, not just the fault. This text is read by the
        # model via `check_lineup_legality`, and "you are wrong" without "do
        # this instead" invites it to guess again and burn another turn.
        if rp.is_starter and pid not in requested:
            problems.append(
                f"{rp.player.name} ({pid}) has already played and cannot be benched — "
                f"keep him in the starters, in slot {rp.slot.value}.")
        elif not rp.is_starter and pid in requested:
            problems.append(
                f"{rp.player.name} ({pid}) has already played and cannot be started — "
                f"remove him from the starters and leave him on the bench.")
    return problems


def build_target_slots(
    roster_players: list,          # list[RosterPlayer]
    starter_player_ids: list[str],
    settings: LeagueSettings,
) -> dict[str, int]:
    """
    Assign each rostered player a target ESPN slot ID such that exactly the
    requested starters occupy starter slots. Reuses the tested optimizer to find
    a legal slot assignment (proposed starters get weight 1.0, everyone else 0).

    Locked players are pinned to the slot they already occupy, whatever was
    requested: their game has kicked off and ESPN rejects the whole transaction
    if it touches them.
    """
    players: list[Player] = [rp.player for rp in roster_players]
    starter_set = set(starter_player_ids)
    proj = {p.platform_id: (1.0 if p.platform_id in starter_set else 0.0) for p in players}

    locked = locks_from_roster(roster_players)
    lineup = optimize_lineup(players, proj, settings, locked=locked)

    target: dict[str, int] = {}
    for rp in lineup:
        pid = rp.player.platform_id
        # Locked players are left out of the target entirely. `plan_moves` only
        # emits a move for a player it finds here, so omitting them is what
        # guarantees no move is ever generated for someone who has played —
        # stronger than assigning them a slot we believe matches, because any
        # slot-id mismatch would silently reintroduce the move.
        if pid in locked:
            continue
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
