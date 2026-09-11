"""
Roster legality checker.

Validates a proposed lineup against league settings: correct number of
starters per slot, no player in an ineligible slot, no duplicate players.
Pure functions — no I/O, no LLM.
"""
from __future__ import annotations

from dataclasses import dataclass

from fantasy_gm.models import LeagueSettings, Player, Position, RosterSlot


@dataclass(frozen=True)
class LegalityError:
    message: str


@dataclass
class LegalityResult:
    is_legal: bool
    errors: list[LegalityError]

    @classmethod
    def ok(cls) -> "LegalityResult":
        return cls(is_legal=True, errors=[])

    @classmethod
    def fail(cls, *messages: str) -> "LegalityResult":
        return cls(is_legal=False, errors=[LegalityError(m) for m in messages])


# Slots that can hold FLEX-eligible players (RB/WR/TE)
FLEX_ELIGIBLE: set[Position] = {Position.RB, Position.WR, Position.TE}
SUPER_FLEX_ELIGIBLE: set[Position] = {Position.QB, Position.RB, Position.WR, Position.TE}


def slot_accepts(slot: Position, player_position: Position) -> bool:
    """Return True if a player of player_position can fill slot."""
    if slot == player_position:
        return True
    if slot == Position.FLEX and player_position in FLEX_ELIGIBLE:
        return True
    if slot == Position.SUPER_FLEX and player_position in SUPER_FLEX_ELIGIBLE:
        return True
    if slot == Position.BENCH:
        return True  # any player can sit on bench
    if slot == Position.IR:
        return True  # legality of IR status is checked separately
    return False


def check_lineup_legality(
    lineup: dict[str, Player],   # slot_id -> Player
    settings: LeagueSettings,
) -> LegalityResult:
    """
    Validate that a proposed lineup is legal.

    lineup: maps each slot_id (from LeagueSettings.roster_slots) to the
            Player assigned to that slot.
    """
    errors: list[str] = []
    slot_by_id: dict[str, RosterSlot] = {s.slot_id: s for s in settings.roster_slots}

    # Every slot in settings must be filled
    for slot in settings.roster_slots:
        if slot.slot_id not in lineup:
            errors.append(f"Slot {slot.slot_id} ({slot.position.value}) is empty")

    # No duplicate player IDs
    assigned_ids = [p.platform_id for p in lineup.values()]
    seen: set[str] = set()
    for pid in assigned_ids:
        if pid in seen:
            errors.append(f"Player {pid} assigned to multiple slots")
        seen.add(pid)

    # Each player must be eligible for their assigned slot
    for slot_id, player in lineup.items():
        slot = slot_by_id.get(slot_id)
        if slot is None:
            errors.append(f"Unknown slot ID: {slot_id}")
            continue
        if not slot_accepts(slot.position, player.position):
            errors.append(
                f"{player.name} ({player.position.value}) cannot fill {slot.position.value} slot"
            )

    if errors:
        return LegalityResult.fail(*errors)
    return LegalityResult.ok()


def required_starter_slots(settings: LeagueSettings) -> list[RosterSlot]:
    return [s for s in settings.roster_slots if s.is_starter]


def bench_slots(settings: LeagueSettings) -> list[RosterSlot]:
    return [s for s in settings.roster_slots if not s.is_starter]
