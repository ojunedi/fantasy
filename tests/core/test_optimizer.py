"""Tests for the deterministic lineup optimizer."""
import pytest
from fantasy_gm.core.optimizer import optimize_lineup, projected_score
from fantasy_gm.models import (
    LeagueSettings,
    Platform,
    Player,
    PlayerStatus,
    Position,
    RosterSlot,
    ScoringRules,
    WaiverType,
)


def make_player(pid: str, position: Position, name: str | None = None) -> Player:
    return Player(
        platform_id=pid,
        name=name or f"Player {pid}",
        position=position,
        eligible_positions=[position],
        status=PlayerStatus.ACTIVE,
    )


def make_settings_standard() -> LeagueSettings:
    """Standard 12-team PPR roster: QB, 2RB, 2WR, TE, FLEX, K, DST + 7 bench."""
    slots = [
        RosterSlot(slot_id="qb", position=Position.QB, is_starter=True),
        RosterSlot(slot_id="rb1", position=Position.RB, is_starter=True),
        RosterSlot(slot_id="rb2", position=Position.RB, is_starter=True),
        RosterSlot(slot_id="wr1", position=Position.WR, is_starter=True),
        RosterSlot(slot_id="wr2", position=Position.WR, is_starter=True),
        RosterSlot(slot_id="te", position=Position.TE, is_starter=True),
        RosterSlot(slot_id="flex", position=Position.FLEX, is_starter=True),
        RosterSlot(slot_id="k", position=Position.K, is_starter=True),
        RosterSlot(slot_id="dst", position=Position.DST, is_starter=True),
        *[RosterSlot(slot_id=f"be{i}", position=Position.BENCH, is_starter=False) for i in range(7)],
    ]
    return LeagueSettings(
        platform=Platform.ESPN,
        league_id="test",
        season=2024,
        team_count=12,
        roster_slots=slots,
        scoring_rules=ScoringRules(rules=[]),
        waiver_type=WaiverType.SNAKE,
        faab_budget=None,
        playoff_start_week=15,
        playoff_weeks=[15, 16, 17],
        regular_season_weeks=list(range(1, 15)),
    )


class TestOptimizeLineup:
    def setup_method(self):
        self.settings = make_settings_standard()
        # 16-player roster: 1 QB, 3 RB, 4 WR, 2 TE, 1 K, 1 DST, 4 bench padding
        self.players = [
            make_player("qb1", Position.QB),
            make_player("rb1", Position.RB),
            make_player("rb2", Position.RB),
            make_player("rb3", Position.RB),
            make_player("wr1", Position.WR),
            make_player("wr2", Position.WR),
            make_player("wr3", Position.WR),
            make_player("wr4", Position.WR),
            make_player("te1", Position.TE),
            make_player("te2", Position.TE),
            make_player("k1", Position.K),
            make_player("dst1", Position.DST),
            make_player("rb4", Position.RB),
            make_player("wr5", Position.WR),
            make_player("qb2", Position.QB),
            make_player("rb5", Position.RB),
        ]

    def test_optimizer_returns_all_players(self):
        projections = {p.platform_id: 10.0 for p in self.players}
        result = optimize_lineup(self.players, projections, self.settings)
        assert len(result) == len(self.players)

    def test_optimal_rb_gets_flex_over_weak_rb(self):
        """When one RB is much better, they should start in FLEX over a weak RB."""
        projections = {p.platform_id: 0.0 for p in self.players}
        projections["rb1"] = 20.0
        projections["rb2"] = 18.0
        projections["rb3"] = 15.0  # third-best RB — should go into FLEX
        projections["wr1"] = 14.0
        projections["wr2"] = 13.0
        projections["wr3"] = 5.0
        projections["wr4"] = 4.0
        projections["te1"] = 8.0

        result = optimize_lineup(self.players, projections, self.settings)
        starters = {rp.player.platform_id for rp in result if rp.is_starter}

        # Top 2 RBs, top WRs, and either rb3 in FLEX should be starters
        assert "rb1" in starters
        assert "rb2" in starters
        assert "rb3" in starters  # should go in FLEX

    def test_correct_number_of_starters(self):
        projections = {p.platform_id: float(i) for i, p in enumerate(self.players)}
        result = optimize_lineup(self.players, projections, self.settings)
        starter_count = sum(1 for rp in result if rp.is_starter)
        bench_count = sum(1 for rp in result if not rp.is_starter)
        assert starter_count == 9  # QB, 2RB, 2WR, TE, FLEX, K, DST
        assert bench_count == 7

    def test_highest_projected_players_start(self):
        """The 9 highest-projected players (respecting position constraints) should start."""
        projections = {
            "qb1": 30.0, "rb1": 25.0, "rb2": 22.0, "rb3": 18.0,
            "wr1": 20.0, "wr2": 19.0, "wr3": 5.0, "wr4": 4.0,
            "te1": 12.0, "te2": 3.0,
            "k1": 10.0, "dst1": 9.0,
            "rb4": 1.0, "wr5": 1.0, "qb2": 1.0, "rb5": 1.0,
        }
        result = optimize_lineup(self.players, projections, self.settings)
        total = projected_score(result, projections)
        # Should include qb1(30), rb1(25), rb2(22), wr1(20), wr2(19), te1(12), rb3 in FLEX(18), k1(10), dst1(9)
        assert total == pytest.approx(30 + 25 + 22 + 20 + 19 + 12 + 18 + 10 + 9)

    def test_no_player_starts_twice(self):
        projections = {p.platform_id: 10.0 for p in self.players}
        result = optimize_lineup(self.players, projections, self.settings)
        starter_ids = [rp.player.platform_id for rp in result if rp.is_starter]
        assert len(starter_ids) == len(set(starter_ids))

    def test_zero_projections_still_fills_roster(self):
        projections = {}
        result = optimize_lineup(self.players, projections, self.settings)
        assert len(result) == len(self.players)
        starter_count = sum(1 for rp in result if rp.is_starter)
        assert starter_count == 9
