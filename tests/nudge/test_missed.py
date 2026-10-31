"""A missed lineup recommendation and its cost (pre-kickoff projections only)."""
from __future__ import annotations

from datetime import datetime

import pytest

from fantasy_gm.db.store import DecisionStore
from fantasy_gm.models import (
    DecisionRecord,
    DecisionType,
    HumanResponse,
    Player,
    Position,
    Roster,
    RosterPlayer,
)
from fantasy_gm.nudge.missed import record_missed_lineups

SEASON, WEEK, TEAM = 2026, 6, "8"
MADE = datetime(2026, 10, 14, 15, 0)            # Wednesday of week 6, UTC
BEFORE_KICKOFF = datetime(2026, 10, 18, 16, 0)  # Sunday 12 PM ET — week 6 kicks off at 1 PM
DURING_WEEK = datetime(2026, 10, 19, 23, 0)     # Monday night: games still going
AFTER_KICKOFF = datetime(2026, 10, 20, 12, 0)   # Tuesday 8 AM ET: the week is settled
LATE_RESPONSE = datetime(2026, 10, 19, 16, 0)   # Monday — after kickoff

# Saved on the decision when it was made. Recommended: A, B (60 + 60 = 120).
PROJECTIONS = {"A": 60.0, "B": 60.0, "C": 52.5}


class League:
    """Fake adapter: the lineup that played, and the week's actual points."""

    def __init__(self, standing=("A", "C"), actual=None):
        self.standing = list(standing)
        self.actual = actual
        self.roster_reads = 0

    def get_roster(self, team_id, week, season, fresh=False):
        self.roster_reads += 1
        self.fresh = fresh
        players = [RosterPlayer(player=Player(platform_id=pid, name=pid, position=Position.WR,
                                              eligible_positions=[Position.WR]),
                                slot=Position.WR, is_starter=True) for pid in self.standing]
        return Roster(team_id=team_id, team_name="Me", owner_name="", players=players,
                      week=week, season=season)

    def get_actual_scores(self, week, season):
        if self.actual is None:
            raise RuntimeError("week not finished")
        return self.actual


@pytest.fixture
def store(tmp_path):
    return DecisionStore(tmp_path / "decisions.db")


def _lineup(store, response=None, reason=None, made=MADE, starters=("A", "B"),
            projections=PROJECTIONS, responded=None) -> DecisionRecord:
    """A lineup decision; a response defaults to the day after it was made."""
    record = DecisionRecord(
        week=WEEK, season=SEASON, created_at=made, decision_type=DecisionType.LINEUP,
        inputs_snapshot={"projections": dict(projections)}, signals_staleness={},
        recommendation={"starter_player_ids": list(starters)}, memo="", confidence=0.8,
        human_response=response, override_reason=reason,
        responded_at=(responded or made.replace(day=made.day + 1)) if response else None,
    )
    store.save(record)
    return record


def test_lmiss01_an_unactioned_week_after_kickoff_is_recorded_as_missed(store):
    record = _lineup(store)

    record_missed_lineups(store, League(), TEAM, SEASON, now=AFTER_KICKOFF)
    stored = store.get(record.id)

    # LMISS-01 THEN the decision's outcome records it as missed
    assert stored.outcome["missed"]["cost"] == 7.5
    # LMISS-01 AND the decision has no human response
    assert stored.human_response is None
    # LMISS-01 AND the decision has no override reason
    assert stored.override_reason is None


def test_lmiss02_a_week_with_an_actioned_decision_is_not_missed(store):
    approved = _lineup(store, HumanResponse.APPROVED)
    unactioned = _lineup(store, made=datetime(2026, 10, 15, 15, 0))

    record_missed_lineups(store, League(), TEAM, SEASON, now=AFTER_KICKOFF)

    # LMISS-02 THEN neither decision is recorded as missed
    assert store.get(approved.id).outcome is None
    assert store.get(unactioned.id).outcome is None


@pytest.mark.parametrize("now", [BEFORE_KICKOFF, DURING_WEEK])
def test_lmiss03_nothing_is_recorded_before_the_week_is_settled(store, now):
    record = _lineup(store)

    recorded = record_missed_lineups(store, League(), TEAM, SEASON, now=now)

    # LMISS-03 THEN nothing is recorded
    assert recorded == []
    assert store.get(record.id).outcome is None


def test_lmiss04_a_recorded_miss_is_not_recomputed(store):
    record = _lineup(store)
    record_missed_lineups(store, League(), TEAM, SEASON, now=AFTER_KICKOFF)
    first = store.get(record.id).outcome

    league = League(standing=("B", "C"), actual={"A": 1.0})
    record_missed_lineups(store, league, TEAM, SEASON, now=AFTER_KICKOFF)

    # LMISS-04 THEN the recorded miss is unchanged
    assert store.get(record.id).outcome == first
    # LMISS-04 AND the standing lineup is not read again
    assert league.roster_reads == 0


