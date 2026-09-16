"""
LangGraph agent test with a fake chat model.

Proves the graph loop, tool execution via ToolNode, terminal-tool routing, and
DecisionRecord construction work end-to-end — no live API call.
"""
import tempfile
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from fantasy_gm.agent.config import AgentConfig
from fantasy_gm.agent.graph import LineupGraphAgent
from fantasy_gm.agent.tools import LineupToolContext
from fantasy_gm.models import (
    DecisionType,
    LeagueSettings,
    Platform,
    Player,
    PlayerStatus,
    Position,
    Roster,
    RosterPlayer,
    RosterSlot,
    ScoringRules,
    WaiverType,
)


# ---- Fakes ---------------------------------------------------------------

class FakeChatModel:
    """Returns a scripted list of AIMessages; ignores the input messages."""
    def __init__(self, script):
        self._script = list(script)
        self.i = 0

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        msg = self._script[self.i]
        self.i += 1
        return msg


class FakeAdapter:
    def __init__(self, roster, projections):
        self._roster = roster
        self._projections = projections
        self.league_id = "test"
        from fantasy_gm.adapters.cache import DiskCache
        self._cache = DiskCache(Path(tempfile.mkdtemp()), ttl_seconds=3600)

    def get_roster(self, team_id, week, season, fresh=False):
        return self._roster

    def get_projections(self, week, season):
        return self._projections

    def get_matchup(self, team_id, week, season):
        raise Exception("no matchup in test")


def make_player(pid, pos):
    return Player(platform_id=pid, name=f"Player {pid}", position=pos,
                  eligible_positions=[pos], status=PlayerStatus.ACTIVE)


@pytest.fixture
def ctx():
    slots = [
        RosterSlot(slot_id="qb", position=Position.QB, is_starter=True),
        RosterSlot(slot_id="rb1", position=Position.RB, is_starter=True),
        RosterSlot(slot_id="wr1", position=Position.WR, is_starter=True),
        RosterSlot(slot_id="be0", position=Position.BENCH, is_starter=False),
    ]
    settings = LeagueSettings(
        platform=Platform.ESPN, league_id="test", season=2025, team_count=12,
        roster_slots=slots, scoring_rules=ScoringRules(rules=[]),
        waiver_type=WaiverType.SNAKE, faab_budget=None,
        playoff_start_week=15, playoff_weeks=[15, 16, 17],
        regular_season_weeks=list(range(1, 15)),
    )
    players = [
        RosterPlayer(player=make_player("qb1", Position.QB), slot=Position.QB, is_starter=True),
        RosterPlayer(player=make_player("rb1", Position.RB), slot=Position.RB, is_starter=True),
        RosterPlayer(player=make_player("wr1", Position.WR), slot=Position.WR, is_starter=True),
        RosterPlayer(player=make_player("wr2", Position.WR), slot=Position.BENCH, is_starter=False),
    ]
    roster = Roster(team_id="8", team_name="Test", owner_name="Me",
                    players=players, week=1, season=2025)
    adapter = FakeAdapter(roster, {"qb1": 20.0, "rb1": 15.0, "wr1": 8.0, "wr2": 14.0})
    return LineupToolContext(adapter=adapter, settings=settings,
                             team_id="8", week=1, season=2025)


def _agent_with(script):
    tmp = Path(tempfile.mkdtemp()) / "cp.db"
    return LineupGraphAgent(AgentConfig(), llm=FakeChatModel(script), checkpoint_path=tmp)


# ---- Tests ---------------------------------------------------------------

