"""
LangChain tool wrappers for the Trade agent.

Thin StructuredTools over `TradeToolContext.dispatch`, mirroring the lineup
agent's `lc_tools.py`. All implementations (rosters, value, matchup, schedule,
usage, sub-agents) are reused from the context; every call is logged into
`ctx.call_log` for the DecisionRecord.

Terminal tools (`propose_trades`, `abstain`) return structured JSON; the graph
detects them by name and ends the run.
"""
from __future__ import annotations

from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from fantasy_gm.agent.schema import StrList, dict_list
from fantasy_gm.agent.trade.tools import TradeToolContext

TERMINAL_TOOLS = {"propose_trades", "abstain"}


# ---- Argument schemas -----------------------------------------------------

class FindTargetsArgs(BaseModel):
    want_position: str | None = Field(default=None, description="Position I want to acquire (QB/RB/WR/TE). Omit to use my computed needs.")
    offer_position: str | None = Field(default=None, description="Position I can offer from surplus. Omit to use my computed surplus.")


class PlayerIdsArgs(BaseModel):
    player_ids: StrList = Field(description="Player ids — pass them all in one call.")


class EvaluateTradeArgs(BaseModel):
    send_player_ids: StrList = Field(description="Player ids I send.")
    receive_player_ids: StrList = Field(description="Player ids I receive.")
    counterparty_team_id: str | None = Field(default=None, description="The other team's id.")


class PlayerIdArgs(BaseModel):
    player_id: str = Field(description="A single player id.")


class MatchupArgs(BaseModel):
    player_id: str = Field(description="A single player id.")
    week: int | None = Field(default=None, description="Week to grade; defaults to the current week.")


class TradePackage(BaseModel):
    counterparty_team_id: str = Field(description="The team id to trade with.")
    send_player_ids: StrList = Field(description="Player ids I send.")
    receive_player_ids: StrList = Field(description="Player ids I receive.")
    rationale: str = Field(description="Why this helps me, citing specific signals (value/matchup/SoS/usage).")
    counterparty_pitch: str = Field(description="Why the other owner should accept — framed for their situation.")
    confidence: float = Field(ge=0.0, le=1.0, description="Honest confidence 0-1.")


class ProposeTradesArgs(BaseModel):
    trades: dict_list(TradePackage) = Field(description="Ranked trade packages, best first.")
    memo: str = Field(description="Short GM memo summarizing the trade strategy this week.")
    what_would_change_this: str = Field(description="What new info would change these proposals.")


class AbstainArgs(BaseModel):
    missing_information: StrList = Field(description="What inputs are missing or too thin.")
    what_you_would_need: str = Field(description="What you'd need to find a good trade.")
    memo: str = Field(description="Short explanation for the human.")


# ---- Tool factory ---------------------------------------------------------

