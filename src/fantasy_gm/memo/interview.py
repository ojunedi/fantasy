"""
Optional pre-run interview for the trade agent.

Three questions, all skippable with a blank line. Skipping everything gives an
empty `TradePreferences`, which reproduces today's behaviour exactly — the
interview can only ever narrow the search, never silently change it.

Never blocks a non-interactive run: with no TTY (CI, pipes, `make` in a script)
it returns empty immediately instead of hanging on input.
"""
from __future__ import annotations

import sys

from fantasy_gm.agent.trade.preferences import TradePreferences, resolve_players
from fantasy_gm.models import Position

_ASKABLE = [Position.QB, Position.RB, Position.WR, Position.TE]


def _prompt(text: str) -> str:
    try:
        return input(text).strip()
    except EOFError:
        return ""


def interview_trade_preferences(ctx, interactive: bool | None = None) -> TradePreferences:
    """Ask the manager what they want. Blank answers mean "no constraint"."""
    prefs = TradePreferences()
    if interactive is None:
        interactive = sys.stdin.isatty()
    if not interactive:
        return prefs

    print("\n" + "-" * 70)
    print("  Trade brief — press Enter to skip any question.")
    print("-" * 70)

    # --- 1. Position to acquire -----------------------------------------
    answer = _prompt(
        f"\n  Any position you want to trade FOR? ({'/'.join(p.value for p in _ASKABLE)}) > "
    )
    if answer:
        wanted = []
        for term in answer.replace(",", " ").split():
            match = next((p for p in _ASKABLE if p.value.lower() == term.lower()), None)
            if match:
                wanted.append(match)
            else:
                print(f"    (ignoring {term!r} — not a tradeable position)")
        prefs.want_positions = wanted

    # --- 2. Players I am willing to give up ------------------------------
    try:
        mine = {rp.player.platform_id: rp.player.name for rp in ctx.roster().players}
    except Exception:
        mine = {}
    answer = _prompt("\n  Which of your players are you willing to give up? "
                     "(comma-separated names) > ")
    if answer and mine:
        ids, problems = resolve_players(answer, mine)
        for p in problems:
            print(f"    ({p})")
        if ids:
            print(f"    offering only: {', '.join(mine[i] for i in ids)}")
            prefs.offerable_ids = ids

    # --- 3. A specific player to go get -----------------------------------
    try:
        others = {pid: info["name"] for pid, info in ctx.player_index().items()
                  if info.get("owner_team_id") != ctx.team_id}
    except Exception:
        others = {}
    answer = _prompt("\n  Any specific player you want to acquire? "
                     "(comma-separated names) > ")
    if answer and others:
        ids, problems = resolve_players(answer, others)
        for p in problems:
            print(f"    ({p})")
        if ids:
            print(f"    targeting: {', '.join(others[i] for i in ids)}")
            prefs.target_ids = ids

    # --- 4. Anything else --------------------------------------------------
    note = _prompt("\n  Anything else the GM should know? > ")
    if note:
        prefs.notes = note

    if prefs.is_empty():
        print("\n  No constraints given — running the standard scan.")
    print("-" * 70)
    return prefs
