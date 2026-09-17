"""Gate 1 — approve / modify / reject, and the plan preview it produces."""
from __future__ import annotations

from datetime import datetime

import pytest

from fantasy_gm.models import DecisionRecord, DecisionType, HumanResponse

# 100 Josh Allen, 102 Breece Hall, 103 Chase, 104 Nacua, 105 McBride,
# 106 Waddle, 107 Ravens, 108 Butker, 101 Bijan
AGENT_STARTERS = ["100", "101", "102", "103", "104", "105", "106", "107", "108"]


def _record(**overrides) -> DecisionRecord:
    base = dict(
        week=3, season=2026, created_at=datetime(2026, 9, 17, 12, 0),
        decision_type=DecisionType.LINEUP,
        inputs_snapshot={"roster": [{"id": "110", "name": "Tank Bigsby"}]},
        signals_staleness={"projections": 30.0},
        recommendation={"starter_player_ids": list(AGENT_STARTERS),
                        "what_would_change_this": "Bigsby being activated."},
        memo="Bench Bigsby, he is out.", confidence=0.81,
    )
    base.update(overrides)
    return DecisionRecord(**base)


@pytest.fixture
def saved(store):
    record = _record()
    store.save(record)
    return record


def _respond(client, record, **data):
    return client.post(f"/decisions/{record.id}/respond", data=data)


# ------------------------------------------------------------------- reject

def test_reject_requires_a_reason(client, saved, store):
    """The override reason is the point of the log — an empty one is refused."""
    resp = _respond(client, saved, action="reject", override_reason="")
    assert resp.status_code == 422
    assert "Say why" in resp.text
    assert store.get(saved.id).human_response is None


def test_reject_with_a_reason_is_logged(client, saved, store):
    resp = _respond(client, saved, action="reject",
                    override_reason="Hall's snaps are trending down")
    assert resp.status_code == 200
    stored = store.get(saved.id)
    assert stored.human_response == HumanResponse.REJECTED
    assert stored.override_reason == "Hall's snaps are trending down"


def test_reject_offers_no_execution(client, saved):
    resp = _respond(client, saved, action="reject", override_reason="no")
    assert "Plan the lineup change" not in resp.text


# ------------------------------------------------------------------- modify

def test_modify_records_the_ticked_starters(client, saved, store):
    mine = AGENT_STARTERS[:-1] + ["110"]
    resp = _respond(client, saved, action="modify", override_reason="I trust Bigsby",
                    starter_player_ids=mine)
    assert resp.status_code == 200
    stored = store.get(saved.id)
    assert stored.human_response == HumanResponse.MODIFIED
    assert stored.modified_recommendation["starter_player_ids"] == mine


def test_modify_preserves_the_rest_of_the_recommendation(client, saved, store):
    """Only the starter list is replaced; the agent's reasoning is not discarded."""
    _respond(client, saved, action="modify", override_reason="hunch",
             starter_player_ids=["100"])
    stored = store.get(saved.id)
    assert stored.modified_recommendation["what_would_change_this"] == "Bigsby being activated."


def test_modify_requires_a_reason(client, saved, store):
    resp = _respond(client, saved, action="modify", override_reason="",
                    starter_player_ids=["100"])
    assert resp.status_code == 422
    assert store.get(saved.id).human_response is None


def test_modify_requires_at_least_one_starter(client, saved, store):
    resp = _respond(client, saved, action="modify", override_reason="because")
    assert resp.status_code == 422
    assert store.get(saved.id).human_response is None


# ------------------------------------------------------------------ approve

def test_approve_is_logged_and_shows_the_plan(client, saved, store):
    resp = _respond(client, saved, action="approve", starter_player_ids=AGENT_STARTERS)
    assert resp.status_code == 200
    assert store.get(saved.id).human_response == HumanResponse.APPROVED
    assert "Execution plan" in resp.text


def test_approve_needs_no_reason(client, saved, store):
    resp = _respond(client, saved, action="approve", starter_player_ids=AGENT_STARTERS)
    assert resp.status_code == 200


