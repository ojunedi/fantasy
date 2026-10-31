"""A live lineup write that failed: read back, then tell the manager in time."""
from __future__ import annotations

from datetime import datetime

import pytest

from fantasy_gm.db.store import DecisionStore
from fantasy_gm.execute.base import ExecutionPlan, ExecutionResult, LineupMove
from fantasy_gm.execute.failure import report_failed_write
from fantasy_gm.models import DecisionRecord, DecisionType, HumanResponse

SEASON, WEEK = 2026, 6              # week 6 kicks off Sun Oct 18, 1 PM ET = 17:00 UTC
BEFORE = datetime(2026, 10, 18, 14, 50)   # 2h 10m before kickoff
AFTER = datetime(2026, 10, 18, 18, 0)

MOVES = [LineupMove(player_id="102", player_name="Breece Hall", from_slot=20, to_slot=2),
         LineupMove(player_id="110", player_name="Tank Bigsby", from_slot=2, to_slot=20)]
STEPS = ["Breece Hall: BENCH -> RB", "Tank Bigsby: RB -> BENCH"]


class Notifier:
    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    def send(self, body, subtitle=""):
        if self.fail:
            raise RuntimeError("osascript failed")
        self.sent.append((body, subtitle))


class League:
    def __init__(self, slots=None, unreadable=False):
        self.slots = slots if slots is not None else {"102": 20, "110": 2}  # unchanged
        self.unreadable = unreadable

    def get_raw_lineup_slots(self, team_id, week, season):
        if self.unreadable:
            raise ConnectionError("ESPN down")
        return dict(self.slots)


@pytest.fixture
def store(tmp_path):
    return DecisionStore(tmp_path / "decisions.db")


def _approved(store) -> DecisionRecord:
    record = DecisionRecord(
        week=WEEK, season=SEASON, decision_type=DecisionType.LINEUP, inputs_snapshot={},
        signals_staleness={}, recommendation={"starter_player_ids": ["102"]}, memo="",
        confidence=0.8, human_response=HumanResponse.APPROVED,
    )
    store.save(record)
    return record


def _failed(plan=None):
    plan = plan or ExecutionPlan(action_type="set_lineup", moves=list(MOVES),
                                 human_steps=list(STEPS))
    return plan, ExecutionResult(False, dry_run=False, executor="espn_api", plan=plan,
                                 error="ESPN API 500: Internal Server Error")


def test_wfail01_a_failed_write_whose_moves_landed_anyway_is_not_reported(store):
    record = _approved(store)
    plan, result = _failed()
    notifier = Notifier()

    done = report_failed_write(store, record, plan, result,
                               League(slots={"102": 2, "110": 20}), "8", notifier, now=BEFORE)

    # WFAIL-01 THEN no notification is sent
    assert notifier.sent == []
    # WFAIL-01 AND the decision records the write as landed
    outcome = store.get(record.id).outcome
    assert done == "landed"
    assert "write_landed" in outcome and "write_failure" not in outcome


def test_wfail02_a_failed_read_back_still_notifies_and_says_so(store):
    record = _approved(store)
    plan, result = _failed()
    notifier = Notifier()

    report_failed_write(store, record, plan, result, League(unreadable=True), "8",
                        notifier, now=BEFORE)

    # WFAIL-02 THEN a notification is sent
    assert len(notifier.sent) == 1
    # WFAIL-02 AND it says the lineup could not be checked
    assert "Couldn't check the lineup" in notifier.sent[0][0]
    assert store.get(record.id).outcome["write_failure"]["read_back"] == "unreadable"


def test_wfail05_after_kickoff_the_failure_is_recorded_not_notified(store):
    record = _approved(store)
    plan, result = _failed()
    notifier = Notifier()

    report_failed_write(store, record, plan, result, League(), "8", notifier, now=AFTER)

    # WFAIL-05 THEN no notification is sent
    assert notifier.sent == []
    # WFAIL-05 AND the failure is recorded on the decision
    failure = store.get(record.id).outcome["write_failure"]
    assert failure["notified"] is False
    assert failure["minutes_to_kickoff"] < 0


def test_wfail06_the_failure_and_the_notification_attempt_are_recorded_on_the_decision(store):
    record = _approved(store)
    plan, result = _failed()

    report_failed_write(store, record, plan, result, League(), "8", Notifier(), now=BEFORE)

    # WFAIL-06 THEN the decision records when it failed, the error, the moves, and that the manager was notified
    failure = store.get(record.id).outcome["write_failure"]
    assert failure["at"] == BEFORE.isoformat()
    assert failure["error"] == "ESPN API 500: Internal Server Error"
    assert failure["moves"] == STEPS
    assert failure["notified"] is True


def test_wfail07_a_notification_that_cannot_be_delivered_is_recorded_not_raised(store):
    record = _approved(store)
    plan, result = _failed()

    done = report_failed_write(store, record, plan, result, League(), "8",
                               Notifier(fail=True), now=BEFORE)

    # WFAIL-07 THEN no error is raised
    assert done == "recorded"
    # WFAIL-07 AND the decision records that the notification was not delivered, and why
    failure = store.get(record.id).outcome["write_failure"]
    assert failure["notified"] is False
    assert "osascript failed" in failure["notify_error"]


def test_a_quote_in_a_player_name_cannot_break_the_notification():
    from fantasy_gm.nudge.notify import _applescript_string
    assert _applescript_string('Ja\'Marr "The" Chase') == '"Ja\'Marr \\"The\\" Chase"'


def test_only_moves_still_missing_are_listed(store):
    record = _approved(store)
    plan, result = _failed()
    notifier = Notifier()

    # Hall's move landed; Bigsby's did not.
    report_failed_write(store, record, plan, result, League(slots={"102": 2, "110": 2}),
                        "8", notifier, now=BEFORE)

    assert store.get(record.id).outcome["write_failure"]["moves"] == ["Tank Bigsby: RB -> BENCH"]
    assert "Breece Hall" not in notifier.sent[0][0]
