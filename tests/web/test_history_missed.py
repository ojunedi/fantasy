"""The decision history shows a missed week and its projected cost."""
from __future__ import annotations

from datetime import datetime

from fantasy_gm.models import DecisionRecord, DecisionType, HumanResponse


def test_lmiss08_history_shows_missed_with_the_projected_cost(client, store):
    record = DecisionRecord(
        week=6, season=2026, created_at=datetime(2026, 10, 14, 15, 0),
        decision_type=DecisionType.LINEUP, inputs_snapshot={}, signals_staleness={},
        recommendation={"starter_player_ids": ["A"]}, memo="", confidence=0.8,
    )
    store.save(record)
    store.record_outcome(record.id, {"missed": {"cost": 7.5}})

    page = client.get("/history").text

    # LMISS-08 THEN the decision's row shows "missed" and "−7.5 proj"
    assert ">missed</span>" in page
    assert "−7.5 proj" in page


def test_a_late_tiny_cost_reads_no_cost(client, store):
    record = DecisionRecord(
        week=6, season=2026, created_at=datetime(2026, 10, 14, 15, 0),
        decision_type=DecisionType.LINEUP, inputs_snapshot={}, signals_staleness={},
        recommendation={"starter_player_ids": ["A"]}, memo="", confidence=0.8,
    )
    store.save(record)
    store.record_outcome(record.id, {"missed": {"cost": 0.03}})
    store.record_human_response(record.id, HumanResponse.APPROVED)

    page = client.get("/history").text

    assert "no cost" in page
    assert "approved after kickoff" in page


def test_history_still_renders_when_the_league_cannot_be_read(client, store, fake_adapter):
    record = DecisionRecord(
        week=1, season=2026, created_at=datetime(2026, 9, 2, 15, 0),
        decision_type=DecisionType.LINEUP, inputs_snapshot={"projections": {"A": 1.0}},
        signals_staleness={}, recommendation={"starter_player_ids": ["A"]}, memo="",
        confidence=0.8,
    )
    store.save(record)
    fake_adapter.get_roster = lambda *a, **k: (_ for _ in ()).throw(ConnectionError("down"))

    resp = client.get("/history")

    assert resp.status_code == 200
    assert store.get(record.id).outcome is None


def test_lmiss11_opening_the_history_records_a_settled_missed_week(client, store, fake_adapter):
    # Week 1 of 2026 kicked off Sep 13 and settled Sep 15 — long past.
    record = DecisionRecord(
        week=1, season=2026, created_at=datetime(2026, 9, 9, 15, 0),
        decision_type=DecisionType.LINEUP,
        inputs_snapshot={"projections": {"100": 30.0, "109": 5.0}}, signals_staleness={},
        recommendation={"starter_player_ids": ["100"]}, memo="", confidence=0.8,
    )
    store.save(record)
    fake_adapter.get_actual_scores = lambda week, season: {}

    page = client.get("/history").text

    # LMISS-11 THEN the week is recorded as missed
    missed = store.get(record.id).outcome["missed"]
    assert missed["recommended_projected"] == 30.0
    # LMISS-11 AND the row shows it
    assert ">missed</span>" in page
