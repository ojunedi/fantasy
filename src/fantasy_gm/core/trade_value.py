"""
Trade valuation and evaluation.

Two layers:
  1. Asset value — rest-of-season projected points scaled by a positional
     scarcity multiplier (a scarce RB/TE is worth more than the same points at
     a deep position). This is the currency trades are compared in.
  2. Trade evaluation — given players sent and received, the value delta,
     fairness, and (when a roster + projections are supplied) the concrete
     impact on *my* optimized starting-lineup points, via `core/optimizer.py`.

Reuses `core.optimizer` for roster impact and `models` types. Pure functions —
no I/O, no LLM.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from fantasy_gm.core.optimizer import optimize_lineup, projected_score
from fantasy_gm.models import LeagueSettings, Player, Position

# Positional scarcity multipliers for a standard 1-QB PPR league. Steeper
# starter-to-replacement drop-offs (RB, TE) carry a premium; QB/K/DST are
# deep/streamable and discounted.
DEFAULT_SCARCITY: dict[Position, float] = {
    Position.RB: 1.12,
    Position.TE: 1.10,
    Position.WR: 1.00,
    Position.QB: 0.85,
    Position.K: 0.55,
    Position.DST: 0.60,
}


@dataclass(frozen=True)
class AssetValue:
    player_id: str
    position: Position
    ros_points: float        # rest-of-season projected points
    scarcity: float
    value: float             # ros_points * scarcity


@dataclass(frozen=True)
class RosterImpact:
    before_total: float
    after_total: float

    @property
    def delta(self) -> float:
        return round(self.after_total - self.before_total, 2)


@dataclass(frozen=True)
class TradeEvaluation:
    send_value: float
    receive_value: float
    ev_delta: float          # receive_value - send_value (my perspective)
    fairness: float          # 0–1, 1.0 = perfectly balanced value
    verdict: str             # "win" | "fair" | "lose" (for me)
    roster_impact: RosterImpact | None = None
    send_ids: list[str] = field(default_factory=list)
    receive_ids: list[str] = field(default_factory=list)


def asset_value(
    player_id: str,
    position: Position,
    ros_points: float,
    scarcity: dict[Position, float] | None = None,
) -> AssetValue:
    mult = (scarcity or DEFAULT_SCARCITY).get(position, 1.0)
    return AssetValue(player_id=player_id, position=position,
                      ros_points=round(ros_points, 2), scarcity=mult,
                      value=round(ros_points * mult, 2))


def build_value_map(
    ros_by_player: dict[str, float],
    position_by_player: dict[str, Position],
    scarcity: dict[Position, float] | None = None,
) -> dict[str, AssetValue]:
    """Value every player from a rest-of-season point map + a position map."""
    out: dict[str, AssetValue] = {}
    for pid, ros in ros_by_player.items():
        pos = position_by_player.get(pid, Position.WR)
        out[pid] = asset_value(pid, pos, ros, scarcity)
    return out


def _verdict(ev_delta: float, send_value: float) -> str:
    # Judge the delta relative to the size of the package sent (min floor so a
    # tiny package doesn't produce extreme percentages).
    base = max(send_value, 1.0)
    pct = ev_delta / base
    if pct >= 0.05:
        return "win"
    if pct <= -0.05:
        return "lose"
    return "fair"


def evaluate_trade(
    send_ids: list[str],
    receive_ids: list[str],
    value_map: dict[str, AssetValue],
) -> TradeEvaluation:
    """Compare the value sent vs. received. Roster impact left None."""
    send_value = round(sum(value_map[i].value for i in send_ids if i in value_map), 2)
    receive_value = round(sum(value_map[i].value for i in receive_ids if i in value_map), 2)
    ev_delta = round(receive_value - send_value, 2)
    hi = max(send_value, receive_value)
    fairness = round(min(send_value, receive_value) / hi, 3) if hi > 0 else 1.0
    return TradeEvaluation(
        send_value=send_value, receive_value=receive_value, ev_delta=ev_delta,
        fairness=fairness, verdict=_verdict(ev_delta, send_value),
        send_ids=list(send_ids), receive_ids=list(receive_ids),
    )


def roster_starting_total(
    players: list[Player],
    projections: dict[str, float],
    settings: LeagueSettings,
) -> float:
    """Optimized starting-lineup projected points for a set of players."""
    lineup = optimize_lineup(players, projections, settings)
    return round(projected_score(lineup, projections), 2)


def evaluate_trade_for_roster(
    my_players: list[Player],
    incoming_players: list[Player],
    send_ids: list[str],
    receive_ids: list[str],
    value_map: dict[str, AssetValue],
    projections: dict[str, float],
    settings: LeagueSettings,
) -> TradeEvaluation:
    """Full evaluation including the effect on my optimized starting lineup.

    `projections` should cover both my players and the incoming players (a
    single-week or per-week mean is fine — it just needs to be consistent).
    """
    base = evaluate_trade(send_ids, receive_ids, value_map)

    before = roster_starting_total(my_players, projections, settings)
    send_set = set(send_ids)
    after_players = [p for p in my_players if p.platform_id not in send_set] + incoming_players
    after = roster_starting_total(after_players, projections, settings)

    return TradeEvaluation(
        send_value=base.send_value, receive_value=base.receive_value,
        ev_delta=base.ev_delta, fairness=base.fairness, verdict=base.verdict,
        roster_impact=RosterImpact(before_total=before, after_total=after),
        send_ids=base.send_ids, receive_ids=base.receive_ids,
    )
