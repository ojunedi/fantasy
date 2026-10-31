"""Scan inputs built from the platform: what a fully available roster means.

The scoring tests hand-set startability; these drive `gather_scan_inputs`,
where a bye week or an injury could otherwise open a fake starting slot.
"""
from __future__ import annotations

from fantasy_gm.agent.waiver_agent import gather_scan_inputs, score_candidates
from fantasy_gm.models import (
    FreeAgent,
    LeagueSettings,
    Platform,
    Player,
    PlayerProjection,
    PlayerStatus,
    Position,
    Roster,
    RosterPlayer,
    RosterSlot,
    ScoringRules,
    WaiverScanState,
    WaiverType,
)

WEEK, SEASON = 9, 2026


def _league() -> LeagueSettings:
    slots = [RosterSlot(slot_id="K", position=Position.K, is_starter=True),
             RosterSlot(slot_id="WR1", position=Position.WR, is_starter=True),
             RosterSlot(slot_id="WR2", position=Position.WR, is_starter=True),
             RosterSlot(slot_id="BE", position=Position.BENCH, is_starter=False)]
    return LeagueSettings(platform=Platform.ESPN, league_id="t", season=SEASON, team_count=12,
                          roster_slots=slots, scoring_rules=ScoringRules(rules=[]),
                          waiver_type=WaiverType.ROLLING, playoff_start_week=15,
                          playoff_weeks=[15, 16, 17], regular_season_weeks=list(range(1, 15)))


def _player(pid, name, pos, status=PlayerStatus.ACTIVE):
    return Player(platform_id=pid, name=name, position=pos, eligible_positions=[pos], status=status)


class Adapter:
    """Rest-of-season per-game projections; nothing here knows about byes."""

    league_id = "t"

    def __init__(self, roster, free_agents, ros):
        self._roster, self._fas, self._ros = roster, free_agents, ros

    def get_roster(self, team_id, week, season, fresh=False):
        return Roster(team_id="1", team_name="Me", owner_name="", week=week, season=season,
                      players=[RosterPlayer(player=p, slot=p.position, is_starter=True)
                               for p in self._roster])

    def get_free_agents(self, week, season, position_filter=None, fresh=False):
        return [FreeAgent(player=p) for p in self._fas]

    def get_ros_projections(self, week, season):
        everyone = self._roster + self._fas
        return [PlayerProjection(player_id=p.platform_id, player_name=p.name,
                                 projected_points=self._ros[p.platform_id], position=p.position,
                                 week=week, season=season)
                for p in everyone if p.platform_id in self._ros]


def test_kicker_on_bye_keeps_his_value_so_a_weaker_kicker_is_not_recommended():
    # My kicker is on bye this week — a weekly projection would read 0.0 and
    # open his slot. His rest-of-season rate does not change.
    mine = _player("1", "Bye Kicker", Position.K)
    fa = _player("2", "Waiver Kicker", Position.K)
    adapter = Adapter([mine], [fa], {"1": 8.5, "2": 8.0})

    roster, candidates, _ = gather_scan_inputs(adapter, "1", WEEK, SEASON, _league())
    result = score_candidates(candidates, roster, _league(), WEEK)

    assert roster == [{"player_id": "1", "name": "Bye Kicker", "position": "K", "ros_value": 8.5}]
    assert candidates[0]["startable_weeks"] == 0
    assert result.scan_state == WaiverScanState.NO_CANDIDATE
    assert result.closest_miss == "Waiver Kicker"


def test_injured_starter_counts_as_available_so_his_slot_is_not_open():
    wr1 = _player("1", "Star WR", Position.WR, PlayerStatus.OUT)
    wr2 = _player("2", "Solid WR", Position.WR)
    wr3 = _player("3", "Bench WR", Position.WR)
    fa = _player("4", "Waiver WR", Position.WR)
    adapter = Adapter([wr1, wr2, wr3], [fa], {"1": 15.0, "2": 14.0, "3": 6.0, "4": 10.0})

    roster, candidates, _ = gather_scan_inputs(adapter, "1", WEEK, SEASON, _league())

    # Beats the bench WR, but on a fully available roster would not start
    assert candidates[0]["startable_weeks"] == 0
    assert candidates[0]["start_gap"] == 4.0


def test_recommendation_always_names_a_displaced_player():
    wr1, wr2 = _player("1", "WR A", Position.WR), _player("2", "WR B", Position.WR)
    fa = _player("3", "Waiver WR", Position.WR)
    adapter = Adapter([wr1, wr2], [fa], {"1": 15.0, "2": 9.0, "3": 12.0})

    roster, candidates, _ = gather_scan_inputs(adapter, "1", WEEK, SEASON, _league())
    result = score_candidates(candidates, roster, _league(), WEEK)

    assert result.scan_state == WaiverScanState.RECOMMENDATION
    assert result.displaced_player == "WR B"
    assert result.value_margin == 3.0
    # the filing step sends these ids to ESPN
    assert result.candidate_id == "3"
    assert result.displaced_id == "2"
