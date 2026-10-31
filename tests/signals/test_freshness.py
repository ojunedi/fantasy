"""Per-signal freshness for a lineup decision."""
from __future__ import annotations

from datetime import datetime, timedelta

from fantasy_gm.signals.base import SignalAvailability, SignalBundle
from fantasy_gm.signals.freshness import assess

NOW = datetime(2026, 11, 1, 15, 0)


def _bundle(**ages) -> SignalBundle:
    """ages: name -> hours old, None for unavailable, 'unstamped' for no as-of."""
    defaults = {"projections": 0.5, "injuries": 0.1, "usage_trends": 1,
                "vegas_lines": 1, "weather": 1}
    defaults.update(ages)
    availability = []
    for name, age in defaults.items():
        if age is None:
            availability.append(SignalAvailability(name=name, available=False, note="error: 503"))
        elif age == "unstamped":
            availability.append(SignalAvailability(name=name, available=True, as_of=None))
        else:
            availability.append(SignalAvailability(name=name, available=True,
                                                   as_of=NOW - timedelta(hours=age)))
    return SignalBundle(week=9, season=2026, availability=availability)


def test_sigstale01_a_required_signal_past_its_threshold_makes_the_bundle_stale():
    result = assess(_bundle(projections=7, injuries=10 / 60), now=NOW)

    # SIGSTALE-01 THEN it reports stale
    assert result.fresh is False
    # SIGSTALE-01 AND it names projections, its age, and its 6-hour threshold
    [stale] = result.stale
    assert stale["name"] == "projections"
    assert stale["age_seconds"] == 7 * 3600
    assert stale["threshold_seconds"] == 6 * 3600


def test_sigstale02_a_missing_or_unstamped_signal_is_stale_never_fresh():
    for projections in (None, "unstamped"):
        result = assess(_bundle(projections=projections), now=NOW)

        # SIGSTALE-02 THEN it reports stale
        assert result.fresh is False
        # SIGSTALE-02 AND names projections as missing
        [stale] = result.stale
        assert stale["name"] == "projections"
        assert stale["age_seconds"] is None
        assert stale["reason"].startswith(("missing", "no as-of"))


def test_sigstale03_a_stale_optional_signal_is_named_but_does_not_make_the_bundle_stale():
    result = assess(_bundle(weather=20), now=NOW)

    # SIGSTALE-03 THEN it reports fresh
    assert result.fresh is True
    # SIGSTALE-03 AND names weather as stale
    assert [s["name"] for s in result.stale] == ["weather"]
    assert result.blocking == []


def test_a_bundle_missing_a_required_signal_entirely_is_stale():
    bundle = _bundle()
    bundle.availability = [a for a in bundle.availability if a.name != "injuries"]
    assert assess(bundle, now=NOW).fresh is False


def test_an_nflverse_file_served_after_a_failed_reload_carries_its_real_age(tmp_path, monkeypatch):
    import os
    import time

    from fantasy_gm.signals.sources import nflverse as nv

    monkeypatch.setattr(nv, "CACHE_DIR", tmp_path)
    path = tmp_path / "schedules_2026.parquet"
    path.write_bytes(b"")
    three_days_ago = time.time() - 3 * 86400
    os.utime(path, (three_days_ago, three_days_ago))

    as_of = nv.data_as_of("schedules_2026")

    assert abs((datetime.utcnow() - as_of).total_seconds() - 3 * 86400) < 60
    assert assess(_bundle(vegas_lines=72), now=NOW).stale[0]["name"] == "vegas_lines"
