"""DecisionStore persistence round-trips and listing order."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from fantasy_gm.db.store import DecisionStore
from fantasy_gm.models import DecisionRecord, DecisionType, HumanResponse


def _record(week: int, season: int = 2026, created_at: datetime | None = None) -> DecisionRecord:
    return DecisionRecord(
        week=week,
        season=season,
        created_at=created_at or datetime(2026, 9, 1) + timedelta(days=week),
        decision_type=DecisionType.LINEUP,
        inputs_snapshot={"roster": []},
        signals_staleness={"projections": 12.0},
        recommendation={"starter_player_ids": ["1", "2"]},
        memo=f"week {week} memo",
        confidence=0.7,
    )


@pytest.fixture
def store(tmp_path):
    return DecisionStore(tmp_path / "decisions.db")


def test_save_and_get_round_trips(store):
    rec = _record(3)
    store.save(rec)
    loaded = store.get(rec.id)
    assert loaded is not None
    assert loaded.week == 3
    assert loaded.memo == "week 3 memo"
    assert loaded.recommendation == {"starter_player_ids": ["1", "2"]}


def test_get_missing_returns_none(store):
    assert store.get(_record(1).id) is None


def test_list_recent_is_newest_first(store):
    for week in (1, 2, 3):
        store.save(_record(week))
    assert [r.week for r in store.list_recent()] == [3, 2, 1]


def test_list_recent_honours_limit(store):
    for week in range(1, 6):
        store.save(_record(week))
    recent = store.list_recent(limit=2)
    assert [r.week for r in recent] == [5, 4]


def test_list_recent_spans_seasons(store):
    store.save(_record(1, season=2025, created_at=datetime(2025, 9, 1)))
    store.save(_record(1, season=2026, created_at=datetime(2026, 9, 1)))
    assert [r.season for r in store.list_recent()] == [2026, 2025]


def test_list_recent_empty_store(store):
    assert store.list_recent() == []


def test_list_recent_includes_the_human_response(store):
    rec = _record(4)
    store.save(rec)
    store.record_human_response(rec.id, HumanResponse.REJECTED, override_reason="gut call")
    loaded = store.list_recent()[0]
    assert loaded.human_response == HumanResponse.REJECTED
    assert loaded.override_reason == "gut call"
