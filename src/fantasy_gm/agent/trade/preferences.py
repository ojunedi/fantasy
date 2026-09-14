"""
Optional manager directives for a trade run.

The trade agent normally infers what to shop for from roster needs and market
value alone. A manager usually has intent the numbers cannot see — "I'd part
with Metcalf but never Worthy", "get me Jonathan Taylor". These preferences
capture that.

Every field is optional: an empty `TradePreferences` reproduces the default
behaviour exactly, so skipping the interview changes nothing.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from fantasy_gm.models import Position


@dataclass
class TradePreferences:
    """What the manager asked for. Empty fields mean "no constraint"."""

    # Positions to acquire. Overrides the computed roster-need scan.
    want_positions: list[Position] = field(default_factory=list)
    # Players I am willing to give up. Empty = any of my tradeable depth.
    offerable_ids: list[str] = field(default_factory=list)
    # Specific players to try to acquire from another team.
    target_ids: list[str] = field(default_factory=list)
    # Free-text steer, passed through to the agent verbatim.
    notes: str = ""

    def is_empty(self) -> bool:
        return not (self.want_positions or self.offerable_ids
                    or self.target_ids or self.notes)

    def violations(self, send_ids: list[str], receive_ids: list[str],
                   names: dict[str, str] | None = None) -> list[str]:
        """Ways a proposed package contradicts what the manager asked for.

        Advisory, not a hard block — the human still approves or rejects, and a
        near-miss that is otherwise good is worth seeing rather than hiding.
        """
        label = (lambda pid: (names or {}).get(pid, pid))
        problems: list[str] = []
        if self.offerable_ids:
            stray = [p for p in send_ids if p not in self.offerable_ids]
            if stray:
                problems.append("sends players you did not offer: "
                                + ", ".join(label(p) for p in stray))
        if self.target_ids and not any(p in self.target_ids for p in receive_ids):
            wanted = ", ".join(label(p) for p in self.target_ids)
            problems.append(f"does not bring back a player you targeted ({wanted})")
        return problems


def resolve_players(query: str, candidates: dict[str, str]) -> tuple[list[str], list[str]]:
    """Map a comma-separated name query to player ids.

    `candidates` is {player_id: display_name}. Matching is case-insensitive
    substring. An ambiguous or unknown term is reported rather than guessed —
    silently picking the wrong player would quietly corrupt the directive.

    Returns (matched_ids, problem_messages).
    """
    matched: list[str] = []
    problems: list[str] = []
    for raw in query.split(","):
        term = raw.strip()
        if not term:
            continue
        hits = [(pid, name) for pid, name in candidates.items()
                if term.lower() in name.lower()]
        if not hits:
            problems.append(f"no player matched {term!r}")
        elif len(hits) > 1:
            exact = [h for h in hits if h[1].lower() == term.lower()]
            if len(exact) == 1:
                matched.append(exact[0][0])
            else:
                names = ", ".join(sorted(n for _, n in hits))
                problems.append(f"{term!r} is ambiguous — matches: {names}")
        else:
            matched.append(hits[0][0])
    return matched, problems


def describe(prefs: TradePreferences, names: dict[str, str]) -> str:
    """Render the directives for the agent prompt. Empty when unconstrained."""
    if prefs.is_empty():
        return ""
    lines = ["## Manager directives — these OVERRIDE your own read of the roster:"]
    if prefs.want_positions:
        lines.append(f"  - Acquire at: {', '.join(p.value for p in prefs.want_positions)}. "
                     f"Do not shop other positions unless nothing there works.")
    if prefs.target_ids:
        who = ", ".join(f"{names.get(p, p)} ({p})" for p in prefs.target_ids)
        lines.append(f"  - Specifically try to acquire: {who}. Build a package whose "
                     f"value matches theirs so the other manager would accept.")
    if prefs.offerable_ids:
        who = ", ".join(f"{names.get(p, p)} ({p})" for p in prefs.offerable_ids)
        lines.append(f"  - ONLY these players may be sent: {who}. Every other player "
                     f"on my roster is off limits — do not include them in any package.")
    if prefs.notes:
        lines.append(f"  - Manager note: {prefs.notes}")
    lines.append("  Respect these while still producing a fair, acceptable trade; if "
                 "they make a fair trade impossible, say so and abstain.")
    return "\n".join(lines)
