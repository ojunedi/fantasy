"""
Agent tools for lineup decisions.

Each tool wraps a lower layer (adapter, signals, deterministic core). Tools are
read/compute/propose only — none execute an irreversible action.

`LineupToolContext` holds per-run state (roster, signals) so repeated tool calls
are consistent and every input the agent sees is captured for logging.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fantasy_gm.agent.base import ToolContext
from fantasy_gm.core.optimizer import optimize_lineup, projected_score
from fantasy_gm.models import PlayerStatus

# A projection at/below this is an AVAILABILITY FLAG, not a score: ESPN zeroes
# players it expects not to play (ruled out, inactive, bye), so a ~0 must be
# reconciled against injury status rather than read as "will score nothing".
_ZERO_PROJ_THRESHOLD = 0.5
_RULED_OUT_STATUSES = frozenset(
    {PlayerStatus.OUT, PlayerStatus.IR, PlayerStatus.SUSPENDED}
)


# --------------------------------------------------------------------------
# Tool JSON schemas (Anthropic tool-use format)
# --------------------------------------------------------------------------

LINEUP_TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_roster",
        "description": "Get my current roster: every player, their position, "
                       "injury status, and current starter/bench slot.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_matchup",
        "description": "Get this week's matchup: opponent team and projected totals for both sides.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_projections",
        "description": "Get ESPN's projected fantasy points for each rostered player this week, "
                       "already scored under this league's rules. Includes a freshness timestamp.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_signals",
        "description": "Get the full signal bundle: injury/practice status per player, plus which "
                       "signal sources (usage, weather, Vegas) are available and how stale each is. "
                       "Use this to judge whether you have enough information to act.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_league_context",
        "description": "Get season context: current week, my record and standing, whether this is "
                       "the regular season or playoffs, and how many weeks remain.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "optimize_lineup",
        "description": "Run the deterministic optimizer to get the best legal lineup for a given "
                       "projection map. Pass adjusted projections to see how your judgment changes "
                       "the optimal lineup. Omit 'projections' to use the raw ESPN projections. "
                       "Returns the optimal starters, bench, and total projected points.",
        "input_schema": {
            "type": "object",
            "properties": {
                "projections": {
                    "type": "object",
                    "description": "Optional map of player_id -> your adjusted projected points. "
                                   "Any player omitted uses the raw ESPN projection.",
                    "additionalProperties": {"type": "number"},
                }
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "check_lineup_legality",
        "description": "Validate that a proposed set of starters is legal under league roster rules "
                       "(correct slots, no duplicates, position eligibility).",
        "input_schema": {
            "type": "object",
            "properties": {
                "starter_player_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "player_ids you intend to start.",
                }
            },
            "required": ["starter_player_ids"],
            "additionalProperties": False,
        },
    },
    {
        "name": "propose_lineup",
        "description": "TERMINAL. Submit your final lineup recommendation. Ends the task.",
        "input_schema": {
            "type": "object",
            "properties": {
                "starter_player_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "The player_ids to start.",
                },
                "changes_from_current": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "bench_out_player_id": {"type": "string"},
                            "start_in_player_id": {"type": "string"},
                            "reason": {"type": "string",
                                       "description": "Specific signals driving this swap."},
                        },
                        "required": ["start_in_player_id", "reason"],
                        "additionalProperties": False,
                    },
                    "description": "The swaps vs. the current lineup, each with a cited reason. "
                                   "Empty if you endorse the current lineup unchanged.",
                },
                "memo": {"type": "string",
                         "description": "A short GM memo (3-6 sentences) explaining the overall "
                                        "reasoning, citing specific signals."},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1,
                               "description": "Honest confidence 0-1."},
                "what_would_change_this": {"type": "string",
                                           "description": "What new information would change the rec."},
            },
            "required": ["starter_player_ids", "changes_from_current", "memo", "confidence",
                         "what_would_change_this"],
            "additionalProperties": False,
        },
    },
    {
        "name": "abstain",
        "description": "TERMINAL. Declare you don't have enough information to make a confident "
                       "recommendation. Ends the task.",
        "input_schema": {
            "type": "object",
            "properties": {
                "missing_information": {"type": "array", "items": {"type": "string"},
                                        "description": "What specific inputs are missing or too stale."},
                "what_you_would_need": {"type": "string",
                                        "description": "What you'd need to make the call."},
                "memo": {"type": "string", "description": "Short explanation for the human."},
            },
            "required": ["missing_information", "what_you_would_need", "memo"],
            "additionalProperties": False,
        },
    },
]

TERMINAL_TOOLS = {"propose_lineup", "abstain"}


@dataclass
class LineupToolContext(ToolContext):
    """Lineup-decision tool context. Shared state/dispatch live in ToolContext."""

    terminal_tools: frozenset[str] = frozenset(TERMINAL_TOOLS)

    # ---- individual tools ----------------------------------------------

    def _tool_get_roster(self, _: dict) -> str:
        players = self.roster().players
        lines = ["Current roster:"]
        for rp in players:
            tag = "STARTER" if rp.is_starter else "bench"
            # LOCKED is load-bearing for the model: the player's game has been
            # played, so points are final and ESPN refuses to move them.
            lock = ""
            if rp.is_locked:
                scored = ("?" if rp.actual_points is None
                          else f"{rp.actual_points:.1f}")
                lock = f" | LOCKED (played, scored {scored}, CANNOT be moved)"
            lines.append(
                f"  {rp.player.platform_id} | {rp.player.name} ({rp.player.position.value}) "
                f"| slot={rp.slot.value} | {tag} | status={rp.player.status.value} "
                f"| eligible={[p.value for p in rp.player.eligible_positions]}{lock}"
            )
        locked = [rp for rp in players if rp.is_locked]
        if locked:
            lines.append(
                "NOTE: " + ", ".join(rp.player.name for rp in locked)
                + f" {'has' if len(locked) == 1 else 'have'} already played. "
                "Keep them exactly where they are — any lineup that starts or "
                "benches them differently is rejected by ESPN. Do not mention "
                "moving them in your recommendation."
            )
        return "\n".join(lines)

    def _tool_get_matchup(self, _: dict) -> str:
        try:
            m = self.adapter.get_matchup(self.team_id, self.week, self.season)
        except Exception as e:
            return f"Matchup unavailable: {e}"
        return (
            f"Week {m.week} matchup:\n"
            f"  {m.home.team_name}: projected {m.home.projected_score}, actual {m.home.actual_score}\n"
            f"  {m.away.team_name}: projected {m.away.projected_score}, actual {m.away.actual_score}\n"
            f"  complete={m.is_complete}"
        )

    def _tool_get_projections(self, _: dict) -> str:
        sig = self.signals()
        avail = next((a for a in sig.availability if a.name == "projections"), None)
        age = f"{avail.age_seconds:.0f}s" if avail and avail.age_seconds is not None else "n/a"
        lines = [f"ESPN projections (age: {age}, {avail.note}):" if avail else "Projections:"]
        for pid, pj in sorted(sig.projections.items(), key=lambda x: -x[1].projected_points):
            flag = "  <-- ZERO/near-zero (see AVAILABILITY FLAGS)" \
                if pj.projected_points <= _ZERO_PROJ_THRESHOLD else ""
            lines.append(
                f"  {pid} | {pj.player_name} ({pj.position.value}) "
                f"| proj={pj.projected_points}{flag}"
            )
        missing = [rp.player.name for rp in self.roster().players
                   if rp.player.platform_id not in sig.projections]
        if missing:
            lines.append(f"NO PROJECTION for: {', '.join(missing)}")

        flag_lines = self._availability_flag_lines()
        if flag_lines:
            lines.append("")
            lines.extend(flag_lines)
        return "\n".join(lines)

    def _availability_flag_lines(self) -> list[str]:
        """Reconcile each near-zero / missing projection against injury status.

        A ~0 projection is ESPN encoding likely unavailability, not a score. When
        it agrees with a ruled-out status it's benign; when it contradicts an
        ACTIVE/QUESTIONABLE status it's SUSPECT and must be corroborated with
        news before it drives a decision.
        """
        sig = self.signals()
        lines: list[str] = []
        for rp in self.roster().players:
            pid = rp.player.platform_id
            pj = sig.projections.get(pid)
            proj = pj.projected_points if pj is not None else None
            if proj is not None and proj > _ZERO_PROJ_THRESHOLD:
                continue
            missing = proj is None
            # Signal-bundle injury status wins; else the roster's ESPN status.
            inj = sig.injuries.get(pid)
            status = inj.status if inj is not None else rp.player.status
            proj_str = "MISSING" if missing else f"{proj}"
            head = f"  * {rp.player.name} ({rp.player.position.value}) — proj {proj_str}"
            if status in _RULED_OUT_STATUSES:
                lines.append(
                    f"{head}, consistent with status {status.value}. "
                    f"Treat as unavailable — do not start. No news check needed."
                )
            else:
                lines.append(
                    f"{head} but status is {status.value} (CONTRADICTION). "
                    f"SUSPECT: a ~0/blank projection is ESPN flagging likely "
                    f"unavailability (bye, inactive, or missing data), NOT a "
                    f"prediction of 0 points. Do NOT start or bench on this number "
                    f"alone — corroborate with nfl_news/search_web (and check for a "
                    f"bye) before it drives the decision, or abstain if unresolved."
                )
        if lines:
            lines.insert(0, "!! AVAILABILITY FLAGS (near-zero or missing projections):")
        return lines

    def _tool_get_signals(self, _: dict) -> str:
        sig = self.signals()
        lines = ["Signal availability:"]
        for a in sig.availability:
            age = f"{a.age_seconds:.0f}s" if a.age_seconds is not None else "n/a"
            lines.append(f"  {a.name}: available={a.available} | source={a.source} | age={age} | {a.note}")
        lines.append("\nInjury / status per player:")
        for pid, inj in sig.injuries.items():
            if inj.status.value != "ACTIVE":
                lines.append(f"  {pid} | {inj.player_name}: {inj.status.value}")
        lines.append("  (all other rostered players ACTIVE)")
        return "\n".join(lines)

    def _tool_get_league_context(self, _: dict) -> str:
        s = self.settings
        phase = "PLAYOFFS" if self.week >= s.playoff_start_week else "regular season"
        weeks_left_regular = max(0, s.playoff_start_week - self.week)
        return (
            f"Season {s.season}, Week {self.week} ({phase}).\n"
            f"Teams: {s.team_count}. Waiver type: {s.waiver_type.value}.\n"
            f"Playoffs start week {s.playoff_start_week}. "
            f"Regular-season weeks remaining (incl. this one): {weeks_left_regular}.\n"
            f"NOTE: live standings/record and playoff odds are not yet wired in — "
            f"factor that uncertainty into season-context judgments."
        )

    def _tool_optimize_lineup(self, tool_input: dict) -> str:
        players = [rp.player for rp in self.roster().players]
        proj = dict(self._raw_projection_map())
        adjustments = tool_input.get("projections") or {}
        proj.update({k: float(v) for k, v in adjustments.items()})

        # Players whose game has kicked off cannot be moved at all: ESPN rejects
        # the whole transaction (409 TRAN_LINEUP_LOCKED). Optimize around them.
        from fantasy_gm.core.optimizer import locks_from_roster
        locked = locks_from_roster(self.roster().players)

        lineup = optimize_lineup(players, proj, self.settings, locked=locked)
        total = projected_score(lineup, proj)
        lines = [f"Optimal lineup (projected total: {total:.2f}"
                 + (f", with {len(adjustments)} adjusted projections):" if adjustments else "):")]
        for rp in lineup:
            if rp.is_starter:
                lines.append(f"  START {rp.slot.value:5} | {rp.player.name} "
                             f"({rp.player.platform_id}) | proj={proj.get(rp.player.platform_id, 0.0)}")
        lines.append("  bench: " + ", ".join(
            rp.player.name for rp in lineup if not rp.is_starter))
        if locked:
            names = {rp.player.platform_id: rp.player.name
                     for rp in self.roster().players}
            lines.append("  LOCKED (already played — cannot be moved, do not "
                         "propose changing them): "
                         + ", ".join(sorted(names.get(pid, pid) for pid in locked)))
        return "\n".join(lines)

    def _tool_check_lineup_legality(self, tool_input: dict) -> str:
        ids = tool_input.get("starter_player_ids", [])
        players = self._players_by_id()
        starters = [players[i] for i in ids if i in players]
        unknown = [i for i in ids if i not in players]
        if unknown:
            return f"Illegal: unknown player_ids not on roster: {unknown}"

        # Assign starters to slots greedily to test legality
        from fantasy_gm.core.roster import required_starter_slots
        slots = required_starter_slots(self.settings)
        if len(starters) != len(slots):
            return (f"Illegal: {len(starters)} starters given but {len(slots)} starter "
                    f"slots required.")
        # Try to find a valid assignment via the optimizer's assignment logic
        proj = {p.platform_id: 1.0 for p in starters}
        from fantasy_gm.core.optimizer import optimize_lineup as _opt
        result = _opt(starters, proj, self.settings)
        assigned_starters = {rp.player.platform_id for rp in result if rp.is_starter}
        if assigned_starters != set(ids):
            return ("Illegal: these players cannot all fit starter slots simultaneously "
                    "(position constraints).")

        # A lineup that moves a locked player is not merely suboptimal, it is a
        # transaction ESPN will refuse outright.
        from fantasy_gm.execute.lineup_plan import locked_conflicts
        conflicts = locked_conflicts(self.roster().players, list(ids))
        if conflicts:
            # Hand back the exact lineup that fixes it, so a correction costs one
            # turn rather than a guess-and-recheck cycle against a hard step cap.
            fixed = self._lock_respecting_starters(list(ids))
            fix = (f" Correct starter_player_ids: {fixed}." if fixed else "")
            return "Illegal: " + " ".join(conflicts) + fix

        return "Legal: all starters fit valid slots with no duplicates."

    def _lock_respecting_starters(self, ids: list[str]) -> list[str] | None:
        """The requested lineup with locked players forced back into place.

        Returned only if it comes out legal, so the tool never suggests a fix
        that is itself invalid.
        """
        from fantasy_gm.core.optimizer import optimize_lineup

        players = self.roster().players
        locked_in = [rp.player.platform_id for rp in players
                     if rp.is_locked and rp.is_starter]
        locked_out = {rp.player.platform_id for rp in players
                      if rp.is_locked and not rp.is_starter}

        keep = [i for i in ids if i not in locked_out]
        keep += [pid for pid in locked_in if pid not in keep]

        # Weight the kept set and let the tested optimizer find a legal
        # arrangement; anyone it cannot slot is dropped from the proposal.
        weights = {p.player.platform_id: (1.0 if p.player.platform_id in keep else 0.0)
                   for p in players}
        from fantasy_gm.core.optimizer import locks_from_roster
        lineup = optimize_lineup([rp.player for rp in players], weights, self.settings,
                                 locked=locks_from_roster(players))
        result = [rp.player.platform_id for rp in lineup if rp.is_starter]
        from fantasy_gm.execute.lineup_plan import locked_conflicts
        if locked_conflicts(players, result):
            return None
        return result

    def _tool_get_opponent_defense(self, tool_input: dict) -> str:
        from fantasy_gm.agent.tools_ext.opponent_defense import tool_get_opponent_defense
        return tool_get_opponent_defense(self, detail=bool(tool_input.get("detail", False)))

    def _tool_get_opponent_injuries(self, _: dict) -> str:
        from fantasy_gm.agent.tools_ext.opponent_injuries import tool_get_opponent_injuries
        return tool_get_opponent_injuries(self)

    def _tool_get_my_injury_summary(self, _: dict) -> str:
        from fantasy_gm.agent.tools_ext.my_injuries import tool_get_my_injury_summary
        return tool_get_my_injury_summary(self)

    def _tool_propose_lineup(self, tool_input: dict) -> str:
        import json
        # Attach human-readable names for the memo/approval layer
        players = self._players_by_id()
        enriched = dict(tool_input)
        enriched["starter_names"] = [
            players[i].name for i in tool_input.get("starter_player_ids", []) if i in players
        ]
        return json.dumps(enriched)

    def _tool_abstain(self, tool_input: dict) -> str:
        import json
        return json.dumps(tool_input)
