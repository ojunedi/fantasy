"""
Shared agent base — the pieces every specialist (lineup, trade, …) reuses.

Two abstractions, extracted from the original lineup agent so a GM Supervisor
can slot multiple specialists onto the same machinery:

  - `ToolContext`: per-run state (lazy roster/signals caches, a `dispatch` that
    routes a tool name to a `_tool_<name>` method, and a `call_log` capturing
    every tool input/output for the DecisionRecord). Each specialist subclasses
    it and declares its own `terminal_tools`.

  - `GraphAgent`: the LangGraph StateGraph loop (agent ⇄ tools), terminal-tool
    routing, lazy `ChatGoogleGenerativeAI` build, a `SqliteSaver` checkpointer, and the
    run driver. Subclasses supply the system prompt, tool set, a thread id, and
    the DecisionRecord builder.

Nothing here executes an irreversible action; terminal tools are propose-only.
"""
from __future__ import annotations

import json
import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from fantasy_gm.agent.config import AgentConfig
from fantasy_gm.models import DecisionRecord, LeagueSettings, Player, Roster
from fantasy_gm.signals.base import SignalBundle
from fantasy_gm.signals.collector import collect_signals


# ---------------------------------------------------------------------------
# Tool context
# ---------------------------------------------------------------------------

@dataclass
class ToolContext:
    """Per-run tool state shared by every specialist agent.

    Subclasses add their own `_tool_<name>` methods and set `terminal_tools`.
    """
    adapter: Any               # ESPNAdapter (or a test fake)
    settings: LeagueSettings
    team_id: str
    week: int
    season: int

    # Populated lazily and cached so repeated tool calls are consistent.
    _roster: Roster | None = None
    _signals: SignalBundle | None = None
    # Every tool call's input+output, captured for the DecisionRecord.
    call_log: list[dict[str, Any]] = field(default_factory=list)

    # Subclasses override with their terminal tool names.
    terminal_tools: frozenset[str] = frozenset()

    # Optional risk posture set by the Supervisor (must_win / coast / normal),
    # surfaced to the agent as an input to weight floor vs. ceiling / urgency.
    posture: str | None = None

    # Shared per-run LLM-call budget (rate-limit guard). Set by GraphAgent.decide;
    # both the agent loop and the LLM sub-agents draw from the same counter.
    llm_budget: int = 999
    llm_calls: int = 0

    def llm_call_allowed(self) -> bool:
        return self.llm_calls < self.llm_budget

    def record_llm_call(self) -> None:
        self.llm_calls += 1

    # ---- lazy loaders --------------------------------------------------

    def roster(self) -> Roster:
        if self._roster is None:
            # Always bypass the disk cache on first load so the agent sees live
            # slot assignments, not a stale snapshot that could trigger phantom swaps.
            self._roster = self.adapter.get_roster(
                self.team_id, self.week, self.season, fresh=True
            )
        return self._roster

    def signals(self) -> SignalBundle:
        if self._signals is None:
            self._signals = collect_signals(
                self.adapter, self.week, self.season, self.roster().players
            )
        return self._signals

    def _players_by_id(self) -> dict[str, Player]:
        return {rp.player.platform_id: rp.player for rp in self.roster().players}

    def _raw_projection_map(self) -> dict[str, float]:
        return {pid: pj.projected_points for pid, pj in self.signals().projections.items()}

    # ---- tool dispatch -------------------------------------------------

    def dispatch(self, name: str, tool_input: dict[str, Any]) -> tuple[str, bool]:
        """Execute a tool. Returns (result_text, is_terminal)."""
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            return f"Error: unknown tool '{name}'", False
        result = handler(tool_input)
        self.call_log.append({"tool": name, "input": tool_input, "output": result})
        return result, name in self.terminal_tools


# ---------------------------------------------------------------------------
# Graph agent
# ---------------------------------------------------------------------------

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


