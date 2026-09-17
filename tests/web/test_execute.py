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
