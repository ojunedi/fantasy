"""
Core Pydantic data models. All data flowing through the system is typed here.
No logic lives in this file — only structure and validation.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Generic, Literal, TypeVar
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Position(str, Enum):
    QB = "QB"
    RB = "RB"
    WR = "WR"
    TE = "TE"
    K = "K"
    DST = "DST"
    FLEX = "FLEX"     # RB/WR/TE flex
    SUPER_FLEX = "SUPER_FLEX"  # QB/RB/WR/TE flex
    BENCH = "BE"
    IR = "IR"


class PlayerStatus(str, Enum):
    ACTIVE = "ACTIVE"
    QUESTIONABLE = "QUESTIONABLE"
    DOUBTFUL = "DOUBTFUL"
    OUT = "OUT"
    IR = "IR"
    SUSPENDED = "SUSPENDED"
    UNKNOWN = "UNKNOWN"


class WaiverType(str, Enum):
    SNAKE = "SNAKE"         # priority-based, no budget
    FAAB = "FAAB"           # free-agent acquisition budget
    ROLLING = "ROLLING"     # add/drop immediately


class DecisionType(str, Enum):
    LINEUP = "lineup"
    WAIVER = "waiver"
    TRADE = "trade"


class HumanResponse(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"


class Platform(str, Enum):
    ESPN = "espn"
    SLEEPER = "sleeper"


# ---------------------------------------------------------------------------
# League & Settings
# ---------------------------------------------------------------------------

class ScoringRule(BaseModel):
    """A single scoring multiplier (e.g. pass_td = 4.0)."""
    stat: str
    points: float


class ScoringRules(BaseModel):
    """Exact league scoring rules derived from the platform API, not hardcoded presets."""
    rules: list[ScoringRule]

    def get(self, stat: str) -> float:
        for rule in self.rules:
            if rule.stat == stat:
                return rule.points
        return 0.0


class RosterSlot(BaseModel):
    slot_id: str          # ESPN slot ID or Sleeper equivalent
    position: Position
    is_starter: bool


class LeagueSettings(BaseModel):
    platform: Platform
    league_id: str
    season: int
    team_count: int
    roster_slots: list[RosterSlot]
    scoring_rules: ScoringRules
    waiver_type: WaiverType
    faab_budget: int | None = None  # None if snake waivers
    playoff_start_week: int
    playoff_weeks: list[int]
    regular_season_weeks: list[int]


# ---------------------------------------------------------------------------
# Players
# ---------------------------------------------------------------------------

class Player(BaseModel):
    platform_id: str
    name: str
    position: Position
    eligible_positions: list[Position]
    nfl_team: str | None = None
    status: PlayerStatus = PlayerStatus.ACTIVE
    jersey_number: int | None = None


class RosterPlayer(BaseModel):
    """A player on a specific fantasy roster, with their current slot."""
    player: Player
    slot: Position
    is_starter: bool
    acquisition_type: str | None = None  # "draft", "waiver", "trade", "free_agent"


# ---------------------------------------------------------------------------
# Rosters & Matchups
# ---------------------------------------------------------------------------

class Roster(BaseModel):
    team_id: str
    team_name: str
    owner_name: str
    players: list[RosterPlayer]
    week: int
    season: int

    @property
    def starters(self) -> list[RosterPlayer]:
        return [p for p in self.players if p.is_starter]

    @property
    def bench(self) -> list[RosterPlayer]:
        return [p for p in self.players if not p.is_starter]


class TeamScore(BaseModel):
    team_id: str
    team_name: str
    projected_score: float | None = None
    actual_score: float | None = None


class Matchup(BaseModel):
    week: int
    season: int
    home: TeamScore
    away: TeamScore
    is_complete: bool


class FreeAgent(BaseModel):
    player: Player
    percent_owned: float = 0.0
    waiver_priority: int | None = None  # None for FAAB leagues


class TeamStanding(BaseModel):
    """A team's season record and scoring, for risk-posture decisions."""
    team_id: str
    team_name: str
    wins: int
    losses: int
    ties: int = 0
    points_for: float = 0.0
    points_against: float = 0.0
    playoff_seed: int | None = None
    games_back: float | None = None

    @property
    def games_played(self) -> int:
        return self.wins + self.losses + self.ties

    @property
    def win_pct(self) -> float:
        gp = self.games_played
        return (self.wins + 0.5 * self.ties) / gp if gp else 0.0


