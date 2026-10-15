"""Round-trip tests: what the dump preserves, and what a restore yields."""
from __future__ import annotations

import json
import sqlite3

from fantasy_gm.db.backup import dump_decisions
from fantasy_gm.db.store import DecisionStore

from .conftest import decision


def _restore(sql: str, path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(sql)
    conn.commit()
    return conn


def _raw_snapshots(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute("SELECT id, inputs_snapshot FROM decisions").fetchall()
    return {r["id"]: r["inputs_snapshot"] for r in rows}


def test_input_snapshots_survive_a_round_trip_unchanged(store, tmp_path):
    """LEDGBAK-03: input snapshots survive a round trip unchanged"""
    for week in (3, 4, 5):
        store.save(decision(week))
    original = _raw_snapshots(store._conn)

    restored = _restore(dump_decisions(store._conn), tmp_path / "restored.db")

    # LEDGBAK-03 THEN every snapshot is byte-identical to the original
    assert _raw_snapshots(restored) == original

    # LEDGBAK-03 AND no snapshot has been rewritten by the backup or restore
    # Compare against the bytes the agent actually saw, not against a
    # re-serialisation of them — key order and separators both matter.
    for raw in _raw_snapshots(restored).values():
        assert raw == json.dumps(decision(3).inputs_snapshot)


def test_the_backtest_runs_against_a_restored_log(store, tmp_path):
    """LEDGBAK-04: the backtest runs against a restored log"""
    for week in (1, 2, 3):
        store.save(decision(week))
    sql = dump_decisions(store._conn)

    restored_path = tmp_path / "restored.db"
    _restore(sql, restored_path).close()
    restored_store = DecisionStore(restored_path)

    # LEDGBAK-04 THEN it completes without error
    weeks = sorted(r.week for r in restored_store.list_recent())
    assert weeks == [1, 2, 3]

    # LEDGBAK-04 AND it rebuilds the weekly scorecards from the restored decisions
    # The scorecards are deliberately not in the dump; a restored database
    # starts with none and the backtest writes them back.
    assert restored_store._conn.execute("SELECT COUNT(*) FROM scorecards").fetchone()[0] == 0
    for week in weeks:
        assert restored_store.list_week(week, 2026)


def test_ac_signal_a_restored_season_keeps_every_week(store, tmp_path, backup_repo):
    """LEDGBAK-01: AC-SIGNAL — a season restored into an empty database keeps every week and rebuilds its scorecards"""
    from fantasy_gm.db.backup import DecisionBackup

    season_weeks = list(range(1, 15))
    for week in season_weeks:
        store.save(decision(week))
    DecisionBackup().back_up(store._conn, week=14, season=2026)

    sql = (backup_repo / "decisions.sql").read_text()
    restored_path = tmp_path / "new-laptop.db"
    _restore(sql, restored_path).close()
    restored = DecisionStore(restored_path)

    # LEDGBAK-01 THEN every week of the season is present after the restore
    assert sorted(r.week for r in restored.list_recent(limit=100)) == season_weeks

    # LEDGBAK-01 AND the input snapshots are the ones the agent saw
    assert _raw_snapshots(restored._conn) == _raw_snapshots(store._conn)

    # LEDGBAK-01 AND the scorecards are rebuilt rather than restored
    assert restored._conn.execute("SELECT COUNT(*) FROM scorecards").fetchone()[0] == 0
