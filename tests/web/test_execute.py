"""Gate 2 — the LIVE confirmation.

This is the most important test file in the suite. Everything else on this site
is a read or a database write; this is the one path that reaches out and changes
something in the real world, irreversibly. The rule is exact-match `LIVE`.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from fantasy_gm.execute.base import Executor, ExecutionPlan, ExecutionResult, LineupMove
from fantasy_gm.models import DecisionRecord, DecisionType, HumanResponse
from fantasy_gm.web import deps

AGENT_STARTERS = ["100", "101", "102", "103", "104", "105", "106", "107", "108"]


class FakeExecutor(Executor):
    """Records exactly what it was asked to do. Never touches the network."""

    name = "fake"

    def __init__(self, noop: bool = False, fail: bool = False):
        self.calls: list[bool] = []
        self.noop = noop
        self.fail = fail
        self.plan_calls: list[tuple] = []

    def plan_set_lineup(self, team_id, week, season, starter_player_ids):
        self.plan_calls.append((team_id, week, season, tuple(starter_player_ids)))
        moves = [] if self.noop else [
            LineupMove(player_id="102", player_name="Breece Hall", from_slot=20, to_slot=2),
            LineupMove(player_id="110", player_name="Tank Bigsby", from_slot=2, to_slot=20),
        ]
        return ExecutionPlan(
            action_type="set_lineup", moves=moves,
            request_payload={"items": [{"playerId": 102}]} if moves else None,
            human_steps=[f"{m.player_name}: BENCH -> RB" for m in moves],
            context={"season": season, "week": week, "team_id": team_id},
        )

    def execute(self, plan, live: bool = False):
        self.calls.append(live)
        if self.fail:
            return ExecutionResult(False, dry_run=not live, executor=self.name,
                                   plan=plan, error="ESPN returned 500")
        return ExecutionResult(True, dry_run=not live, executor=self.name, plan=plan,
                               message="would POST 2 moves" if not live else "POSTed 2 moves")


@pytest.fixture
def fake_executor(app):
    executor = FakeExecutor()
    app.state.executor = executor
    app.dependency_overrides[deps.get_executor] = lambda: executor
    return executor


def _record(**overrides) -> DecisionRecord:
    base = dict(
        week=3, season=2026, created_at=datetime(2026, 9, 17, 12, 0),
        decision_type=DecisionType.LINEUP,
        inputs_snapshot={"roster": []},
        signals_staleness={},
        recommendation={"starter_player_ids": list(AGENT_STARTERS)},
        memo="Bench Bigsby.", confidence=0.8,
    )
    base.update(overrides)
    return DecisionRecord(**base)


@pytest.fixture
def approved(store):
    record = _record()
    store.save(record)
    store.record_human_response(record.id, HumanResponse.APPROVED)
    return record


def _execute(client, record, confirm):
    return client.post(f"/decisions/{record.id}/execute", data={"confirm": confirm})


# ------------------------------------------------- the gate itself

@pytest.mark.parametrize("confirm", [
    "",            # empty — the default
    " ",
    "live",        # wrong case
    "Live",
    "LIVE ",       # trailing space
    " LIVE",
    "LIVE!",
    "yes",
    "y",
    "true",
    "1",
    "LIVELIVE",
    "L I V E",
])
def test_anything_but_the_exact_word_is_a_dry_run(client, approved, fake_executor, confirm):
    resp = _execute(client, approved, confirm)
    assert resp.status_code == 200
    assert fake_executor.calls == [False], f"{confirm!r} must not go live"
    assert "Dry run" in resp.text


def test_exactly_live_executes_for_real(client, approved, fake_executor):
    resp = _execute(client, approved, "LIVE")
    assert fake_executor.calls == [True]
    assert "Sent to ESPN" in resp.text
    assert "Dry run" not in resp.text


def test_a_missing_confirm_field_is_a_dry_run(client, approved, fake_executor):
    """A form posted without the field at all must never be treated as consent."""
    resp = client.post(f"/decisions/{approved.id}/execute", data={})
    assert resp.status_code == 200
    assert fake_executor.calls == [False]


def test_dry_run_offers_the_form_again(client, approved, fake_executor):
    resp = _execute(client, approved, "")
    assert "Type LIVE" in resp.text


def test_a_live_write_does_not_re_offer_the_form(client, approved, fake_executor):
    """Nothing should invite you to send the same write twice."""
    resp = _execute(client, approved, "LIVE")
    assert "Type LIVE" not in resp.text


# ------------------------------------------- the client cannot supply the plan

def test_the_plan_is_recomputed_server_side(client, approved, fake_executor):
    """The browser supplies a decision id and a word. Never moves, never a payload."""
    _execute(client, approved, "LIVE")
    team_id, week, season, starters = fake_executor.plan_calls[-1]
    assert (team_id, week, season) == ("8", 3, 2026)
    assert set(starters) == set(AGENT_STARTERS)


def test_a_client_supplied_payload_is_ignored(client, approved, fake_executor):
    client.post(f"/decisions/{approved.id}/execute", data={
        "confirm": "LIVE",
        "request_payload": '{"items": [{"playerId": 999}]}',
        "moves": "999",
        "team_id": "1",
    })
    team_id, _, _, starters = fake_executor.plan_calls[-1]
    assert team_id == "8"
    assert "999" not in starters


def test_execution_follows_the_modified_starters(client, store, fake_executor):
    """After a human override, the write must carry the human's lineup."""
    record = _record()
    store.save(record)
    mine = [p for p in AGENT_STARTERS if p != "106"] + ["109"]
    store.record_human_response(record.id, HumanResponse.MODIFIED,
                                override_reason="my call",
                                modified_recommendation={"starter_player_ids": mine})
    _execute(client, record, "LIVE")
    _, _, _, starters = fake_executor.plan_calls[-1]
    assert set(starters) == set(mine)


