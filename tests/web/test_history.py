"""Decision history list and detail."""
from __future__ import annotations

from datetime import datetime

import pytest

from fantasy_gm.models import DecisionRecord, DecisionType, HumanResponse


def _record(week: int = 3, **overrides) -> DecisionRecord:
    base = dict(
        week=week,
        season=2026,
        created_at=datetime(2026, 9, 15, 9, 30),
        decision_type=DecisionType.LINEUP,
        inputs_snapshot={"roster": [
            {"id": "100", "name": "Josh Allen"},
            {"id": "102", "name": "Breece Hall"},
            {"id": "110", "name": "Tank Bigsby"},
        ]},
        signals_staleness={"projections": 240.0, "injuries": 3600.0},
        recommendation={
            "starter_player_ids": ["100", "102"],
            "changes_from_current": [
                {"start_in_player_id": "102", "bench_out_player_id": "110",
                 "reason": "Bigsby is ruled out."},
            ],
            "what_would_change_this": "Bigsby being upgraded before kickoff.",
        },
        memo="Start Hall over Bigsby, who is out.",
        confidence=0.82,
    )
    base.update(overrides)
    return DecisionRecord(**base)


@pytest.fixture
def saved(store):
    record = _record()
    store.save(record)
    return record


def test_history_lists_saved_decisions(client, saved):
    resp = client.get("/history")
    assert resp.status_code == 200
    assert str(saved.id) in resp.text
    assert "1 logged" in resp.text


def test_history_does_not_claim_a_total_it_did_not_query(client, store):
    """The list is capped at 50; the store holds more. Do not invent a total."""
    for i in range(55):
        store.save(_record(week=(i % 14) + 1,
                           created_at=datetime(2026, 9, 1, 0, i)))
    text = client.get("/history").text
    assert "50 most recent" in text
    assert "55 logged" not in text


def test_history_is_newest_first(client, store):
    old = _record(week=1, created_at=datetime(2026, 9, 1))
    new = _record(week=2, created_at=datetime(2026, 9, 8))
    store.save(old)
    store.save(new)
    text = client.get("/history").text
    assert text.index(str(new.id)) < text.index(str(old.id))


def test_empty_history_says_so(client):
    assert "No decisions logged yet" in client.get("/history").text


def test_history_marks_an_abstention(client, store):
    store.save(_record(recommendation={"abstained": True, "missing_information": ["x"]}))
    assert "abstained" in client.get("/history").text


def test_history_marks_a_truncated_run(client, store):
    """A truncated run and an abstention mean different things and must not read alike."""
    store.save(_record(recommendation={"abstained": True, "truncated": True}))
    assert "truncated" in client.get("/history").text


def test_detail_renders_memo_and_confidence(client, saved):
    text = client.get(f"/decisions/{saved.id}").text
    assert "Start Hall over Bigsby" in text
    assert "82%" in text


def test_detail_joins_player_ids_to_names(client, saved):
    """The ids in a record are meaningless on a page; the join is the point."""
    text = client.get(f"/decisions/{saved.id}").text
    assert "Josh Allen" in text
    assert "Breece Hall" in text
    assert ">100<" not in text


def test_detail_shows_the_proposed_changes_with_reasons(client, saved):
    text = client.get(f"/decisions/{saved.id}").text
    assert "Bigsby is ruled out." in text


def test_detail_shows_staleness_as_recorded(client, saved):
    text = client.get(f"/decisions/{saved.id}").text
    assert "projections" in text
    assert "Measured when the decision was made" in text


def test_detail_shows_the_logged_override_reason(client, store):
    record = _record()
    store.save(record)
    store.record_human_response(record.id, HumanResponse.REJECTED,
                                override_reason="Hall's snap count worries me")
    text = client.get(f"/decisions/{record.id}").text
    assert "Hall&#39;s snap count worries me" in text or "snap count worries me" in text


def test_unknown_decision_is_a_404(client):
    import uuid
    assert client.get(f"/decisions/{uuid.uuid4()}").status_code == 404


def test_malformed_decision_id_is_a_404_not_a_500(client):
    assert client.get("/decisions/not-a-uuid").status_code == 404


def test_detail_falls_back_to_the_snapshot_when_espn_is_down(client, fake_adapter, saved):
    """An old decision must still render after ESPN or the roster goes away."""
    def boom(*args, **kwargs):
        raise RuntimeError("espn down")
    fake_adapter.get_roster = boom
    text = client.get(f"/decisions/{saved.id}").text
    assert "Josh Allen" in text
