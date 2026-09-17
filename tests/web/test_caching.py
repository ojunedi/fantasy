"""The read memo.

What this saves is repeated JSON parsing and model construction, not network —
the adapter already disk-caches for an hour. The TTL is deliberately far below
the adapter's so it can never mask an explicit refresh.
"""
from __future__ import annotations

import time

from fantasy_gm.web.deps import ReadCache


def test_repeated_reads_within_the_ttl_hit_once():
    cache = ReadCache(ttl_seconds=60)
    calls = []

    def compute():
        calls.append(1)
        return "value"

    assert cache.get("k", compute) == "value"
    assert cache.get("k", compute) == "value"
    assert len(calls) == 1


def test_the_ttl_expires():
    cache = ReadCache(ttl_seconds=0.05)
    calls = []
    cache.get("k", lambda: calls.append(1))
    time.sleep(0.08)
    cache.get("k", lambda: calls.append(1))
    assert len(calls) == 2


def test_distinct_keys_do_not_collide():
    cache = ReadCache(ttl_seconds=60)
    assert cache.get(("roster", 3), lambda: "week3") == "week3"
    assert cache.get(("roster", 4), lambda: "week4") == "week4"


def test_invalidate_clears_everything():
    cache = ReadCache(ttl_seconds=60)
    cache.get("k", lambda: "old")
    cache.invalidate()
    assert cache.get("k", lambda: "new") == "new"


def test_one_page_with_three_partials_reads_each_source_once(client, fake_adapter):
    """The concrete case the memo exists for."""
    client.get("/team")
    fake_adapter.calls.clear()
    client.get("/partials/standings")
    client.get("/partials/matchups")
    client.get("/partials/roster")
    assert fake_adapter.calls.count("get_standings") == 0
    assert fake_adapter.calls.count("get_projections") == 0


def test_refresh_is_never_masked_by_the_memo(client, fake_adapter):
    """A 60s memo must not be able to swallow an explicit fresh=True."""
    client.get("/team")
    fake_adapter.calls.clear()
    client.post("/partials/refresh")
    assert "get_roster" in fake_adapter.calls


def test_league_settings_are_cached_for_the_process(client, fake_adapter):
    """Scoring rules do not move mid-season; one fetch is enough."""
    client.get("/team")
    before = fake_adapter.calls.count("get_league_settings")
    client.get("/team")
    assert fake_adapter.calls.count("get_league_settings") == before


def test_raw_lineup_slots_are_never_cached(client, fake_adapter, store):
    """This one feeds the write path — a stale current slot produces a plan
    ESPN rejects."""
    from fantasy_gm.web import reads
    import inspect
    source = inspect.getsource(reads.raw_lineup_slots)
    assert "reads.get" not in source and "cache.get" not in source