# ----------------------------------------------------------- failure handling

def test_a_failed_write_falls_back_to_manual_steps(client, approved, app):
    """Mirror the CLI: when ESPN rejects the write, tell them how to do it by hand."""
    executor = FakeExecutor(fail=True)
    app.state.executor = executor
    app.dependency_overrides[deps.get_executor] = lambda: executor

    resp = _execute(client, approved, "LIVE")
    assert "ESPN rejected the write" in resp.text
    assert "ESPN returned 500" in resp.text
    import html
    assert "Breece Hall: BENCH -> RB" in html.unescape(resp.text)


def test_a_noop_plan_reports_nothing_to_do(client, approved, app):
    executor = FakeExecutor(noop=True)
    app.state.executor = executor
    app.dependency_overrides[deps.get_executor] = lambda: executor
    resp = _execute(client, approved, "LIVE")
    assert executor.calls == [True]
    assert resp.status_code == 200


def test_execute_on_an_unknown_decision_is_a_404(client, fake_executor):
    import uuid
    resp = client.post(f"/decisions/{uuid.uuid4()}/execute", data={"confirm": "LIVE"})
    assert resp.status_code == 404
    assert fake_executor.calls == []


def test_gate_two_is_reachable_from_the_decision_page(client, approved, fake_executor):
    """A reload must never strand an approved decision with no way to execute."""
    page = client.get(f"/decisions/{approved.id}").text
    assert "Plan the lineup change" in page
    plan = client.post(f"/decisions/{approved.id}/plan").text
    assert "Type LIVE" in plan


# ------------------------------------------------- the shared approval gate

def test_appgate07_web_write_step_refuses_an_unapproved_decision(client, store, fake_executor):
    record = _record()
    store.save(record)  # pending: no human response

    resp = client.post(f"/decisions/{record.id}/execute", data={
        "confirm": "LIVE", "approved": "1", "human_response": "approved",
    })

    # APPGATE-07 THEN the response is a refusal with status 409
    assert resp.status_code == 409
    assert "Nothing was sent" in resp.text
    # APPGATE-07 AND the executor is not called
    assert fake_executor.calls == []
    assert fake_executor.plan_calls == []
    # APPGATE-07 AND the decision's state in the decision log is unchanged
    assert store.get(record.id).human_response is None


def test_appgate06_a_live_execution_does_not_authorise_the_next_one(client, store, approved,
                                                                   fake_executor):
    _execute(client, approved, "LIVE")
    second = _execute(client, approved, "")

    # APPGATE-06 THEN the second execution is a Dry run
    assert fake_executor.calls == [True, False]
    assert "Dry run" in second.text
    # APPGATE-06 AND the decision log holds no record of the earlier authorisation
    stored = store.get(approved.id)
    assert stored.human_response == HumanResponse.APPROVED
    assert "LIVE" not in str(stored.model_dump())


@pytest.mark.parametrize("decision_type", [DecisionType.TRADE, DecisionType.WAIVER])
def test_appgate10_web_write_step_refuses_an_approved_decision_that_is_not_a_lineup(
        client, store, fake_executor, decision_type):
    record = _record(decision_type=decision_type, recommendation={"trades": []})
    store.save(record)
    store.record_human_response(record.id, HumanResponse.APPROVED)

    resp = _execute(client, record, "LIVE")

    # APPGATE-10 THEN the response is a refusal with status 409
    assert resp.status_code == 409
    assert "not a lineup" in resp.text
    # APPGATE-10 AND no lineup is planned or written
    assert fake_executor.plan_calls == []
    assert fake_executor.calls == []


