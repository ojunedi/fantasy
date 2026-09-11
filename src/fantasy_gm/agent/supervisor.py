"""
GM Supervisor (thin scaffold).

Sits above the specialist agents (lineup, trade). Its job this phase:
  1. Read standings and set a **risk posture** — must_win / coast / normal —
     from the team's record and how many weeks remain (a simple, deterministic
     record-based model; a Monte-Carlo playoff-odds model is deferred).
  2. Route to the specialists, passing the posture in as an input, and assemble
     a consolidated weekly action plan.

Deliberately thin: the Waiver and Season-Strategy specialists are deferred, and
posture is not yet baked into the optimizer objective (it is passed as an input
the agents weigh). The base agents already support additional specialists.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fantasy_gm.models import LeagueSettings, TeamStanding


@dataclass
class RiskPosture:
    posture: str          # "must_win" | "coast" | "normal"
    rationale: str
    my_seed: int | None = None
    weeks_left_regular: int = 0


@dataclass
class WeeklyPlan:
    week: int
    season: int
    posture: RiskPosture
    lineup_record: Any | None = None
    trade_record: Any | None = None
    notes: list[str] = field(default_factory=list)


def risk_posture(
    standings: list[TeamStanding],
    my_team_id: str,
    week: int,
    settings: LeagueSettings,
) -> RiskPosture:
    """Derive a risk posture from standings + weeks remaining (record-based)."""
    weeks_left = max(0, settings.playoff_start_week - week)
    mine = next((s for s in standings if s.team_id == my_team_id), None)
    if mine is None:
        return RiskPosture(posture="normal", rationale="Standings unavailable.",
                           weeks_left_regular=weeks_left)

    n_playoff = max(4, settings.team_count // 2)
    seed = mine.playoff_seed
    in_position = seed is not None and seed <= n_playoff
    late = weeks_left <= 3

    if not late:
        posture = "normal"
        rationale = (f"Week {week}: {weeks_left} weeks left before playoffs — "
                     f"too early to change posture (seed {seed}).")
    elif not in_position:
        posture = "must_win"
        rationale = (f"Seed {seed} is outside the top {n_playoff} with only "
                     f"{weeks_left} weeks left — must-win mode.")
    elif seed is not None and seed <= 2:
        posture = "coast"
        rationale = (f"Seed {seed} is near-locked for a top-{n_playoff} spot with "
                     f"{weeks_left} weeks left — protect the position.")
    else:
        posture = "normal"
        rationale = (f"Seed {seed} is in playoff position but not locked — "
                     f"stay balanced with {weeks_left} weeks left.")

    return RiskPosture(posture=posture, rationale=rationale, my_seed=seed,
                       weeks_left_regular=weeks_left)


class GMSupervisor:
    """Orchestrates the specialist agents under a single risk posture."""

    def __init__(self, adapter, settings: LeagueSettings, team_id: str):
        self.adapter = adapter
        self.settings = settings
        self.team_id = team_id

    def posture(self, week: int, season: int) -> RiskPosture:
        try:
            standings = self.adapter.get_standings(season)
        except Exception as e:  # standings are best-effort
            return RiskPosture(posture="normal",
                               rationale=f"Standings unavailable ({e}).")
        return risk_posture(standings, self.team_id, week, self.settings)

    def run_week(
        self,
        week: int,
        season: int,
        do_lineup: bool = True,
        do_trades: bool = False,
        lineup_agent=None,
        trade_agent=None,
    ) -> WeeklyPlan:
        """Set posture, run the requested specialists, assemble a plan."""
        posture = self.posture(week, season)
        plan = WeeklyPlan(week=week, season=season, posture=posture)
        plan.notes.append(f"Posture: {posture.posture.upper()} — {posture.rationale}")

        if do_lineup:
            from fantasy_gm.agent.graph import LineupGraphAgent
            from fantasy_gm.agent.tools import LineupToolContext
            ctx = LineupToolContext(
                adapter=self.adapter, settings=self.settings, team_id=self.team_id,
                week=week, season=season, posture=posture.posture)
            agent = lineup_agent or LineupGraphAgent()
            plan.lineup_record = agent.decide(ctx)

        if do_trades:
            from fantasy_gm.agent.trade.graph import TradeGraphAgent
            from fantasy_gm.agent.trade.tools import TradeToolContext
            ctx = TradeToolContext(
                adapter=self.adapter, settings=self.settings, team_id=self.team_id,
                week=week, season=season, posture=posture.posture)
            agent = trade_agent or TradeGraphAgent()
            plan.trade_record = agent.decide(ctx)

        return plan
