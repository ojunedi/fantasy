"""
Market-value (FantasyCalc) currency for trades.

- The FantasyCalc source maps rows to MarketValue keyed by espn id, degrading to
  {} on any error.
- TradeToolContext.value_map() uses market values when available (a player absent
  from the market list is waiver/replacement level, value 0) and falls back to the
  in-house model when the market is unavailable.
"""
from fantasy_gm.agent.trade.tools import TradeToolContext
from fantasy_gm.models import (
    LeagueSettings,
    Platform,
    Position,
    RosterSlot,
    ScoringRules,
    WaiverType,
)
from fantasy_gm.signals.sources import fantasycalc
from fantasy_gm.signals.sources.fantasycalc import MarketValue, get_market_values


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_fantasycalc_maps_by_espn_id(monkeypatch):
    payload = [
        {"player": {"espnId": "3052587", "position": "QB"},
         "value": 789, "positionRank": 17, "overallRank": 150},
        {"player": {"espnId": "4429615", "position": "WR"},
         "value": 3814, "positionRank": 15, "overallRank": 40},
        {"player": {"position": "K"}, "value": 5},  # no espnId → skipped
    ]
    monkeypatch.setattr(fantasycalc, "_cache", {})
    monkeypatch.setattr(fantasycalc.httpx, "get", lambda *a, **k: _FakeResp(payload))
    vals = get_market_values(num_qbs=1, num_teams=12, ppr=1.0)
    assert vals["3052587"].value == 789
    assert vals["3052587"].position_rank == 17
    assert vals["4429615"].value == 3814
    assert len(vals) == 2  # the K with no espnId is dropped


