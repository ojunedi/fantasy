"""Agent runs: the trace stream, single-flight, and reload-resumability.

The agent is faked — a stub that emits a scripted event list and returns a
fixture DecisionRecord. What is under test is the run plumbing, not the LLM.
"""
from __future__ import annotations

import time
from datetime import datetime

import pytest

from fantasy_gm.models import DecisionRecord, DecisionType

SCRIPT = [
    {"kind": "start", "label": "fake · LineupGraphAgent · week 3 / 2026", "full": False},
    {"kind": "tool_call", "name": "get_my_injury_summary", "args": {},
     "display": "{}", "block": False},
    {"kind": "tool_result", "name": "get_my_injury_summary", "terminal": False,
     "display": "1 player OUT: Tank Bigsby", "block": False},
    {"kind": "ai_text", "text": "Bigsby is out, start Hall.",
     "display": "Bigsby is out, start Hall."},
    {"kind": "tool_call", "name": "optimize_lineup", "args": {},
     "display": "{}", "block": False},
    {"kind": "tool_result", "name": "propose_lineup", "terminal": True,
     "display": "proposed 9 starters", "block": False},
    {"kind": "summary", "tool_count": 3, "elapsed": 12.0, "reached_terminal": True,
     "failed_count": 0, "failed_names": []},
]


def _decision_record(week: int = 3) -> DecisionRecord:
    return DecisionRecord(
        week=week, season=2026, created_at=datetime(2026, 9, 17, 14, 30),
        decision_type=DecisionType.LINEUP,
        inputs_snapshot={"roster": [{"id": "100", "name": "Josh Allen"}]},
        signals_staleness={"projections": 30.0},
        recommendation={"starter_player_ids": ["100", "102"]},
        memo="Start Hall over Bigsby.", confidence=0.8,
    )


class FakeAgent:
    """Emits the scripted trace, then returns a record — like the real agent."""

    record = None
    delay = 0.0
    block = None

    def decide(self, ctx, verbose=True, emit=None):
        # `block` holds the run open so a test can observe it mid-flight; it is
        # waited on once, not per event, so gating a run costs one timeout.
        if self.block is not None and not self.block.wait(timeout=5):
            raise AssertionError("fake agent was never released")
        for event in SCRIPT:
            if self.delay:
                time.sleep(self.delay)
            if emit is not None:
                emit(event)
        return self.record or _decision_record()


@pytest.fixture
def fake_agent(app, monkeypatch):
    agent = FakeAgent()
    app.state.agent_factory = lambda: agent
    # The worker builds its own adapter and league settings; point both at fakes.
    import fantasy_gm.web.runs as runs_mod
    monkeypatch.setattr(runs_mod, "lineup_worker", runs_mod.lineup_worker)
    return agent


@pytest.fixture
def patched_worker(app, fake_adapter, monkeypatch):
    """Make the worker's own adapter the fake one."""
    from fantasy_gm.web import deps
    monkeypatch.setattr(deps, "build_adapter", lambda settings: fake_adapter)
    return fake_adapter


def _start(client, week=3, season=2026, **extra):
    return client.post("/runs", data={"week": week, "season": season, **extra})


