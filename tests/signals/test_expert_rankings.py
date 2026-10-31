"""FantasyPros consensus rankings, beside ESPN's projections."""
from __future__ import annotations

from datetime import datetime

import polars as pl

from fantasy_gm.models import Player, PlayerProjection, Position, RosterPlayer
from fantasy_gm.signals.base import SignalBundle
from fantasy_gm.signals.collector import _collect_expert_rankings
from fantasy_gm.signals.freshness import assess
from fantasy_gm.signals.sources import nflverse as nv


def _rp(pid, name, pos):
    return RosterPlayer(player=Player(platform_id=pid, name=name, position=pos,
                                      eligible_positions=[pos]),
                        slot=pos, is_starter=True)


class Adapter:
    def get_player_projections(self, week, season):
        return [PlayerProjection(player_id=pid, player_name=pid, projected_points=pts,
                                 position=Position.RB, week=week, season=season)
                for pid, pts in (("4430807", 23.1), ("9", 25.0), ("10", 12.0))]


def test_fprank01_a_rostered_player_gets_his_consensus_rank_and_the_feeds_date(monkeypatch):
    rankings = pl.DataFrame({
        "page": ["ppr-rb", "ppr-rb", "db"], "page_pos": ["RB", "RB", "DB"],
        "pos": ["RB", "RB", "DB"], "fantasypros_id": [22978, 1, 2],
        "ecr": [2.16, 1.0, 3.0], "sd": [0.67, 0.2, 1.0], "best": [1, 1, 2],
        "worst": [5, 2, 4], "pos_rank": ["RB2", "RB1", "DB3"],
        "scrape_date": ["2026-10-30"] * 3,
    })
    ids = pl.DataFrame({"fantasypros_id": [22978, 1], "espn_id": [4430807, 9]})
    monkeypatch.setattr(nv, "load_ff_rankings", lambda: rankings)
    monkeypatch.setattr(nv, "load_ff_playerids", lambda: ids)
    bundle = SignalBundle(week=9, season=2026)

    _collect_expert_rankings(bundle, Adapter(), [_rp("4430807", "Bijan Robinson", Position.RB)],
                             9, 2026)
    r = bundle.expert_rankings["4430807"]
    signal = next(a for a in bundle.availability if a.name == "expert_rankings")

    # FPRANK-01 THEN that player carries ecr 2.16, spread 0.67, best and worst
    assert (r.ecr, r.sd, r.best, r.worst, r.pos_rank) == (2.16, 0.67, 1, 5, "RB2")
    assert r.espn_pos_rank == 2  # second by ESPN projected points among the backs
    # FPRANK-01 AND the signal's source is FantasyPros and its as-of time is 2026-10-30
    assert signal.source == "FantasyPros (via nflverse)"
    assert signal.as_of == datetime(2026, 10, 30)


def test_fprank04_missing_rankings_never_stop_a_lineup_run(monkeypatch):
    def broken():
        raise ConnectionError("nflverse unreachable")
    monkeypatch.setattr(nv, "load_ff_rankings", broken)
    bundle = SignalBundle(week=9, season=2026)
    _collect_expert_rankings(bundle, Adapter(), [], 9, 2026)
    from fantasy_gm.signals.base import SignalAvailability
    now = datetime.utcnow()
    bundle.availability += [SignalAvailability(name=n, available=True, as_of=now)
                            for n in ("projections", "injuries", "usage_trends",
                                      "vegas_lines", "weather")]

    result = assess(bundle, now=now)

    # FPRANK-04 THEN the bundle reports fresh
    assert result.fresh is True
    # FPRANK-04 AND names the expert rankings as missing
    assert [s["name"] for s in result.stale] == ["expert_rankings"]
    assert result.stale[0]["reason"].startswith("missing")