def test_fantasycalc_degrades_to_empty_on_error(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("network down")
    monkeypatch.setattr(fantasycalc, "_cache", {})
    monkeypatch.setattr(fantasycalc.httpx, "get", _boom)
    assert get_market_values() == {}


def _settings():
    slots = [
        RosterSlot(slot_id="qb", position=Position.QB, is_starter=True),
        RosterSlot(slot_id="wr1", position=Position.WR, is_starter=True),
        RosterSlot(slot_id="rb1", position=Position.RB, is_starter=True),
        RosterSlot(slot_id="be0", position=Position.BENCH, is_starter=False),
    ]
    return LeagueSettings(
        platform=Platform.ESPN, league_id="t", season=2026, team_count=12,
        roster_slots=slots, scoring_rules=ScoringRules(rules=[]),
        waiver_type=WaiverType.SNAKE, faab_budget=None,
        playoff_start_week=15, playoff_weeks=[15, 16, 17],
        regular_season_weeks=list(range(1, 15)),
    )


def _ctx_with_market(market):
    ctx = TradeToolContext(adapter=None, settings=_settings(), team_id="8",
                           week=1, season=2026, market_fn=lambda **k: market)
    # Inject caches so value_map() never hits the network.
    ctx._player_index = {
        "qb2": {"position": Position.QB, "name": "Backup QB", "team": "X"},
        "wr1": {"position": Position.WR, "name": "Star WR", "team": "Y"},
        "deep": {"position": Position.WR, "name": "Deep Bench", "team": "Z"},
    }
    ctx._weekly_proj = {"qb2": 18.0, "wr1": 15.0, "deep": 3.0}
    return ctx


def test_value_map_uses_market_and_zeroes_unranked():
    market = {
        "qb2": MarketValue(value=789, position="QB", position_rank=17, overall_rank=150),
        "wr1": MarketValue(value=3814, position="WR", position_rank=15, overall_rank=40),
        # "deep" intentionally absent → waiver/replacement level
    }
    vm = _ctx_with_market(market).value_map()
    assert vm["qb2"].source == "market" and vm["qb2"].value == 789
    assert vm["wr1"].value == 3814
    # A backup QB is worth far less than a startable WR — the whole point.
    assert vm["qb2"].value < vm["wr1"].value
    assert vm["deep"].source == "unranked" and vm["deep"].value == 0.0


def test_value_map_falls_back_to_model_when_market_empty():
    vm = _ctx_with_market({}).value_map()
    # In-house model path: QB gets the 0.85 scarcity multiplier, value > 0.
    assert vm["qb2"].source == "model"
    assert vm["qb2"].value > 0


def _chip_settings():
    slots = [
        RosterSlot(slot_id="qb", position=Position.QB, is_starter=True),
        RosterSlot(slot_id="wr1", position=Position.WR, is_starter=True),
        RosterSlot(slot_id="wr2", position=Position.WR, is_starter=True),
        RosterSlot(slot_id="flex", position=Position.FLEX, is_starter=True),
        RosterSlot(slot_id="be0", position=Position.BENCH, is_starter=False),
    ]
    return LeagueSettings(
        platform=Platform.ESPN, league_id="t", season=2026, team_count=12,
        roster_slots=slots, scoring_rules=ScoringRules(rules=[]),
        waiver_type=WaiverType.SNAKE, faab_budget=None,
        playoff_start_week=15, playoff_weeks=[15, 16, 17],
        regular_season_weeks=list(range(1, 15)),
    )


def test_need_requires_a_material_gap_not_just_below_baseline():
    """Being a few ranks under the last starter is 'thin', not a NEED.

    Guards the real-league case: a QB15 in a 1-QB league starts every week and
    is not a hole to trade for, but a team whose only QB is worthless is.
    """
    from fantasy_gm.models import Player, PlayerStatus, Roster, RosterPlayer

    slots = [
        RosterSlot(slot_id="qb", position=Position.QB, is_starter=True),
        RosterSlot(slot_id="be0", position=Position.BENCH, is_starter=False),
    ]
    settings = LeagueSettings(
        platform=Platform.ESPN, league_id="t", season=2026, team_count=2,
        roster_slots=slots, scoring_rules=ScoringRules(rules=[]),
        waiver_type=WaiverType.SNAKE, faab_budget=None,
        playoff_start_week=15, playoff_weeks=[15, 16, 17],
        regular_season_weeks=list(range(1, 15)),
    )
    # League QB pool: 1000, 600, 450, 200 -> baseline is the 2nd (600).
    market = {p: MarketValue(value=v, position="QB", position_rank=i + 1, overall_rank=i + 1)
              for i, (p, v) in enumerate([("a", 1000), ("b", 600), ("d", 450), ("c", 200)])}

    def ctx_for(pid):
        ctx = TradeToolContext(adapter=None, settings=settings, team_id="8",
                               week=1, season=2026, market_fn=lambda **k: market)
        ctx._player_index = {p: {"position": Position.QB, "name": p, "team": "X"}
                             for p in market}
        ctx._weekly_proj = {p: 10.0 for p in market}
        player = Player(platform_id=pid, name=pid, position=Position.QB,
                        eligible_positions=[Position.QB], status=PlayerStatus.ACTIVE)
        ctx._roster = Roster(team_id="8", team_name="T", owner_name="Me", week=1, season=2026,
                             players=[RosterPlayer(player=player, slot=Position.QB,
                                                   is_starter=True)])
        return ctx

    # 450 is under the 600 baseline but clears 0.6 * 600 = 360 -> thin, not a need.
    thin = ctx_for("d").roster_needs(ctx_for("d")._roster)[Position.QB]
    assert thin["need"] is False
    assert thin["thin"] is True

    # 200 is materially below startable -> a genuine need.
    real = ctx_for("c").roster_needs(ctx_for("c")._roster)[Position.QB]
    assert real["need"] is True


def test_trade_chips_includes_bench_and_respects_flex():
    """Depth beyond the starting lineup is tradeable even below replacement."""
    from fantasy_gm.models import Player, PlayerStatus, Roster, RosterPlayer

    def rp(pid, pos, starter):
        p = Player(platform_id=pid, name=pid, position=pos,
                   eligible_positions=[pos], status=PlayerStatus.ACTIVE)
        return RosterPlayer(player=p, slot=pos, is_starter=starter)

    players = [
        rp("q1", Position.QB, True), rp("q2", Position.QB, False),
        rp("w1", Position.WR, True), rp("w2", Position.WR, True),
        rp("w3", Position.WR, True), rp("w4", Position.WR, False),
    ]
    market = {
        "q1": MarketValue(value=1000, position="QB", position_rank=5, overall_rank=40),
        "q2": MarketValue(value=500, position="QB", position_rank=20, overall_rank=150),
        "w1": MarketValue(value=2000, position="WR", position_rank=3, overall_rank=10),
        "w2": MarketValue(value=1500, position="WR", position_rank=8, overall_rank=25),
        "w3": MarketValue(value=800, position="WR", position_rank=30, overall_rank=90),
        "w4": MarketValue(value=300, position="WR", position_rank=60, overall_rank=200),
    }
    ctx = TradeToolContext(adapter=None, settings=_chip_settings(), team_id="8",
                           week=1, season=2026, market_fn=lambda **k: market)
    ctx._player_index = {p.player.platform_id: {"position": p.player.position,
                                                "name": p.player.platform_id, "team": "X"}
                         for p in players}
    ctx._weekly_proj = {pid: 10.0 for pid in market}
    ctx._roster = Roster(team_id="8", team_name="T", owner_name="Me",
                         players=players, week=1, season=2026)

    chips = [rp_.player.platform_id for rp_, _ in ctx.trade_chips(ctx._roster)]
    # q1 locked at QB; w1/w2 locked at WR; w3 takes the flex slot as the best
    # remaining flex-eligible player. What's left is genuinely tradeable.
    assert chips == ["q2", "w4"]


def _one_qb_league(team_count: int = 2):
    slots = [
        RosterSlot(slot_id="qb", position=Position.QB, is_starter=True),
        RosterSlot(slot_id="be0", position=Position.BENCH, is_starter=False),
    ]
    return LeagueSettings(
        platform=Platform.ESPN, league_id="t", season=2026, team_count=team_count,
        roster_slots=slots, scoring_rules=ScoringRules(rules=[]),
        waiver_type=WaiverType.SNAKE, faab_budget=None,
        playoff_start_week=15, playoff_weeks=[15, 16, 17],
        regular_season_weeks=list(range(1, 15)),
    )


def _qb_ctx(roster_pids, market_values):
    """A 1-QB league context whose roster holds `roster_pids`."""
    from fantasy_gm.models import Player, PlayerStatus, Roster, RosterPlayer

    market = {p: MarketValue(value=v, position="QB", position_rank=i + 1,
                             overall_rank=i + 1)
              for i, (p, v) in enumerate(market_values)}
    ctx = TradeToolContext(adapter=None, settings=_one_qb_league(), team_id="8",
                           week=1, season=2026, market_fn=lambda **k: market)
    ctx._player_index = {p: {"position": Position.QB, "name": p, "team": "X"}
                         for p in market}
    ctx._weekly_proj = {p: 10.0 for p in market}
    players = [
        RosterPlayer(player=Player(platform_id=p, name=p, position=Position.QB,
                                   eligible_positions=[Position.QB],
                                   status=PlayerStatus.ACTIVE),
                     slot=Position.QB if i == 0 else Position.BENCH,
                     is_starter=(i == 0))
        for i, p in enumerate(roster_pids)
    ]
    ctx._roster = Roster(team_id="8", team_name="T", owner_name="Me", week=1,
                         season=2026, players=players)
    return ctx


_QB_POOL = [("a", 1000), ("b", 600), ("d", 450), ("c", 200)]


def test_a_covered_slot_is_never_reported_as_unfilled():
    """The phantom QB crisis: `startable` counts players clearing the LAST
    LEAGUE-WIDE STARTER's value, so most of the league scores 0 there while
    starting a QB every week. `filled` must tell the truth."""
    n = _qb_ctx(["d"], _QB_POOL).roster_needs(_qb_ctx(["d"], _QB_POOL)._roster)[Position.QB]
    assert n["startable"] == 0        # below the bar, as before
    assert n["filled"] == 1           # but the slot IS covered
    assert n["unfilled"] == 0
    assert n["need"] is False


def test_an_actually_empty_slot_is_a_need():
    ctx = _qb_ctx([], _QB_POOL)
    n = ctx.roster_needs(ctx._roster)[Position.QB]
    assert n["filled"] == 0 and n["unfilled"] == 1
    assert n["need"] is True


def test_just_under_the_bar_is_not_even_thin():
    """`best < bar` alone flags over half a 1-QB league by construction."""
    pool = [("a", 1000), ("b", 600), ("e", 580)]
    ctx = _qb_ctx(["e"], pool)
    n = ctx.roster_needs(ctx._roster)[Position.QB]
    assert n["best"] < n["bar"]        # genuinely below the last starter
    assert n["thin"] is False          # ...but not by a material margin
    assert n["need"] is False


def test_materially_below_the_bar_is_thin():
    ctx = _qb_ctx(["d"], _QB_POOL)
    n = ctx.roster_needs(ctx._roster)[Position.QB]
    assert n["thin"] is True and n["need"] is False


def test_needs_output_leads_with_bodies_not_quality():
    """The model read '0startable/1req' as an empty slot and called it a crisis."""
    ctx = _qb_ctx(["d"], _QB_POOL)
    ctx._all_rosters = [ctx._roster]
    out, _ = ctx.dispatch("get_roster_needs", {})
    assert "0startable" not in out
    assert "1/1filled" in out
    assert "NOT a hole" in out          # the guidance the model needs
    assert "NEED" not in out.split("READ THIS CAREFULLY")[1].split("\n  Team")[1]