class Transaction(BaseModel):
    transaction_id: str
    week: int
    type: Literal["add", "drop", "trade", "waiver"]
    team_id: str
    player_added: Player | None = None
    player_dropped: Player | None = None
    faab_bid: int | None = None
    timestamp: datetime


# ---------------------------------------------------------------------------
# Signals (each module in signals/ produces one of these)
# ---------------------------------------------------------------------------

T = TypeVar("T")


class Signal(BaseModel, Generic[T]):
    """Typed signal with provenance and freshness metadata."""
    source: str
    as_of: datetime
    value: T

    @property
    def age_seconds(self) -> float:
        return (datetime.utcnow() - self.as_of).total_seconds()

    @property
    def is_stale(self) -> bool:
        return self.age_seconds > 3600  # configurable threshold


class PlayerProjection(BaseModel):
    player_id: str
    player_name: str
    projected_points: float
    position: Position
    nfl_team: str | None = None
    opponent: str | None = None
    week: int
    season: int


class InjuryReport(BaseModel):
    player_id: str
    player_name: str
    status: PlayerStatus
    injury_description: str | None = None
    practice_participation: str | None = None  # "full", "limited", "dnp"
    week: int


class DepthChartEntry(BaseModel):
    player_id: str
    player_name: str
    position: Position
    nfl_team: str
    depth_position: int  # 1 = starter
    snap_share_last3: float | None = None  # 0.0–1.0


class WeatherReport(BaseModel):
    nfl_team: str
    stadium: str
    is_dome: bool
    temperature_f: float | None = None
    wind_mph: float | None = None
    precipitation_chance: float | None = None  # 0.0–1.0
    week: int


class VegasLine(BaseModel):
    nfl_team: str
    opponent: str
    implied_team_total: float
    spread: float         # negative = favorite
    over_under: float
    week: int


class UsageTrend(BaseModel):
    player_id: str
    player_name: str
    position: Position
    nfl_team: str
    targets_last3: float | None = None
    carries_last3: float | None = None
    red_zone_targets_last3: float | None = None
    red_zone_carries_last3: float | None = None
    snap_share_last3: float | None = None
    weeks_sampled: int = 3


# ---------------------------------------------------------------------------
# Decisions & Approval Log
# ---------------------------------------------------------------------------

class LineupSlotChange(BaseModel):
    slot: Position
    player_out: Player | None
    player_in: Player


class ProposedLineup(BaseModel):
    week: int
    season: int
    slots: list[LineupSlotChange]
    projected_points: float
    reasoning: str


class WaiverProposal(BaseModel):
    player_add: Player
    player_drop: Player | None  # None = just add (if roster space)
    priority_use: int | None = None  # waiver priority position used
    reasoning: str
    projected_weekly_value: float | None = None


class TradeProposal(BaseModel):
    send_players: list[Player]
    receive_players: list[Player]
    counterparty_team_id: str
    reasoning: str
    trade_rationale: str  # for the memo


class DecisionRecord(BaseModel):
    """The canonical log entry for every agent decision. Written to SQLite."""
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    week: int
    season: int
    decision_type: DecisionType

    # Everything the agent saw — frozen at decision time for replay
    inputs_snapshot: dict[str, Any]
    signals_staleness: dict[str, float]  # signal_name -> age_seconds at decision time

    # What the agent recommended
    recommendation: dict[str, Any]       # serialized ProposedLineup / WaiverProposal / TradeProposal
    memo: str                            # GM memo text
    confidence: float = Field(ge=0.0, le=1.0)

    # Human response — filled in by the approval CLI
    human_response: HumanResponse | None = None
    override_reason: str | None = None
    modified_recommendation: dict[str, Any] | None = None

    # Outcome — filled in after the week resolves
    outcome: dict[str, Any] | None = None
    outcome_recorded_at: datetime | None = None


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

class BaselineType(str, Enum):
    PLATFORM_RANK = "platform_rank"    # start whoever platform ranks highest
    LAST_WEEK_BEST = "last_week_best"  # start last week's highest scorers
    DO_NOTHING = "do_nothing"          # never change the lineup


class WeeklyScorecard(BaseModel):
    week: int
    season: int
    actual_score: float
    optimal_score: float                          # hindsight optimal lineup
    agent_projected_score: float | None = None
    baseline_scores: dict[BaselineType, float]
    points_left_on_bench: float
    decision_regret: float                        # optimal - actual
    agent_agreement_with_human: bool | None = None  # whether agent and human agreed
