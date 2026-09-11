"""
Signal ingestion base types.

Each signal source produces a typed record wrapped in Signal[T] (see models.py)
so the agent can always see the source and how stale the input is.

A SignalProvider that isn't implemented yet returns availability=False rather
than raising — the agent treats missing signals as a reason to hedge or abstain,
not as an error.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from fantasy_gm.models import (
    InjuryReport,
    PlayerProjection,
    UsageTrend,
    VegasLine,
    WeatherReport,
)


@dataclass
class SignalAvailability:
    """Tracks whether a signal source produced data and how fresh it is."""
    name: str
    available: bool
    as_of: datetime | None = None
    source: str = ""
    note: str = ""

    @property
    def age_seconds(self) -> float | None:
        if self.as_of is None:
            return None
        return (datetime.utcnow() - self.as_of).total_seconds()


@dataclass
class SignalBundle:
    """
    All signals gathered for a decision, with per-source availability/freshness.
    This is what the agent inspects to decide whether it has enough to act.
    """
    week: int
    season: int
    projections: dict[str, PlayerProjection] = field(default_factory=dict)
    injuries: dict[str, InjuryReport] = field(default_factory=dict)
    usage: dict[str, UsageTrend] = field(default_factory=dict)
    weather: dict[str, WeatherReport] = field(default_factory=dict)
    vegas: dict[str, VegasLine] = field(default_factory=dict)
    availability: list[SignalAvailability] = field(default_factory=list)

    def staleness_map(self) -> dict[str, float]:
        """signal_name -> age_seconds, for logging into the DecisionRecord."""
        return {
            a.name: a.age_seconds
            for a in self.availability
            if a.age_seconds is not None
        }

    def unavailable_signals(self) -> list[str]:
        return [a.name for a in self.availability if not a.available]


class SignalProvider(Protocol):
    """Interface every signal source implements."""

    name: str

    def fetch(self, week: int, season: int, player_ids: list[str]) -> SignalAvailability:
        """Fetch this signal for the given players. Populates a shared bundle
        (implementation-specific) and returns its availability record."""
        ...
