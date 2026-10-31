"""Both surfaces, one verdict.

Drives the real callers — the command line's lineup write with `input`
patched, and the web write step through the test client — across every
decision state and confirmation, and checks they reach the same verdict.
"""
from __future__ import annotations

import builtins

import pytest

from fantasy_gm.memo.cli import _execute_approved_lineup
from fantasy_gm.models import DecisionType, HumanResponse
from tests.web.test_execute import FakeExecutor, _record

STATES = {
    "pending": (None, None),
    "approved": (HumanResponse.APPROVED, None),
    "overridden with a reason": (HumanResponse.MODIFIED, "Hall is healthy"),
    "overridden without one": (HumanResponse.MODIFIED, ""),
    "rejected": (HumanResponse.REJECTED, "Not this week"),
    "declined": (HumanResponse.DECLINED, None),
}
CONFIRMATIONS = ["LIVE", "live", "Live", "LIVE ", " LIVE", ""]


def _verdict(executor: FakeExecutor) -> str:
    """live / dry_run / refused, read off what the executor was asked to do."""
    if not executor.calls:
        return "refused"
    return "live" if executor.calls == [True] else "dry_run"


def _cli_verdict(record, confirmation, monkeypatch) -> str:
    executor = FakeExecutor()
    monkeypatch.setattr(builtins, "input", lambda prompt="": confirmation)
    _execute_approved_lineup(record, executor, team_id="8")
    return _verdict(executor)


def _web_verdict(client, app, record, confirmation) -> str:
    from fantasy_gm.web import deps
    executor = FakeExecutor()
    app.dependency_overrides[deps.get_executor] = lambda: executor
    client.post(f"/decisions/{record.id}/execute", data={"confirm": confirmation})
    return _verdict(executor)


@pytest.mark.parametrize("state", list(STATES))
def test_appgate08_both_surfaces_give_the_same_verdict(client, app, store, monkeypatch, state):
    response, reason = STATES[state]
    record = _record()
    store.save(record)
    if response is not None:
        store.record_human_response(record.id, response, override_reason=reason)
    stored = store.get(record.id)

    verdicts = {c: (_cli_verdict(stored, c, monkeypatch), _web_verdict(client, app, stored, c))
                for c in CONFIRMATIONS}

    # APPGATE-08 THEN both reach the same verdict — live, Dry run or refused — for every combination
    assert all(cli == web for cli, web in verdicts.values()), verdicts
    expected_live = state in ("approved", "overridden with a reason")
    assert verdicts["LIVE"][0] == ("live" if expected_live else "refused")
    assert verdicts["LIVE "][0] == ("dry_run" if expected_live else "refused")


class RecordingTradeExecutor:
    name = "fake-trade"

    def __init__(self):
        self.calls: list[bool] = []

    def plan(self, trade, team_id, week, season):
        from types import SimpleNamespace
        # The three fields the send step reads; a real payload means sendable.
        return SimpleNamespace(human_steps=["send A for B"], notes=[],
                               request_payload={"items": []})

    def execute(self, plan, season, live=False):
        from types import SimpleNamespace
        self.calls.append(live)
        return SimpleNamespace(success=True, dry_run=not live, confirmed=live, message="ok", error=None)


@pytest.mark.parametrize("confirmation", CONFIRMATIONS)
def test_appgate08_cli_trade_send_gives_the_same_verdict(store, monkeypatch, confirmation):
    from fantasy_gm.memo.cli import _send_approved_trade

    record = _record(decision_type=DecisionType.TRADE,
                     recommendation={"trades": [{"counterparty_team_id": "3"}]})
    store.save(record)
    record.human_response = HumanResponse.APPROVED  # as the trade approval step sets it
    executor = RecordingTradeExecutor()
    monkeypatch.setattr(builtins, "input", lambda prompt="": confirmation)

    _send_approved_trade(record, record.recommendation["trades"], executor, "8", store)

    # APPGATE-08 THEN both reach the same verdict — live, Dry run or refused — for every combination
    assert executor.calls == [confirmation == "LIVE"]
    assert store.get(record.id).human_response == HumanResponse.APPROVED
