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


def _parse_selection(answer: str, count: int) -> tuple[list[int], list[str]]:
    """Parse '1,3,5-7' into zero-based indices, preserving order, de-duplicated.

    Returns (indices, problems). Out-of-range or non-numeric tokens are reported
    rather than ignored, so a typo cannot silently drop a player.
    """
    indices: list[int] = []
    problems: list[str] = []
    for token in answer.replace(",", " ").split():
        if "-" in token[1:]:
            lo_s, _, hi_s = token.partition("-")
            if lo_s.isdigit() and hi_s.isdigit():
                lo, hi = int(lo_s), int(hi_s)
                if 1 <= lo <= hi <= count:
                    indices.extend(range(lo - 1, hi))
                    continue
            problems.append(f"{token!r} is not a valid range (1-{count})")
        elif token.isdigit():
            value = int(token)
            if 1 <= value <= count:
                indices.append(value - 1)
            else:
                problems.append(f"{value} is out of range (1-{count})")
        else:
            problems.append(f"{token!r} is not a number")

    seen: set[int] = set()
    ordered = [i for i in indices if not (i in seen or seen.add(i))]
    return ordered, problems


def _ask_offerable(ctx) -> list[str]:
    """Show the roster as a numbered list and let the manager pick from it."""
    try:
        players = list(ctx.roster().players)
    except Exception:
        return []
    if not players:
        return []

    # Values and tradeable-depth flags are best-effort: without them the list
    # still works, it is just less informative.
    try:
        vm = ctx.value_map()
        chips = {rp.player.platform_id for rp, _ in ctx.trade_chips(ctx.roster())}
    except Exception:
        vm, chips = {}, set()

    def _value(rp) -> float:
        av = vm.get(rp.player.platform_id)
        return av.value if av else 0.0

    # Tradeable depth first — those are the realistic pieces — then by value.
    players.sort(key=lambda rp: (rp.player.platform_id not in chips, -_value(rp)))

    print("\n  Your roster (* = depth beyond your starting lineup):\n")
    print(f"    {'#':>3}  {'player':22} {'pos':4} {'slot':8} {'value':>7}")
    for i, rp in enumerate(players, 1):
        mark = "*" if rp.player.platform_id in chips else " "
        slot = "starter" if rp.is_starter else "bench"
        val = f"{_value(rp):.0f}" if vm else "-"
        print(f"  {mark} {i:>3}  {rp.player.name:22} {rp.player.position.value:4} "
              f"{slot:8} {val:>7}")

    answer = _prompt(
        "\n  Which are you willing to give up? Numbers (e.g. 1,3 or 1-4), "
        "'*' for all depth, Enter to skip > "
    )
    if not answer:
        return []
    if answer.strip() in ("*", "chips", "depth"):
        picked = [rp for rp in players if rp.player.platform_id in chips]
    else:
        indices, problems = _parse_selection(answer, len(players))
        for problem in problems:
            print(f"    ({problem})")
        picked = [players[i] for i in indices]
    if picked:
        print(f"    offering only: {', '.join(rp.player.name for rp in picked)}")
    return [rp.player.platform_id for rp in picked]


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
    prefs.offerable_ids = _ask_offerable(ctx)

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
