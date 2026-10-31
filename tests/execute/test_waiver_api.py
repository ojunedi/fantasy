"""The waiver claim payload: one transaction, an ADD and a DROP.

The shape is copied from claims ESPN's own app filed in this league
(mTransactions2, week 1, team 8).
"""
from __future__ import annotations

from fantasy_gm.execute.waiver_api import ESPNWaiverApiExecutor


def test_wadd11_filing_builds_one_transaction_with_the_add_and_the_drop(monkeypatch):
    monkeypatch.setenv("ESPN_SWID", "{swid}")
    executor = ESPNWaiverApiExecutor(adapter=None)

    plan = executor.plan("4696044", "Waiver WR", "4428850", "Bench WR",
                         team_id="8", week=9, season=2026)
    txn = plan.request_payload

    # WADD-11 THEN exactly one waiver transaction is built for the manager's team
    assert isinstance(txn, dict)
    assert txn["type"] == "WAIVER"
    assert txn["teamId"] == 8
    assert txn["executionType"] == "EXECUTE"
    assert txn["scoringPeriodId"] == 9
    # WADD-11 AND it holds one ADD item for the recommended player and one DROP item for the displaced player
    assert txn["items"] == [
        {"playerId": 4696044, "type": "ADD", "fromTeamId": 0, "toTeamId": 8},
        {"playerId": 4428850, "type": "DROP", "fromTeamId": 8, "toTeamId": 0},
    ]
