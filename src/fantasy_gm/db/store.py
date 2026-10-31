"""
SQLite decision log store.

Every DecisionRecord is written here at creation time, then updated
when the human responds and again when the outcome is recorded.
Schema migrations are applied on first connection.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import UUID

from fantasy_gm.models import DecisionRecord, HumanResponse, WeeklyScorecard


DB_PATH = Path("data/decisions.db")

CREATE_DECISIONS = """
CREATE TABLE IF NOT EXISTS decisions (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    week INTEGER NOT NULL,
    season INTEGER NOT NULL,
    decision_type TEXT NOT NULL,
    inputs_snapshot TEXT NOT NULL,
    signals_staleness TEXT NOT NULL,
    recommendation TEXT NOT NULL,
    memo TEXT NOT NULL,
    confidence REAL NOT NULL,
    human_response TEXT,
    override_reason TEXT,
    modified_recommendation TEXT,
    outcome TEXT,
    outcome_recorded_at TEXT,
    responded_at TEXT
);
"""

CREATE_SCORECARDS = """
CREATE TABLE IF NOT EXISTS scorecards (
    week INTEGER NOT NULL,
    season INTEGER NOT NULL,
    actual_score REAL,
    optimal_score REAL,
    agent_projected_score REAL,
    points_left_on_bench REAL,
    decision_regret REAL,
    baseline_scores TEXT,
    agent_agreement_with_human INTEGER,
    PRIMARY KEY (week, season)
);
"""

CREATE_NUDGE_LOG = """
CREATE TABLE IF NOT EXISTS nudge_log (
    id        INTEGER PRIMARY KEY,
    week      INTEGER NOT NULL,
    season    INTEGER NOT NULL,
    failed_at TEXT NOT NULL,
    reason    TEXT NOT NULL
);
"""

DROP_NUDGE_LOG = "DROP TABLE IF EXISTS nudge_log;"


def _connect(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(CREATE_DECISIONS + CREATE_SCORECARDS + CREATE_NUDGE_LOG)
    # When the manager responded. Added after the table shipped, so older logs
    # gain it here; responses recorded before it existed have no time.
    columns = {row[1] for row in conn.execute("PRAGMA table_info(decisions)")}
    if "responded_at" not in columns:
        conn.execute("ALTER TABLE decisions ADD COLUMN responded_at TEXT")
    conn.commit()
    return conn


class DecisionStore:
    # What has been written and not yet copied off-machine, keyed by database.
    # Shared across instances on purpose: a run opens several stores — the CLI
    # one, the agent's, the web layer's — and the backup at the end of the run
    # has to see what any of them wrote. Set by writes to the decisions table
    # only; a backtest writing seventeen scorecards must not look like
    # seventeen decisions.
    _pending: dict[Path, tuple[int, int]] = {}

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = Path(db_path)
        self._conn = _connect(db_path)

    def save(self, record: DecisionRecord) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO decisions (
                id, created_at, week, season, decision_type,
                inputs_snapshot, signals_staleness, recommendation,
                memo, confidence, human_response, override_reason,
                modified_recommendation, outcome, outcome_recorded_at, responded_at
            ) VALUES (
                :id, :created_at, :week, :season, :decision_type,
                :inputs_snapshot, :signals_staleness, :recommendation,
                :memo, :confidence, :human_response, :override_reason,
                :modified_recommendation, :outcome, :outcome_recorded_at, :responded_at
            )""",
            {
                "id": str(record.id),
                "created_at": record.created_at.isoformat(),
                "week": record.week,
                "season": record.season,
                "decision_type": record.decision_type.value,
                "inputs_snapshot": json.dumps(record.inputs_snapshot),
                "signals_staleness": json.dumps(record.signals_staleness),
                "recommendation": json.dumps(record.recommendation),
                "memo": record.memo,
                "confidence": record.confidence,
                "human_response": record.human_response.value if record.human_response else None,
                "override_reason": record.override_reason,
                "modified_recommendation": json.dumps(record.modified_recommendation) if record.modified_recommendation else None,
                "outcome": json.dumps(record.outcome) if record.outcome else None,
                "outcome_recorded_at": record.outcome_recorded_at.isoformat() if record.outcome_recorded_at else None,
                "responded_at": record.responded_at.isoformat() if record.responded_at else None,
            },
        )
        self._conn.commit()
        DecisionStore._pending[self._db_path] = (record.week, record.season)

    def record_human_response(
        self,
        decision_id: UUID,
        response: HumanResponse,
        override_reason: str | None = None,
        modified_recommendation: dict | None = None,
    ) -> None:
        self._conn.execute(
            """UPDATE decisions SET
                human_response = ?,
                override_reason = ?,
                modified_recommendation = ?,
                responded_at = ?
            WHERE id = ?""",
            (
                response.value,
                override_reason,
                json.dumps(modified_recommendation) if modified_recommendation else None,
                datetime.utcnow().isoformat(),
                str(decision_id),
            ),
        )
        self._conn.commit()
        self._mark_pending(decision_id)

    def record_outcome(self, decision_id: UUID, outcome: dict) -> None:
        self._conn.execute(
            """UPDATE decisions SET outcome = ?, outcome_recorded_at = ? WHERE id = ?""",
            (json.dumps(outcome), datetime.utcnow().isoformat(), str(decision_id)),
        )
        self._conn.commit()
        self._mark_pending(decision_id)

    def get(self, decision_id: UUID) -> DecisionRecord | None:
        row = self._conn.execute(
            "SELECT * FROM decisions WHERE id = ?", (str(decision_id),)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def list_week(self, week: int, season: int) -> list[DecisionRecord]:
        rows = self._conn.execute(
            "SELECT * FROM decisions WHERE week = ? AND season = ? ORDER BY created_at",
            (week, season),
        ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def list_recent(self, limit: int = 50) -> list[DecisionRecord]:
        """Most recent decisions first, across every week and season."""
        rows = self._conn.execute(
            "SELECT * FROM decisions ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def save_scorecard(self, scorecard: WeeklyScorecard) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO scorecards VALUES (
                :week, :season, :actual_score, :optimal_score,
                :agent_projected_score, :points_left_on_bench, :decision_regret,
                :baseline_scores, :agent_agreement_with_human
            )""",
            {
                "week": scorecard.week,
                "season": scorecard.season,
                "actual_score": scorecard.actual_score,
                "optimal_score": scorecard.optimal_score,
                "agent_projected_score": scorecard.agent_projected_score,
                "points_left_on_bench": scorecard.points_left_on_bench,
                "decision_regret": scorecard.decision_regret,
                "baseline_scores": json.dumps({k.value: v for k, v in scorecard.baseline_scores.items()}),
                "agent_agreement_with_human": (
                    int(scorecard.agent_agreement_with_human)
                    if scorecard.agent_agreement_with_human is not None
                    else None
                ),
            },
        )
        self._conn.commit()

    def log_nudge_failure(self, week: int, season: int, reason: str) -> None:
        self._conn.execute(
            "INSERT INTO nudge_log (week, season, failed_at, reason) VALUES (?, ?, ?, ?)",
            (week, season, datetime.utcnow().isoformat(), reason),
        )
        self._conn.commit()

    def _mark_pending(self, decision_id: UUID) -> None:
        row = self._conn.execute(
            "SELECT week, season FROM decisions WHERE id = ?", (str(decision_id),)
        ).fetchone()
        if row is not None:
            DecisionStore._pending[self._db_path] = (row["week"], row["season"])

    def backup_if_dirty(self) -> bool:
        """Copy the decision log off this machine, if anything was written.

        Called at the end of a run rather than inside each write: one run is
        one commit, and no network call sits inside the path NFR-10 protects.
        Returns whether a copy reached the remote; False is never fatal.
        """
        pending = DecisionStore._pending.get(self._db_path)
        if pending is None:
            return True
        from fantasy_gm.db.backup import DecisionBackup

        week, season = pending
        reached_remote = DecisionBackup().back_up(self._conn, week=week, season=season)
        if reached_remote:
            DecisionStore._pending.pop(self._db_path, None)
        return reached_remote

    def _row_to_record(self, row: sqlite3.Row) -> DecisionRecord:
        from fantasy_gm.models import DecisionType
        return DecisionRecord(
            id=UUID(row["id"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            week=row["week"],
            season=row["season"],
            decision_type=DecisionType(row["decision_type"]),
            inputs_snapshot=json.loads(row["inputs_snapshot"]),
            signals_staleness=json.loads(row["signals_staleness"]),
            recommendation=json.loads(row["recommendation"]),
            memo=row["memo"],
            confidence=row["confidence"],
            human_response=HumanResponse(row["human_response"]) if row["human_response"] else None,
            override_reason=row["override_reason"],
            modified_recommendation=json.loads(row["modified_recommendation"]) if row["modified_recommendation"] else None,
            outcome=json.loads(row["outcome"]) if row["outcome"] else None,
            outcome_recorded_at=datetime.fromisoformat(row["outcome_recorded_at"]) if row["outcome_recorded_at"] else None,
            responded_at=datetime.fromisoformat(row["responded_at"]) if row["responded_at"] else None,
        )
