"""
Injury-interpreter sub-agent (single-shot LLM).

Turns an unstructured injury/practice picture — ESPN status, practice
participation, injury description, recent snap share — into a structured signal:

    {"availability_pct": 0-100, "role_change_flag": bool, "note": str}

`availability_pct` is the model's read on how likely the player is to play a
meaningful role (not a betting number — a directional confidence). The
deterministic tools then discount projections accordingly.

Single model call. Degrades to a neutral result with a note when no LLM/API key
is available, consistent with the signal-availability design.
"""
from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from fantasy_gm.agent.subagents.base import default_llm, parse_json_object, _message_text

_SYSTEM = """\
You interpret NFL injury information for a fantasy manager. Given a player's \
status, practice participation, injury description, and recent snap share, \
output ONLY a JSON object:

{"availability_pct": <int 0-100>, "role_change_flag": <true|false>, "note": "<one sentence>"}

- availability_pct: your read on the chance the player suits up AND plays a \
normal role. OUT ≈ 0. DOUBTFUL ≈ 15. QUESTIONABLE with full practice ≈ 80; \
with DNP ≈ 40. ACTIVE ≈ 95+.
- role_change_flag: true if the injury (theirs or a teammate's) likely shifts \
usage — e.g. a backup inheriting a lead role, or a player returning to limited snaps.
- note: one concise sentence a manager can act on.
Output the JSON and nothing else."""


def interpret_injury(
    player_name: str,
    status: str,
    practice_participation: str | None = None,
    injury_description: str | None = None,
    snap_share_last3: float | None = None,
    llm=None,
) -> dict:
    """Interpret an injury picture into a structured availability signal."""
    llm = llm if llm is not None else default_llm()
    neutral = {"availability_pct": None, "role_change_flag": False,
               "note": "Injury interpreter unavailable (no LLM configured); "
                       "rely on raw ESPN status.", "raw_status": status}
    if llm is None:
        return neutral

    facts = [f"Player: {player_name}", f"ESPN status: {status}"]
    if practice_participation:
        facts.append(f"Practice participation: {practice_participation}")
    if injury_description:
        facts.append(f"Injury: {injury_description}")
    if snap_share_last3 is not None:
        facts.append(f"Snap share last 3 games: {snap_share_last3:.0%}")
    user = "\n".join(facts)

    try:
        resp = llm.invoke([SystemMessage(content=_SYSTEM), HumanMessage(content=user)])
    except Exception as e:
        return {**neutral, "note": f"Injury interpreter error: {e}"}

    parsed = parse_json_object(_message_text(resp))
    if parsed is None:
        return {**neutral, "note": "Injury interpreter returned no parseable JSON."}
    parsed.setdefault("role_change_flag", False)
    parsed.setdefault("note", "")
    parsed["raw_status"] = status
    return parsed
