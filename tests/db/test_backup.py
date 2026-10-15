"""Commit, push, failure paths, and what the dump must never contain."""
from __future__ import annotations

import os

import pytest

from fantasy_gm.db.backup import DecisionBackup, dump_decisions
from fantasy_gm.db.store import DecisionStore

from .conftest import decision, git, scorecard


def test_the_dump_is_inspected_for_secrets(store, live_secrets):
    """LEDGBAK-07: the dump is inspected for secrets"""
    store.save(decision(5))

    sql = dump_decisions(store._conn)

    # LEDGBAK-07 THEN no ESPN session cookie value appears in it
    assert live_secrets["ESPN_S2"] not in sql
    assert live_secrets["ESPN_SWID"] not in sql

    # LEDGBAK-07 AND no API key value appears in it
    assert live_secrets["ANTHROPIC_API_KEY"] not in sql

    # LEDGBAK-07 AND no value read from the environment appears in it
    # Every environment value, not just the three above — a column added
    # later that happens to carry one is caught here.
    for name, value in os.environ.items():
        if len(value) >= 12 and not value.startswith("/"):
            assert value not in sql, f"{name} leaked into the dump"


def _run_that_records(store, rec) -> tuple[str, list[str]]:
    """A stand-in for a run: record a decision, back up, carry on.

    `steps` is what distinguishes "reports complete" from "is not aborted" —
    an aborted run never reaches the work that follows the backup.
    """
    steps: list[str] = []
    store.save(rec)
    steps.append("decision recorded")
    store.backup_if_dirty()
    steps.append("work after the backup")
    return "complete", steps


def _commit_count(repo) -> int:
    out = git(repo, "rev-list", "--all", "--count").stdout.strip()
    return int(out or 0)


def test_a_recorded_decision_is_committed_off_machine(store, backup_repo, remote):
    """LEDGBAK-01: a recorded decision is committed off-machine"""
    store.save(decision(5))

    store.backup_if_dirty()

    # LEDGBAK-01 THEN a SQL dump of the decision log exists in the backup repository
    dump = backup_repo / "decisions.sql"
    assert dump.exists()

    # LEDGBAK-01 AND the dump contains the week 5 decision
    assert "week 5 memo" in dump.read_text()

    # LEDGBAK-01 AND a commit exists whose message names week 5 and season 2026
    message = git(backup_repo, "log", "-1", "--format=%s").stdout
    assert "week 5" in message and "2026" in message

    # LEDGBAK-01 AND the commit is present on the remote
    local_head = git(backup_repo, "rev-parse", "HEAD").stdout.strip()
    remote_heads = git(remote, "rev-list", "--all").stdout.split()
    assert local_head in remote_heads


def test_computed_scorecards_are_not_committed(store, backup_repo):
    """LEDGBAK-02: computed scorecards are not committed"""
    store.save(decision(1))
    store.backup_if_dirty()
    before = _commit_count(backup_repo)
    dump_before = (backup_repo / "decisions.sql").read_text()

    for week in range(1, 18):
        store.save_scorecard(scorecard(week))
    store.backup_if_dirty()

    # LEDGBAK-02 THEN no new commit is created in the backup repository
    assert _commit_count(backup_repo) == before

    # LEDGBAK-02 AND the decision log dump is unchanged
    assert (backup_repo / "decisions.sql").read_text() == dump_before


def test_the_remote_is_unreachable(store, backup_repo, caplog):
    """LEDGBAK-05: the remote is unreachable"""
    git(backup_repo, "remote", "set-url", "origin", "/nonexistent/remote.git")
    rec = decision(7)

    with caplog.at_level("WARNING"):
        outcome, steps = _run_that_records(store, rec)

    # LEDGBAK-05 THEN the manager is shown a message naming the backup failure
    # and the week it affects
    assert "backup" in caplog.text.lower()
    assert "week 7" in caplog.text

    # LEDGBAK-05 AND the decision remains present and readable in the local log
    # Read through a fresh connection: a decision that is only in this
    # process's memory is not durable.
    reopened = DecisionStore(store._db_path)
    assert reopened.get(rec.id) is not None
    assert reopened.get(rec.id).memo == "week 7 memo"

    # LEDGBAK-05 AND the run reports complete
    assert outcome == "complete"

    # LEDGBAK-05 AND the run is not aborted
    # An aborted run would never reach the work that follows the backup.
    assert steps == ["decision recorded", "work after the backup"]

    # LEDGBAK-05 AND the decision is not rolled back
    assert len(reopened.list_week(7, 2026)) == 1


def test_the_backup_repository_is_missing_or_has_no_remote(store, tmp_path, monkeypatch, caplog):
    """LEDGBAK-06: the backup repository is missing or has no remote configured"""
    import subprocess
    no_remote = tmp_path / "no-remote"
    subprocess.run(["git", "init", "-q", str(no_remote)], check=True)
    git(no_remote, "config", "user.email", "t@e.com")
    git(no_remote, "config", "user.name", "T")
    monkeypatch.setenv("FANTASY_GM_BACKUP_REPO", str(no_remote))
    rec = decision(2)

    with caplog.at_level("WARNING"):
        outcome, steps = _run_that_records(store, rec)

    # LEDGBAK-06 THEN the manager is shown a message naming what is not configured
    assert "remote" in caplog.text.lower()

    # LEDGBAK-06 AND the decision is written to the local decision log
    assert DecisionStore(store._db_path).get(rec.id) is not None

    # LEDGBAK-06 AND the run reports complete
    assert outcome == "complete"
    assert steps == ["decision recorded", "work after the backup"]

    # LEDGBAK-06 AND no partial or empty commit is created
    assert _commit_count(no_remote) == 0


def test_no_backup_repository_is_configured_at_all(store, tmp_path, monkeypatch, caplog):
    """LEDGBAK-06: the backup repository is missing or has no remote configured (nothing configured)"""
    # The other half of this scenario's GIVEN, and the state of every machine
    # before setup: the setting is unset entirely.
    monkeypatch.delenv("FANTASY_GM_BACKUP_REPO", raising=False)
    rec = decision(4)

    with caplog.at_level("WARNING"):
        outcome, steps = _run_that_records(store, rec)

    # LEDGBAK-06 THEN the manager is shown a message naming what is not configured
    assert "no backup repository configured" in caplog.text.lower()
    assert "FANTASY_GM_BACKUP_REPO" in caplog.text

    # LEDGBAK-06 AND the decision is written to the local decision log
    assert DecisionStore(store._db_path).get(rec.id) is not None

    # LEDGBAK-06 AND the run reports complete
    assert outcome == "complete"
    assert steps == ["decision recorded", "work after the backup"]

    # LEDGBAK-06 AND no partial or empty commit is created
    # Nothing was written anywhere: no dump file exists outside a repository.
    assert list(tmp_path.glob("**/decisions.sql")) == []