def test_graph_proposes_lineup(ctx):
    # Read tools are pre-fetched before the LLM runs; the model goes straight
    # to optimize_lineup / propose_lineup without calling the read tools.
    script = [
        AIMessage(content="Starting wr2 over wr1.", tool_calls=[
            {"name": "propose_lineup", "args": {
                "starter_player_ids": ["qb1", "rb1", "wr2"],
                "changes_from_current": [
                    {"start_in_player_id": "wr2", "bench_out_player_id": "wr1",
                     "reason": "wr2 projects 14 vs wr1's 8."}
                ],
                "memo": "Swap wr1 for wr2 on a clear projection edge.",
                "confidence": 0.8,
                "what_would_change_this": "A late injury to wr2.",
            }, "id": "t1"},
        ]),
    ]
    record = _agent_with(script).decide(ctx)

    assert record.decision_type == DecisionType.LINEUP
    assert record.confidence == 0.8
    assert not record.recommendation.get("abstained")
    assert record.recommendation["starter_player_ids"] == ["qb1", "rb1", "wr2"]
    assert record.inputs_snapshot["projections"]["wr2"] == 14.0
    # prefetch logs: get_roster, get_projections, get_signals, get_league_context
    # (get_matchup raises in FakeAdapter → not logged); plus propose_lineup = 5 total.
    tool_names = [c["tool"] for c in record.inputs_snapshot["tool_calls"]]
    assert "propose_lineup" in tool_names
    assert "get_roster" in tool_names
    assert "get_projections" in tool_names


def test_graph_abstains(ctx):
    script = [
        AIMessage(content="", tool_calls=[
            {"name": "abstain", "args": {
                "missing_information": ["wr1 injury status unclear"],
                "what_you_would_need": "Final injury report.",
                "memo": "Too much uncertainty.",
            }, "id": "t1"},
        ]),
    ]
    record = _agent_with(script).decide(ctx)
    assert record.recommendation.get("abstained") is True
    assert record.confidence == 0.0
    assert "wr1 injury status unclear" in record.recommendation["missing_information"]


def test_graph_uses_news_tool(ctx, monkeypatch):
    """The nfl_news tool is wired and logged."""
    import fantasy_gm.signals.news as news
    monkeypatch.setattr(news, "get_nfl_news", lambda limit=10: "FAKE NEWS: nothing new.")
    script = [
        AIMessage(content="", tool_calls=[{"name": "nfl_news", "args": {"limit": 5}, "id": "n1"}]),
        AIMessage(content="", tool_calls=[
            {"name": "abstain", "args": {
                "missing_information": ["still unclear"],
                "what_you_would_need": "more",
                "memo": "abstaining",
            }, "id": "t2"},
        ]),
    ]
    record = _agent_with(script).decide(ctx)
    tools_used = [c["tool"] for c in record.inputs_snapshot["tool_calls"]]
    assert "nfl_news" in tools_used


def test_optimize_lineup_tool_uses_adjusted_projections(ctx):
    out_raw, _ = ctx.dispatch("optimize_lineup", {})
    assert "Player wr2" in out_raw
    out_adj, _ = ctx.dispatch("optimize_lineup", {"projections": {"wr1": 25.0}})
    assert "Player wr1" in out_adj


class _FlakyModel:
    """Raises a scripted error on the first call(s), then abstains."""
    def __init__(self, errors):
        self.errors = list(errors)
        self.calls = 0

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        self.calls += 1
        if self.errors:
            raise RuntimeError(self.errors.pop(0))
        return AIMessage(content="", tool_calls=[
            {"name": "abstain", "args": {"missing_information": ["x"],
                                         "what_you_would_need": "y",
                                         "memo": "z"}, "id": "t1"},
        ])