def build_trade_tools(ctx: TradeToolContext, include_prefetch_tools: bool = True) -> list[StructuredTool]:
    def _dispatch(name: str, payload: dict[str, Any]) -> str:
        out, _ = ctx.dispatch(name, payload)
        return out

    def get_my_roster() -> str:
        return _dispatch("get_my_roster", {})

    def get_all_rosters() -> str:
        return _dispatch("get_all_rosters", {})

    def get_roster_needs() -> str:
        return _dispatch("get_roster_needs", {})

    def find_trade_targets(want_position: str | None = None, offer_position: str | None = None) -> str:
        return _dispatch("find_trade_targets",
                         {"want_position": want_position, "offer_position": offer_position})

    def get_trade_value(player_ids: list[str]) -> str:
        return _dispatch("get_trade_value", {"player_ids": player_ids})

    def evaluate_trade(send_player_ids: list[str], receive_player_ids: list[str],
                       counterparty_team_id: str | None = None) -> str:
        return _dispatch("evaluate_trade", {
            "send_player_ids": send_player_ids,
            "receive_player_ids": receive_player_ids,
            "counterparty_team_id": counterparty_team_id,
        })

    def get_matchup_analysis(player_id: str, week: int | None = None) -> str:
        payload = {"player_id": player_id}
        if week is not None:
            payload["week"] = week
        return _dispatch("get_matchup_analysis", payload)

    def get_schedule_strength(player_id: str) -> str:
        return _dispatch("get_schedule_strength", {"player_id": player_id})

    def get_usage_trends(player_id: str) -> str:
        return _dispatch("get_usage_trends", {"player_id": player_id})

    def get_injury_report(player_ids: list[str]) -> str:
        return _dispatch("get_injury_report", {"player_ids": player_ids})

    def get_player_news(player_ids: list[str]) -> str:
        return _dispatch("get_player_news", {"player_ids": player_ids})

    def propose_trades(trades: list[dict], memo: str, what_would_change_this: str) -> str:
        payload = {
            "trades": [t if isinstance(t, dict) else t.model_dump() for t in trades],
            "memo": memo,
            "what_would_change_this": what_would_change_this,
        }
        return _dispatch("propose_trades", payload)

    def abstain(missing_information: list[str], what_you_would_need: str, memo: str) -> str:
        return _dispatch("abstain", {
            "missing_information": missing_information,
            "what_you_would_need": what_you_would_need,
            "memo": memo,
        })

    prefetch_tools = [
        StructuredTool.from_function(get_my_roster, name="get_my_roster",
            description="Get my roster with each player's asset value and status."),
        StructuredTool.from_function(get_all_rosters, name="get_all_rosters",
            description="Get every team's roster grouped by position."),
        StructuredTool.from_function(get_roster_needs, name="get_roster_needs",
            description="Per-team surplus/need map (startable depth vs. starter requirement)."),
    ]
    judgment_tools = [
        StructuredTool.from_function(find_trade_targets, name="find_trade_targets",
            args_schema=FindTargetsArgs,
            description="Find cross-roster fits: teams whose surplus meets my need (and vice versa)."),
        StructuredTool.from_function(get_trade_value, name="get_trade_value",
            args_schema=PlayerIdsArgs,
            description="Asset value (rest-of-season projection × positional scarcity) for players."),
        StructuredTool.from_function(evaluate_trade, name="evaluate_trade",
            args_schema=EvaluateTradeArgs,
            description="Evaluate a specific package: EV delta, fairness, and my starting-lineup impact."),
        StructuredTool.from_function(get_matchup_analysis, name="get_matchup_analysis",
            args_schema=MatchupArgs,
            description="Defense-vs-position matchup grade for a player in a given week."),
        StructuredTool.from_function(get_schedule_strength, name="get_schedule_strength",
            args_schema=PlayerIdArgs,
            description="Rest-of-season and playoff-window (wks 15-17) strength of schedule for a player."),
        StructuredTool.from_function(get_usage_trends, name="get_usage_trends",
            args_schema=PlayerIdArgs,
            description="Volume/opportunity trends (targets, carries, shares, breakout flag) for a player."),
        StructuredTool.from_function(get_injury_report, name="get_injury_report",
            args_schema=PlayerIdsArgs,
            description="LLM-interpreted injury read (availability %, role-change flag, note) "
                        "for a BATCH of players. Pass EVERY player you care about in ONE call — "
                        "it costs the same as one player and lets teammates be read together."),
        StructuredTool.from_function(get_player_news, name="get_player_news",
            args_schema=PlayerIdsArgs,
            description="LLM-interpreted recent news (events, net outlook) for a BATCH of "
                        "players. Pass EVERY player you care about in ONE call — the news feed "
                        "is league-wide, so one call covers them all at the cost of one."),
        StructuredTool.from_function(propose_trades, name="propose_trades",
            args_schema=ProposeTradesArgs,
            description="TERMINAL. Submit ranked trade proposals with rationale + pitch. Ends the task."),
        StructuredTool.from_function(abstain, name="abstain", args_schema=AbstainArgs,
            description="TERMINAL. Declare no good trade is available and why. Ends the task."),
    ]
    return (prefetch_tools if include_prefetch_tools else []) + judgment_tools
