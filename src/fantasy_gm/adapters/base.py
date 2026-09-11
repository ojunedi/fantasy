"""
FantasyPlatform interface. All platform adapters implement this.
Nothing above this layer imports platform-specific code.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from fantasy_gm.models import (
    FreeAgent,
    LeagueSettings,
    Matchup,
    Roster,
    Transaction,
)


class FantasyPlatform(ABC):
    """Read-only fantasy platform interface.

    Every method returns a typed Pydantic model. Caching is handled by
    concrete implementations — callers get fresh-enough data transparently.
    """

    @abstractmethod
    def get_league_settings(self, season: int) -> LeagueSettings:
        ...

    @abstractmethod
    def get_roster(self, team_id: str, week: int, season: int) -> Roster:
        ...

    @abstractmethod
    def get_all_rosters(self, week: int, season: int) -> list[Roster]:
        ...

    @abstractmethod
    def get_matchup(self, team_id: str, week: int, season: int) -> Matchup:
        ...

    @abstractmethod
    def get_free_agents(self, week: int, season: int, position_filter: list[str] | None = None) -> list[FreeAgent]:
        ...

    @abstractmethod
    def get_transactions(self, week: int, season: int) -> list[Transaction]:
        ...
