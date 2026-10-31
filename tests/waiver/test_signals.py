"""Signal validation tests for the waiver agent.

Each signal must carry a source identifier and an as-of timestamp (I-01), and
be younger than its source's freshness threshold (I-02). A source with no
threshold cannot be shown to be fresh, so it fails as stale.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pydantic
import pytest

from fantasy_gm.agent.waiver_agent import SignalError, validate_signals
from fantasy_gm.models import Signal


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _signal(source: str, age_seconds: float, value: str = "v") -> Signal:
    return Signal(source=source, as_of=_now() - timedelta(seconds=age_seconds), value=value)


# ---------------------------------------------------------------------------
# WADD-05: provenance — the run-level halt is asserted in test_agent.py
# ---------------------------------------------------------------------------

def test_wadd05_signal_without_timestamp_cannot_be_constructed():
    # The as-of timestamp is required by the model, so a signal missing one is
    # rejected where it is built, before it can reach the waiver scan at all.
    with pytest.raises(pydantic.ValidationError):
        Signal(source="projections", value="x")


def test_wadd05_signal_with_future_timestamp_fails_provenance():
    signals = [Signal(source="projections", as_of=_now() + timedelta(days=2), value="x")]

    with pytest.raises(SignalError) as exc:
        validate_signals(signals, now=_now())

    assert exc.value.code == "SIGNAL_MISSING_PROVENANCE"
    assert exc.value.signal_label == "projections"


# ---------------------------------------------------------------------------
# WADD-06: freshness — the run-level record is asserted in test_agent.py
# ---------------------------------------------------------------------------

def test_wadd06_stale_signal_is_named():
    stale = _signal("injury_report", age_seconds=48 * 3600)
    fresh = _signal("projections", age_seconds=300)

    with pytest.raises(SignalError) as exc:
        validate_signals([fresh, stale], now=_now())

    assert exc.value.code == "SIGNAL_STALE"
    assert exc.value.signal_label == "injury_report"


def test_wadd06_source_with_no_threshold_fails_as_stale():
    # A brand-new source nobody has set a threshold for: even a minute-old
    # signal from it cannot be shown to be fresh.
    with pytest.raises(SignalError) as exc:
        validate_signals([_signal("fantasypros", age_seconds=60)], now=_now())

    assert exc.value.code == "SIGNAL_STALE"
    assert exc.value.signal_label == "fantasypros"


def test_wadd06_fresh_signals_pass_validation():
    signals = [
        _signal("projections", age_seconds=300),
        _signal("injury_report", age_seconds=1800),
        _signal("roster", age_seconds=0),
        _signal("free_agents", age_seconds=0),
    ]
    validate_signals(signals, now=_now())
