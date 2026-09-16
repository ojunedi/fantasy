"""
LangChain tool wrappers.

Thin LangChain `StructuredTool`s over the existing `LineupToolContext` dispatch
(so all tool *implementations* — adapter/signals/core wiring — are reused) plus
the news/web-search tools. Every call is logged into `ctx.call_log` for the
DecisionRecord's inputs snapshot.

Terminal tools (`propose_lineup`, `abstain`) return their structured JSON; the
graph detects them by name and ends the run.
"""
from __future__ import annotations

from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from fantasy_gm.agent.schema import StrList, dict_list
from fantasy_gm.agent.tools import LineupToolContext
from fantasy_gm.signals.news import get_nfl_news, web_search

TERMINAL_TOOLS = {"propose_lineup", "abstain"}


# ---- Argument schemas for tools that take input ---------------------------

class OptimizeLineupArgs(BaseModel):
    projections: dict[str, float] | None = Field(
        default=None,
        description="Optional map of player_id -> your adjusted projected points. "
                    "Players omitted use the raw ESPN projection.",
    )


class CheckLegalityArgs(BaseModel):
    starter_player_ids: StrList = Field(description="player_ids you intend to start.")


class LineupChange(BaseModel):
    start_in_player_id: str
    bench_out_player_id: str | None = Field(default=None)
    reason: str = Field(description="Specific signals driving this swap.")


class ProposeLineupArgs(BaseModel):
    starter_player_ids: StrList = Field(description="The player_ids to start.")
    changes_from_current: dict_list(LineupChange) = Field(
        description="Swaps vs. the current lineup, each with a cited reason. "
                    "Empty if you endorse the current lineup unchanged.",
    )
    memo: str = Field(description="Short GM memo (3-6 sentences) citing specific signals.")
    confidence: float = Field(ge=0.0, le=1.0, description="Honest confidence 0-1.")
    what_would_change_this: str = Field(description="What new info would change the rec.")


class AbstainArgs(BaseModel):
    missing_information: StrList = Field(description="What inputs are missing or too stale.")
    what_you_would_need: str = Field(description="What you'd need to make the call.")
    memo: str = Field(description="Short explanation for the human.")


class WebSearchArgs(BaseModel):
    query: str = Field(description="Search query, e.g. 'Player X injury status week 3'.")


class NewsArgs(BaseModel):
    limit: int = Field(default=10, description="Number of headlines to return.")


class OpponentDefenseArgs(BaseModel):
    detail: bool = Field(
        default=False,
        description="False (default) gives one line per player with the points-allowed "
                    "rate and rank. True adds the full per-stat breakdown and team-offense "
                    "context — far longer, so only for a genuinely close call.",
    )


# ---- Tool factory ---------------------------------------------------------

