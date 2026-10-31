"""
Off-machine backup of the decision log.

After a run writes a decision, a SQL dump of the `decisions` table alone is
committed to a private git repository the manager created and configured.
The scorecards are deliberately excluded: they are recomputed by one backtest
run, and including them would make a backtest writing seventeen of them look
like seventeen decisions.

The backup is always additional. A decision is durable in SQLite before
anything here runs, so every failure path leaves the decision intact, names
what went wrong, and lets the run finish.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

DUMP_NAME = "decisions.sql"

# The repository is created by the manager, with its remote already configured
# — the same way every other external dependency here is pointed at rather than
# provisioned. Unset means no backup is configured.
BACKUP_REPO_ENV = "FANTASY_GM_BACKUP_REPO"


def backup_repo_path() -> Path | None:
    configured = os.environ.get(BACKUP_REPO_ENV, "").strip()
    return Path(configured) if configured else None


def _literal(value: object) -> str:
    """Render a stored value as a SQL literal, without interpreting it.

    Text is taken exactly as SQLite holds it and only its quotes are escaped.
    Nothing here parses JSON, reformats a timestamp, or reorders keys — a
    snapshot that went in as the agent saw it comes out the same bytes, which
    is what invariant I-10 depends on.
    """
    if value is None:
        return "NULL"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, bytes):
        return "X'" + value.hex() + "'"
    return "'" + str(value).replace("'", "''") + "'"


def dump_decisions(conn: sqlite3.Connection) -> str:
    """A SQL dump of the `decisions` table alone.

    Rows are ordered by id so that unchanged data produces an unchanged file,
    and an unchanged file produces no commit. `Connection.iterdump` is not
    used: it would pull in the scorecards, and a backtest writing seventeen of
    them would then look like seventeen decisions worth committing.
    """
    from fantasy_gm.db.store import CREATE_DECISIONS

    columns = [row[1] for row in conn.execute("PRAGMA table_info(decisions)")]
    lines = ["BEGIN TRANSACTION;", CREATE_DECISIONS.strip()]
    for row in conn.execute(
        f"SELECT {', '.join(columns)} FROM decisions ORDER BY id"
    ):
        values = ", ".join(_literal(v) for v in row)
        # Columns named, so a dump stays loadable as the table gains columns.
        lines.append(f"INSERT INTO decisions ({', '.join(columns)}) VALUES({values});")
    lines.append("COMMIT;")
    return "\n".join(lines) + "\n"


class BackupNotConfigured(Exception):
    """The repository is absent, is not a git repository, or has no remote."""


class DecisionBackup:
    """Commits the decision log to the repository the manager configured.

    Every method here is best-effort by design. The decision is already
    durable in SQLite before any of this runs (NFR-10), so a failure costs
    the off-machine copy of one write and nothing else.
    """

    def __init__(self, repo: Path | None = None):
        self._repo = repo if repo is not None else backup_repo_path()

    @property
    def repo(self) -> Path | None:
        return self._repo

    def _git(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", "-C", str(self._repo), *args],
            capture_output=True, text=True,
        )

    def _check_configured(self) -> None:
        if self._repo is None:
            raise BackupNotConfigured(
                f"no backup repository configured — set {BACKUP_REPO_ENV} to a "
                "private git repository with a remote"
            )
        if not (self._repo / ".git").exists():
            raise BackupNotConfigured(
                f"{self._repo} is not a git repository"
            )
        if not self._git("remote").stdout.strip():
            raise BackupNotConfigured(
                f"{self._repo} has no remote configured — the backup would "
                "never leave this machine"
            )

    def back_up(self, conn: sqlite3.Connection, week: int, season: int) -> bool:
        """Dump, commit and push. Returns whether the copy reached the remote.

        Never raises into the caller: a run that produced a decision finishes
        whether or not the decision reached the remote.
        """
        try:
            self._check_configured()
            dump_path = self._repo / DUMP_NAME
            dump_path.write_text(dump_decisions(conn))

            self._git("add", DUMP_NAME)
            # Nothing staged means nothing changed — no empty commit.
            if self._git("diff", "--cached", "--quiet").returncode == 0:
                return True

            message = f"decisions through week {week}, season {season}"
            commit = self._git("commit", "-m", message)
            if commit.returncode != 0:
                raise BackupNotConfigured(commit.stderr.strip() or "commit failed")

            push = self._git("push", "-u", "origin", "HEAD")
            if push.returncode != 0:
                # The commit stands locally; only the push failed. Trusting
                # the exit status is deliberate — see design.md. Unlike the
                # ESPN endpoints ADR-002 was written about, git reports a
                # failed push as a failure.
                logger.warning(
                    "Decision log backup: could not reach the remote for week %s, "
                    "season %s — the decision is safe locally and committed to %s, "
                    "but it has not left this machine. %s",
                    week, season, self._repo, push.stderr.strip(),
                )
                return False
            return True
        except BackupNotConfigured as exc:
            logger.warning(
                "Decision log backup skipped for week %s, season %s: %s. "
                "The decision is written locally and the run is unaffected.",
                week, season, exc,
            )
            return False

    def missing_weeks(self, conn: sqlite3.Connection) -> list[tuple[int, int]]:
        """Weeks the backup holds that the local decision log does not.

        The dump is restored into an in-memory database and queried, rather
        than scraped with a regular expression — the file is already readable
        by the thing that wrote it, and a second, weaker reader of the same
        format is a bug waiting for an apostrophe.

        Reports only. Nothing here restores anything or touches the local log.
        """
        if self._repo is None:
            return []
        dump_path = self._repo / DUMP_NAME
        if not dump_path.exists():
            return []

        scratch = sqlite3.connect(":memory:")
        try:
            scratch.executescript(dump_path.read_text())
            backed_up = {
                (row[0], row[1])
                for row in scratch.execute("SELECT DISTINCT week, season FROM decisions")
            }
        except sqlite3.Error as exc:
            logger.warning(
                "Decision log backup: could not read %s to compare weeks (%s). "
                "Startup continues; the local log is untouched.", dump_path, exc,
            )
            return []
        finally:
            scratch.close()

        local = {
            (row[0], row[1])
            for row in conn.execute("SELECT DISTINCT week, season FROM decisions")
        }
        return sorted(backed_up - local)

    def report_missing_weeks(self, conn: sqlite3.Connection) -> list[tuple[int, int]]:
        """Name every week held off-machine but not locally. Reports only."""
        missing = self.missing_weeks(conn)
        if missing:
            weeks = ", ".join(f"week {w} of {s}" for w, s in missing)
            logger.warning(
                "The backup holds decisions this machine does not: %s. "
                "Nothing has been restored — restore by importing %s if this is "
                "a replacement machine.",
                weeks, self._repo / DUMP_NAME,
            )
        return missing