class GraphAgent(ABC):
    """A LangGraph agent: agent ⇄ tools loop ending on a terminal tool.

    Subclasses declare `system_prompt`, `terminal_tools`, and implement
    `build_tools`, `user_prompt`, `thread_id`, and `build_record`.
    """

    system_prompt: str = ""
    terminal_tools: frozenset[str] = frozenset()

    def __init__(self, config: AgentConfig | None = None, llm: Any | None = None,
                 checkpoint_path: Path | None = None):
        self.config = config or AgentConfig()
        self._llm = llm  # inject a fake for testing; else built lazily
        self._checkpoint_path = checkpoint_path or Path("data/langgraph.db")

    # ---- to be provided by subclasses ---------------------------------

    @abstractmethod
    def build_tools(self, ctx: ToolContext) -> list:
        ...

    @abstractmethod
    def user_prompt(self, ctx: ToolContext) -> str:
        ...

    @abstractmethod
    def thread_id(self, ctx: ToolContext) -> str:
        ...

    @abstractmethod
    def build_record(self, ctx: ToolContext, messages: list) -> DecisionRecord:
        ...

    # ---- shared machinery ---------------------------------------------

    def _build_llm(self):
        if self._llm is not None:
            return self._llm
        from langchain_google_genai import ChatGoogleGenerativeAI
        from fantasy_gm.agent.config import shared_rate_limiter
        return ChatGoogleGenerativeAI(
            model=self.config.model,
            google_api_key=self.config.google_api_key or None,
            max_output_tokens=self.config.max_tokens,
            # Shared with the sub-agents' `default_llm` so the RPM cap is
            # process-wide, and low retries so a 429 can't burst.
            rate_limiter=shared_rate_limiter(self.config.max_rpm),
            max_retries=self.config.max_retries,
        )

    @staticmethod
    def _llm_description(llm: Any) -> str:
        """`ClassName(model)` — makes each run self-document its live backend."""
        model = getattr(llm, "model", None) or getattr(llm, "model_name", None) or "?"
        return f"{type(llm).__name__}({model})"

    def _route_after_agent(self, state: AgentState) -> str:
        last = state["messages"][-1]
        if getattr(last, "tool_calls", None):
            return "tools"
        return END

    def _compile(self, ctx: ToolContext, checkpointer, llm):
        tools = self.build_tools(ctx)
        bound = llm.bind_tools(tools)
        system_prompt = self.system_prompt
        terminal = ", ".join(sorted(self.terminal_tools))

        def agent_node(state: AgentState) -> dict:
            prompt = [SystemMessage(content=system_prompt)] + state["messages"]
            # On the last call in the budget, force a terminal decision.
            if ctx.llm_calls >= ctx.llm_budget - 1:
                prompt.append(SystemMessage(content=(
                    "LLM CALL BUDGET REACHED — this is your FINAL turn. Do NOT request "
                    "any more read/compute tools. Using only what you have already "
                    f"gathered, call exactly one terminal tool now ({terminal}); if the "
                    "data is insufficient, call abstain.")))
            response = bound.invoke(prompt)
            ctx.record_llm_call()
            return {"messages": [response]}

        def route_after_tools(state: AgentState) -> str:
            for msg in reversed(state["messages"]):
                if isinstance(msg, ToolMessage):
                    if msg.name in self.terminal_tools:
                        return END
                else:
                    break
            # Stop looping once the shared LLM budget is spent.
            if ctx.llm_calls >= ctx.llm_budget:
                return END
            return "agent"

        graph = StateGraph(AgentState)
        graph.add_node("agent", agent_node)
        graph.add_node("tools", ToolNode(tools))
        graph.add_edge(START, "agent")
        graph.add_conditional_edges("agent", self._route_after_agent,
                                    {"tools": "tools", END: END})
        graph.add_conditional_edges("tools", route_after_tools,
                                    {"agent": "agent", END: END})
        return graph.compile(checkpointer=checkpointer)

    def decide(self, ctx: ToolContext, verbose: bool = True) -> DecisionRecord:
        ctx.llm_budget = self.config.max_llm_calls
        self._checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._checkpoint_path), check_same_thread=False)
        try:
            checkpointer = SqliteSaver(conn)
            llm = self._build_llm()
            app = self._compile(ctx, checkpointer, llm)
            max_iter = getattr(self, "max_tool_iterations", self.config.max_tool_iterations)
            config = {
                "recursion_limit": max_iter * 2,
                "configurable": {"thread_id": self.thread_id(ctx)},
            }
            input_msg = {"messages": [HumanMessage(content=self.user_prompt(ctx))]}
            if verbose:
                from fantasy_gm.agent.tracer import stream_verbose
                label = (f"{self._llm_description(llm)} · "
                         f"{type(self).__name__} · "
                         f"week {ctx.week} / {ctx.season}")
                final_state = stream_verbose(
                    app, input_msg, config, self.terminal_tools, label=label,
                    full=(self.config.trace == "full"))
            else:
                final_state = app.invoke(input_msg, config=config)
        finally:
            conn.close()
        return self.build_record(ctx, final_state["messages"])

    def _extract_terminal(self, messages: list) -> tuple[str | None, dict | None]:
        for msg in reversed(messages):
            if isinstance(msg, ToolMessage) and msg.name in self.terminal_tools:
                try:
                    content = msg.content
                    if isinstance(content, list):  # some LC versions wrap content
                        content = content[0].get("text", "") if content else ""
                    return msg.name, json.loads(content)
                except (json.JSONDecodeError, TypeError, AttributeError):
                    return msg.name, None
        return None, None
