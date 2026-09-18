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
from typing import Annotated, Any, Callable, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.errors import GraphRecursionError
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

    # Set when the graph hit its step limit instead of stopping on its own. The
    # LLM budget is the intended stop condition, so this means something looped.
    hit_step_limit: bool = False

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


_TRANSIENT_MARKERS = ("503", "500", "502", "504", "unavailable",
                      "high demand", "overloaded", "internal error")


def _bind_forced(llm: Any, tools: list, choice: str = "any") -> Any:
    """Bind `tools` and require the model to call one of them.

    Withdrawing the other tools is not enough on its own: offered only
    `propose_trades`/`abstain`, Haiku still emitted `evaluate_trade` and
    `get_usage_trends` — tool names it had used earlier in the conversation but
    which were NOT in that request — and ToolNode executed them. `tool_choice`
    is the provider-side guarantee that the reply is one of these tools.

    Falls back to a plain binding when the provider or a test double does not
    accept `tool_choice`, so this can never break a run.
    """
    attempts = [choice] if choice == "any" else [choice, "any"]
    for attempt in attempts:
        try:
            return llm.bind_tools(tools, tool_choice=attempt)
        except Exception:
            continue
    return llm.bind_tools(tools)


def _strip_non_terminal(response: Any, terminal_tools: frozenset[str]) -> Any:
    """Drop tool calls the final turn was not allowed to make.

    A belt-and-braces guard behind `tool_choice`: ToolNode knows every tool, so
    a stray call would otherwise execute and burn the reserved turn on analysis
    the run has no budget left to use.
    """
    calls = getattr(response, "tool_calls", None)
    if not calls:
        return response
    kept = [c for c in calls if c.get("name") in terminal_tools]
    if len(kept) == len(calls):
        return response
    dropped = ", ".join(sorted({c.get("name", "?") for c in calls
                                if c.get("name") not in terminal_tools}))
    print(f"  dropped withdrawn tool call(s) on the final turn: {dropped}", flush=True)
    response.tool_calls = kept
    # Providers that return block content (Anthropic) ALSO carry the call as a
    # `tool_use` block, and `tool_calls` is not what gets re-sent — the blocks
    # are. Leaving a dropped call's block behind means the next request holds a
    # `tool_use` with no matching `tool_result`, which the API rejects outright
    # (400), killing the run this guard exists to save.
    content = getattr(response, "content", None)
    if isinstance(content, list):
        kept_ids = {c.get("id") for c in kept}
        blocks = [
            b for b in content
            if not (isinstance(b, dict)
                    and b.get("type") in ("tool_use", "tool_call", "function_call")
                    and b.get("id") not in kept_ids)
        ]
        # An emptied block list is NOT dropped on the way out: the client only
        # skips a blank assistant message when it is followed by another one,
        # and here it never is — a reply left with no tool calls routes straight
        # back to the agent, so it is the last message in the next request. That
        # would put `{"role": "assistant", "content": []}` on the wire. Leave a
        # truthful text block instead of an empty turn.
        response.content = blocks or [
            {"type": "text",
             "text": f"(withdrawn tool call(s) removed: {dropped})"}]
    return response