def _wait_for(manager_getter, predicate, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = manager_getter()
        if run is not None and predicate(run):
            return run
        time.sleep(0.02)
    raise AssertionError("run did not reach the expected state in time")


# ------------------------------------------------------------------ starting

def test_starting_a_run_returns_the_panel(client, app, fake_agent, patched_worker):
    resp = _start(client)
    assert resp.status_code == 200
    assert "running" in resp.text
    assert "run-trace" in resp.text


def test_run_completes_and_saves_the_decision(client, app, fake_agent, patched_worker, store):
    resp = _start(client)
    run_id = list(app.state.runs._runs)[0]
    run = _wait_for(lambda: app.state.runs.get(run_id), lambda r: r.status == "done")

    assert run.decision_id is not None
    # Saved before `done` was published, so it is already there.
    from uuid import UUID
    assert store.get(UUID(run.decision_id)) is not None


def test_every_scripted_event_reaches_the_buffer_in_order(client, app, fake_agent, patched_worker):
    _start(client)
    run_id = list(app.state.runs._runs)[0]
    run = _wait_for(lambda: app.state.runs.get(run_id), lambda r: r.status == "done")

    kinds = [e["kind"] for e in run.events]
    assert kinds == [e["kind"] for e in SCRIPT] + ["done"]
    assert [e["seq"] for e in run.events] == list(range(len(run.events)))


def test_second_run_for_the_same_week_is_a_409(client, app, patched_worker):
    """A second click must not spend another eight LLM calls."""
    agent = FakeAgent()
    import threading
    agent.block = threading.Event()
    app.state.agent_factory = lambda: agent

    first = _start(client)
    assert first.status_code == 200

    second = _start(client)
    assert second.status_code == 409
    assert "running" in second.text          # it gets the live panel, not an error

    agent.block.set()


def test_a_different_week_may_run_concurrently(client, app, patched_worker):
    import threading
    agent = FakeAgent()
    agent.block = threading.Event()
    app.state.agent_factory = lambda: agent

    assert _start(client, week=3).status_code == 200
    assert _start(client, week=4).status_code == 200
    agent.block.set()


def test_a_finished_week_can_be_rerun(client, app, fake_agent, patched_worker):
    _start(client)
    run_id = list(app.state.runs._runs)[0]
    _wait_for(lambda: app.state.runs.get(run_id), lambda r: r.status == "done")
    assert _start(client).status_code == 200


# -------------------------------------------------------------------- panel

def test_panel_renders_the_full_trace_after_completion(client, app, fake_agent, patched_worker):
    """A reload after the run ends must still show everything it did."""
    _start(client)
    run_id = list(app.state.runs._runs)[0]
    _wait_for(lambda: app.state.runs.get(run_id), lambda r: r.status == "done")

    text = client.get(f"/runs/{run_id}/panel").text
    assert "get_my_injury_summary" in text
    assert "propose_lineup" in text
    assert "Bigsby is out, start Hall." in text
    assert "Review and approve" in text
    # A finished run must not try to reopen a stream.
    assert "sse-connect" not in text


def test_panel_for_an_unknown_run_is_a_404(client):
    assert client.get("/runs/nope/panel").status_code == 404


def test_failed_run_reports_the_error(client, app, patched_worker):
    class Exploding:
        def decide(self, ctx, verbose=True, emit=None):
            raise RuntimeError("provider refused")

    app.state.agent_factory = lambda: Exploding()
    _start(client)
    run_id = list(app.state.runs._runs)[0]
    run = _wait_for(lambda: app.state.runs.get(run_id), lambda r: r.status == "error")
    assert "provider refused" in run.error
    assert "failed" in client.get(f"/runs/{run_id}/panel").text


def test_cancel_stops_the_run(client, app, patched_worker):
    import threading
    agent = FakeAgent()
    agent.block = threading.Event()
    app.state.agent_factory = lambda: agent

    _start(client)
    run_id = list(app.state.runs._runs)[0]
    client.post(f"/runs/{run_id}/cancel")
    agent.block.set()

    run = _wait_for(lambda: app.state.runs.get(run_id), lambda r: r.status == "cancelled")
    assert run.status == "cancelled"


# ----------------------------------------------------------------- streaming

def test_stream_replays_the_backlog(client, app, fake_agent, patched_worker):
    _start(client)
    run_id = list(app.state.runs._runs)[0]
    _wait_for(lambda: app.state.runs.get(run_id), lambda r: r.status == "done")

    body = client.get(f"/runs/{run_id}/stream").text
    assert "get_my_injury_summary" in body
    assert "propose_lineup" in body
    assert body.count("event: trace") == len(SCRIPT) + 1
    assert "event: close" in body


def test_stream_frames_are_one_line_each(client, app, fake_agent, patched_worker):
    """A newline inside `data:` would end the frame early and truncate the row."""
    _start(client)
    run_id = list(app.state.runs._runs)[0]
    _wait_for(lambda: app.state.runs.get(run_id), lambda r: r.status == "done")

    for line in client.get(f"/runs/{run_id}/stream").text.splitlines():
        if line.startswith("data: "):
            assert "\n" not in line[6:]


def test_stream_events_carry_ascending_ids(client, app, fake_agent, patched_worker):
    _start(client)
    run_id = list(app.state.runs._runs)[0]
    _wait_for(lambda: app.state.runs.get(run_id), lambda r: r.status == "done")

    ids = [int(l.split("id: ")[1]) for l in
           client.get(f"/runs/{run_id}/stream").text.splitlines() if l.startswith("id: ")]
    assert ids == sorted(ids)
    assert ids[0] == 0


def test_last_event_id_replays_only_newer_events(client, app, fake_agent, patched_worker):
    """The reconnect contract: a dropped connection resumes, it does not repeat."""
    _start(client)
    run_id = list(app.state.runs._runs)[0]
    _wait_for(lambda: app.state.runs.get(run_id), lambda r: r.status == "done")

    body = client.get(f"/runs/{run_id}/stream", headers={"Last-Event-ID": "2"}).text
    ids = [int(l.split("id: ")[1]) for l in body.splitlines() if l.startswith("id: ")]
    assert ids and min(ids) == 3
    assert "get_my_injury_summary" not in body        # seq 1 and 2, already seen


def test_after_query_param_also_resumes(client, app, fake_agent, patched_worker):
    _start(client)
    run_id = list(app.state.runs._runs)[0]
    _wait_for(lambda: app.state.runs.get(run_id), lambda r: r.status == "done")

    body = client.get(f"/runs/{run_id}/stream?after=4").text
    ids = [int(l.split("id: ")[1]) for l in body.splitlines() if l.startswith("id: ")]
    assert ids and min(ids) == 5


def test_stream_for_an_unknown_run_closes_cleanly(client):
    body = client.get("/runs/nope/stream").text
    assert "event: close" in body


# ------------------------------------------------------------------ registry

def test_registry_is_capped_and_evicts_oldest(app):
    from fantasy_gm.web.runs import RunManager
    manager = RunManager(max_runs=3)
    created = [manager.create("lineup", week, 2026, "8", False) for week in range(5)]
    for run in created:
        manager.finish(run, "done")
    assert manager.get(created[0].id) is None
    assert manager.get(created[-1].id) is not None


def test_subscribe_returns_backlog_atomically(app):
    """Nothing may be lost or duplicated between replay and live."""
    import asyncio

    from fantasy_gm.web.runs import RunManager
    manager = RunManager()
    run = manager.create("lineup", 3, 2026, "8", False)
    for i in range(4):
        manager.publish(run, {"kind": "ai_text", "text": str(i), "display": str(i)})

    queue: asyncio.Queue = asyncio.Queue()
    backlog = manager.subscribe(run, queue, after_seq=1)
    assert [e["seq"] for e in backlog] == [2, 3]
    assert queue.empty()


def test_events_reach_an_open_stream_live(client, app, patched_worker):
    """The thread -> loop handoff: a worker thread's emit must wake a subscriber
    that is already connected, not just show up in a later replay."""
    import threading

    agent = FakeAgent()
    gate = threading.Event()
    agent.block = gate
    app.state.agent_factory = lambda: agent

    _start(client)
    run_id = list(app.state.runs._runs)[0]

    # Released on a timer, not inline: opening the stream blocks until its first
    # byte, and with an empty buffer that byte only arrives once the worker emits.
    threading.Timer(0.3, gate.set).start()

    with client.stream("GET", f"/runs/{run_id}/stream") as response:
        lines = response.iter_lines()
        seen = []
        for line in lines:
            if line.startswith("data: "):
                seen.append(line)
            if line.startswith("event: close"):
                break
        assert any("propose_lineup" in s for s in seen)
        assert any("get_my_injury_summary" in s for s in seen)


def test_a_step_limit_event_is_rendered_in_the_trace(client, app, patched_worker):
    """A run that hits the graph step limit must explain itself in the panel
    rather than surfacing a raw GraphRecursionError."""
    class HitsLimit:
        def decide(self, ctx, verbose=True, emit=None):
            emit({"kind": "step_limit", "limit": 22})
            emit({"kind": "summary", "tool_count": 9, "elapsed": 30.0,
                  "reached_terminal": False, "failed_count": 0, "failed_names": []})
            return _decision_record()

    app.state.agent_factory = lambda: HitsLimit()
    _start(client)
    run_id = list(app.state.runs._runs)[0]
    _wait_for(lambda: app.state.runs.get(run_id), lambda r: r.status == "done")

    text = client.get(f"/runs/{run_id}/panel").text
    assert "step limit" in text
    assert "22 graph steps" in text
    assert "truncated" in text
    assert "GraphRecursionError" not in text
