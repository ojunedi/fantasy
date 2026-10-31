"""Brief integrity tests for the waiver agent (I-26).

The run-level clauses of WADD-09 — the run fails and nothing is surfaced —
are asserted in test_agent.py.
"""
from __future__ import annotations

import pytest

from fantasy_gm.agent.waiver_agent import BriefIntegrityError, validate_brief
from fantasy_gm.models import WaiverScanResult, WaiverScanState

WEEK = 7
SEASON = 2026


def _result() -> WaiverScanResult:
    return WaiverScanResult(
        scan_state=WaiverScanState.RECOMMENDATION,
        candidate="J. Smith",
        displaced_player="B. Jones",
        value_margin=12.5,
        bars_cleared=["relative", "absolute", "startability"],
        candidate_value=21.5,
        displaced_value=9.0,
        candidate_rank=3,
        startable_tier=24,
    )


def test_wadd09_brief_with_untraced_number_is_rejected():
    brief = "Add J. Smith — projects 47.3 points ahead of B. Jones."  # 47.3 not in analysis

    with pytest.raises(BriefIntegrityError) as exc:
        validate_brief(brief, _result(), WEEK, SEASON)

    assert "BRIEF_INTEGRITY_VIOLATION" in str(exc.value)
    assert "47.3" in str(exc.value)


def test_wadd09_brief_quoting_every_analysis_number_passes():
    brief = ("Week 7 of 2026: add J. Smith, the WR3 against a startable tier of 24, "
             "projecting 21.50 to B. Jones's 9 — a 12.5 point margin.")

    validate_brief(brief, _result(), WEEK, SEASON)


def test_wadd09_digit_inside_a_label_must_still_trace():
    # "WR4" carries a 4 the analysis never produced
    with pytest.raises(BriefIntegrityError):
        validate_brief("J. Smith is the WR4 this week.", _result(), WEEK, SEASON)


def test_wadd09_brief_with_no_numbers_passes():
    validate_brief("Add J. Smith over B. Jones.", _result(), WEEK, SEASON)
