"""
LangGraph lineup agent.

Now a thin subclass of `agent.base.GraphAgent`: the StateGraph loop, terminal
routing, LLM build, and SqliteSaver checkpointing all live in the shared base.
This module supplies only the lineup-specific parts — the system prompt, tool
set, thread id, and the DecisionRecord builder.

Design notes:
  - The model is Gemini (`gemini-2.5-flash`) via `langchain-google-genai`
    ChatGoogleGenerativeAI; the build lives in `base.GraphAgent._build_llm`.
  - Nothing here executes an irreversible action; terminal tools are propose-only.
"""
from __future__ import annotations

import time

from fantasy_gm.agent.base import GraphAgent, ToolContext
from fantasy_gm.agent.lc_tools import TERMINAL_TOOLS, build_lineup_tools
from fantasy_gm.agent.prompts import LINEUP_SYSTEM_PROMPT
from fantasy_gm.agent.tools import LineupToolContext
from fantasy_gm.models import DecisionRecord, DecisionType


def _posture_line(ctx: ToolContext) -> str:
    posture = getattr(ctx, "posture", None)
    if not posture:
        return ""
    guidance = {
        "must_win": " Risk posture: MUST-WIN — favor ceiling/upside; a loss is costly.",
        "coast": " Risk posture: COAST — favor floor/safety; protect health and position.",
        "normal": " Risk posture: NORMAL — balance floor and ceiling.",
    }
    return guidance.get(posture, f" Risk posture: {posture}.")


class LineupGraphAgent(GraphAgent):
    system_prompt = LINEUP_SYSTEM_PROMPT
    terminal_tools = frozenset(TERMINAL_TOOLS)
    max_tool_iterations = 6  # pre-fetch removes the read round-trips; 6 is plenty

    def build_tools(self, ctx: ToolContext) -> list:
        # Prefetch tools are stripped — their output is already in the user prompt.
        return build_lineup_tools(ctx, include_prefetch_tools=False)  # type: ignore[arg-type]

    def thread_id(self, ctx: ToolContext) -> str:
        # Fresh thread each invocation. A stable id makes LangGraph resume the
        # previous run's checkpoint, so re-running a week appended to the old
        # message history instead of starting clean — the prompt grew every run
        # and stale tool output leaked into the new decision.
        return f"lineup-{ctx.season}-w{ctx.week}-t{ctx.team_id}-{int(time.time())}"

    def user_prompt(self, ctx: ToolContext) -> str:
        # Pre-fetch the five read tools deterministically so the LLM skips those
        # round-trips entirely and goes straight to optimize → propose.
        sections = []
        for name in ("get_roster", "get_matchup", "get_projections",
                     "get_signals", "get_league_context"):
            try:
                text, _ = ctx.dispatch(name, {})
            except Exception as e:
                text = f"[{name} unavailable: {e}]"
            sections.append(text)
        data_block = "\n\n".join(sections)
        posture = _posture_line(ctx)
        return (
            f"Recommend the starting lineup for team {ctx.team_id}, week {ctx.week}, "
            f"season {ctx.season}.{posture}\n\n"
            f"## Context (already fetched — do NOT call the read tools again)\n\n"
            f"{data_block}\n\n"
            f"Use get_my_injury_summary to identify any players who cannot start. "
            f"Use get_opponent_defense to spot favorable/tough matchups. "
            f"Use get_opponent_injuries if a key opponent defender is missing. "
            f"Then optimize_lineup (with adjusted projections if warranted). "
            f"Use nfl_news or search_web ONLY for genuinely close calls not answered above. "
            f"Call propose_lineup or abstain."
        )

    def build_record(self, ctx: LineupToolContext, messages: list) -> DecisionRecord:
        from langchain_core.messages import AIMessage

        terminal_tool, terminal_result = self._extract_terminal(messages)
        signals = ctx.signals()

        inputs_snapshot = {
            "roster": [
                {"id": rp.player.platform_id, "name": rp.player.name,
                 "position": rp.player.position.value, "slot": rp.slot.value,
                 "is_starter": rp.is_starter, "status": rp.player.status.value}
                for rp in ctx.roster().players
            ],
            "projections": {pid: pj.projected_points for pid, pj in signals.projections.items()},
            "signal_availability": [
                {"name": a.name, "available": a.available, "source": a.source,
                 "age_seconds": a.age_seconds, "note": a.note}
                for a in signals.availability
            ],
            "tool_calls": ctx.call_log,
        }

        if terminal_tool == "propose_lineup" and terminal_result:
            recommendation = terminal_result
            memo = terminal_result.get("memo", "")
            confidence = float(terminal_result.get("confidence", 0.0))
        elif terminal_tool == "abstain" and terminal_result:
            recommendation = {"abstained": True, **terminal_result}
            memo = terminal_result.get("memo", "Abstained.")
            confidence = 0.0
        else:
            text = "\n".join(
                m.content for m in messages
                if isinstance(m, AIMessage) and isinstance(m.content, str)
            )
            # Truncated, not abstained — see the note in trade/graph.py.
            out_of_budget = ctx.llm_calls >= ctx.llm_budget
            recommendation = {
                "abstained": True,
                "truncated": True,
                "reason": ("LLM call budget exhausted before a terminal tool"
                           if out_of_budget else "no terminal tool called"),
                "llm_calls": ctx.llm_calls,
                "llm_budget": ctx.llm_budget,
                "agent_text": text,
            }
            memo = ("Run was cut off before a recommendation — "
                    + ("the LLM call budget ran out mid-analysis."
                       if out_of_budget else "the agent stopped without proposing."))
            confidence = 0.0

        return DecisionRecord(
            week=ctx.week, season=ctx.season, decision_type=DecisionType.LINEUP,
            inputs_snapshot=inputs_snapshot,
            signals_staleness=signals.staleness_map(),
            recommendation=recommendation, memo=memo, confidence=confidence,
        )