def build_lineup_tools(ctx: LineupToolContext, include_prefetch_tools: bool = True) -> list[StructuredTool]:
    """Build the LangChain tool set bound to a specific decision context.

    When include_prefetch_tools=False the five no-arg read tools (roster,
    matchup, projections, signals, league_context) are omitted because the
    caller already injected their output into the user prompt.
    """

    def _dispatch(name: str, payload: dict[str, Any]) -> str:
        out, _ = ctx.dispatch(name, payload)
        return out

    # No-arg read tools
    def get_roster() -> str:
        return _dispatch("get_roster", {})

    def get_matchup() -> str:
        return _dispatch("get_matchup", {})

    def get_projections() -> str:
        return _dispatch("get_projections", {})

    def get_signals() -> str:
        return _dispatch("get_signals", {})

    def get_league_context() -> str:
        return _dispatch("get_league_context", {})

    # Compute tools
    def optimize_lineup(projections: dict[str, float] | None = None) -> str:
        return _dispatch("optimize_lineup", {"projections": projections or {}})

    def check_lineup_legality(starter_player_ids: list[str]) -> str:
        return _dispatch("check_lineup_legality", {"starter_player_ids": starter_player_ids})

    # Matchup / injury context tools (no-arg reads — called on demand, not pre-fetched)
    def get_opponent_defense(detail: bool = False) -> str:
        return _dispatch("get_opponent_defense", {"detail": detail})

    def get_opponent_injuries() -> str:
        return _dispatch("get_opponent_injuries", {})

    def get_my_injury_summary() -> str:
        return _dispatch("get_my_injury_summary", {})

    # News / research tools
    def nfl_news(limit: int = 10) -> str:
        result = get_nfl_news(limit=limit)
        ctx.call_log.append({"tool": "nfl_news", "input": {"limit": limit}, "output": result})
        return result

    def search_web(query: str) -> str:
        result = web_search(query)
        ctx.call_log.append({"tool": "search_web", "input": {"query": query}, "output": result})
        return result

    # Terminal tools
    def propose_lineup(
        starter_player_ids: list[str],
        changes_from_current: list[dict],
        memo: str,
        confidence: float,
        what_would_change_this: str,
    ) -> str:
        payload = {
            "starter_player_ids": starter_player_ids,
            "changes_from_current": [
                c if isinstance(c, dict) else c.model_dump() for c in changes_from_current
            ],
            "memo": memo,
            "confidence": confidence,
            "what_would_change_this": what_would_change_this,
        }
        return _dispatch("propose_lineup", payload)

    def abstain(missing_information: list[str], what_you_would_need: str, memo: str) -> str:
        return _dispatch("abstain", {
            "missing_information": missing_information,
            "what_you_would_need": what_you_would_need,
            "memo": memo,
        })

    prefetch_tools = [
        StructuredTool.from_function(
            get_roster, name="get_roster",
            description="Get my current roster: players, positions, injury status, and slots.",
        ),
        StructuredTool.from_function(
            get_matchup, name="get_matchup",
            description="Get this week's matchup: opponent and projected totals.",
        ),
        StructuredTool.from_function(
            get_projections, name="get_projections",
            description="Get ESPN projected fantasy points per rostered player, with freshness.",
        ),
        StructuredTool.from_function(
            get_signals, name="get_signals",
            description="Get the signal bundle: injury/practice status plus which signal sources "
                        "(usage, weather, Vegas) are available and how stale each is.",
        ),
        StructuredTool.from_function(
            get_league_context, name="get_league_context",
            description="Get season context: week, phase (regular/playoffs), weeks remaining.",
        ),
    ]
    judgment_tools = [
        StructuredTool.from_function(
            optimize_lineup, name="optimize_lineup", args_schema=OptimizeLineupArgs,
            description="Run the deterministic optimizer for a projection map. Pass adjusted "
                        "projections to see how your judgment changes the optimal lineup.",
        ),
        StructuredTool.from_function(
            check_lineup_legality, name="check_lineup_legality", args_schema=CheckLegalityArgs,
            description="Validate that a set of starters is legal under league roster rules.",
        ),
        StructuredTool.from_function(
            get_opponent_defense, name="get_opponent_defense",
            args_schema=OpponentDefenseArgs,
            description="For each rostered player: who their NFL team faces this week and how "
                        "generous that defense is to their position (fantasy points allowed per "
                        "game plus a 1-32 rank). Use it to spot favorable/tough matchups before "
                        "adjusting projections. Pass detail=true only if you need the full "
                        "per-stat breakdown for a close call — it is much longer.",
        ),
        StructuredTool.from_function(
            get_opponent_injuries, name="get_opponent_injuries",
            description="Key injuries (Out/Doubtful/Questionable) on the opposing NFL teams "
                        "your players face this week. Helps spot if a CB1 is out (WR boost), "
                        "pass rush is hobbled (QB boost), or run defense is weakened (RB boost).",
        ),
        StructuredTool.from_function(
            get_my_injury_summary, name="get_my_injury_summary",
            description="Consolidated injury status for ALL my players at once — sorted by "
                        "urgency (Out/IR > Doubtful > Questionable > Active). No LLM call. "
                        "Use before optimize_lineup to identify who cannot start.",
        ),
        StructuredTool.from_function(
            nfl_news, name="nfl_news", args_schema=NewsArgs,
            description="Get recent NFL news headlines from ESPN (injuries, roster moves, etc.).",
        ),
        StructuredTool.from_function(
            search_web, name="search_web", args_schema=WebSearchArgs,
            description="Search the web for targeted research (e.g. a specific player's injury "
                        "status this week). May be unavailable if no search key is configured.",
        ),
        StructuredTool.from_function(
            propose_lineup, name="propose_lineup", args_schema=ProposeLineupArgs,
            description="TERMINAL. Submit your final lineup recommendation. Ends the task.",
        ),
        StructuredTool.from_function(
            abstain, name="abstain", args_schema=AbstainArgs,
            description="TERMINAL. Declare insufficient information to recommend. Ends the task.",
        ),
    ]
    return (prefetch_tools if include_prefetch_tools else []) + judgment_tools
