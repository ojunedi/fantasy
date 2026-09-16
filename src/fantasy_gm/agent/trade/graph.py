"""
LangGraph trade agent.

A thin subclass of `agent.base.GraphAgent` (same loop/checkpointer/LLM as the
lineup agent) that emits a `DecisionRecord(decision_type=TRADE)`. The untyped
`recommendation` dict carries a ranked list of trade packages.
"""
from __future__ import annotations

import time

from fantasy_gm.agent.base import GraphAgent, ToolContext
from fantasy_gm.agent.trade.lc_tools import TERMINAL_TOOLS, build_trade_tools
from fantasy_gm.agent.trade.prompts import TRADE_SYSTEM_PROMPT
from fantasy_gm.agent.trade.tools import TradeToolContext
from fantasy_gm.models import DecisionRecord, DecisionType


def _prior_proposals_block(week: int, season: int) -> str:
    """Return a prompt section listing previously proposed+reviewed trades this week.

    Lists each rejected package by its CONCRETE structure (players + counterparty)
    so "propose something different" binds on the trade itself, not just the memo
    wording — the model was re-skinning the same swap otherwise.
    """
    try:
        from fantasy_gm.db.store import DB_PATH, DecisionStore
        if not DB_PATH.exists():
            return ""
        records = [
            r for r in DecisionStore().list_week(week, season)
            if r.decision_type == DecisionType.TRADE and r.human_response is not None
        ]
        if not records:
            return ""
        lines = ["\n## Prior proposals this week — REJECTED, do NOT repeat:\n"]
        for r in records:
            status = r.human_response.value.upper()
            reason = r.override_reason or ""
            trades = r.recommendation.get("trades", []) if isinstance(r.recommendation, dict) else []
            if trades:
                for t in trades:
                    send = ", ".join(t.get("send_names") or t.get("send_player_ids", []))
                    recv = ", ".join(t.get("receive_names") or t.get("receive_player_ids", []))
                    cp = t.get("counterparty_team_id", "?")
                    lines.append(f"  [{status}] SEND {send}  ⇄  RECEIVE {recv}  (with Team {cp})")
                    if reason:
                        lines.append(f"      human reason: {reason}")
            else:
                lines.append(f"  [{status}] {r.memo}")
                if reason:
                    lines.append(f"      human reason: {reason}")
        lines.append(
            "\nA new proposal involving the SAME counterparty AND any of the same core "
            "players above is a REPEAT and is FORBIDDEN. Propose a STRUCTURALLY different "
            "trade — different players and/or a different counterparty. Read the human "
            "reasons as a PATTERN and fix the underlying flaw they point to (e.g. lopsided "
            "value, ignored positional value), not just the wording. If no genuinely "
            "different, acceptable trade exists, `abstain` and say exactly why.\n"
        )
        return "\n".join(lines)
    except Exception:
        return ""


def _evaluated_packages(call_log: list[dict]) -> list[dict]:
    """Packages the run already priced, salvaged from the tool log.

    A truncated run has usually done the expensive part — scoring candidate
    trades — before it died. Surfacing those lets the human see (and act on)
    work that was previously discarded with the record.
    """
    packages = []
    for call in call_log:
        if call.get("tool") != "evaluate_trade":
            continue
        args = call.get("input") or {}
        packages.append({
            "send_player_ids": args.get("send_player_ids", []),
            "receive_player_ids": args.get("receive_player_ids", []),
            "counterparty_team_id": args.get("counterparty_team_id"),
            "evaluation": call.get("output", ""),
        })
    return packages


