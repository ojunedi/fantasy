"""Trade runs: the brief form, dispatch by kind, and single-flight.

The trade agent is faked. What is under test is that the four brief fields make
it from an HTML form into a `TradePreferences` unchanged, and that a trade run
and a lineup run are tracked independently.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime

import pytest

from fantasy_gm.agent.trade.preferences import TradePreferences
from fantasy_gm.models import DecisionRecord, DecisionType, Position
from fantasy_gm.web.runs import _preferences_from_brief

TRADE_SCRIPT = [
    {"kind": "start", "label": "fake · TradeGraphAgent · week 2 / 2026", "full": False},
    {"kind": "tool_call", "name": "find_trade_targets", "args": {},
     "display": "{}", "block": False},
    {"kind": "tool_result", "name": "find_trade_targets", "terminal": False,
     "display": "3 teams with gettable WRs", "block": False},
    {"kind": "tool_call", "name": "evaluate_trade", "args": {},
     "display": "{}", "block": False},
    {"kind": "tool_result", "name": "propose_trades", "terminal": True,
     "display": "1 package", "block": False},
    {"kind": "summary", "tool_count": 2, "elapsed": 40.0, "reached_terminal": True,
     "failed_count": 0, "failed_names": []},
]


def _trade_record() -> DecisionRecord:
    return DecisionRecord(
        week=2, season=2026, created_at=datetime(2026, 9, 18, 10, 0),
        decision_type=DecisionType.TRADE,
        inputs_snapshot={"my_team_id": "8", "team_count": 12, "tool_calls": []},
        signals_staleness={},
        recommendation={"trades": [{
            "counterparty_team_id": "6",
            "send_player_ids": ["103"], "receive_player_ids": ["203"],
            "send_names": ["Ja'Marr Chase"], "receive_names": ["CeeDee Lamb"],
            "rationale": "Consolidates WR depth.",
            "counterparty_pitch": "You're thin at WR.",
            "confidence": 0.72,
        }], "memo": "Acquire an elite WR.",
            "what_would_change_this": "A Lamb injury."},
        memo="Acquire an elite WR.", confidence=0.72,
    )


class FakeTradeAgent:
    record = None
    block = None
    seen_preferences = None

    def decide(self, ctx, verbose=True, emit=None):
        FakeTradeAgent.seen_preferences = ctx.preferences
        if self.block is not None and not self.block.wait(timeout=5):
            raise AssertionError("fake trade agent was never released")
        for event in TRADE_SCRIPT:
            if emit is not None:
                emit(event)
        return self.record or _trade_record()


@pytest.fixture
def trade_agent(app, fake_adapter, monkeypatch):
    FakeTradeAgent.seen_preferences = None
    agent = FakeTradeAgent()
    app.state.trade_agent_factory = lambda: agent
    from fantasy_gm.web import deps
    monkeypatch.setattr(deps, "build_adapter", lambda settings: fake_adapter)
    # The real TradeToolContext reaches nflverse and FantasyCalc on construction
    # of its caches; the fake agent never touches them, but the worker builds the
    # context, so keep league settings coming from the fake adapter.
    return agent


def _start_trade(client, **extra):
    data = {"week": 2, "season": 2026, "kind": "trade"}
    data.update(extra)
    return client.post("/runs", data=data)


def _wait(getter, predicate, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = getter()
        if run is not None and predicate(run):
            return run
        time.sleep(0.02)
    raise AssertionError("run never reached the expected state")


# ---------------------------------------------------- brief -> preferences

def test_an_empty_brief_means_no_constraints():
    """Skipping every field must behave exactly like skipping the CLI interview."""
    prefs = _preferences_from_brief({"want_positions": [], "offerable_ids": [],
                                     "target_ids": [], "notes": ""})
    assert prefs.is_empty()


def test_a_missing_brief_is_also_empty():
    assert _preferences_from_brief(None).is_empty()


def test_positions_are_parsed_into_enum_members():
    prefs = _preferences_from_brief({"want_positions": ["WR", "rb"]})
    assert prefs.want_positions == [Position.WR, Position.RB]


def test_unknown_positions_are_dropped_not_crashed():
    prefs = _preferences_from_brief({"want_positions": ["WR", "PUNTER", ""]})
    assert prefs.want_positions == [Position.WR]


def test_non_tradeable_positions_are_refused():
    """The interview only ever offered QB/RB/WR/TE; a K or D/ST is not a target."""
    prefs = _preferences_from_brief({"want_positions": ["K", "DST"]})
    assert prefs.want_positions == []


def test_ids_and_notes_pass_through(monkeypatch):
    prefs = _preferences_from_brief({
        "offerable_ids": ["101", "102"], "target_ids": ["203"],
        "notes": "  don't touch my RBs  ",
    })
    assert prefs.offerable_ids == ["101", "102"]
    assert prefs.target_ids == ["203"]
    assert prefs.notes == "don't touch my RBs"


def test_offerable_ids_are_a_hard_constraint():
    """This is the field that actually blocks packages, so confirm the object
    we build enforces it."""
    prefs = _preferences_from_brief({"offerable_ids": ["101"]})
    assert prefs.forbidden_sends(["101"]) == []
    assert prefs.forbidden_sends(["999"]) == ["999"]


# ------------------------------------------------------------- dispatch

def test_a_trade_run_starts_and_saves_a_record(client, app, trade_agent, store):
    resp = _start_trade(client)
    assert resp.status_code == 200
    run_id = list(app.state.runs._runs)[0]
    run = _wait(lambda: app.state.runs.get(run_id), lambda r: r.status == "done")

    from uuid import UUID
    saved = store.get(UUID(run.decision_id))
    assert saved is not None
    assert saved.decision_type == DecisionType.TRADE


def test_the_run_is_labelled_a_trade(client, app, trade_agent):
    resp = _start_trade(client)
    assert "trade" in resp.text


def test_the_form_brief_reaches_the_agent(client, app, trade_agent):
    """The whole point of the form: these four values must arrive intact."""
    _start_trade(client, want_positions=["WR"], offerable_ids=["101", "102"],
                 target_ids=["203"], notes="only depth")
    run_id = list(app.state.runs._runs)[0]
    _wait(lambda: app.state.runs.get(run_id), lambda r: r.status == "done")

    prefs = FakeTradeAgent.seen_preferences
    assert isinstance(prefs, TradePreferences)
    assert prefs.want_positions == [Position.WR]
    assert prefs.offerable_ids == ["101", "102"]
    assert prefs.target_ids == ["203"]
    assert prefs.notes == "only depth"


def test_an_empty_form_gives_the_agent_empty_preferences(client, app, trade_agent):
    _start_trade(client)
    run_id = list(app.state.runs._runs)[0]
    _wait(lambda: app.state.runs.get(run_id), lambda r: r.status == "done")
    assert FakeTradeAgent.seen_preferences.is_empty()


def test_an_unknown_run_kind_is_refused(client):
    resp = client.post("/runs", data={"week": 2, "season": 2026, "kind": "waivers"})
    assert resp.status_code == 400


# --------------------------------------------------------- single-flight

def test_a_second_trade_run_for_the_week_is_a_409(client, app, trade_agent):
    trade_agent.block = threading.Event()
    assert _start_trade(client).status_code == 200
    assert _start_trade(client).status_code == 409
    trade_agent.block.set()


def test_a_trade_run_and_a_lineup_run_can_overlap(client, app, trade_agent):
    """Different kinds are tracked separately — one must not block the other."""
    trade_agent.block = threading.Event()
    assert _start_trade(client).status_code == 200

    from tests.web.test_runs import FakeAgent
    lineup = FakeAgent()
    lineup.block = threading.Event()
    app.state.agent_factory = lambda: lineup
    assert client.post("/runs", data={"week": 2, "season": 2026}).status_code == 200

    trade_agent.block.set()
    lineup.block.set()


def test_the_trace_shows_the_brief_when_one_was_given(client, app, trade_agent):
    """A run constrained by a brief must say so, or the output looks arbitrary."""
    run = app.state.runs.create("trade", 2, 2026, "8", supervised=False)
    app.state.runs.publish(run, {"kind": "brief", "summary": "acquire WR; offering 2 players"})
    text = client.get(f"/runs/{run.id}/panel").text
    assert "your brief" in text
    assert "acquire WR" in text