def test_plan_lists_real_espn_slot_moves(client, saved):
    """The fixture roster starts Bigsby (OUT) at RB and benches Hall, so the
    plan must move both, labelled with ESPN slot names."""
    resp = _respond(client, saved, action="approve", starter_player_ids=AGENT_STARTERS)
    assert "Breece Hall" in resp.text
    assert "Tank Bigsby" in resp.text
    assert "BENCH" in resp.text
    assert "RB" in resp.text


def test_plan_shows_the_exact_request_body_behind_a_disclosure(client, saved):
    resp = _respond(client, saved, action="approve", starter_player_ids=AGENT_STARTERS)
    assert "<details>" in resp.text
    assert "fromLineupSlotId" in resp.text


def test_approving_a_changed_lineup_is_recorded_as_a_modification(client, saved, store):
    """Silently approving a lineup the human altered would corrupt the
    agent-vs-human agreement record."""
    mine = AGENT_STARTERS[:-1] + ["110"]
    resp = _respond(client, saved, action="approve", override_reason="my call",
                    starter_player_ids=mine)
    assert resp.status_code == 200
    stored = store.get(saved.id)
    assert stored.human_response == HumanResponse.MODIFIED
    assert stored.modified_recommendation["starter_player_ids"] == mine


def test_approving_a_changed_lineup_without_a_reason_is_refused(client, saved, store):
    mine = AGENT_STARTERS[:-1] + ["110"]
    resp = _respond(client, saved, action="approve", starter_player_ids=mine)
    assert resp.status_code == 422
    assert store.get(saved.id).human_response is None


def test_plan_is_built_from_the_modified_starters(client, saved, store):
    """After a modification, the plan must follow the human's list, not the agent's."""
    # Swap the agent's flex (Waddle) for Odunze — a lineup that is legal, and
    # different from both the agent's list and what ESPN currently has.
    mine = [p for p in AGENT_STARTERS if p != "106"] + ["109"]
    _respond(client, saved, action="modify", override_reason="Odunze's target share",
             starter_player_ids=mine)
    resp = client.post(f"/decisions/{saved.id}/plan")
    assert resp.status_code == 200
    # Odunze comes in and Waddle goes to the bench — the human's list, not the agent's.
    assert "Rome Odunze" in resp.text
    assert "Jaylen Waddle" in resp.text
    assert "BENCH" in resp.text


# -------------------------------------------------------------------- noop

def test_a_lineup_that_already_matches_offers_no_execution(client, store, roster):
    """If ESPN already has this lineup there is nothing to send, and the page
    must say so rather than offering a pointless write."""
    current = [rp.player.platform_id for rp in roster.players if rp.is_starter]
    record = _record(recommendation={"starter_player_ids": current})
    store.save(record)
    resp = client.post(f"/decisions/{record.id}/respond",
                       data={"action": "approve", "starter_player_ids": current})
    assert "already matches" in resp.text
    assert "Type LIVE" not in resp.text


# ------------------------------------------------------------ gate on reload

def test_gate_stays_reachable_after_approval(client, saved, store):
    """A reload must never lose the ability to execute an approved decision."""
    _respond(client, saved, action="approve", starter_player_ids=AGENT_STARTERS)
    page = client.get(f"/decisions/{saved.id}").text
    assert "Plan the lineup change" in page


def test_abstained_decision_offers_no_gate(client, store):
    record = _record(recommendation={"abstained": True, "missing_information": ["x"]})
    store.save(record)
    page = client.get(f"/decisions/{record.id}").text
    assert "Approve lineup" not in page
    assert "agent abstained" in page.lower()


def test_truncated_run_says_rerun_rather_than_abstained(client, store):
    record = _record(recommendation={"abstained": True, "truncated": True})
    store.save(record)
    page = client.get(f"/decisions/{record.id}").text
    assert "cut off" in page
    assert "Re-run the week" in page


def test_respond_to_unknown_decision_is_a_404(client):
    import uuid
    resp = client.post(f"/decisions/{uuid.uuid4()}/respond", data={"action": "approve"})
    assert resp.status_code == 404