def test_refusals_and_validation_errors_reach_the_page(client):
    # htmx drops 4xx bodies unless told otherwise; 409 and 422 must swap.
    page = client.get("/history").text
    assert '"code":"4(09|22)","swap":true' in page


# ------------------------------------------------- a failed write reaches the manager

def _week_of_kickoff_soon(store):
    """An approved decision for the week whose kickoff is ~2h away."""
    from fantasy_gm.nudge.missed import week_kickoff
    record = _record(week=6, season=2026)
    store.save(record)
    store.record_human_response(record.id, HumanResponse.APPROVED)
    return record, week_kickoff(2026, 6)


def test_wfail04_a_confirmed_failure_before_kickoff_notifies_with_the_moves_and_time_left(
        client, app, store, monkeypatch):
    from datetime import timedelta

    import fantasy_gm.execute.failure as failure_mod

    record, kickoff = _week_of_kickoff_soon(store)
    failing = FakeExecutor(fail=True)
    app.dependency_overrides[deps.get_executor] = lambda: failing

    class Clock:
        @staticmethod
        def utcnow():
            return kickoff - timedelta(hours=2, minutes=10)
    monkeypatch.setattr(failure_mod, "datetime", Clock)

    _execute(client, record, "LIVE")
    sent = app.state.notifier.sent

    sent_plan = failing.plan_set_lineup("8", 6, 2026, AGENT_STARTERS)
    # WFAIL-04 THEN the notification lists the moves from the plan that was sent
    assert len(sent) == 1
    assert sent[0][0].endswith("Set it by hand: " + "; ".join(sent_plan.human_steps))
    # WFAIL-04 AND it says kickoff is in 2h 10m
    assert sent[0][1] == "Kickoff in 2h 10m"
    assert "Couldn't check" not in sent[0][0]  # the read-back worked: say nothing of the sort


@pytest.mark.parametrize("case", ["dry_run", "success", "refused"])
def test_wfail03_a_dry_run_a_success_or_a_refusal_never_notifies(client, app, store, case,
                                                                 monkeypatch):
    from datetime import timedelta

    import fantasy_gm.execute.failure as failure_mod

    record, kickoff = _week_of_kickoff_soon(store)

    class Clock:  # before kickoff, so a notification would be sent if one were due
        @staticmethod
        def utcnow():
            return kickoff - timedelta(hours=1)
    monkeypatch.setattr(failure_mod, "datetime", Clock)
    executor = FakeExecutor()
    app.dependency_overrides[deps.get_executor] = lambda: executor
    if case == "refused":
        pending = _record(week=6, season=2026)
        store.save(pending)
        record = pending

    _execute(client, record, "" if case == "dry_run" else "LIVE")

    # WFAIL-03 THEN no notification is sent
    assert app.state.notifier.sent == []
    # WFAIL-03 AND nothing is recorded as a write failure
    assert "write_failure" not in (store.get(record.id).outcome or {})


def test_wfail04_the_command_line_write_notifies_too(store):
    """The weekly run's path: the command-line prompt, with a notifier passed in."""
    import builtins
    from datetime import timedelta
    from unittest.mock import patch

    import fantasy_gm.execute.failure as failure_mod
    from fantasy_gm.memo.cli import _execute_approved_lineup
    from tests.web.conftest import RecordingNotifier

    record, kickoff = _week_of_kickoff_soon(store)
    executor = FakeExecutor(fail=True)
    executor.adapter = type("League", (), {
        "get_raw_lineup_slots": lambda self, team, week, season: {"102": 20, "110": 2}})()
    notifier = RecordingNotifier()

    class Clock:
        @staticmethod
        def utcnow():
            return kickoff - timedelta(minutes=45)

    with patch.object(builtins, "input", lambda prompt="": "LIVE"), \
         patch.object(failure_mod, "datetime", Clock):
        _execute_approved_lineup(store.get(record.id), executor, "8", store, notifier)

    # WFAIL-04 THEN the notification lists the moves from the plan that was sent
    assert len(notifier.sent) == 1
    assert "Breece Hall" in notifier.sent[0][0]
    # WFAIL-04 AND it says kickoff is in 45m
    assert notifier.sent[0][1] == "Kickoff in 45m"
    assert store.get(record.id).outcome["write_failure"]["notified"] is True
