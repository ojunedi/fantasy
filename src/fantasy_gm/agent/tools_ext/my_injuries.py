"""
Injury summary tool: consolidated, structured injury status for all roster players.

No LLM call — reads directly from ESPN roster data + signal bundle.
"""
from __future__ import annotations

from typing import Any

from fantasy_gm.models import PlayerStatus, Position


# Urgency rank: lower number = higher urgency
_URGENCY: dict[PlayerStatus, int] = {
    PlayerStatus.OUT: 0,
    PlayerStatus.IR: 0,
    PlayerStatus.SUSPENDED: 0,
    PlayerStatus.DOUBTFUL: 1,
    PlayerStatus.QUESTIONABLE: 2,
    PlayerStatus.ACTIVE: 3,
    PlayerStatus.UNKNOWN: 3,
}

_CRITICAL_STATUSES = {PlayerStatus.OUT, PlayerStatus.IR, PlayerStatus.SUSPENDED}

# Position display order for the ACTIVE summary line
_POS_ORDER = [
    Position.QB, Position.RB, Position.WR, Position.TE,
    Position.K, Position.DST, Position.FLEX, Position.SUPER_FLEX,
]


def _action_note(status: PlayerStatus) -> str:
    if status in _CRITICAL_STATUSES:
        return "DO NOT START"
    if status == PlayerStatus.DOUBTFUL:
        return "Unlikely to play (25%)"
    if status == PlayerStatus.QUESTIONABLE:
        return "Monitor final report"
    return "Safe to start"


def _effective_status(rp: Any, injuries: dict) -> PlayerStatus:
    """Return the most informative status: signal bundle wins if present."""
    sig = injuries.get(rp.player.platform_id)
    if sig is not None:
        return sig.status
    return rp.player.status


def tool_get_my_injury_summary(ctx: Any) -> str:
    """
    Consolidated, structured injury status for ALL players on my roster.
    No LLM call — reads directly from ESPN roster data + signal bundle.

    Sorted by urgency:
    1. OUT / IR / SUSPENDED (do not start)
    2. DOUBTFUL (very unlikely to play — 25%)
    3. QUESTIONABLE (50/50 — check final reports)
    4. ACTIVE (healthy — shown briefly at bottom)

    For each non-ACTIVE player, shows:
    - Name, position, current slot (starter or bench)
    - ESPN status + injury description from signal bundle (if available)
    - Action note: "DO NOT START", "Unlikely to play (25%)", "Monitor final report"

    Output is plain text, designed to be scanned quickly.
    """
    roster = ctx.roster()
    signals = ctx.signals()
    injuries = signals.injuries  # dict[player_id, InjuryReport]

    players = roster.players

    # Split into non-active (anything worth surfacing) and active
    non_active = [
        rp for rp in players
        if _effective_status(rp, injuries) not in (PlayerStatus.ACTIVE, PlayerStatus.UNKNOWN)
    ]

    if not non_active:
        return "All players ACTIVE — no injury concerns."

    # Sort non-active: by urgency tier first, then starters before bench
    def _sort_key(rp: Any) -> tuple[int, int]:
        urgency = _URGENCY.get(_effective_status(rp, injuries), 3)
        starter_rank = 0 if rp.is_starter else 1
        return (urgency, starter_rank)

    non_active_sorted = sorted(non_active, key=_sort_key)

    starters_at_risk = [rp for rp in non_active_sorted if rp.is_starter]
    bench_concern = [rp for rp in non_active_sorted if not rp.is_starter]

    active_players = [
        rp for rp in players
        if _effective_status(rp, injuries) in (PlayerStatus.ACTIVE, PlayerStatus.UNKNOWN)
    ]

    # ---- build output ---------------------------------------------------

    lines: list[str] = [f"=== My Roster Injury Summary (Week {ctx.week}, {ctx.season}) ==="]

    def _format_player_line(rp: Any, slot_label: str) -> str:
        player = rp.player
        status = _effective_status(rp, injuries)
        sig = injuries.get(player.platform_id)

        injury_detail = ""
        if sig and sig.injury_description:
            injury_detail = f" ({sig.injury_description})"

        note = _action_note(status)
        return (
            f"  * {player.name} ({player.position.value}) [{slot_label}]"
            f" -- {status.value}{injury_detail} | {note}"
        )

    if starters_at_risk:
        lines.append("")
        lines.append("!! STARTERS AT RISK:")
        for rp in starters_at_risk:
            lines.append(_format_player_line(rp, "STARTER"))

    if bench_concern:
        lines.append("")
        lines.append("Bench / low concern:")
        for rp in bench_concern:
            lines.append(_format_player_line(rp, "BENCH"))

    # Active players summary grouped by position
    if active_players:
        lines.append("")
        by_pos: dict[Position, list[str]] = {}
        for rp in active_players:
            pos = rp.player.position
            by_pos.setdefault(pos, []).append(rp.player.name)

        parts: list[str] = []
        seen: set[Position] = set()
        for pos in _POS_ORDER:
            if pos in by_pos:
                parts.append(f"{pos.value}: {', '.join(by_pos[pos])}")
                seen.add(pos)
        # Any positions not in the standard order
        for pos, names in by_pos.items():
            if pos not in seen:
                parts.append(f"{pos.value}: {', '.join(names)}")

        lines.append("All other players ACTIVE:")
        lines.append("  " + " | ".join(parts))

    return "\n".join(lines)