def test_exactly_one_system_message_is_sent(ctx):
    """Anthropic rejects non-consecutive system messages — never send two.

    The final-turn budget directive must be folded into the single system
    message rather than appended as a second one.
    """
    from langchain_core.messages import SystemMessage

    seen: list[int] = []

    class _Recorder:
        def __init__(self):
            self.calls = 0

        def bind_tools(self, tools):
            return self

        def invoke(self, messages):
            seen.append(sum(1 for m in messages if isinstance(m, SystemMessage)))
            self.calls += 1
            if self.calls < 2:      # first turn: a non-terminal tool, so we loop
                return AIMessage(content="", tool_calls=[
                    {"name": "get_my_injury_summary", "args": {}, "id": f"t{self.calls}"}])
            return AIMessage(content="", tool_calls=[
                {"name": "abstain", "args": {"missing_information": ["x"],
                                             "what_you_would_need": "y",
                                             "memo": "z"}, "id": "t9"}])

    tmp = Path(tempfile.mkdtemp()) / "cp.db"
    # Budget 2 so the second turn is the final one and triggers the directive.
    agent = LineupGraphAgent(AgentConfig(max_llm_calls=2), llm=_Recorder(),
                             checkpoint_path=tmp)
    agent.decide(ctx, verbose=False)

    assert seen == [1, 1], f"expected one system message per call, got {seen}"


def test_transient_provider_error_is_retried(ctx):
    """A 503 gets another attempt — through the rate limiter, not under it."""
    model = _FlakyModel(["503 UNAVAILABLE - model experiencing high demand"])
    tmp = Path(tempfile.mkdtemp()) / "cp.db"
    agent = LineupGraphAgent(AgentConfig(), llm=model, checkpoint_path=tmp)
    record = agent.decide(ctx, verbose=False)
    assert model.calls == 2                        # failed once, then succeeded
    assert record.recommendation.get("abstained")


def test_rate_limit_error_is_not_retried(ctx):
    """429 must propagate — retrying a quota rejection is what caused the storms."""
    model = _FlakyModel(["429 RESOURCE_EXHAUSTED - quota exceeded"])
    tmp = Path(tempfile.mkdtemp()) / "cp.db"
    agent = LineupGraphAgent(AgentConfig(), llm=model, checkpoint_path=tmp)
    with pytest.raises(RuntimeError, match="429"):
        agent.decide(ctx, verbose=False)
    assert model.calls == 1


def test_llm_call_budget_caps_the_loop(ctx):
    """A model that never terminates is stopped after max_llm_calls LLM calls."""
    class LoopingModel:
        def __init__(self):
            self.calls = 0

        def bind_tools(self, tools):
            return self

        def invoke(self, messages):
            self.calls += 1
            return AIMessage(content="", tool_calls=[
                {"name": "get_my_injury_summary", "args": {}, "id": f"t{self.calls}"}])

    model = LoopingModel()
    tmp = Path(tempfile.mkdtemp()) / "cp.db"
    agent = LineupGraphAgent(AgentConfig(max_llm_calls=3), llm=model, checkpoint_path=tmp)
    record = agent.decide(ctx, verbose=False)

    # Capped at the analysis budget plus the single reserved terminal call —
    # bounded, and nowhere near the recursion limit.
    assert model.calls == 4
    assert ctx.llm_calls == 4
    assert record.recommendation.get("abstained")  # no terminal tool → fallback


# ---- Final-turn tool restriction ------------------------------------------

class _BoundModel:
    """One binding of the recorder — remembers which tools it was given."""
    def __init__(self, parent, names):
        self.parent = parent
        self.names = names

    def invoke(self, messages):
        self.parent.offered.append(self.names)
        return self.parent.next_message()


class _BindRecorder:
    """Records the tool names offered at each turn; always asks for a read tool."""
    def __init__(self):
        self.offered: list[list[str]] = []
        self.calls = 0

    def bind_tools(self, tools):
        return _BoundModel(self, [t.name for t in tools])

    def next_message(self):
        self.calls += 1
        return AIMessage(content="", tool_calls=[
            {"name": "get_my_injury_summary", "args": {}, "id": f"t{self.calls}"}])


