"""Startup comparison: which weeks the backup holds that the local log does not."""
from __future__ import annotations

from fantasy_gm.db.backup import DecisionBackup, dump_decisions
from fantasy_gm.db.store import DecisionStore

from .conftest import decision


def _backup_holding(backup_repo, weeks, tmp_path) -> None:
    """Put a dump covering `weeks` into the backup repository."""
    source = DecisionStore(tmp_path / "source.db")
    for week in weeks:
        source.save(decision(week))
    (backup_repo / "decisions.sql").write_text(dump_decisions(source._conn))


def test_the_local_log_is_missing_weeks_the_backup_holds(store, backup_repo, tmp_path):
    """LEDGBAK-08: the local log is missing weeks the backup holds"""
    _backup_holding(backup_repo, [1, 2, 3, 4, 5], tmp_path)
    for week in (1, 2, 5):
        store.save(decision(week))
    before = {r.id for r in store.list_recent(limit=100)}

    missing = DecisionBackup().missing_weeks(store._conn)

    # LEDGBAK-08 THEN the manager is shown a message naming weeks 3 and 4 as
    # missing locally
    assert missing == [(3, 2026), (4, 2026)]

    # LEDGBAK-08 AND no restore is performed automatically
    # LEDGBAK-08 AND the local decision log is not modified
    assert {r.id for r in store.list_recent(limit=100)} == before
    assert sorted(r.week for r in store.list_recent(limit=100)) == [1, 2, 5]


def test_the_local_log_is_level_with_or_ahead_of_the_backup(store, backup_repo, tmp_path):
    """LEDGBAK-09: the local log is level with or ahead of the backup"""
    _backup_holding(backup_repo, [1, 2, 3], tmp_path)
    for week in (1, 2, 3, 4):   # ahead: holds a week the backup does not
        store.save(decision(week))

    missing = DecisionBackup().missing_weeks(store._conn)

    # LEDGBAK-09 THEN no missing-week message is shown
    assert missing == []

    # LEDGBAK-09 AND startup proceeds
    # Nothing raised, and the local log is untouched by the comparison.
    assert sorted(r.week for r in store.list_recent(limit=100)) == [1, 2, 3, 4]


def test_no_backup_configured_reports_nothing_missing(store, monkeypatch):
    # Not a scenario — a guard that startup survives an unconfigured backup
    # rather than crashing before it can report anything.
    monkeypatch.delenv("FANTASY_GM_BACKUP_REPO", raising=False)
    assert DecisionBackup().missing_weeks(store._conn) == []
