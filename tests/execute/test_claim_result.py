"""Reading a filed claim's fate, against ESPN's real status names."""
from __future__ import annotations

from fantasy_gm.execute.waiver_api import resolve_claim

TEAM, WEEK = "8", 4
ADD, DROP = "4711533", "4428850"
FILING = {"transaction": {"items": [
    {"playerId": int(ADD), "type": "ADD", "fromTeamId": 0, "toTeamId": 8},
    {"playerId": int(DROP), "type": "DROP", "fromTeamId": 8, "toTeamId": 0},
]}}


def _claim(status, team=TEAM, add=ADD, drop=DROP, week=WEEK):
    return {"type": "WAIVER", "status": status, "teamId": int(team), "scoringPeriodId": week,
            "items": [{"playerId": int(add), "type": "ADD"},
                      {"playerId": int(drop), "type": "DROP"}]}


def test_wadd24_any_other_failure_is_not_a_priority_loss():
    # Our drop was already gone; meanwhile someone else did take the add player.
    transactions = [_claim("FAILED_PLAYERALREADYDROPPED"), _claim("EXECUTED", team="10", drop="1")]

    result = resolve_claim(transactions, FILING, TEAM, WEEK)

    # WADD-24 THEN the result is recorded as failed with ESPN's reason
    assert result.state == "failed"
    assert result.reason == "FAILED_PLAYERALREADYDROPPED"
    # WADD-24 AND it is not recorded as lost to priority
    assert result.winner_team_id is None


def test_left_the_pool_with_no_winning_claim_found_is_failed_not_lost():
    result = resolve_claim([_claim("FAILED_INVALIDPLAYERSOURCE")], FILING, TEAM, WEEK)
    assert result.state == "failed"


def test_wadd26_a_cancelled_claim_is_recorded_as_cancelled():
    result = resolve_claim([_claim("CANCELED")], FILING, TEAM, WEEK)

    # WADD-26 THEN the result is recorded as cancelled
    assert result.state == "cancelled"


def test_a_matching_claim_from_another_week_does_not_resolve_this_one():
    assert resolve_claim([_claim("EXECUTED", week=1)], FILING, TEAM, WEEK) is None


def test_executed_beats_a_failed_duplicate():
    assert resolve_claim([_claim("FAILED_PLAYERALREADYDROPPED"), _claim("EXECUTED")],
                         FILING, TEAM, WEEK).state == "cleared"


def test_a_pending_copy_keeps_the_claim_unresolved_over_a_failed_or_cancelled_one():
    for other in ("CANCELED", "FAILED_PLAYERALREADYDROPPED"):
        assert resolve_claim([_claim(other), _claim("PENDING")], FILING, TEAM, WEEK) is None


def test_a_transaction_with_no_week_does_not_match():
    claim = _claim("EXECUTED")
    del claim["scoringPeriodId"]
    assert resolve_claim([claim], FILING, TEAM, WEEK) is None
