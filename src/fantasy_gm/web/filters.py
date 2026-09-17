"""Jinja filters — formatting only, never computation.

Anything that decides *what* a number is belongs in `core/`; these decide only
how it is spelled on the page.
"""
from __future__ import annotations

from datetime import datetime, timezone


def points(value: float | None, places: int = 1) -> str:
    """A fantasy point total. An absent projection is an em dash, never 0.0."""
    if value is None:
        return "—"
    return f"{value:.{places}f}"


def signed(value: float | None, places: int = 1) -> str:
    """A delta, always carrying its sign. Exactly zero reads as a dash."""
    if value is None:
        return "—"
    if abs(value) < 0.05:
        return "—"
    return f"{value:+.{places}f}"


def pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.0%}"


def record(standing) -> str:
    base = f"{standing.wins}-{standing.losses}"
    return f"{base}-{standing.ties}" if standing.ties else base


def clock(ts: float | datetime | None) -> str:
    """A cache timestamp as a local wall clock, e.g. 14:02."""
    if ts is None:
        return "unknown"
    if isinstance(ts, (int, float)):
        ts = datetime.fromtimestamp(ts)
    elif ts.tzinfo is not None:
        ts = ts.astimezone().replace(tzinfo=None)
    return ts.strftime("%H:%M")


def age(seconds: float | None) -> str:
    """Staleness, at the coarsest honest resolution."""
    if seconds is None:
        return "unknown"
    seconds = max(seconds, 0)
    if seconds < 90:
        return f"{seconds:.0f}s ago"
    minutes = seconds / 60
    if minutes < 90:
        return f"{minutes:.0f}m ago"
    hours = minutes / 60
    if hours < 36:
        return f"{hours:.0f}h ago"
    return f"{hours / 24:.0f}d ago"


def datestamp(value: datetime | None) -> str:
    if value is None:
        return "—"
    if value.tzinfo is None:                       # records are stored in UTC
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone().strftime("%d %b · %H:%M")


FILTERS = {
    "points": points,
    "signed": signed,
    "pct": pct,
    "record": record,
    "clock": clock,
    "age": age,
    "datestamp": datestamp,
}
