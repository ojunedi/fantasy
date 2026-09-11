"""Tests for usage / opportunity trends and breakout detection."""
import pytest

from fantasy_gm.core.usage import opportunity_score, usage_summary


def _wk(week, targets=0, carries=0, ts=0.0, ays=0.0, snap=0.0):
    return {"week": week, "targets": targets, "carries": carries,
            "target_share": ts, "air_yards_share": ays, "snap_share": snap,
            "player_id": "p1"}


def test_opportunity_score_monotone_in_targets():
    lo = opportunity_score(2, 0, 0.1, 0.1, 0.5)
    hi = opportunity_score(10, 0, 0.1, 0.1, 0.5)
    assert hi > lo


def test_opportunity_score_capped_at_100():
    assert opportunity_score(30, 30, 1.0, 1.0, 1.0) == 100.0


def test_window_averages_last_n_games():
    rows = [_wk(1, targets=2), _wk(2, targets=4), _wk(3, targets=6), _wk(4, targets=12)]
    prof = usage_summary(rows, windows=(3,))
    w3 = prof.window(3)
    assert w3.games == 3
    assert w3.targets == pytest.approx((4 + 6 + 12) / 3, abs=0.01)  # last 3


def test_breakout_flag_on_rising_usage():
    # Early weeks near-zero usage, recent weeks heavy → breakout.
    rows = [
        _wk(1, targets=1, ts=0.05), _wk(2, targets=1, ts=0.05),
        _wk(3, targets=2, ts=0.08), _wk(4, targets=2, ts=0.08),
        _wk(5, targets=11, ts=0.30, ays=0.35), _wk(6, targets=12, ts=0.32, ays=0.38),
        _wk(7, targets=13, ts=0.34, ays=0.40),
    ]
    prof = usage_summary(rows)
    assert prof.trend == "rising"
    assert prof.breakout is True


def test_no_breakout_on_steady_usage():
    rows = [_wk(w, targets=7, ts=0.2, ays=0.2) for w in range(1, 8)]
    prof = usage_summary(rows)
    assert prof.trend == "steady"
    assert prof.breakout is False


def test_falling_usage_detected():
    rows = [
        _wk(1, targets=12, ts=0.32), _wk(2, targets=12, ts=0.32),
        _wk(3, targets=11, ts=0.30), _wk(4, targets=11, ts=0.30),
        _wk(5, targets=2, ts=0.06), _wk(6, targets=1, ts=0.05), _wk(7, targets=1, ts=0.05),
    ]
    prof = usage_summary(rows)
    assert prof.trend == "falling"


def test_multiple_windows_present():
    rows = [_wk(w, targets=5) for w in range(1, 12)]
    prof = usage_summary(rows)
    assert set(prof.windows.keys()) == {3, 5, 10}
