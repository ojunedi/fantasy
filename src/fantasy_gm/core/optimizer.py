"""
Deterministic lineup optimizer.

Given a set of projected points per player, finds the legal lineup
that maximizes total projected points. Uses greedy slot-filling with
a backtracking assignment — not a full ILP solver, but correct for
standard fantasy roster structures (<=16 players, <=10 starter slots).

No LLM. No randomness. Given the same inputs, always returns the same lineup.
"""
from __future__ import annotations

from fantasy_gm.core.roster import slot_accepts
from fantasy_gm.models import LeagueSettings, Player, Position, RosterPlayer, RosterSlot


BENCHED = (Position.BENCH, Position.IR)


def locks_from_roster(roster_players: list[RosterPlayer]) -> dict[str, Position]:
    """player_id -> the slot they are locked into, for players who have played.

    Once an NFL game kicks off ESPN refuses any lineup change involving that
    player, so a "better" lineup that moves them is not a lineup at all — it is
    a write that will be rejected with 409 TRAN_LINEUP_LOCKED.
    """
    return {
        rp.player.platform_id: rp.slot
        for rp in roster_players
        if rp.is_locked
    }


def optimize_lineup(
    players: list[Player],
    projections: dict[str, float],  # platform_id -> projected points
    settings: LeagueSettings,
    locked: dict[str, Position] | None = None,
) -> list[RosterPlayer]:
    """
    Return the optimal legal lineup as a list of RosterPlayer.

    Players not in projections are assumed to project 0 points.
    Players not assigned to a starter slot are placed on bench.

    `locked` maps player_id -> the slot that player is already locked into
    (see `locks_from_roster`). A locked starter keeps their slot and a locked
    bench player stays benched: their game has kicked off, so the optimizer
    must treat them as immovable furniture and optimize around them rather
    than proposing a change ESPN will refuse.

    Uses a greedy-with-exhaustion approach: fills the most constrained
    slots first (QB, K, DST before FLEX) to maximize correct assignment.
    """
    locked = locked or {}
    starter_slots = [s for s in settings.roster_slots if s.is_starter]
    bench_slots = [s for s in settings.roster_slots if not s.is_starter]

    by_id = {p.platform_id: p for p in players}

    # A locked bench player can never be promoted, so they are not a candidate
    # for any starter slot.
    locked_out = {pid for pid, slot in locked.items()
                  if slot in BENCHED and pid in by_id}

    # A locked starter is pinned to a starter slot of the slot they occupy.
    pinned: dict[int, Player] = {}
    for pid, slot_pos in locked.items():
        if slot_pos in BENCHED or pid not in by_id:
            continue
        for i, slot in enumerate(starter_slots):
            if i not in pinned and slot.position == slot_pos:
                pinned[i] = by_id[pid]
                break

    # Sort players by projection descending
    ranked = sorted(players, key=lambda p: projections.get(p.platform_id, 0.0), reverse=True)
    candidates = [p for p in ranked if p.platform_id not in locked_out]

    best_score, best_assignment = _assign(starter_slots, candidates, projections,
                                          pinned=pinned)

    if best_assignment is None:
        # Fallback: return all players on bench (should not happen with valid roster)
        result = []
        for i, player in enumerate(players):
            slot = bench_slots[i] if i < len(bench_slots) else bench_slots[-1]
            result.append(RosterPlayer(player=player, slot=slot.position, is_starter=False))
        return result

    assigned_ids = {p.platform_id for p in best_assignment.values()}
    result: list[RosterPlayer] = []

    # best_assignment keys are slot indices into starter_slots
    for slot_idx, player in best_assignment.items():
        slot = starter_slots[slot_idx]
        result.append(RosterPlayer(player=player, slot=slot.position, is_starter=True))

    bench_iter = iter(bench_slots)
    for player in ranked:
        if player.platform_id not in assigned_ids:
            try:
                slot = next(bench_iter)
            except StopIteration:
                slot = RosterSlot(slot_id="be_overflow", position=Position.BENCH, is_starter=False)
            result.append(RosterPlayer(player=player, slot=slot.position, is_starter=False))

    return result


def _assign(
    slots: list[RosterSlot],
    players: list[Player],
    projections: dict[str, float],
    pinned: dict[int, Player] | None = None,
) -> tuple[float, dict[int, Player] | None]:
    """
    Backtracking assignment: fills slots left to right, trying players
    in projection order. Returns (best_score, {slot_index: Player}).

    `pinned` pre-fills slots that are not up for negotiation (locked players).
    Those indices are removed from the search and their occupants are never
    offered as candidates elsewhere.

    Slots are sorted most-constrained first to prune the search space.
    Uses slot index as key (RosterSlot is a Pydantic model, not hashable).
    """
    pinned = dict(pinned or {})
    pinned_ids = {p.platform_id for p in pinned.values()}

    def constraint_count(slot: RosterSlot) -> int:
        return sum(1 for p in players if slot_accepts(slot.position, p.position))

    # Sort indices by constraint count so we fill the tightest slots first
    ordered_indices = sorted((i for i in range(len(slots)) if i not in pinned),
                             key=lambda i: constraint_count(slots[i]))

    best: list[tuple[float, dict[int, Player]]] = [(float("-inf"), {})]

    def backtrack(step: int, used_ids: set[str], current: dict[int, Player]) -> None:
        if step == len(ordered_indices):
            score = sum(projections.get(p.platform_id, 0.0) for p in current.values())
            if score > best[0][0]:
                best[0] = (score, dict(current))
            return
        slot_idx = ordered_indices[step]
        slot = slots[slot_idx]
        candidates = [
            p for p in players
            if p.platform_id not in used_ids and p.platform_id not in pinned_ids
            and slot_accepts(slot.position, p.position)
        ]
        if not candidates:
            return  # can't fill this slot — prune branch
        for player in candidates:
            current[slot_idx] = player
            used_ids.add(player.platform_id)
            backtrack(step + 1, used_ids, current)
            del current[slot_idx]
            used_ids.remove(player.platform_id)

    backtrack(0, set(pinned_ids), dict(pinned))
    score, assignment = best[0]
    if not assignment:
        return float("-inf"), None
    return score, assignment


def live_score(lineup: list[RosterPlayer], projections: dict[str, float]) -> float:
    """Starter total using banked points where they exist, projections elsewhere.

    Mid-week, a played starter's projection is no longer the best estimate of
    their contribution — their actual score is the fact. Mixing the two is what
    makes an in-progress total mean anything.
    """
    total = 0.0
    for rp in lineup:
        if not rp.is_starter:
            continue
        if rp.actual_points is not None:
            total += rp.actual_points
        else:
            total += projections.get(rp.player.platform_id, 0.0)
    return total


def projected_score(lineup: list[RosterPlayer], projections: dict[str, float]) -> float:
    """Sum projected points for all starters in a lineup."""
    return sum(
        projections.get(rp.player.platform_id, 0.0)
        for rp in lineup
        if rp.is_starter
    )
