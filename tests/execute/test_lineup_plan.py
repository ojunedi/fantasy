"""Tests for the deterministic lineup-move planner (the write path's core)."""
import pytest

from fantasy_gm.execute.base import LineupMove
from fantasy_gm.execute.lineup_plan import (
    BENCH_SLOT,
    build_espn_transaction,
    build_target_slots,
    plan_moves,
)
from fantasy_gm.models import (
    LeagueSettings,
    Platform,
    Player,
    PlayerStatus,
    Position,
    Roster,
    RosterPlayer,
    RosterSlot,
    ScoringRules,
    WaiverType,
)


def make_player(pid, pos):
    return Player(platform_id=pid, name=f"Player {pid}", position=pos,
                  eligible_positions=[pos], status=PlayerStatus.ACTIVE)


def settings():
    slots = [
        RosterSlot(slot_id="qb", position=Position.QB, is_starter=True),
        RosterSlot(slot_id="rb1", position=Position.RB, is_starter=True),
        RosterSlot(slot_id="wr1", position=Position.WR, is_starter=True),
        RosterSlot(slot_id="flex", position=Position.FLEX, is_starter=True),
        RosterSlot(slot_id="be0", position=Position.BENCH, is_starter=False),
        RosterSlot(slot_id="be1", position=Position.BENCH, is_starter=False),
    ]
    return LeagueSettings(
        platform=Platform.ESPN, league_id="1", season=2025, team_count=12,
        roster_slots=slots, scoring_rules=ScoringRules(rules=[]),
        waiver_type=WaiverType.SNAKE, faab_budget=None,
        playoff_start_week=15, playoff_weeks=[15], regular_season_weeks=list(range(1, 15)),
    )


def roster_players():
    return [
        RosterPlayer(player=make_player("qb1", Position.QB), slot=Position.QB, is_starter=True),
        RosterPlayer(player=make_player("rb1", Position.RB), slot=Position.RB, is_starter=True),
        RosterPlayer(player=make_player("wr1", Position.WR), slot=Position.WR, is_starter=True),
        RosterPlayer(player=make_player("rb2", Position.RB), slot=Position.FLEX, is_starter=True),
        RosterPlayer(player=make_player("wr2", Position.WR), slot=Position.BENCH, is_starter=False),
        RosterPlayer(player=make_player("te1", Position.TE), slot=Position.BENCH, is_starter=False),
    ]


class TestBuildTargetSlots:
    def test_proposed_starters_get_starter_slots(self):
        players = roster_players()
        target = build_target_slots(players, ["qb1", "rb1", "wr1", "rb2"], settings())
        assert target["qb1"] == 0    # QB slot
        assert target["rb1"] == 2    # RB slot
        assert target["wr1"] == 4    # WR slot
        assert target["rb2"] == 23   # RB in FLEX
        assert target["wr2"] == BENCH_SLOT
        assert target["te1"] == BENCH_SLOT

    def test_swapping_a_starter_for_a_bench_player(self):
        players = roster_players()
        # Start wr2 (currently benched) instead of wr1
        target = build_target_slots(players, ["qb1", "rb1", "wr2", "rb2"], settings())
        assert target["wr2"] == 4          # wr2 now starts at WR
        assert target["wr1"] == BENCH_SLOT  # wr1 benched


class TestPlanMoves:
    def test_no_moves_when_lineup_unchanged(self):
        current = {"qb1": 0, "rb1": 2, "wr1": 4, "rb2": 23, "wr2": 20, "te1": 20}
        target = dict(current)
        names = {k: k for k in current}
        assert plan_moves(current, target, names) == []

    def test_single_swap_produces_two_moves(self):
        current = {"qb1": 0, "rb1": 2, "wr1": 4, "rb2": 23, "wr2": 20, "te1": 20}
        # swap wr1 out, wr2 in
        target = dict(current)
        target["wr1"] = 20
        target["wr2"] = 4
        names = {k: k for k in current}
        moves = plan_moves(current, target, names)
        assert len(moves) == 2
        by_player = {m.player_id: m for m in moves}
        assert by_player["wr1"].from_slot == 4 and by_player["wr1"].to_slot == 20
        assert by_player["wr2"].from_slot == 20 and by_player["wr2"].to_slot == 4

    def test_missing_current_slot_is_skipped(self):
        current = {"qb1": 0}
        target = {"qb1": 0, "unknown": 4}
        moves = plan_moves(current, target, {})
        assert moves == []


class TestBuildEspnTransaction:
    def test_transaction_shape(self):
        moves = [LineupMove("123", "Player 123", from_slot=20, to_slot=4)]
        txn = build_espn_transaction("8", week=3, season=2025, moves=moves, swid="{SWID}")
        assert txn["teamId"] == 8
        assert txn["type"] == "ROSTER"
        assert txn["scoringPeriodId"] == 3
        assert txn["executionType"] == "EXECUTE"
        assert len(txn["items"]) == 1
        item = txn["items"][0]
        assert item["playerId"] == 123
        assert item["type"] == "LINEUP"
        assert item["fromLineupSlotId"] == 20
        assert item["toLineupSlotId"] == 4