def test_final_turn_offers_only_terminal_tools(ctx):
    """The model must not be able to spend its last call on more analysis."""
    model = _BindRecorder()
    tmp = Path(tempfile.mkdtemp()) / "cp.db"
    agent = LineupGraphAgent(AgentConfig(max_llm_calls=2), llm=model, checkpoint_path=tmp)
    agent.decide(ctx, verbose=False)

    # Turn 1 has the full toolset; the run's last turn has only terminal tools.
    assert "get_my_injury_summary" in model.offered[0]
    assert set(model.offered[-1]) == set(agent.terminal_tools)
    # The analysis tools are never offered again once the budget is reached.
    assert all("get_my_injury_summary" not in names for names in model.offered[1:])


def test_non_final_turns_keep_the_full_toolset(ctx):
    """A generous budget must not restrict the early turns."""
    model = _BindRecorder()
    tmp = Path(tempfile.mkdtemp()) / "cp.db"
    agent = LineupGraphAgent(AgentConfig(max_llm_calls=4), llm=model, checkpoint_path=tmp)
    agent.decide(ctx, verbose=False)

    full = [("get_my_injury_summary" in names) for names in model.offered]
    # The early turns keep everything; once restricted, it never reverts.
    assert full[0] is True and full[-1] is False
    assert full == sorted(full, reverse=True)
    assert full.count(True) == 3       # budget-1 turns of unrestricted analysis


def test_final_turn_directive_says_tools_were_withdrawn(ctx):
    """The prompt must match reality, or the model reports a broken tool call."""
    from langchain_core.messages import SystemMessage

    seen: list[str] = []

    class _Recorder(_BindRecorder):
        def bind_tools(self, tools):
            outer = self

            class _B(_BoundModel):
                def invoke(self, messages):
                    seen.append(next(m.content for m in messages
                                     if isinstance(m, SystemMessage)))
                    return outer.next_message()
            return _B(self, [t.name for t in tools])

    tmp = Path(tempfile.mkdtemp()) / "cp.db"
    agent = LineupGraphAgent(AgentConfig(max_llm_calls=2), llm=_Recorder(),
                             checkpoint_path=tmp)
    agent.decide(ctx, verbose=False)

    assert "WITHDRAWN" not in seen[0]
    assert "WITHDRAWN" in seen[-1]


class _EmptyThenTerminal:
    """Returns a blank message first — the live failure — then a terminal call."""
    def __init__(self):
        self.offered: list[list[str]] = []
        self.calls = 0

    def bind_tools(self, tools):
        outer = self

        class _B:
            def __init__(self, names):
                self.names = names

            def invoke(self, messages):
                outer.offered.append(self.names)
                outer.calls += 1
                if outer.calls == 1:
                    return AIMessage(content="")      # no content, no tool calls
                return AIMessage(content="", tool_calls=[
                    {"name": "abstain", "args": {"missing_information": ["x"],
                                                 "what_you_would_need": "y",
                                                 "memo": "z"}, "id": "t1"}])
        return _B([t.name for t in tools])


def test_an_empty_model_response_does_not_silently_end_the_run(ctx):
    """A blank reply is not a valid ending — the run must get another turn."""
    model = _EmptyThenTerminal()
    tmp = Path(tempfile.mkdtemp()) / "cp.db"
    agent = LineupGraphAgent(AgentConfig(max_llm_calls=6), llm=model, checkpoint_path=tmp)
    record = agent.decide(ctx, verbose=False)

    assert model.calls == 2
    # The retry is restricted to terminal tools so it cannot wander off again.
    assert set(model.offered[1]) == set(agent.terminal_tools)
    # A real abstain came back, not the synthesized "truncated" fallback.
    assert not record.recommendation.get("truncated")
    assert record.recommendation["abstained"] is True


