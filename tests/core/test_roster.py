"""Tests for roster legality checker."""
import pytest
from fantasy_gm.core.roster import check_lineup_legality, slot_accepts
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
        name=name or pid,
        position=position,
        eligible_positions=[position],
        status=PlayerStatus.ACTIVE,
    )


def make_settings(slots: list[tuple[str, Position, bool]]) -> LeagueSettings:
    roster_slots = [
        RosterSlot(slot_id=sid, position=pos, is_starter=starter)
        for sid, pos, starter in slots
    ]
    return LeagueSettings(
        platform=Platform.ESPN,
        league_id="test",
        season=2024,
        team_count=12,
        roster_slots=roster_slots,
        scoring_rules=ScoringRules(rules=[]),
        waiver_type=WaiverType.SNAKE,
        faab_budget=None,
        playoff_start_week=15,
        playoff_weeks=[15, 16, 17],
        regular_season_weeks=list(range(1, 15)),
    )


class TestSlotAccepts:
    def test_exact_position_match(self):
        assert slot_accepts(Position.QB, Position.QB) is True
        assert slot_accepts(Position.RB, Position.RB) is True

    def test_position_mismatch(self):
        assert slot_accepts(Position.QB, Position.RB) is False
        assert slot_accepts(Position.RB, Position.QB) is False

    def test_flex_accepts_rb_wr_te(self):
        assert slot_accepts(Position.FLEX, Position.RB) is True
        assert slot_accepts(Position.FLEX, Position.WR) is True
        assert slot_accepts(Position.FLEX, Position.TE) is True

    def test_flex_rejects_qb_k_dst(self):
        assert slot_accepts(Position.FLEX, Position.QB) is False
        assert slot_accepts(Position.FLEX, Position.K) is False
        assert slot_accepts(Position.FLEX, Position.DST) is False

    def test_super_flex_accepts_qb(self):
        assert slot_accepts(Position.SUPER_FLEX, Position.QB) is True
        assert slot_accepts(Position.SUPER_FLEX, Position.RB) is True

    def test_bench_accepts_any(self):
        for pos in [Position.QB, Position.RB, Position.WR, Position.TE, Position.K, Position.DST]:
            assert slot_accepts(Position.BENCH, pos) is True


class TestLineupLegality:
    def setup_method(self):
        self.settings = make_settings([
            ("qb_0", Position.QB, True),
            ("rb_0", Position.RB, True),
            ("rb_1", Position.RB, True),
            ("wr_0", Position.WR, True),
            ("wr_1", Position.WR, True),
            ("te_0", Position.TE, True),
            ("flex_0", Position.FLEX, True),
            ("be_0", Position.BENCH, False),
        ])

    def _all_players(self) -> dict[str, Player]:
        return {
            "qb_0": make_player("p1", Position.QB),
            "rb_0": make_player("p2", Position.RB),
            "rb_1": make_player("p3", Position.RB),
            "wr_0": make_player("p4", Position.WR),
            "wr_1": make_player("p5", Position.WR),
            "te_0": make_player("p6", Position.TE),
            "flex_0": make_player("p7", Position.RB),   # RB in FLEX slot — legal
            "be_0": make_player("p8", Position.WR),
        }

    def test_valid_lineup_is_legal(self):
        result = check_lineup_legality(self._all_players(), self.settings)
        assert result.is_legal is True
        assert result.errors == []

    def test_missing_slot_is_illegal(self):
        lineup = self._all_players()
        del lineup["qb_0"]
        result = check_lineup_legality(lineup, self.settings)
        assert result.is_legal is False
        assert any("qb_0" in e.message for e in result.errors)

    def test_duplicate_player_is_illegal(self):
        lineup = self._all_players()
        # Assign same player to two slots
        lineup["rb_1"] = lineup["rb_0"]
        result = check_lineup_legality(lineup, self.settings)
        assert result.is_legal is False
        assert any("multiple slots" in e.message for e in result.errors)

    def test_wrong_position_in_slot_is_illegal(self):
        lineup = self._all_players()
        lineup["qb_0"] = make_player("p99", Position.RB)  # RB in QB slot
        result = check_lineup_legality(lineup, self.settings)
        assert result.is_legal is False
        assert any("QB" in e.message for e in result.errors)

    def test_wr_in_flex_slot_is_legal(self):
        lineup = self._all_players()
        lineup["flex_0"] = make_player("p9", Position.WR)
        result = check_lineup_legality(lineup, self.settings)
        assert result.is_legal is True

    def test_qb_in_flex_slot_is_illegal(self):
        lineup = self._all_players()
        lineup["flex_0"] = make_player("p9", Position.QB)
        result = check_lineup_legality(lineup, self.settings)
        assert result.is_legal is False
