"""
FantasyCalc market trade values.

Community-consensus redraft trade values (fantasycalc.com public API), keyed by
ESPN player id. This is the *market* currency for trades: it prices positional
scarcity and replaceability the way real managers do — a backup QB in a 1-QB
league is near-worthless, startable RB/WR are scarce — which raw projected
points do NOT. Using it as the trade currency stops the agent proposing "fair"
QB-for-WR swaps that no human would accept.

Best-effort: returns {} on any failure so the trade agent degrades to the
in-house value model rather than raising.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

_API = "https://api.fantasycalc.com/values/current"
_cache: dict[tuple, dict[str, "MarketValue"]] = {}


@dataclass(frozen=True)
class MarketValue:
    value: float
    position: str
    position_rank: int
    overall_rank: int


def get_market_values(
    num_qbs: int = 1, num_teams: int = 12, ppr: float = 1.0
) -> dict[str, MarketValue]:
    """espn_id -> MarketValue for the given league format. {} on any failure.

    Cached per (num_qbs, num_teams, ppr) for the process — values move slowly, so
    one fetch per run is plenty.
    """
    key = (num_qbs, num_teams, ppr)
    if key in _cache:
        return _cache[key]
    params = {
        "isDynasty": "false",
        "numQbs": num_qbs,
        "numTeams": num_teams,
        "ppr": ppr,
    }
    try:
        resp = httpx.get(_API, params=params, timeout=15)
        resp.raise_for_status()
        rows = resp.json()
    except Exception:
        _cache[key] = {}
        return {}

    out: dict[str, MarketValue] = {}
    for row in rows:
        p = row.get("player", {})
        eid = p.get("espnId")
        if not eid:
            continue
        out[str(eid)] = MarketValue(
            value=float(row.get("value", 0.0)),
            position=p.get("position", ""),
            position_rank=int(row.get("positionRank") or 0),
            overall_rank=int(row.get("overallRank") or 0),
        )
    _cache[key] = out
    return out
