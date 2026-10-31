"""The one gate in front of every ESPN write.

Live only from an approved or overridden decision confirmed with exactly
`LIVE`; a dry run for any other confirmation; refused outright when the
decision carries no approval, or an override carries no reason.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from fantasy_gm.db.store import DecisionStore
from fantasy_gm.execute.gate import Verdict, authorise
from fantasy_gm.models import DecisionRecord, DecisionType, HumanResponse

NOT_LIVE = ["live", "Live", "LIVE ", " LIVE", ""]


@pytest.fixture
def store(tmp_path):
    return DecisionStore(tmp_path / "decisions.db")


def _decision(store, response=None, reason=None) -> DecisionRecord:
    """Save a lineup decision, give it a response through the store, read it back."""
    record = DecisionRecord(
        week=3, season=2026, decision_type=DecisionType.LINEUP,
        inputs_snapshot={}, signals_staleness={},
        recommendation={"starter_player_ids": ["100"]}, memo="", confidence=0.8,
    )
    store.save(record)
    if response is not None:
        store.record_human_response(record.id, response, override_reason=reason)
    return store.get(record.id)


def test_appgate01_approved_decision_confirmed_with_live_writes(store):
    auth = authorise(_decision(store, HumanResponse.APPROVED), "LIVE")

    # APPGATE-01 THEN the gate authorises a live write
    assert auth.verdict is Verdict.LIVE
    # APPGATE-01 AND the executor is called with live set
    assert auth.live is True


def test_appgate02_overridden_decision_with_a_reason_confirmed_with_live_writes(store):
    record = _decision(store, HumanResponse.MODIFIED, reason="Hall is healthy, Bigsby is out")

    # APPGATE-02 THEN the gate authorises a live write
    assert authorise(record, "LIVE").verdict is Verdict.LIVE


@pytest.mark.parametrize("confirmation", NOT_LIVE + [None])
def test_appgate03_anything_but_exactly_live_is_a_dry_run(store, confirmation):
    auth = authorise(_decision(store, HumanResponse.APPROVED), confirmation)

    # APPGATE-03 THEN the gate authorises a Dry run
    assert auth.verdict is Verdict.DRY_RUN
    # APPGATE-03 AND the executor is called with live unset
    assert auth.live is False
    assert not auth.refused


@pytest.mark.parametrize("confirmation", NOT_LIVE)
def test_appgate03_dry_run_transmits_nothing_to_espn(store, monkeypatch, confirmation):
    from fantasy_gm.execute.base import ExecutionPlan, LineupMove
    from fantasy_gm.execute.espn_api import ESPNApiExecutor

    def _no_network(*args, **kwargs):
        raise AssertionError("a dry run reached the network")
    monkeypatch.setattr("fantasy_gm.execute.espn_api.httpx.post", _no_network)
    monkeypatch.setenv("ESPN_SWID", "{swid}")
    monkeypatch.setenv("ESPN_S2", "s2")

    executor = ESPNApiExecutor(adapter=None)
    plan = ExecutionPlan(
        action_type="set_lineup",
        moves=[LineupMove(player_id="102", player_name="Breece Hall", from_slot=20, to_slot=2)],
        request_payload={"items": [{"playerId": 102}]},
        human_steps=["Breece Hall: BENCH -> RB"],
        context={"season": 2026, "week": 3, "team_id": "8"},
    )
    auth = authorise(_decision(store, HumanResponse.APPROVED), confirmation)
    result = executor.execute(plan, live=auth.live)

    # APPGATE-03 AND nothing is transmitted to ESPN
    assert result.success and result.dry_run


@pytest.mark.parametrize("response,state", [
    (None, "pending"),
    (HumanResponse.REJECTED, "rejected"),
    (HumanResponse.DECLINED, "declined"),
])
def test_appgate04_pending_rejected_or_declined_decision_is_refused(store, response, state):
    auth = authorise(_decision(store, response), "LIVE")

    # APPGATE-04 THEN the gate refuses it
    assert auth.verdict is Verdict.REFUSED
    assert auth.code == "NOT_APPROVED"
    # APPGATE-04 AND the refusal names the decision's state
    assert state in auth.message
    # APPGATE-04 AND the executor is not called
    assert auth.refused and not auth.live


@pytest.mark.parametrize("reason", [None, "", "   "])
def test_appgate05_override_without_a_written_reason_is_refused(store, reason):
    auth = authorise(_decision(store, HumanResponse.MODIFIED, reason=reason), "LIVE")

    # APPGATE-05 THEN the gate refuses it
    assert auth.verdict is Verdict.REFUSED
    # APPGATE-05 AND the refusal says the written reason is missing
    assert auth.code == "OVERRIDE_REASON_MISSING"
    assert "no written reason" in auth.message
    # APPGATE-05 AND the executor is not called
    assert auth.refused and not auth.live


def _live_literals(path: Path) -> list[int]:
    """Lines holding the bare string constant `LIVE`, however it is used —
    `== "LIVE"`, `in ("LIVE",)`, `case "LIVE":`, a constant alias. Prompt text
    that merely mentions LIVE is a longer string and does not count."""
    tree = ast.parse(path.read_text())
    return [node.lineno for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and node.value == "LIVE"]


def test_appgate09_no_code_outside_the_gate_compares_against_live():
    src = Path(__file__).resolve().parents[2] / "src" / "fantasy_gm"
    holding = sorted(str(path.relative_to(src)) for path in src.rglob("*.py")
                     if _live_literals(path))

    # APPGATE-09 THEN the only one is inside the gate
    assert holding == ["execute/gate.py"]
