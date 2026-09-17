"""FastAPI dependencies: the shared objects a request handler needs.

Three lifetimes are in play and they are not interchangeable:

  * `ESPNAdapter` — one per process, held on `app.state`, so its 1 req/sec
    throttle is genuinely global. Worker threads build their own (see runs.py):
    an httpx client is not worth sharing across threads.
  * `DecisionStore` — one per thread. `db/store.py` opens its sqlite connection
    without `check_same_thread=False`, so a store built on the event loop thread
    cannot legally be touched from a run worker. Constructing one is cheap.
  * read memo — a 60s TTL cache so one page with three HTMX partials parses the
    same cached JSON once. Deliberately far below the adapter's 1h disk TTL, so
    it can never mask an explicit `fresh=True` refresh.
"""
from __future__ import annotations

import threading
import time
from functools import lru_cache
from typing import Any, Callable, TypeVar

from fastapi import Request

from fantasy_gm.adapters.espn import ESPNAdapter
from fantasy_gm.db.store import DecisionStore
from fantasy_gm.execute.base import Executor
from fantasy_gm.execute.espn_api import ESPNApiExecutor
from fantasy_gm.models import LeagueSettings
from fantasy_gm.web.settings import WebSettings

T = TypeVar("T")

_thread_local = threading.local()


def get_settings(request: Request) -> WebSettings:
    return request.app.state.settings


def get_adapter(request: Request) -> ESPNAdapter:
    return request.app.state.adapter


def build_adapter(settings: WebSettings) -> ESPNAdapter:
    return ESPNAdapter(league_id=settings.league_id, cache_dir=settings.cache_dir)


def get_store(request: Request) -> DecisionStore:
    """A DecisionStore bound to the calling thread."""
    return store_for_thread(request.app.state.settings)


def store_for_thread(settings: WebSettings) -> DecisionStore:
    key = str(settings.db_path)
    stores = getattr(_thread_local, "stores", None)
    if stores is None:
        stores = _thread_local.stores = {}
    if key not in stores:
        stores[key] = DecisionStore(settings.db_path)
    return stores[key]


def get_executor(request: Request) -> Executor:
    return request.app.state.executor


@lru_cache(maxsize=8)
def _league_settings_cached(adapter: ESPNAdapter, season: int) -> LeagueSettings:
    return adapter.get_league_settings(season)


def league_settings_for(adapter: ESPNAdapter, season: int) -> LeagueSettings:
    """League settings for the process lifetime — scoring rules do not move mid-season."""
    return _league_settings_cached(adapter, season)


class ReadCache:
    """Tiny TTL memo over the adapter's read calls, keyed by call signature."""

    def __init__(self, ttl_seconds: float = 60.0):
        self.ttl = ttl_seconds
        self._entries: dict[Any, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: Any, compute: Callable[[], T]) -> T:
        now = time.time()
        with self._lock:
            hit = self._entries.get(key)
            if hit is not None and now - hit[0] < self.ttl:
                return hit[1]
        value = compute()          # computed outside the lock: this can do I/O
        with self._lock:
            self._entries[key] = (now, value)
        return value

    def invalidate(self) -> None:
        with self._lock:
            self._entries.clear()


def get_reads(request: Request) -> ReadCache:
    return request.app.state.reads
