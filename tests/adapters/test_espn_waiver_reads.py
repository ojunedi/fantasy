"""The two fresh league reads the waiver filing depends on, against ESPN's raw shape."""
from __future__ import annotations

from unittest.mock import patch

from fantasy_gm.adapters.espn import ESPNAdapter
from fantasy_gm.execute.waiver_api import ESPNWaiverApiExecutor

# Captured from this league's mTransactions2 view (week 1, team 8), trimmed.
PENDING_CLAIM = {
    "type": "WAIVER", "status": "PENDING", "executionType": "EXECUTE", "teamId": 8,
    "bidAmount": 0, "scoringPeriodId": 1, "isPending": True,
    "items": [
        {"playerId": 4696044, "type": "ADD", "fromTeamId": 0, "toTeamId": 8,
         "fromLineupSlotId": -1, "toLineupSlotId": -1, "isKeeper": False},
        {"playerId": 4428850, "type": "DROP", "fromTeamId": 8, "toTeamId": 0,
         "fromLineupSlotId": 20, "toLineupSlotId": -1, "isKeeper": False},
    ],
}
TRANSACTIONS = {"transactions": [
    PENDING_CLAIM,
    {**PENDING_CLAIM, "status": "EXECUTED", "executionType": "PROCESS"},
    {**PENDING_CLAIM, "type": "TRADE_PROPOSAL"},
]}


def _adapter(tmp_path):
    return ESPNAdapter(league_id="1660218687", cache_dir=tmp_path)


def test_pending_waiver_claims_keeps_only_pending_waivers_and_bypasses_the_cache(tmp_path):
    adapter = _adapter(tmp_path)
    with patch.object(ESPNAdapter, "_fetch", return_value=TRANSACTIONS) as fetch:
        claims = adapter.get_pending_waiver_claims(2026)
    assert claims == [PENDING_CLAIM]
    assert fetch.call_args.kwargs["bypass_cache"] is True


def test_waiver_rank_reads_our_team_fresh(tmp_path):
    adapter = _adapter(tmp_path)
    teams = {"teams": [{"id": 1, "waiverRank": 4}, {"id": 8, "waiverRank": 9}, {"id": 3}]}
    with patch.object(ESPNAdapter, "_fetch", return_value=teams) as fetch:
        assert adapter.get_waiver_rank("8", 2026) == (9, 3)
    assert fetch.call_args.kwargs["bypass_cache"] is True


def test_read_back_matches_the_captured_claim_only_for_its_own_week(tmp_path, monkeypatch):
    monkeypatch.setenv("ESPN_SWID", "{swid}")
    adapter = _adapter(tmp_path)
    executor = ESPNWaiverApiExecutor(adapter)
    with patch.object(ESPNAdapter, "_fetch", return_value=TRANSACTIONS):
        week1 = executor.plan("4696044", "A", "4428850", "B", team_id="8", week=1, season=2026)
        week9 = executor.plan("4696044", "A", "4428850", "B", team_id="8", week=9, season=2026)
        assert executor._confirm_filed(week1) is True
        assert executor._confirm_filed(week9) is False
