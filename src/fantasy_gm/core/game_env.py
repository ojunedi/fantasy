"""
Game-environment analysis from betting lines.

Turns a game's total (over/under) and a team's spread into an implied team
point total and a pass/run game-script tilt:

  - implied team total  = total/2 - team_spread/2   (favorites score more)
  - high total          → more scoring opportunity for everyone
  - big favorite         → positive game script, run-leaning late (helps RBs)
  - big underdog         → trailing script, pass-leaning (helps WRs/pass game)

Lines come from live odds (`espn_odds`) or the closing lines carried in
nflverse `load_schedules`. Pure functions — no I/O.
"""
from __future__ import annotations

from dataclasses import dataclass

# Reference implied totals for scaling env_score to 0–100.
_LOW_TOTAL = 16.0
_HIGH_TOTAL = 30.0


@dataclass(frozen=True)
class GameEnvironment:
    team: str
    opponent: str | None
    total: float
    spread: float                 # team's spread (negative = favorite)
    implied_team_total: float
    opponent_implied_total: float
    is_favorite: bool
    script: str                   # "run-leaning" | "pass-leaning" | "neutral"
    pass_tilt: float              # -1..1, >0 = more passing than neutral expected
    env_score: float              # 0–100, higher = better scoring environment

    @property
    def is_shootout(self) -> bool:
        return self.total >= 48.0 and abs(self.spread) <= 3.0


def game_environment(team: str, opponent: str | None, total: float, spread: float) -> GameEnvironment:
    """Build a GameEnvironment for a team given the game total and its spread."""
    implied = round(total / 2.0 - spread / 2.0, 2)
    opp_implied = round(total / 2.0 + spread / 2.0, 2)

    # pass_tilt: underdogs (positive spread) throw more; favorites run more.
    pass_tilt = max(-1.0, min(1.0, round(spread / 10.0, 3)))
    if spread <= -4.0:
        script = "run-leaning"
    elif spread >= 4.0:
        script = "pass-leaning"
    else:
        script = "neutral"

    env_score = round(
        max(0.0, min(100.0, (implied - _LOW_TOTAL) / (_HIGH_TOTAL - _LOW_TOTAL) * 100.0)),
        1,
    )

    return GameEnvironment(
        team=team, opponent=opponent, total=total, spread=spread,
        implied_team_total=implied, opponent_implied_total=opp_implied,
        is_favorite=spread < 0, script=script, pass_tilt=pass_tilt, env_score=env_score,
    )


def from_schedule_row(row: dict, team: str) -> GameEnvironment | None:
    """Build a GameEnvironment from an nflverse schedule row for one team.

    `spread_line` in nflverse is the home team's spread; flip it for the away
    team. Returns None if the row lacks usable lines.
    """
    total = row.get("total_line")
    spread_line = row.get("spread_line")
    home, away = row.get("home_team"), row.get("away_team")
    if total is None or spread_line is None or team not in (home, away):
        return None
    # nflverse convention: spread_line > 0 means the home team is favored, so
    # the home team's signed spread is -spread_line.
    if team == home:
        team_spread = -float(spread_line)
        opponent = away
    else:
        team_spread = float(spread_line)
        opponent = home
    return game_environment(team, opponent, float(total), team_spread)
