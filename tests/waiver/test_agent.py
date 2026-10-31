"""Integration tests for the waiver scanning agent."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from fantasy_gm.agent.waiver_agent import BriefIntegrityError, run_waiver_scan
from fantasy_gm.db.store import DecisionStore
from fantasy_gm.models import (
    DecisionType,
    LeagueSettings,
    Platform,
    Position,
    RosterSlot,
    ScoringRules,
    Signal,
    WaiverScanState,
    WaiverType,
)
from fantasy_gm.web.context import waiver_view


WEEK = 7
SEASON = 2026


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _signal(source: str, age_seconds: float = 300) -> Signal:
    return Signal(source=source, as_of=_now() - timedelta(seconds=age_seconds), value="ok")


def _settings() -> LeagueSettings:
    return LeagueSettings(
        platform=Platform.ESPN,
        league_id="test",
        season=SEASON,
        team_count=12,
        roster_slots=[
            RosterSlot(slot_id="WR1", position=Position.WR, is_starter=True),
            RosterSlot(slot_id="WR2", position=Position.WR, is_starter=True),
            RosterSlot(slot_id="BE1", position=Position.BENCH, is_starter=False),
        ],
        scoring_rules=ScoringRules(rules=[]),
        waiver_type=WaiverType.SNAKE,
        playoff_start_week=14,
        playoff_weeks=[14, 15, 16],
        regular_season_weeks=list(range(1, 14)),
    )


def _fresh_signals() -> list[Signal]:
    return [_signal("projections"), _signal("injury_report")]


def _candidate_clears_all() -> list[dict]:
    return [{"name": "Good WR", "position": "WR", "ros_value": 80.0,
             "tier_rank": 5, "startable_weeks": 3}]


def _roster_below() -> list[dict]:
    # Two WRs, so naming the displaced player means picking the right one.
    return [{"name": "Solid WR", "position": "WR", "ros_value": 75.0},
            {"name": "Weak WR", "position": "WR", "ros_value": 60.0}]


class FakeLLM:
    """A chat model stand-in: `.invoke` returns a message and counts calls."""

    def __init__(self, reply: str):
        self.reply = reply
        self.calls = 0

    def invoke(self, prompt: str):
        self.calls += 1
        return SimpleNamespace(content=self.reply)


GOOD_BRIEF = "Add Good WR over Weak WR: 80 against 60, a 20 point margin."


@pytest.fixture
def store(tmp_path):
    return DecisionStore(tmp_path / "decisions.db")


# ---------------------------------------------------------------------------
# WADD-01: candidate clearing all bars produces recommendation
# ---------------------------------------------------------------------------

def test_wadd01_candidate_clearing_all_bars_produces_recommendation(store):
    result = run_waiver_scan(
        store, WEEK, SEASON, _settings(),
        candidates=_candidate_clears_all(),
        roster=_roster_below(),
        signals=_fresh_signals(),
        llm=FakeLLM(GOOD_BRIEF),
        now=_now(),
    )

    # WADD-01 THEN the candidate is included in the recommendation with the player it displaces and the value margin named
    assert result.scan_state == WaiverScanState.RECOMMENDATION
    assert result.candidate == "Good WR"
    assert result.displaced_player == "Weak WR"
    assert result.value_margin == 20.0


# ---------------------------------------------------------------------------
# WADD-04: no-candidate output names closest miss and which bar failed
# ---------------------------------------------------------------------------

def test_wadd04_no_candidate_names_closest_miss(store):
    candidates = [
        {"name": "Far WR", "position": "WR", "ros_value": 30.0,
         "tier_rank": 5, "startable_weeks": 3},
        {"name": "Fringe WR", "position": "WR", "ros_value": 40.0,
         "tier_rank": 5, "startable_weeks": 3},
        {"name": "Deep WR", "position": "WR", "ros_value": 35.0,
         "tier_rank": 5, "startable_weeks": 3},
    ]

    result = run_waiver_scan(
        store, WEEK, SEASON, _settings(),
        candidates=candidates,
        roster=_roster_below(),  # worst WR has 60.0 — 40 fails the relative bar
        signals=_fresh_signals(),
        now=_now(),
    )

    # WADD-04 THEN the output names the closest candidate
    assert result.closest_miss == "Fringe WR"
    # WADD-04 AND which condition it failed
    assert result.failed_bar == "relative"
    # WADD-04 AND by how much
    assert result.failed_by == 20.0
    # WADD-04 AND no recommendation is produced
    assert result.scan_state == WaiverScanState.NO_CANDIDATE
    assert result.candidate is None
    # WADD-04 AND no error is raised — reaching here means run_waiver_scan returned
    assert result is not None


def test_closest_miss_prefers_more_bars_cleared_and_reports_the_real_gap(store):
    candidates = [
        # misses the relative bar by 0.5 points
        {"name": "Almost WR", "position": "WR", "ros_value": 59.5,
         "tier_rank": 5, "startable_weeks": 1, "start_gap": 0.0},
        # clears relative and absolute, 2.0 points short of starting
        {"name": "Bench WR", "position": "WR", "ros_value": 70.0,
         "tier_rank": 5, "startable_weeks": 0, "start_gap": 2.0},
    ]

    result = run_waiver_scan(
        store, WEEK, SEASON, _settings(),
        candidates=candidates, roster=_roster_below(),
        signals=_fresh_signals(), now=_now(),
    )

    assert result.closest_miss == "Bench WR"
    assert result.failed_bar == "startability"
    assert result.failed_by == 2.0


# ---------------------------------------------------------------------------
# WADD-05: signal missing provenance halts the run before scoring
# ---------------------------------------------------------------------------

def test_wadd05_signal_missing_provenance_halts_run_before_scoring(store):
    scorer = MagicMock(side_effect=AssertionError("scoring ran"))
    unprovenanced = Signal(source="", as_of=_now(), value="x")

    result = run_waiver_scan(
        store, WEEK, SEASON, _settings(),
        candidates=_candidate_clears_all(),
        roster=_roster_below(),
        signals=[_signal("projections"), unprovenanced],
        now=_now(),
        scorer=scorer,
    )

    # WADD-05 THEN the run halts before any candidate is scored
    scorer.assert_not_called()
    # WADD-05 AND no recommendation is produced
    assert result.scan_state == WaiverScanState.PROVENANCE_ERROR
    assert result.candidate is None
    assert store.list_week(WEEK, SEASON)[0].recommendation["candidate"] is None
    # WADD-05 AND the error names the signal that failed provenance validation
    assert result.failing_source == "#2"  # second in the bundle; it has no other name
    assert "signal '#2'" in store.list_week(WEEK, SEASON)[0].inputs_snapshot["error"]


# ---------------------------------------------------------------------------
# WADD-06: stale signal halts the run and the record carries the reason
# ---------------------------------------------------------------------------

def test_wadd06_stale_signal_writes_record_before_halting(store):
    scorer = MagicMock(side_effect=AssertionError("scoring ran"))
    stale = _signal("injury_report", age_seconds=48 * 3600)

    result = run_waiver_scan(
        store, WEEK, SEASON, _settings(),
        candidates=_candidate_clears_all(),
        roster=_roster_below(),
        signals=[_signal("projections"), stale],
        now=_now(),
        scorer=scorer,
    )

    # WADD-06 THEN the run reports stale and names the failing source
    assert result.scan_state == WaiverScanState.STALE
    assert result.failing_source == "injury_report"
    # WADD-06 AND no recommendation is produced
    scorer.assert_not_called()
    assert result.candidate is None
    # WADD-06 AND the WaiverDecision record is still written to decisions.db with the stale-signal reason before the run reports completion
    records = store.list_week(WEEK, SEASON)
    assert len(records) == 1
    assert records[0].decision_type == DecisionType.WAIVER
    assert records[0].recommendation["scan_state"] == "stale"
    assert records[0].recommendation["failing_source"] == "injury_report"
    assert records[0].inputs_snapshot["error"].startswith("SIGNAL_STALE")


# ---------------------------------------------------------------------------
# WADD-07: recommendation record written to SQLite before run reports completion
# ---------------------------------------------------------------------------

def test_wadd07_recommendation_record_written_before_run_completes(store):
    result = run_waiver_scan(
        store, WEEK, SEASON, _settings(),
        candidates=_candidate_clears_all(),
        roster=_roster_below(),
        signals=_fresh_signals(),
        llm=FakeLLM(GOOD_BRIEF),
        now=_now(),
    )
    records = store.list_week(WEEK, SEASON)

    # A run whose write fails never reports completion: the write sits on the
    # path to the return, not after it.
    broken = MagicMock()
    broken.save.side_effect = RuntimeError("disk full")
    with pytest.raises(RuntimeError, match="disk full"):
        run_waiver_scan(
            broken, WEEK, SEASON, _settings(),
            candidates=_candidate_clears_all(),
            roster=_roster_below(),
            signals=_fresh_signals(),
            llm=FakeLLM(GOOD_BRIEF),
            now=_now(),
        )

    # WADD-07 THEN the WaiverDecision record is written to decisions.db before the run reports completion
    assert result.scan_state == WaiverScanState.RECOMMENDATION
    assert len(records) == 1
    assert records[0].decision_type == DecisionType.WAIVER
    broken.save.assert_called_once()
    # WADD-07 AND the record includes the recommended candidate, the displaced player, and the value margin
    rec_data = records[0].recommendation
    assert rec_data["candidate"] == "Good WR"
    assert rec_data["displaced_player"] == "Weak WR"
    assert rec_data["value_margin"] == 20.0


# ---------------------------------------------------------------------------
# WADD-08: no-add record written with same weight as recommendation
# ---------------------------------------------------------------------------

def test_wadd08_no_add_record_written_with_same_weight(store):
    candidates = [{"name": "Fringe WR", "position": "WR", "ros_value": 40.0,
                   "tier_rank": 5, "startable_weeks": 3}]

    run_waiver_scan(
        store, WEEK, SEASON, _settings(),
        candidates=candidates,
        roster=_roster_below(),
        signals=_fresh_signals(),
        now=_now(),
    )

    records = store.list_week(WEEK, SEASON)
    # WADD-08 THEN a WaiverDecision record is still written to decisions.db before the run reports completion
    assert len(records) == 1
    assert records[0].decision_type == DecisionType.WAIVER
    # WADD-08 AND the record includes the closest candidate, which condition it failed, and by how much
    rec_data = records[0].recommendation
    assert rec_data["closest_miss"] == "Fringe WR"
    assert rec_data["failed_bar"] == "relative"
    assert rec_data["failed_by"] == 20.0


# ---------------------------------------------------------------------------
# WADD-09: brief with an untraced number fails the run, nothing surfaced
# ---------------------------------------------------------------------------

def test_wadd09_untraced_brief_fails_run_and_withholds_recommendation(store):
    llm = FakeLLM("Add Good WR — projects 47.3 points ahead of Weak WR.")

    with pytest.raises(BriefIntegrityError) as exc:
        run_waiver_scan(
            store, WEEK, SEASON, _settings(),
            candidates=_candidate_clears_all(),
            roster=_roster_below(),
            signals=_fresh_signals(),
            llm=llm,
            now=_now(),
        )

    # WADD-09 THEN the brief is rejected and the run fails with a brief-integrity error
    assert "BRIEF_INTEGRITY_VIOLATION" in str(exc.value)
    records = store.list_week(WEEK, SEASON)
    assert len(records) == 1  # the failure is logged like every other outcome (I-19)
    assert records[0].recommendation["scan_state"] == "brief_rejected"
    # WADD-09 AND no recommendation is surfaced to the manager
    view = waiver_view(records[0], active_run=None)
    assert view == {"state": "brief_rejected"}


# ---------------------------------------------------------------------------
# WADD-10: the LLM budget is enforced, not just observed
# ---------------------------------------------------------------------------

def test_wadd10_run_uses_at_most_3_llm_calls(store):
    llm = FakeLLM(GOOD_BRIEF)

    run_waiver_scan(
        store, WEEK, SEASON, _settings(),
        candidates=_candidate_clears_all(),
        roster=_roster_below(),
        signals=_fresh_signals(),
        llm=llm,
        now=_now(),
    )

    record = store.list_week(WEEK, SEASON)[0]
    # WADD-10 THEN the total LLM calls made during the run is ≤ 3
    assert llm.calls <= 3
    assert record.inputs_snapshot["llm_calls"] == llm.calls


def test_wadd10_exhausted_budget_makes_no_call(store):
    llm = FakeLLM(GOOD_BRIEF)

    result = run_waiver_scan(
        store, WEEK, SEASON, _settings(),
        candidates=_candidate_clears_all(),
        roster=_roster_below(),
        signals=_fresh_signals(),
        llm=llm,
        llm_budget=0,
        now=_now(),
    )

    # The guard refuses the call; the recommendation stands without a brief.
    assert llm.calls == 0
    assert result.scan_state == WaiverScanState.RECOMMENDATION
    assert store.list_week(WEEK, SEASON)[0].memo == ""


def test_brief_call_failure_still_logs_the_recommendation(store):
    class DownLLM:
        def invoke(self, prompt):
            raise ConnectionError("provider unreachable")

    result = run_waiver_scan(
        store, WEEK, SEASON, _settings(),
        candidates=_candidate_clears_all(),
        roster=_roster_below(),
        signals=_fresh_signals(),
        llm=DownLLM(),
        now=_now(),
    )

    record = store.list_week(WEEK, SEASON)[0]
    assert result.scan_state == WaiverScanState.RECOMMENDATION
    assert record.recommendation["candidate"] == "Good WR"
    assert record.memo == ""
    assert record.inputs_snapshot["error"].startswith("BRIEF_UNAVAILABLE")


# ---------------------------------------------------------------------------
# WADD-AC-SIGNAL: acceptance signal (manual only)
# ---------------------------------------------------------------------------

@pytest.mark.skip(
    reason="AC-SIGNAL is a manual end-to-end test: run waiver scan, confirm "
           "recommendation appears on /waiver, record intent to claim, "
           "confirm WaiverDecision in decisions.db"
)
def test_wadd_ac_signal_manager_receives_recommendation_and_records_intent():
    # AC-SIGNAL THEN manager acts on a waiver recommendation each Tuesday window
    pass
