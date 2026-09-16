"""
Injury-interpreter sub-agent (single-shot LLM).

Turns an unstructured injury/practice picture — ESPN status, practice
participation, injury description, recent snap share — into a structured signal
per player:

    {"availability_pct": 0-100, "role_change_flag": bool, "note": str}

`availability_pct` is the model's read on how likely the player is to play a
meaningful role (not a betting number — a directional confidence). The
deterministic tools then discount projections accordingly.

`interpret_injuries` is the primary entry point and handles MANY players in one
model call. Beyond the cost saving, a shared call lets the model connect
teammates: one back being OUT is exactly what flips the other's role_change_flag,
which independent single-player calls cannot see.

Degrades to neutral results with a note when no LLM/API key is available,
consistent with the signal-availability design.
"""
from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from fantasy_gm.agent.subagents.base import default_llm, parse_json_object, _message_text

# Players per model call — see the note in `subagents/news.py`.
_BATCH_SIZE = 8

_SYSTEM = """\
You interpret NFL injury information for a fantasy manager. Given several \
players' status, practice participation, injury description, and recent snap \
share, output ONLY a JSON object keyed by the EXACT player names you were given:

{"players": {"<player name>": {"availability_pct": <int 0-100>,
                               "role_change_flag": <true|false>,
                               "note": "<one sentence>"}}}

- Include an entry for EVERY player listed.
- availability_pct: your read on the chance the player suits up AND plays a \
normal role. OUT ≈ 0. DOUBTFUL ≈ 15. QUESTIONABLE with full practice ≈ 80; \
with DNP ≈ 40. ACTIVE ≈ 95+.
- role_change_flag: true if the injury (theirs or a teammate's) likely shifts \
usage — e.g. a backup inheriting a lead role, or a player returning to limited \
snaps. Players listed together may be teammates: if one being out promotes \
another listed player, flag that player too.
- note: one concise sentence a manager can act on.
Output the JSON and nothing else."""

_NEUTRAL_NOTE = ("Injury interpreter unavailable (no LLM configured); "
                 "rely on raw ESPN status.")


def _neutral(status: str, note: str = _NEUTRAL_NOTE) -> dict:
    return {"availability_pct": None, "role_change_flag": False,
            "note": note, "raw_status": status}


def _normalize(entry: object, status: str, fallback_note: str) -> dict:
    """Coerce one player's parsed entry into the documented shape."""
    if not isinstance(entry, dict):
        return _neutral(status, fallback_note)
    return {
        "availability_pct": entry.get("availability_pct"),
        "role_change_flag": bool(entry.get("role_change_flag", False)),
        "note": entry.get("note") or "",
        "raw_status": status,
    }


def _facts_for(player: dict) -> str:
    """Render one player's injury picture, omitting fields we don't have."""
    lines = [f"- Player: {player.get('player_name', '?')}",
             f"  ESPN status: {player.get('status', 'UNKNOWN')}"]
    if player.get("practice_participation"):
        lines.append(f"  Practice participation: {player['practice_participation']}")
    if player.get("injury_description"):
        lines.append(f"  Injury: {player['injury_description']}")
    snaps = player.get("snap_share_last3")
    if snaps is not None:
        lines.append(f"  Snap share last 3 games: {snaps:.0%}")
    return "\n".join(lines)


def interpret_injuries(players: list[dict], llm=None) -> dict[str, dict]:
    """Interpret many players' injury pictures in one model call per chunk.

    Each entry in `players` accepts the same fields as `interpret_injury`:
    `player_name`, `status`, and the optional `practice_participation`,
    `injury_description`, `snap_share_last3`.

    Returns a dict keyed by player name. Players the model omits degrade to a
    neutral entry individually rather than failing the whole batch.
    """
    seen: dict[str, dict] = {}
    for p in players:
        name = (p.get("player_name") or "").strip()
        if name and name not in seen:
            seen[name] = p
    if not seen:
        return {}

    llm = llm if llm is not None else default_llm()
    if llm is None:
        return {name: _neutral(p.get("status", "UNKNOWN")) for name, p in seen.items()}

    names = list(seen)
    out: dict[str, dict] = {}
    for start in range(0, len(names), _BATCH_SIZE):
        chunk = [seen[n] for n in names[start:start + _BATCH_SIZE]]
        out.update(_interpret_chunk(chunk, llm))
    return out


def _interpret_chunk(players: list[dict], llm) -> dict[str, dict]:
    statuses = {p["player_name"].strip(): p.get("status", "UNKNOWN") for p in players}
    user = "\n".join(_facts_for(p) for p in players)
    try:
        resp = llm.invoke([SystemMessage(content=_SYSTEM), HumanMessage(content=user)])
    except Exception as e:
        note = f"Injury interpreter error: {e}"
        return {name: _neutral(st, note) for name, st in statuses.items()}

    parsed = parse_json_object(_message_text(resp))
    if not isinstance(parsed, dict):
        note = "Injury interpreter returned no parseable JSON."
        return {name: _neutral(st, note) for name, st in statuses.items()}

    entries = parsed.get("players")
    if not isinstance(entries, dict):
        # A single-player response often comes back as the bare entry itself
        # rather than a name-keyed map; accept that when it is unambiguous.
        if len(players) == 1 and ("availability_pct" in parsed or "note" in parsed):
            name = players[0]["player_name"].strip()
            return {name: _normalize(parsed, statuses[name], "")}
        # Otherwise tolerate the mapping returned without the wrapper key.
        entries = parsed
    # Match case-insensitively so a re-capitalized key still lands.
    by_lower = {str(k).strip().lower(): v for k, v in entries.items()}
    return {
        name: _normalize(by_lower.get(name.lower()), st,
                         "No entry returned for this player.")
        for name, st in statuses.items()
    }


def interpret_injury(
    player_name: str,
    status: str,
    practice_participation: str | None = None,
    injury_description: str | None = None,
    snap_share_last3: float | None = None,
    llm=None,
) -> dict:
    """Single-player convenience wrapper over `interpret_injuries`."""
    result = interpret_injuries([{
        "player_name": player_name,
        "status": status,
        "practice_participation": practice_participation,
        "injury_description": injury_description,
        "snap_share_last3": snap_share_last3,
    }], llm=llm)
    return result.get(player_name, _neutral(status))