def test_lmiss05_the_cost_is_the_difference_in_saved_projections(store):
    record = _lineup(store)

    record_missed_lineups(store, League(standing=("A", "C")), TEAM, SEASON, now=AFTER_KICKOFF)
    missed = store.get(record.id).outcome["missed"]

    # LMISS-05 THEN the cost is 7.5
    assert (missed["recommended_projected"], missed["standing_projected"]) == (120.0, 112.5)
    assert missed["cost"] == 7.5
    # LMISS-05 AND the recommended and standing starters are recorded
    assert missed["recommended_ids"] == ["A", "B"]
    assert missed["standing_ids"] == ["A", "C"]


def test_lmiss06_a_standing_starter_with_no_saved_projection_counts_as_zero_and_is_named(store):
    record = _lineup(store)

    record_missed_lineups(store, League(standing=("A", "Z")), TEAM, SEASON, now=AFTER_KICKOFF)
    missed = store.get(record.id).outcome["missed"]

    # LMISS-06 THEN that starter counts as 0 in the standing total
    assert missed["standing_projected"] == 60.0
    # LMISS-06 AND the miss lists that starter as unprojected
    assert missed["unprojected"] == ["Z"]


def test_lmiss07_actual_points_are_recorded_as_hindsight_never_as_the_cost(store):
    record = _lineup(store)
    actual = {"A": 10.0, "B": 3.0, "C": 40.0}   # hindsight says the standing lineup won

    record_missed_lineups(store, League(standing=("A", "C"), actual=actual), TEAM, SEASON,
                          now=AFTER_KICKOFF)
    missed = store.get(record.id).outcome["missed"]

    # LMISS-07 THEN the actual totals for both lineups are recorded as hindsight
    assert missed["hindsight"] == {"recommended_actual": 13.0, "standing_actual": 50.0}
    # LMISS-07 AND the cost is still the difference in saved projections
    assert missed["cost"] == 7.5


def test_an_abstention_is_never_a_miss(store):
    abstained = _lineup(store, starters=())

    record_missed_lineups(store, League(), TEAM, SEASON, now=AFTER_KICKOFF)

    assert store.get(abstained.id).outcome is None


def test_the_miss_lands_on_the_newest_pre_kickoff_run(store):
    older = _lineup(store)
    newer = _lineup(store, made=datetime(2026, 10, 16, 15, 0))

    record_missed_lineups(store, League(), TEAM, SEASON, now=AFTER_KICKOFF)

    assert store.get(older.id).outcome is None
    assert store.get(newer.id).outcome["missed"]["cost"] == 7.5


def test_lmiss09_a_run_made_after_kickoff_is_never_charged(store):
    # Monday of week 6: the week's games have kicked off; its projections are hindsight.
    late = _lineup(store, made=datetime(2026, 10, 19, 16, 0))

    recorded = record_missed_lineups(store, League(), TEAM, SEASON, now=AFTER_KICKOFF)

    # LMISS-09 THEN nothing is recorded for that run
    assert recorded == []
    assert store.get(late.id).outcome is None


def test_lmiss09_the_miss_lands_on_the_pre_kickoff_run_not_a_later_one(store):
    early = _lineup(store)
    late = _lineup(store, made=datetime(2026, 10, 19, 16, 0))

    record_missed_lineups(store, League(), TEAM, SEASON, now=AFTER_KICKOFF)

    assert store.get(early.id).outcome["missed"]["cost"] == 7.5
    assert store.get(late.id).outcome is None


def test_lmiss10_a_response_after_kickoff_does_not_erase_the_miss(store):
    record = _lineup(store, HumanResponse.APPROVED, responded=LATE_RESPONSE)

    record_missed_lineups(store, League(), TEAM, SEASON, now=AFTER_KICKOFF)

    # LMISS-10 THEN the week is recorded as missed
    assert store.get(record.id).outcome["missed"]["cost"] == 7.5
    # LMISS-10 AND the late response is kept as it was
    assert store.get(record.id).human_response == HumanResponse.APPROVED


def test_a_response_with_no_recorded_time_counts_as_in_time(store):
    record = DecisionRecord(
        week=WEEK, season=SEASON, created_at=MADE, decision_type=DecisionType.LINEUP,
        inputs_snapshot={"projections": PROJECTIONS}, signals_staleness={},
        recommendation={"starter_player_ids": ["A", "B"]}, memo="", confidence=0.8,
        human_response=HumanResponse.APPROVED,
    )
    store.save(record)

    assert record_missed_lineups(store, League(), TEAM, SEASON, now=AFTER_KICKOFF) == []


def test_the_lineup_is_read_fresh(store):
    _lineup(store)
    league = League()

    record_missed_lineups(store, league, TEAM, SEASON, now=AFTER_KICKOFF)

    assert league.fresh is True


def test_an_unprojected_recommended_starter_is_named_too(store):
    record = _lineup(store, starters=("A", "Q"))

    record_missed_lineups(store, League(), TEAM, SEASON, now=AFTER_KICKOFF)

    assert store.get(record.id).outcome["missed"]["unprojected"] == ["Q"]


def test_responding_records_when_it_happened(store):
    record = _lineup(store)
    store.record_human_response(record.id, HumanResponse.APPROVED)
    assert store.get(record.id).responded_at is not None