def _is_transient(exc: Exception) -> bool:
    """True for provider-side hiccups worth another (rate-limited) attempt.

    Deliberately excludes 429: retrying a rate-limit rejection is what produced
    the original quota storms, and the client's own retries already sit below
    the limiter where they cannot be paced.
    """
    text = f"{type(exc).__name__}: {exc}".lower()
    if "429" in text or "resource_exhausted" in text or "rate_limit" in text:
        return False
    return any(marker in text for marker in _TRANSIENT_MARKERS)


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

    def final_tool_choice(self, ctx: ToolContext) -> str:
        """Which terminal tool to force on the final turn.

        A tool name constrains the provider harder than "any". Subclasses that
        can tell from their own state whether a recommendation is warranted
        should name the tool; the default leaves the model the choice.
        """
        return "any"

    # ---- shared machinery ---------------------------------------------

    def _build_llm(self):
        if self._llm is not None:
            return self._llm
        from fantasy_gm.agent.llm import build_chat_model
        return build_chat_model(self.config)

    @staticmethod
    def _llm_description(llm: Any) -> str:
        """`ClassName(model)` — makes each run self-document its live backend."""
        model = getattr(llm, "model", None) or getattr(llm, "model_name", None) or "?"
        return f"{type(llm).__name__}({model})"

    def _compile(self, ctx: ToolContext, checkpointer, llm):
        tools = self.build_tools(ctx)
        bound = llm.bind_tools(tools)
        system_prompt = self.system_prompt
        terminal = ", ".join(sorted(self.terminal_tools))

        # On the final turn the model is offered ONLY the terminal tools, so it
        # cannot spend its last call on more analysis. The prompt directive alone
        # was not enough — Haiku read "this is your FINAL turn" and called
        # evaluate_trade anyway, ending the run with 20 priced packages and no
        # proposal. Removing the other tools makes that outcome unreachable
        # rather than merely discouraged.
        terminal_only = [t for t in tools if getattr(t, "name", None) in self.terminal_tools]
        forced_cache: dict[str, Any] = {}

        def terminal_model():
            """Bind the terminal tools, forcing whichever one now applies."""
            if not terminal_only:
                return bound
            choice = self.final_tool_choice(ctx)
            if choice not in forced_cache:
                forced_cache[choice] = _bind_forced(llm, terminal_only, choice)
            return forced_cache[choice]

        # Set when a turn comes back with no tool call at all, so the retry is
        # offered only the terminal tools. Consumed by the next agent turn: it
        # buys ONE forced turn, not a permanent switch. Leaving it latched meant
        # a single blank reply on turn 1 withdrew the analysis tools for the
        # whole run, which forced an immediate abstain with nothing gathered.
        force_terminal = False
        # `max_llm_calls` budgets ANALYSIS. One further call is held in reserve
        # purely to submit a decision, because the budget can be overshot inside
        # a single tools step: LLM sub-agents (injury/news) draw from the same
        # counter, so a tools step could jump it straight past the limit and the
        # run would end having never been asked for a recommendation. The reserve
        # guarantees every run gets exactly one terminal-tool turn.
        reserve_used = False

        def claim_reserve() -> bool:
            """Take the reserved terminal call, if it has not been used yet."""
            nonlocal reserve_used, force_terminal
            if reserve_used:
                return False
            reserve_used = True
            force_terminal = True
            return True

        def agent_node(state: AgentState) -> dict:
            nonlocal force_terminal
            # Exactly one system message, always. Anthropic exposes a single
            # top-level `system` field and rejects non-consecutive system
            # messages, so the final-turn directive is folded in here rather
            # than appended as a second one.
            system_text = system_prompt
            forced, force_terminal = force_terminal, False
            final_turn = ctx.llm_calls >= ctx.llm_budget - 1 or forced
            if final_turn:
                # Say why truthfully: a blank-reply retry can happen with budget
                # left, and telling the model its budget is gone when it is not
                # argues for an abstain it does not need to make.
                headline = ("LLM CALL BUDGET REACHED — this is your FINAL turn."
                            if ctx.llm_calls >= ctx.llm_budget - 1
                            else "NO TOOL CALL RECEIVED — decide now.")
                system_text += (
                    f"\n\n## {headline}\n"
                    "The analysis tools have been WITHDRAWN; only the terminal tools "
                    f"remain ({terminal}). Using only what you have already gathered, "
                    "call exactly one of them now; if the data is insufficient, call "
                    "abstain.")
            model = terminal_model() if final_turn else bound
            prompt = [SystemMessage(content=system_text)] + state["messages"]
            # Retry transient provider errors here rather than in the client, so
            # each attempt passes through the shared rate limiter and stays
            # inside the requests/minute bound.
            attempts = max(0, self.config.transient_retries) + 1
            for attempt in range(attempts):
                try:
                    response = model.invoke(prompt)
                    ctx.record_llm_call()
                    break
                except Exception as exc:
                    ctx.record_llm_call()  # it reached the provider either way
                    if attempt + 1 >= attempts or not _is_transient(exc):
                        raise
                    print(f"  transient provider error, retrying "
                          f"({attempt + 1}/{attempts - 1}): {exc}", flush=True)
            if final_turn:
                response = _strip_non_terminal(response, self.terminal_tools)
            return {"messages": [response]}

        def route_after_agent(state: AgentState) -> str:
            nonlocal force_terminal
            last = state["messages"][-1]
            if getattr(last, "tool_calls", None):
                return "tools"
            # No tool call. A run must end on a terminal tool, so an empty or
            # prose-only reply is not a valid ending — the provider returning a
            # blank message was silently killing runs mid-analysis. Give it one
            # more turn with only the terminal tools bound; the LLM budget bounds
            # how often this can repeat.
            if ctx.llm_calls < ctx.llm_budget:
                force_terminal = True
                return "agent"
            return "agent" if claim_reserve() else END

        def route_after_tools(state: AgentState) -> str:
            for msg in reversed(state["messages"]):
                if isinstance(msg, ToolMessage):
                    if msg.name in self.terminal_tools:
                        return END
                else:
                    break
            # The analysis budget is spent — spend the reserved call asking for
            # a decision rather than ending with nothing.
            if ctx.llm_calls >= ctx.llm_budget:
                return "agent" if claim_reserve() else END
            return "agent"

        graph = StateGraph(AgentState)
        graph.add_node("agent", agent_node)
        graph.add_node("tools", ToolNode(tools))
        graph.add_edge(START, "agent")
        graph.add_conditional_edges("agent", route_after_agent,
                                    {"tools": "tools", "agent": "agent", END: END})
        graph.add_conditional_edges("tools", route_after_tools,
                                    {"agent": "agent", END: END})
        return graph.compile(checkpointer=checkpointer)

    @staticmethod
    def _recursion_limit(max_iter: int, llm_budget: int) -> int:
        """Graph step budget — a safety net, deliberately not the stop condition.

        The LLM call budget is what is supposed to end a run: it forces a
        terminal tool and degrades to a truncated record. So the step limit has
        to sit *above* whatever that budget can consume, or it fires first and
        crashes the run. Each LLM call can cost two steps (agent + tools), and
        the reserved final turn costs a couple more.

        Raising this does not make a run more expensive — `llm_budget` still
        bounds the spend. It only stops the net from catching the normal path.
        """
        return 2 * max(max_iter, llm_budget) + 6

    def _recover_state(self, app, config: dict) -> dict:
        """Messages accumulated so far, read back from the checkpointer."""
        try:
            snapshot = app.get_state(config)
            return dict(snapshot.values or {})
        except Exception:
            return {"messages": []}

    def decide(self, ctx: ToolContext, verbose: bool = True,
               emit: Callable[[dict], None] | None = None) -> DecisionRecord:
        """Run the graph and build the DecisionRecord.

        `emit` receives each trace event as a dict instead of printing it, so a
        non-terminal caller (the web dashboard) consumes the same stream the CLI
        does. Passing `emit` implies a traced run.
        """
        ctx.llm_budget = self.config.max_llm_calls
        self._checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._checkpoint_path), check_same_thread=False)
        try:
            checkpointer = SqliteSaver(conn)
            llm = self._build_llm()
            app = self._compile(ctx, checkpointer, llm)
            max_iter = getattr(self, "max_tool_iterations", self.config.max_tool_iterations)
            config = {
                "recursion_limit": self._recursion_limit(max_iter, ctx.llm_budget),
                "configurable": {"thread_id": self.thread_id(ctx)},
            }
            input_msg = {"messages": [HumanMessage(content=self.user_prompt(ctx))]}
            try:
                if verbose or emit is not None:
                    from fantasy_gm.agent.tracer import stream_verbose
                    label = (f"{self._llm_description(llm)} · "
                             f"{type(self).__name__} · "
                             f"week {ctx.week} / {ctx.season}")
                    final_state = stream_verbose(
                        app, input_msg, config, self.terminal_tools, label=label,
                        full=(self.config.trace == "full"), emit=emit)
                else:
                    final_state = app.invoke(input_msg, config=config)
            except GraphRecursionError:
                # Never lose a run to the safety net. The analysis so far is in
                # the checkpointer, and `build_record` already knows how to
                # report a run that ended without a terminal tool: a truncated
                # record keeps the work and tells the human what happened, where
                # an exception throws away eight LLM calls' worth of analysis.
                ctx.hit_step_limit = True
                final_state = self._recover_state(app, config)
                note = (f"  step limit ({config['recursion_limit']}) reached — "
                        "recording a truncated run")
                if emit is not None:
                    emit({"kind": "step_limit",
                          "limit": config["recursion_limit"]})
                else:
                    print(note, flush=True)
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