class TradeGraphAgent(GraphAgent):
    system_prompt = TRADE_SYSTEM_PROMPT
    terminal_tools = frozenset(TERMINAL_TOOLS)
    max_tool_iterations = 10  # roster is pre-fetched; remaining calls are analytical

    def build_tools(self, ctx: ToolContext) -> list:
        return build_trade_tools(ctx, include_prefetch_tools=False)  # type: ignore[arg-type]

    def thread_id(self, ctx: ToolContext) -> str:
        # Fresh thread each invocation so prior checkpoint state doesn't bias proposals.
        return f"trade-{ctx.season}-w{ctx.week}-t{ctx.team_id}-{int(time.time())}"

    def user_prompt(self, ctx: ToolContext) -> str:
        # Pre-fetch the three read tools so the LLM jumps straight to analysis.
        roster_txt, _ = ctx.dispatch("get_my_roster", {})
        all_txt, _ = ctx.dispatch("get_all_rosters", {})
        needs_txt, _ = ctx.dispatch("get_roster_needs", {})

        posture = getattr(ctx, "posture", None)
        posture_line = ""
        if posture == "must_win":
            posture_line = (" Risk posture: MUST-WIN — prioritize win-now upgrades even at "
                            "some future cost.")
        elif posture == "coast":
            posture_line = (" Risk posture: COAST — only make clearly value-positive, low-risk "
                            "trades; don't destabilize a strong roster.")
        elif posture == "normal":
            posture_line = " Risk posture: NORMAL — balanced rest-of-season value."

        prior = _prior_proposals_block(ctx.week, ctx.season)

        directives = ""
        prefs = getattr(ctx, "preferences", None)
        if prefs is not None and not prefs.is_empty():
            from fantasy_gm.agent.trade.preferences import describe
            names = {pid: info["name"] for pid, info in ctx.player_index().items()}
            directives = describe(prefs, names) + "\n\n"

        return (
            f"Find and propose the best trades for team {ctx.team_id}, week {ctx.week}, "
            f"season {ctx.season}.{posture_line}\n\n"
            f"{directives}"
            f"## Context (already fetched — do NOT call get_my_roster / get_all_rosters / get_roster_needs again)\n\n"
            f"{roster_txt}\n\n{all_txt}\n\n{needs_txt}\n"
            f"{prior}"
            f"Use find_trade_targets, then pressure-test candidates with get_trade_value, "
            f"evaluate_trade, get_matchup_analysis, get_schedule_strength, get_usage_trends. "
            f"get_injury_report and get_player_news take a LIST of player ids — pass every "
            f"player you care about in ONE call each; do NOT call them once per player. "
            f"Then call propose_trades or abstain."
        )

    def build_record(self, ctx: TradeToolContext, messages: list) -> DecisionRecord:
        from langchain_core.messages import AIMessage

        terminal_tool, terminal_result = self._extract_terminal(messages)

        inputs_snapshot = {
            "my_team_id": ctx.team_id,
            "team_count": len(ctx.all_rosters()),
            "weeks_remaining": ctx._weeks_remaining(),
            "tool_calls": ctx.call_log,
        }

        if terminal_tool == "propose_trades" and terminal_result:
            recommendation = terminal_result
            memo = terminal_result.get("memo", "")
            trades = terminal_result.get("trades", [])
            confidence = (
                max((float(t.get("confidence", 0.0)) for t in trades), default=0.0)
                if trades else 0.0
            )
        elif terminal_tool == "abstain" and terminal_result:
            recommendation = {"abstained": True, **terminal_result}
            memo = terminal_result.get("memo", "Abstained.")
            confidence = 0.0
        else:
            # The loop ended WITHOUT a terminal tool. This is a truncated run, not
            # an abstention: an abstain is a judgment the model made, whereas this
            # is the run being cut off mid-analysis. Labelling it "ABSTAINED" hid
            # real work — runs died holding a +997-value package they never got to
            # propose. `abstained` stays set so downstream executors still refuse
            # to act, but `truncated` tells the human what actually happened.
            text = "\n".join(
                m.content for m in messages
                if isinstance(m, AIMessage) and isinstance(m.content, str)
            )
            out_of_budget = ctx.llm_calls >= ctx.llm_budget
            recommendation = {
                "abstained": True,
                "truncated": True,
                "reason": ("LLM call budget exhausted before a terminal tool"
                           if out_of_budget else "no terminal tool called"),
                "llm_calls": ctx.llm_calls,
                "llm_budget": ctx.llm_budget,
                "evaluated_packages": _evaluated_packages(ctx.call_log),
                "agent_text": text,
            }
            memo = ("Run was cut off before a recommendation — "
                    + ("the LLM call budget ran out mid-analysis."
                       if out_of_budget else "the agent stopped without proposing."))
            confidence = 0.0

        return DecisionRecord(
            week=ctx.week, season=ctx.season, decision_type=DecisionType.TRADE,
            inputs_snapshot=inputs_snapshot,
            signals_staleness={},
            recommendation=recommendation, memo=memo, confidence=confidence,
        )
