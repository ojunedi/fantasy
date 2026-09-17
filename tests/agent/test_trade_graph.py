"""
Trade agent graph test with a fake chat model — no live API, no nflverse.

Proves the trade loop, tool execution, terminal routing (propose_trades /
abstain), and DecisionRecord(TRADE) construction. Heavy analytics inputs are
injected so the test runs fully offline.
"""
import tempfile
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from fantasy_gm.agent.config import AgentConfig
from fantasy_gm.agent.trade.graph import TradeGraphAgent
from fantasy_gm.agent.trade.tools import TradeToolContext
from fantasy_gm.models import (
    DecisionRecord,
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


class FakeChatModel:
    def __init__(self, script):
        self._script = list(script)
        self.i = 0

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        msg = self._script[self.i]
        self.i += 1
        return msg


def _p(pid, pos, team=None):
    return Player(platform_id=pid, name=f"P{pid}", position=pos,
                  eligible_positions=[pos], nfl_team=team, status=PlayerStatus.ACTIVE)


def _rp(pid, pos, starter):
    return RosterPlayer(player=_p(pid, pos), slot=pos if starter else Position.BENCH,
                        is_starter=starter)


class FakeAdapter:
    def __init__(self, rosters):
        self._rosters = {r.team_id: r for r in rosters}
        self.league_id = "test"

    def get_all_rosters(self, week, season, fresh=False):
        return list(self._rosters.values())

    def get_roster(self, team_id, week, season, fresh=False):
        return self._rosters[team_id]

    def get_projections(self, week, season):
        return {}


@pytest.fixture
def settings():
    slots = [
        RosterSlot(slot_id="qb", position=Position.QB, is_starter=True),
        RosterSlot(slot_id="rb1", position=Position.RB, is_starter=True),
        RosterSlot(slot_id="wr1", position=Position.WR, is_starter=True),
        RosterSlot(slot_id="te1", position=Position.TE, is_starter=True),
        RosterSlot(slot_id="be0", position=Position.BENCH, is_starter=False),
        RosterSlot(slot_id="be1", position=Position.BENCH, is_starter=False),
    ]
    return LeagueSettings(
        platform=Platform.ESPN, league_id="test", season=2026, team_count=2,
        roster_slots=slots, scoring_rules=ScoringRules(rules=[]),
        waiver_type=WaiverType.SNAKE, faab_budget=None, playoff_start_week=15,
        playoff_weeks=[15, 16, 17], regular_season_weeks=list(range(1, 15)),
    )


@pytest.fixture
def ctx(settings):
    mine = Roster(team_id="8", team_name="Me", owner_name="Me", week=1, season=2026, players=[
        _rp("qb1", Position.QB, True),
        _rp("rb_weak", Position.RB, True),
        _rp("wr1", Position.WR, True),
        _rp("te1", Position.TE, True),
        _rp("wr_spare", Position.WR, False),
        _rp("wr_spare2", Position.WR, False),
    ])
    other = Roster(team_id="3", team_name="Them", owner_name="Rival", week=1, season=2026, players=[
        _rp("qb2", Position.QB, True),
        _rp("rb_strong", Position.RB, True),
        _rp("rb_strong2", Position.RB, False),
        _rp("wr3", Position.WR, True),
        _rp("te2", Position.TE, True),
    ])
    adapter = FakeAdapter([mine, other])
    weekly = {"qb1": 20, "rb_weak": 5, "wr1": 15, "te1": 8, "wr_spare": 9, "wr_spare2": 7,
              "qb2": 18, "rb_strong": 22, "rb_strong2": 12, "wr3": 10, "te2": 6}
    return TradeToolContext(
        adapter=adapter, settings=settings, team_id="8", week=1, season=2026,
        _weekly_proj={k: float(v) for k, v in weekly.items()},
    )


def _agent_with(script):
    tmp = Path(tempfile.mkdtemp()) / "cp.db"
    return TradeGraphAgent(AgentConfig(), llm=FakeChatModel(script), checkpoint_path=tmp)


def test_trade_agent_proposes(ctx):
    script = [
        AIMessage(content="", tool_calls=[
            {"name": "get_all_rosters", "args": {}, "id": "t1"},
            {"name": "get_roster_needs", "args": {}, "id": "t2"},
        ]),
        AIMessage(content="", tool_calls=[
            {"name": "get_trade_value", "args": {"player_ids": ["wr_spare", "rb_strong"]}, "id": "t3"},
            {"name": "evaluate_trade", "args": {
                "send_player_ids": ["wr_spare", "wr_spare2"],
                "receive_player_ids": ["rb_strong"],
                "counterparty_team_id": "3"}, "id": "t4"},
        ]),
        AIMessage(content="Proposing.", tool_calls=[
            {"name": "propose_trades", "args": {
                "trades": [{
                    "counterparty_team_id": "3",
                    "send_player_ids": ["wr_spare", "wr_spare2"],
                    "receive_player_ids": ["rb_strong"],
                    "rationale": "Consolidates WR surplus into a scarce RB1; upgrades my RB starter.",
                    "counterparty_pitch": "They have RB depth and start only one WR-worthy option.",
                    "confidence": 0.7,
                }],
                "memo": "Consolidate WR depth for RB1.",
                "what_would_change_this": "A wr_spare injury.",
            }, "id": "t5"},
        ]),
    ]
    record = _agent_with(script).decide(ctx)
    assert record.decision_type == DecisionType.TRADE
    assert not record.recommendation.get("abstained")
    trades = record.recommendation["trades"]
    assert trades[0]["receive_player_ids"] == ["rb_strong"]
    assert trades[0]["send_names"] == ["Pwr_spare", "Pwr_spare2"]  # enriched
    assert record.confidence == 0.7
    tools_used = [c["tool"] for c in record.inputs_snapshot["tool_calls"]]
    assert "evaluate_trade" in tools_used and "propose_trades" in tools_used


def test_trade_agent_abstains(ctx):
    script = [
        AIMessage(content="", tool_calls=[
            {"name": "abstain", "args": {
                "missing_information": ["no clear surplus/need fit"],
                "what_you_would_need": "A team willing to move an RB1.",
                "memo": "No favorable trade available.",
            }, "id": "t1"},
        ]),
    ]
    record = _agent_with(script).decide(ctx)
    assert record.recommendation.get("abstained") is True
    assert record.confidence == 0.0


def test_evaluate_trade_tool_reports_roster_impact(ctx):
    out, terminal = ctx.dispatch("evaluate_trade", {
        "send_player_ids": ["wr_spare", "wr_spare2"],
        "receive_player_ids": ["rb_strong"],
    })
    assert not terminal
    assert "EV delta" in out
    assert "Starting-lineup impact" in out
    # Receiving a 22-pt RB for bench WRs should raise the optimized starter total.
    assert "→" in out


def test_get_trade_value_tool(ctx):
    out, _ = ctx.dispatch("get_trade_value", {"player_ids": ["rb_strong", "wr_spare"]})
    assert "rb_strong" in out and "value" in out


# ---- Batched injury / news tools ------------------------------------------

def _hurt(pid, status):
    """A roster player with a non-ACTIVE status, so the injury LLM is engaged."""
    p = Player(platform_id=pid, name=f"P{pid}", position=Position.WR,
               eligible_positions=[Position.WR], status=status)
    return RosterPlayer(player=p, slot=Position.BENCH, is_starter=False)


@pytest.fixture
def hurt_ctx(settings):
    mine = Roster(team_id="8", team_name="Me", owner_name="Me", week=1, season=2026, players=[
        _rp("qb1", Position.QB, True),
        _rp("rb1", Position.RB, True),
        _rp("wr_ok", Position.WR, True),
        _rp("te1", Position.TE, True),
        _hurt("wr_out", PlayerStatus.OUT),
        _hurt("wr_quest", PlayerStatus.QUESTIONABLE),
    ])
    return TradeToolContext(
        adapter=FakeAdapter([mine]), settings=settings, team_id="8", week=1, season=2026,
        _weekly_proj={"qb1": 20.0, "rb1": 10.0, "wr_ok": 12.0, "te1": 8.0,
                      "wr_out": 0.0, "wr_quest": 6.0},
    )


def test_injury_tool_makes_one_subagent_call_for_the_batch(hurt_ctx):
    calls = []

    def fake_injury(players):
        calls.append([p["player_name"] for p in players])
        return {p["player_name"]: {"availability_pct": 25, "role_change_flag": True,
                                   "note": "Limited."} for p in players}

    hurt_ctx.injury_fn = fake_injury
    hurt_ctx.llm_budget = 8
    out, _ = hurt_ctx.dispatch("get_injury_report",
                               {"player_ids": ["wr_out", "wr_quest"]})

    assert len(calls) == 1                      # ONE call, not one per player
    assert calls[0] == ["Pwr_out", "Pwr_quest"]
    assert hurt_ctx.llm_calls == 1
    assert out.count("availability_pct=25") == 2


def test_injury_tool_answers_active_players_without_an_llm(hurt_ctx):
    def fake_injury(players):
        raise AssertionError("ACTIVE players must not reach the LLM")

    hurt_ctx.injury_fn = fake_injury
    hurt_ctx.llm_budget = 8
    out, _ = hurt_ctx.dispatch("get_injury_report", {"player_ids": ["wr_ok"]})
    assert "ACTIVE" in out
    assert hurt_ctx.llm_calls == 0


def test_injury_tool_mixes_active_and_hurt_in_one_call(hurt_ctx):
    calls = []

    def fake_injury(players):
        calls.append([p["player_name"] for p in players])
        return {p["player_name"]: {"availability_pct": 50} for p in players}

    hurt_ctx.injury_fn = fake_injury
    hurt_ctx.llm_budget = 8
    out, _ = hurt_ctx.dispatch("get_injury_report",
                               {"player_ids": ["wr_ok", "wr_out", "nope"]})
    assert calls == [["Pwr_out"]]               # only the hurt player was sent
    assert "ACTIVE" in out and "not found" in out
    assert hurt_ctx.llm_calls == 1


def test_news_tool_makes_one_subagent_call_for_the_batch(hurt_ctx):
    calls = []

    def fake_news(names):
        calls.append(list(names))
        return {n: {"events": [{"type": "usage_trend", "impact": "up",
                                "summary": "More targets."}],
                    "net_outlook": "up", "note": "Trending."} for n in names}

    hurt_ctx.news_fn = fake_news
    hurt_ctx.llm_budget = 8
    out, _ = hurt_ctx.dispatch("get_player_news",
                               {"player_ids": ["wr_ok", "wr_out", "qb1"]})

    assert len(calls) == 1                      # ONE call for all three
    assert calls[0] == ["Pwr_ok", "Pwr_out", "Pqb1"]
    assert hurt_ctx.llm_calls == 1
    assert out.count("net outlook up") == 3


def test_batched_tools_respect_the_remaining_budget(hurt_ctx):
    """A batch that would overrun the budget is skipped, not half-charged."""
    def fake_news(names):
        raise AssertionError("must not call the LLM with no budget left")

    hurt_ctx.news_fn = fake_news
    hurt_ctx.llm_budget = 2
    hurt_ctx.llm_calls = 2
    out, _ = hurt_ctx.dispatch("get_player_news", {"player_ids": ["wr_ok"]})
    assert "budget reached" in out
    assert hurt_ctx.llm_calls == 2


def test_batched_tool_charges_once_per_chunk(hurt_ctx):
    """Beyond the chunk cap the budget must be charged per model call."""
    from fantasy_gm.agent.subagents.base import BATCH_SIZE

    hurt_ctx.news_fn = lambda names: {n: {"net_outlook": "neutral"} for n in names}
    hurt_ctx.llm_budget = 8
    pids = ["qb1", "rb1", "wr_ok", "te1", "wr_out", "wr_quest"]
    assert len(pids) <= BATCH_SIZE
    hurt_ctx.dispatch("get_player_news", {"player_ids": pids})
    assert hurt_ctx.llm_calls == 1              # 6 players, one chunk, one charge


# ---- Truncated runs are not abstentions -----------------------------------

class _LoopingModel:
    """Never calls a terminal tool — it just keeps evaluating trades."""
    def __init__(self):
        self.calls = 0

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        self.calls += 1
        return AIMessage(content="", tool_calls=[{
            "name": "evaluate_trade",
            "args": {"send_player_ids": ["wr_spare"],
                     "receive_player_ids": ["rb_strong"],
                     "counterparty_team_id": "3"},
            "id": f"t{self.calls}"}])


def _looping_agent(budget):
    tmp = Path(tempfile.mkdtemp()) / "cp.db"
    return TradeGraphAgent(AgentConfig(max_llm_calls=budget), llm=_LoopingModel(),
                           checkpoint_path=tmp)


def test_budget_exhaustion_is_reported_as_truncated_not_abstained(ctx):
    record = _looping_agent(2).decide(ctx, verbose=False)
    rec = record.recommendation
    assert rec["truncated"] is True
    assert "budget exhausted" in rec["reason"]
    # Budget 2 of analysis, plus the one reserved call spent asking for a decision.
    assert rec["llm_budget"] == 2 and rec["llm_calls"] == 3
    assert "cut off" in record.memo
    # Still flagged abstained so executors refuse to act on a truncated run.
    assert rec["abstained"] is True


def test_truncated_run_salvages_the_packages_it_already_priced(ctx):
    """The work that used to be silently discarded must survive the cut-off."""
    record = _looping_agent(2).decide(ctx, verbose=False)
    packages = record.recommendation["evaluated_packages"]
    assert packages, "evaluated trades were dropped on truncation"
    assert packages[0]["send_player_ids"] == ["wr_spare"]
    assert packages[0]["receive_player_ids"] == ["rb_strong"]
    assert "EV delta" in packages[0]["evaluation"]


def test_a_real_abstain_is_not_marked_truncated(ctx):
    script = [AIMessage(content="", tool_calls=[{
        "name": "abstain",
        "args": {"missing_information": ["no fits"], "what_you_would_need": "more depth",
                 "memo": "Nothing available."},
        "id": "t1"}])]
    record = _agent_with(script).decide(ctx, verbose=False)
    assert record.recommendation["abstained"] is True
    assert not record.recommendation.get("truncated")
    assert record.memo == "Nothing available."


def _record_with(rec: dict, memo: str) -> DecisionRecord:
    return DecisionRecord(week=1, season=2026, decision_type=DecisionType.TRADE,
                          inputs_snapshot={}, signals_staleness={},
                          recommendation=rec, memo=memo, confidence=0.0)


def test_renderer_distinguishes_truncation_from_abstention(capsys):
    from fantasy_gm.memo.cli import _render_no_recommendation

    truncated = _record_with(
        {"abstained": True, "truncated": True, "llm_calls": 8, "llm_budget": 8,
         "evaluated_packages": [{"send_player_ids": ["A"], "receive_player_ids": ["B"],
                                 "counterparty_team_id": "3",
                                 "evaluation": "EV delta: +997.0 | verdict: WIN"}]},
        "Run was cut off before a recommendation.")
    _render_no_recommendation(truncated, truncated.recommendation)
    out = capsys.readouterr().out
    assert "RUN TRUNCATED" in out and "ABSTAINED" not in out
    assert "8 of 8" in out
    assert "+997.0" in out          # salvaged work is shown to the human

    abstained = _record_with(
        {"abstained": True, "missing_information": ["no fits"],
         "what_you_would_need": "more depth"}, "Nothing available.")
    _render_no_recommendation(abstained, abstained.recommendation)
    out = capsys.readouterr().out
    assert "AGENT ABSTAINED" in out and "TRUNCATED" not in out
    assert "no fits" in out


class _GreedyModel:
    """Evaluates trades forever, but proposes once only terminal tools remain.

    Mirrors the live failure: the model ignored the "final turn" wording and
    kept analysing. Withdrawing the analysis tools is what forces it to land.
    """
    def __init__(self):
        self.calls = 0

    def bind_tools(self, tools):
        names = {t.name for t in tools}
        return _GreedyBound(self, names)

    def evaluate(self):
        self.calls += 1
        return AIMessage(content="", tool_calls=[{
            "name": "evaluate_trade",
            "args": {"send_player_ids": ["wr_spare"],
                     "receive_player_ids": ["rb_strong"],
                     "counterparty_team_id": "3"},
            "id": f"t{self.calls}"}])

    def propose(self):
        self.calls += 1
        return AIMessage(content="Landing it.", tool_calls=[{
            "name": "propose_trades",
            "args": {"trades": [{
                "counterparty_team_id": "3",
                "send_player_ids": ["wr_spare"],
                "receive_player_ids": ["rb_strong"],
                "rationale": "Turns surplus WR depth into a scarce starting RB.",
                "counterparty_pitch": "They are RB-rich and start only one real WR.",
                "confidence": 0.7}],
                "memo": "Consolidate WR depth into RB1.",
                "what_would_change_this": "An injury to rb_strong."},
            "id": f"t{self.calls}"}])


class _GreedyBound:
    def __init__(self, parent, names):
        self.parent = parent
        self.names = names

    def invoke(self, messages):
        if "evaluate_trade" in self.names:
            return self.parent.evaluate()
        return self.parent.propose()


def test_restriction_forces_a_proposal_instead_of_a_truncated_run(ctx):
    tmp = Path(tempfile.mkdtemp()) / "cp.db"
    agent = TradeGraphAgent(AgentConfig(max_llm_calls=3), llm=_GreedyModel(),
                            checkpoint_path=tmp)
    record = agent.decide(ctx, verbose=False)

    assert not record.recommendation.get("truncated")
    assert not record.recommendation.get("abstained")
    assert record.recommendation["trades"][0]["receive_player_ids"] == ["rb_strong"]
    assert record.confidence == 0.7


class _NewsThenPropose:
    """Burns budget on an LLM sub-agent tool, then proposes when forced."""
    def __init__(self):
        self.calls = 0

    def bind_tools(self, tools):
        outer = self
        names = {t.name for t in tools}

        class _B:
            def invoke(self, messages):
                outer.calls += 1
                if "get_player_news" in names:
                    return AIMessage(content="", tool_calls=[{
                        "name": "get_player_news",
                        "args": {"player_ids": ["rb_strong", "wr3"]},
                        "id": f"n{outer.calls}"}])
                return AIMessage(content="", tool_calls=[{
                    "name": "propose_trades",
                    "args": {"trades": [{
                        "counterparty_team_id": "3",
                        "send_player_ids": ["wr_spare"],
                        "receive_player_ids": ["rb_strong"],
                        "rationale": "Converts spare WR depth into a starting RB.",
                        "counterparty_pitch": "They are deep at RB and thin at WR.",
                        "confidence": 0.6}],
                        "memo": "Land the RB.",
                        "what_would_change_this": "An injury."},
                    "id": f"p{outer.calls}"}])
        return _B()


def test_subagent_overshoot_still_leaves_a_turn_to_decide(ctx):
    """Sub-agent tools drain the SAME budget and can blow past it in one step.

    That used to end the run without ever asking for a recommendation. The
    reserved call must guarantee a terminal turn regardless.
    """
    ctx.news_fn = lambda names: {n: {"net_outlook": "up", "note": "Hot."} for n in names}
    tmp = Path(tempfile.mkdtemp()) / "cp.db"
    agent = TradeGraphAgent(AgentConfig(max_llm_calls=2), llm=_NewsThenPropose(),
                            checkpoint_path=tmp)
    record = agent.decide(ctx, verbose=False)

    assert ctx.llm_calls > ctx.llm_budget          # the overshoot really happened
    assert not record.recommendation.get("truncated")
    assert record.recommendation["trades"][0]["receive_player_ids"] == ["rb_strong"]


# ---- Deterministic selection when the model never submits -----------------

@pytest.fixture
def valued_ctx(ctx):
    """The ctx fixture is offline, so every asset prices at 0 and no package can
    clear the gain threshold. Inject a value map so the WR-for-RB consolidation
    is a genuine, near-balanced upgrade."""
    from fantasy_gm.core.trade_value import AssetValue

    values = {"wr_spare": 900.0, "rb_strong": 1150.0, "wr1": 2400.0,
              "rb_weak": 300.0, "qb1": 800.0, "te1": 700.0,
              "wr_spare2": 500.0, "rb_strong2": 1200.0, "wr3": 1000.0,
              "te2": 400.0, "qb2": 750.0}
    ctx._value_map = {
        pid: AssetValue(pid, info["position"], ros_points=0.0, scarcity=1.0,
                        value=values.get(pid, 0.0), source="test", note="")
        for pid, info in ctx.player_index().items()
    }
    return ctx


def test_deterministic_pick_rescues_a_truncated_run(valued_ctx):
    """The scoring is already done — a cut-off run should not throw it away."""
    ctx = valued_ctx
    record = _looping_agent(2).decide(ctx, verbose=False)
    rec = record.recommendation

    assert rec["selected_deterministically"] is True
    assert not rec.get("abstained")
    assert rec["trades"][0]["receive_player_ids"] == ["rb_strong"]
    assert "cut off" in rec["reason"]
    # Confidence is capped — nothing here carries model judgment.
    assert 0 < record.confidence <= 0.5


def test_deterministic_pick_ranks_by_gain(ctx):
    from fantasy_gm.agent.trade.tools import acceptable_packages

    evs = [
        {"ev_delta": 100.0, "fairness": 0.90, "send_player_ids": [], "receive_player_ids": []},
        {"ev_delta": 900.0, "fairness": 0.80, "send_player_ids": [], "receive_player_ids": []},
        {"ev_delta": 400.0, "fairness": 0.95, "send_player_ids": [], "receive_player_ids": []},
    ]
    ranked = acceptable_packages(evs)
    assert [e["ev_delta"] for e in ranked] == [900.0, 400.0, 100.0]


def test_deterministic_pick_rejects_fleeces_and_noise(ctx):
    from fantasy_gm.agent.trade.tools import acceptable_packages

    evs = [
        {"ev_delta": 5000.0, "fairness": 0.20, "send_player_ids": [], "receive_player_ids": []},
        {"ev_delta": 10.0, "fairness": 0.99, "send_player_ids": [], "receive_player_ids": []},
        {"ev_delta": -500.0, "fairness": 0.95, "send_player_ids": [], "receive_player_ids": []},
    ]
    # A lopsided steal nobody accepts, rounding noise, and a loss — none qualify.
    assert acceptable_packages(evs) == []


def test_deterministic_pick_honours_the_managers_brief(ctx):
    """Unlike the model path, this cannot explain itself — so it must not
    propose a player the manager ruled out."""
    from fantasy_gm.agent.trade.preferences import TradePreferences
    from fantasy_gm.agent.trade.tools import acceptable_packages

    ev = {"ev_delta": 900.0, "fairness": 0.90,
          "send_player_ids": ["wr1"], "receive_player_ids": ["rb_strong"]}
    prefs = TradePreferences(offerable_ids=["wr_spare"])      # wr1 is off-limits
    assert acceptable_packages([ev], prefs, {}) == []
    assert acceptable_packages([ev], TradePreferences(), {}) == [ev]


def test_truncation_with_no_viable_package_still_abstains(ctx):
    """No cherry-picking: if nothing qualifies, report the truncation honestly."""
    class _BadTradesOnly:
        def __init__(self):
            self.calls = 0

        def bind_tools(self, tools, **kwargs):
            return self

        def invoke(self, messages):
            self.calls += 1
            return AIMessage(content="", tool_calls=[{
                "name": "evaluate_trade",
                # Sending a starter for a weak bench player: a clear loss.
                "args": {"send_player_ids": ["wr1"],
                         "receive_player_ids": ["te2"],
                         "counterparty_team_id": "3"},
                "id": f"t{self.calls}"}])

    tmp = Path(tempfile.mkdtemp()) / "cp.db"
    record = TradeGraphAgent(AgentConfig(max_llm_calls=2), llm=_BadTradesOnly(),
                             checkpoint_path=tmp).decide(ctx, verbose=False)
    assert record.recommendation["truncated"] is True
    assert record.confidence == 0.0


def test_final_tool_choice_follows_the_evidence(ctx):
    from fantasy_gm.agent.trade.graph import TradeGraphAgent as TGA

    agent = TGA(AgentConfig())
    assert agent.final_tool_choice(ctx) == "abstain"        # nothing priced yet
    ctx.evaluations.append({"ev_delta": 900.0, "fairness": 0.9,
                            "send_player_ids": [], "receive_player_ids": []})
    assert agent.final_tool_choice(ctx) == "propose_trades"


def test_renderer_marks_a_deterministic_pick(capsys):
    from fantasy_gm.memo.cli import _render_trade_packages

    rec = _record_with({"selected_deterministically": True, "trades": [{
        "counterparty_team_id": "3", "send_names": ["A"], "receive_names": ["B"],
        "rationale": "Computed value gain +900", "counterparty_pitch": "Not drafted",
        "confidence": 0.45}]}, "Picked by scoring.")
    _render_trade_packages(rec)
    out = capsys.readouterr().out
    assert "PICKED BY SCORING, NOT BY THE AGENT" in out
    assert "+900" in out


def test_duplicate_packages_are_priced_once(valued_ctx):
    """Re-pricing the same players must not let one trade fill every slot."""
    ctx = valued_ctx
    for _ in range(3):
        ctx.dispatch("evaluate_trade", {"send_player_ids": ["wr_spare"],
                                        "receive_player_ids": ["rb_strong"],
                                        "counterparty_team_id": "3"})
    # Same players, different (and omitted) team id — still the same package.
    ctx.dispatch("evaluate_trade", {"send_player_ids": ["wr_spare"],
                                    "receive_player_ids": ["rb_strong"]})
    ctx.dispatch("evaluate_trade", {"receive_player_ids": ["rb_strong"],
                                    "send_player_ids": ["wr_spare"],
                                    "counterparty_team_id": "9"})
    assert len(ctx.evaluations) == 1


def test_counterparty_is_derived_when_the_model_omits_it(valued_ctx):
    """A package with no counterparty renders as 'team None' and can't be sent."""
    ctx = valued_ctx
    ctx.dispatch("evaluate_trade", {"send_player_ids": ["wr_spare"],
                                    "receive_player_ids": ["rb_strong"]})
    assert ctx.evaluations[0]["counterparty_team_id"] == "3"   # rb_strong's owner


def test_counterparty_stays_unset_when_it_cannot_be_derived(valued_ctx):
    """A hand-built player index has no owner data — must not raise."""
    ctx = valued_ctx
    ctx._player_index = {pid: {k: v for k, v in info.items() if k != "owner_team_id"}
                         for pid, info in ctx.player_index().items()}
    ctx.dispatch("evaluate_trade", {"send_player_ids": ["wr_spare"],
                                    "receive_player_ids": ["rb_strong"]})
    assert ctx.evaluations[0]["counterparty_team_id"] is None


# ---- Targets must include the counterparty's starters ---------------------

def test_acquirable_includes_their_starters_not_just_their_bench(valued_ctx):
    """Filtering targets to a team's spare depth makes an upgrade impossible —
    their spare depth is by definition worse than their starters."""
    ctx = valued_ctx
    them = next(r for r in ctx.all_rosters() if r.team_id == "3")
    got = ctx.acquirable(them, [Position.RB])
    tiers = {rp.player.platform_id: tier for rp, _, tier in got}

    # The slot is allocated by VALUE, not by ESPN's slot label: rb_strong2 (1200)
    # outranks rb_strong (1150), so he is the one filling the lineup.
    assert tiers["rb_strong2"] == "starter"    # in their lineup, still listed
    assert tiers["rb_strong"] == "depth"       # spare
    # The better player is surfaced first, which `trade_chips` could never do.
    assert got[0][0].player.platform_id == "rb_strong2"


def test_trade_chips_still_excludes_their_starters(valued_ctx):
    """`acquirable` is for what I GET; `trade_chips` is for what a team can
    spare. The second must keep excluding locked starters."""
    ctx = valued_ctx
    them = next(r for r in ctx.all_rosters() if r.team_id == "3")
    chip_ids = {rp.player.platform_id for rp, _ in ctx.trade_chips(them)}
    assert "rb_strong" in chip_ids             # spare depth
    assert "rb_strong2" not in chip_ids        # fills their lineup


def test_scan_lists_a_starter_as_acquirable(valued_ctx):
    ctx = valued_ctx
    out, _ = ctx.dispatch("find_trade_targets", {"want_position": "RB"})
    assert "IN THEIR LINEUP" in out
    assert "rb_strong2" in out


# ---- An offered starter must not be filtered out -------------------------

def test_a_starter_the_manager_offered_is_still_offerable(valued_ctx):
    """Naming a player IS the authorisation to trade him. Intersecting the
    offer with `trade_chips` silently dropped offered starters, understating
    the budget and making every target look unaffordable."""
    from fantasy_gm.agent.trade.preferences import TradePreferences

    ctx = valued_ctx
    # wr1 is a STARTER (value 2400); wr_spare is bench (900).
    ctx.preferences = TradePreferences(want_positions=[Position.RB],
                                       offerable_ids=["wr1", "wr_spare"])
    out, _ = ctx.dispatch("find_trade_targets", {})
    chips_line = next(ln for ln in out.splitlines() if "My best chips" in ln)
    assert "Pwr1" in chips_line          # the offered starter survived
    assert "Pwr_spare" in chips_line


def test_scan_states_the_combined_offer_budget(valued_ctx):
    """The agent judged targets against ONE chip and declared them
    unaffordable; the combined total is what actually buys an upgrade."""
    from fantasy_gm.agent.trade.preferences import TradePreferences

    ctx = valued_ctx
    ctx.preferences = TradePreferences(offerable_ids=["wr1", "wr_spare"])
    out, _ = ctx.dispatch("find_trade_targets", {"want_position": "RB"})
    assert "COMBINED value of everything I can offer: 3300" in out   # 2400 + 900
    assert "Package SEVERAL chips together" in out


# ---- Withheld players cannot reach a proposal ----------------------------

def _prefs_offering(*ids):
    from fantasy_gm.agent.trade.preferences import TradePreferences
    return TradePreferences(offerable_ids=list(ids))


def test_evaluate_trade_refuses_to_price_a_withheld_player(valued_ctx):
    """Blocked at pricing: a package never scored can never be proposed."""
    ctx = valued_ctx
    ctx.preferences = _prefs_offering("wr_spare")
    out, _ = ctx.dispatch("evaluate_trade", {"send_player_ids": ["wr1"],
                                             "receive_player_ids": ["rb_strong"],
                                             "counterparty_team_id": "3"})
    assert out.startswith("REJECTED")
    assert "Pwr1" in out                 # names who was withheld
    assert "Pwr_spare" in out            # and what IS allowed
    assert ctx.evaluations == []         # not recorded, so not pickable


def test_evaluate_trade_still_prices_an_offered_player(valued_ctx):
    ctx = valued_ctx
    ctx.preferences = _prefs_offering("wr_spare")
    out, _ = ctx.dispatch("evaluate_trade", {"send_player_ids": ["wr_spare"],
                                             "receive_player_ids": ["rb_strong"],
                                             "counterparty_team_id": "3"})
    assert "EV delta" in out
    assert len(ctx.evaluations) == 1


def test_propose_trades_drops_a_package_with_a_withheld_player(valued_ctx):
    import json

    ctx = valued_ctx
    ctx.preferences = _prefs_offering("wr_spare")
    out, _ = ctx.dispatch("propose_trades", {"trades": [
        {"counterparty_team_id": "3", "send_player_ids": ["wr1"],
         "receive_player_ids": ["rb_strong"], "rationale": "r",
         "counterparty_pitch": "p", "confidence": 0.9},
        {"counterparty_team_id": "3", "send_player_ids": ["wr_spare"],
         "receive_player_ids": ["rb_strong"], "rationale": "r",
         "counterparty_pitch": "p", "confidence": 0.7},
    ], "memo": "m", "what_would_change_this": "w"})
    result = json.loads(out)

    assert len(result["trades"]) == 1
    assert result["trades"][0]["send_player_ids"] == ["wr_spare"]
    assert len(result["refused_trades"]) == 1
    assert "did not offer" in result["refused_trades"][0]["refused_because"]


class _ProposesWithheldPlayer:
    """Prices a legal package, then proposes an illegal one anyway."""
    def __init__(self):
        self.calls = 0

    def bind_tools(self, tools, **kwargs):
        return self

    def invoke(self, messages):
        self.calls += 1
        if self.calls == 1:
            return AIMessage(content="", tool_calls=[{
                "name": "evaluate_trade",
                "args": {"send_player_ids": ["wr_spare"],
                         "receive_player_ids": ["rb_strong"],
                         "counterparty_team_id": "3"}, "id": "e1"}])
        return AIMessage(content="", tool_calls=[{
            "name": "propose_trades",
            "args": {"trades": [{
                "counterparty_team_id": "3",
                "send_player_ids": ["wr1"],          # withheld
                "receive_player_ids": ["rb_strong"],
                "rationale": "r", "counterparty_pitch": "p", "confidence": 0.9}],
                "memo": "m", "what_would_change_this": "w"}, "id": "p1"}])


def test_an_all_refused_proposal_falls_back_to_a_legal_package(valued_ctx):
    """Never show a 0%-confidence empty proposal — substitute a legal one."""
    ctx = valued_ctx
    ctx.preferences = _prefs_offering("wr_spare")
    tmp = Path(tempfile.mkdtemp()) / "cp.db"
    record = TradeGraphAgent(AgentConfig(max_llm_calls=4),
                             llm=_ProposesWithheldPlayer(),
                             checkpoint_path=tmp).decide(ctx, verbose=False)
    rec = record.recommendation

    assert rec["selected_deterministically"] is True
    assert len(rec["refused_trades"]) == 1
    # The substituted package only sends what was offered.
    assert rec["trades"][0]["send_player_ids"] == ["wr_spare"]
    assert record.confidence > 0