def test_an_empty_response_with_no_budget_left_still_terminates(ctx):
    """The retry must not loop forever when the budget is already spent."""
    class _AlwaysEmpty:
        def __init__(self):
            self.calls = 0

        def bind_tools(self, tools):
            return self

        def invoke(self, messages):
            self.calls += 1
            return AIMessage(content="")

    model = _AlwaysEmpty()
    tmp = Path(tempfile.mkdtemp()) / "cp.db"
    agent = LineupGraphAgent(AgentConfig(max_llm_calls=3), llm=model, checkpoint_path=tmp)
    record = agent.decide(ctx, verbose=False)

    assert model.calls == 4            # budget + the one reserved call, then stop
    assert record.recommendation["truncated"] is True


# ---- The final turn is enforced, not just requested -----------------------

def test_final_turn_requests_tool_choice_any(ctx):
    """Withdrawing tools is not enough — the provider must be told to pick one."""
    seen: list[dict] = []

    class _Model:
        def bind_tools(self, tools, **kwargs):
            seen.append({"names": [t.name for t in tools], "kwargs": kwargs})
            return self

        def invoke(self, messages):
            return AIMessage(content="", tool_calls=[
                {"name": "abstain", "args": {"missing_information": ["x"],
                                             "what_you_would_need": "y",
                                             "memo": "z"}, "id": "t1"}])

    tmp = Path(tempfile.mkdtemp()) / "cp.db"
    LineupGraphAgent(AgentConfig(max_llm_calls=2), llm=_Model(),
                     checkpoint_path=tmp).decide(ctx, verbose=False)

    forced = [b for b in seen if b["kwargs"].get("tool_choice") == "any"]
    assert forced, "the terminal binding did not force a tool choice"
    assert all(n in {"propose_lineup", "abstain"} for n in forced[0]["names"])


def test_binding_falls_back_when_tool_choice_is_unsupported(ctx):
    """A provider or fake that rejects tool_choice must still work."""
    class _Picky:
        def __init__(self):
            self.rejected = 0

        def bind_tools(self, tools, **kwargs):
            if kwargs:
                self.rejected += 1
                raise TypeError("unexpected keyword argument 'tool_choice'")
            return self

        def invoke(self, messages):
            return AIMessage(content="", tool_calls=[
                {"name": "abstain", "args": {"missing_information": ["x"],
                                             "what_you_would_need": "y",
                                             "memo": "z"}, "id": "t1"}])

    model = _Picky()
    tmp = Path(tempfile.mkdtemp()) / "cp.db"
    record = LineupGraphAgent(AgentConfig(max_llm_calls=2), llm=model,
                              checkpoint_path=tmp).decide(ctx, verbose=False)
    assert model.rejected == 1
    assert record.recommendation["abstained"] is True   # ran anyway


def test_stray_tool_calls_are_dropped_on_the_final_turn(ctx, capsys):
    """Haiku emitted withdrawn tool names live; ToolNode must not run them."""
    class _Stray:
        def __init__(self):
            self.calls = 0

        def bind_tools(self, tools, **kwargs):
            return self

        def invoke(self, messages):
            self.calls += 1
            if self.calls == 1:      # burn the analysis budget
                return AIMessage(content="", tool_calls=[
                    {"name": "get_my_injury_summary", "args": {}, "id": "a"}])
            # Final turn: a withdrawn tool alongside a legitimate terminal call.
            return AIMessage(content="", tool_calls=[
                {"name": "get_my_injury_summary", "args": {}, "id": "b"},
                {"name": "abstain", "args": {"missing_information": ["x"],
                                             "what_you_would_need": "y",
                                             "memo": "z"}, "id": "c"}])

    tmp = Path(tempfile.mkdtemp()) / "cp.db"
    record = LineupGraphAgent(AgentConfig(max_llm_calls=2), llm=_Stray(),
                              checkpoint_path=tmp).decide(ctx, verbose=False)

    assert "dropped withdrawn tool call" in capsys.readouterr().out
    # Only the terminal tool ran on the final turn.
    final_tools = [c["tool"] for c in record.inputs_snapshot["tool_calls"]]
    assert final_tools.count("get_my_injury_summary") == 1   # the first turn only
    assert record.recommendation["abstained"] is True
