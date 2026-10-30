"""Pre-kickoff nudge check — integration tests.

All tests use a real in-memory SQLite store and a mock notifier so no
osascript process is ever spawned. The clock is injected via `now_utc`.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, call

import pytest

from fantasy_gm.db.store import DecisionStore
from fantasy_gm.models import DecisionRecord, DecisionType, HumanResponse
from fantasy_gm.nudge.check import should_nudge
from fantasy_gm.nudge.notify import MacNotifier, NudgeDeliveryFailed


WEEK = 7
SEASON = 2026
# Sunday 2026-11-08 13:00 ET = 18:00 UTC (EST)
KICKOFF = datetime(2026, 11, 8, 18, 0, 0)
THRESHOLD = 120  # minutes


def _lineup_rec(human_response: HumanResponse | None = None) -> DecisionRecord:
    rec = DecisionRecord(
        week=WEEK,
        season=SEASON,
        created_at=datetime(2026, 11, 7, 20, 0, 0),
        decision_type=DecisionType.LINEUP,
        inputs_snapshot={"roster": []},
        signals_staleness={"projections": 0.5},
        recommendation={"starter_player_ids": ["p1", "p2"]},
        memo="week 7 lineup",
        confidence=0.85,
        human_response=human_response,
    )
    return rec


@pytest.fixture
def store(tmp_path):
    return DecisionStore(tmp_path / "decisions.db")


# ---------------------------------------------------------------------------
# PKICK-01: nudge fires when recommendation is unread at threshold
# ---------------------------------------------------------------------------

def test_pkick01_nudge_fires_at_threshold(store):
    store.save(_lineup_rec(human_response=None))
    # Exactly at threshold boundary (2 hours before kickoff)
    now = KICKOFF - timedelta(minutes=THRESHOLD)

    mock_notifier = MagicMock()
    fired = should_nudge(store, WEEK, SEASON, KICKOFF, notifier=mock_notifier, now_utc=now, threshold_minutes=THRESHOLD)

    # PKICK-01 THEN a nudge is delivered containing the time remaining until kickoff
    assert fired is True
    mock_notifier.notify.assert_called_once()
    call_minutes = mock_notifier.notify.call_args[0][0]
    assert abs(call_minutes - THRESHOLD) < 1  # minutes_remaining ≈ threshold passed to notifier
    # PKICK-01 AND the LineupDecision remains in presented state (nudge is not a state transition)
    reloaded = store.list_week(WEEK, SEASON)
    assert all(r.human_response is None for r in reloaded if r.decision_type == DecisionType.LINEUP)


# PKICK-01 AND the nudge includes the URL or CLI command to open the recommendation
# Verified by inspecting MacNotifier.notify() directly (clause cannot be asserted with a mock notifier)
def test_mac_notifier_includes_command_in_message():
    with patch("fantasy_gm.nudge.notify.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        MacNotifier().notify(90.0)
        script_arg = mock_run.call_args[0][0][-1]
        assert "fantasy-gm-web" in script_arg or "Decisions" in script_arg


# ---------------------------------------------------------------------------
# PKICK-02: nudge fires for a briefed-but-not-presented recommendation
# ---------------------------------------------------------------------------

def test_pkick02_nudge_fires_for_briefed_recommendation(store):
    store.save(_lineup_rec(human_response=None))
    now = KICKOFF - timedelta(minutes=90)

    mock_notifier = MagicMock()
    fired = should_nudge(store, WEEK, SEASON, KICKOFF, notifier=mock_notifier, now_utc=now, threshold_minutes=THRESHOLD)

    # PKICK-02 THEN a nudge is delivered
    assert fired is True
    mock_notifier.notify.assert_called_once()
    # PKICK-02 AND the LineupDecision remains in `briefed` state
    after = store.list_week(WEEK, SEASON)
    assert after[0].human_response is None


# ---------------------------------------------------------------------------
# PKICK-03: no nudge when recommendation is approved
# ---------------------------------------------------------------------------

def test_pkick03_no_nudge_when_approved(store):
    store.save(_lineup_rec(human_response=HumanResponse.APPROVED))
    now = KICKOFF - timedelta(minutes=90)

    mock_notifier = MagicMock()
    fired = should_nudge(store, WEEK, SEASON, KICKOFF, notifier=mock_notifier, now_utc=now, threshold_minutes=THRESHOLD)

    # PKICK-03 THEN no nudge is delivered
    assert fired is False
    mock_notifier.notify.assert_not_called()


# ---------------------------------------------------------------------------
# PKICK-04: no nudge when recommendation is overridden
# ---------------------------------------------------------------------------

def test_pkick04_no_nudge_when_overridden(store):
    store.save(_lineup_rec(human_response=HumanResponse.MODIFIED))
    now = KICKOFF - timedelta(minutes=90)

    mock_notifier = MagicMock()
    fired = should_nudge(store, WEEK, SEASON, KICKOFF, notifier=mock_notifier, now_utc=now, threshold_minutes=THRESHOLD)

    # PKICK-04 THEN no nudge is delivered
    assert fired is False
    mock_notifier.notify.assert_not_called()


# ---------------------------------------------------------------------------
# PKICK-05: no nudge when recommendation is recorded as unactioned (rejected)
# ---------------------------------------------------------------------------

def test_pkick05_no_nudge_when_unactioned(store):
    store.save(_lineup_rec(human_response=HumanResponse.REJECTED))
    now = KICKOFF - timedelta(minutes=90)

    mock_notifier = MagicMock()
    fired = should_nudge(store, WEEK, SEASON, KICKOFF, notifier=mock_notifier, now_utc=now, threshold_minutes=THRESHOLD)

    # PKICK-05 THEN no nudge is delivered
    assert fired is False
    mock_notifier.notify.assert_not_called()


# ---------------------------------------------------------------------------
# PKICK-06: no nudge when no recommendation exists for the current week
# ---------------------------------------------------------------------------

def test_pkick06_no_nudge_when_no_recommendation(store):
    now = KICKOFF - timedelta(minutes=90)

    mock_notifier = MagicMock()
    fired = should_nudge(store, WEEK, SEASON, KICKOFF, notifier=mock_notifier, now_utc=now, threshold_minutes=THRESHOLD)

    # PKICK-06 THEN no nudge is delivered
    assert fired is False
    mock_notifier.notify.assert_not_called()
    # PKICK-06 AND no error is raised (implicit — test would fail with exception)


# ---------------------------------------------------------------------------
# PKICK-07: no nudge when kickoff has already passed
# ---------------------------------------------------------------------------

def test_pkick07_no_nudge_when_kickoff_passed(store):
    store.save(_lineup_rec(human_response=None))
    # 5 minutes after kickoff
    now = KICKOFF + timedelta(minutes=5)

    mock_notifier = MagicMock()
    fired = should_nudge(store, WEEK, SEASON, KICKOFF, notifier=mock_notifier, now_utc=now, threshold_minutes=THRESHOLD)

    # PKICK-07 THEN no nudge is delivered
    assert fired is False
    mock_notifier.notify.assert_not_called()


# ---------------------------------------------------------------------------
# PKICK-08: delivery failure is logged without changing decision state
# ---------------------------------------------------------------------------

def test_pkick08_delivery_failure_logged_state_unchanged(store, tmp_path):
    store.save(_lineup_rec(human_response=None))
    now = KICKOFF - timedelta(minutes=90)

    failing_notifier = MagicMock()
    failing_notifier.notify.side_effect = NudgeDeliveryFailed("permission denied")

    fired = should_nudge(store, WEEK, SEASON, KICKOFF, notifier=failing_notifier, now_utc=now, threshold_minutes=THRESHOLD)

    # PKICK-08 THEN a failure record is written to decisions.db with an as_of timestamp
    row = store._conn.execute("SELECT * FROM nudge_log WHERE week=? AND season=?", (WEEK, SEASON)).fetchone()
    assert row is not None
    assert row["reason"] == "permission denied"
    assert row["failed_at"]  # non-empty ISO timestamp

    # PKICK-08 AND the LineupDecision remains in presented state
    decisions = store.list_week(WEEK, SEASON)
    lineup = next(d for d in decisions if d.decision_type == DecisionType.LINEUP)
    assert lineup.human_response is None

    # PKICK-08 AND the input snapshot is not modified
    assert lineup.inputs_snapshot == {"roster": []}

    # Function returns False on delivery failure (nudge was not successfully delivered)
    assert fired is False


# ---------------------------------------------------------------------------
# PKICK-09: custom threshold is respected
# ---------------------------------------------------------------------------

def test_pkick09_custom_threshold_respected(store):
    store.save(_lineup_rec(human_response=None))
    custom_threshold = 60  # minutes

    mock_notifier = MagicMock()

    # At 75 minutes before kickoff — outside the custom threshold
    now_75 = KICKOFF - timedelta(minutes=75)
    fired_75 = should_nudge(store, WEEK, SEASON, KICKOFF, notifier=mock_notifier, now_utc=now_75, threshold_minutes=custom_threshold)

    # PKICK-09 THEN no nudge is delivered at 75 minutes (outside 60-minute threshold)
    assert fired_75 is False
    mock_notifier.notify.assert_not_called()

    # At 55 minutes before kickoff — inside the custom threshold
    now_55 = KICKOFF - timedelta(minutes=55)
    fired_55 = should_nudge(store, WEEK, SEASON, KICKOFF, notifier=mock_notifier, now_utc=now_55, threshold_minutes=custom_threshold)

    # PKICK-09 AND when checked again with 55 minutes remaining, a nudge is delivered
    assert fired_55 is True
    mock_notifier.notify.assert_called_once()


# ---------------------------------------------------------------------------
# PKICK-10: acceptance signal (manual only — cannot be automated)
# ---------------------------------------------------------------------------

@pytest.mark.skip(reason="PKICK-10 is a manual acceptance-signal test: seed an unread recommendation, run the check script, confirm macOS notification fires and web banner appears, set the lineup, confirm banner disappears")
def test_pkick10_acceptance_signal_manager_sets_lineup_on_time():
    # PKICK-10 THEN the lineup is set before kickoff
    pass
