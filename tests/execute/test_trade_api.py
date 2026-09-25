"""
ESPN trade offer payload + the dry-run contract.

The payload shape is pinned because it is reverse-engineered: an item is
directional (fromTeamId/toTeamId), carries no lineup slot, and the outer type
is TRADE_PROPOSAL, not TRADE.
"""
from fantasy_gm.execute.trade_api import (
    ESPNTradeApiExecutor,
    build_espn_trade_transaction,
)


class _FakeAdapter:
    league_id = "999"


def _executor(monkeypatch, swid="{SW-ID}", s2="s2"):
    monkeypatch.setenv("ESPN_SWID", swid)
    monkeypatch.setenv("ESPN_S2", s2)
    return ESPNTradeApiExecutor(_FakeAdapter())


def test_payload_shape():
    payload = build_espn_trade_transaction(
        team_id="8", counterparty_team_id="3",
        send_player_ids=["111"], receive_player_ids=["222", "333"],
        week=4, season=2026, swid="{SW-ID}",
    )
    assert payload["type"] == "TRADE_PROPOSAL"
    assert payload["teamId"] == 8
    assert payload["scoringPeriodId"] == 4
    assert payload["executionType"] == "EXECUTE"
    assert payload["isLeagueManager"] is False
    assert payload["memberId"] == "{SW-ID}"

    # Sent player flows me -> them; received players flow them -> me.
    assert payload["items"][0] == {
        "playerId": 111, "type": "TRADE", "fromTeamId": 8, "toTeamId": 3,
    }
    assert payload["items"][1] == {
        "playerId": 222, "type": "TRADE", "fromTeamId": 3, "toTeamId": 8,
    }
    assert len(payload["items"]) == 3
    # Trade items carry no lineup slot, unlike ROSTER items.
    assert all("fromLineupSlotId" not in i for i in payload["items"])


def test_plan_blocks_without_counterparty(monkeypatch):
    ex = _executor(monkeypatch)
    plan = ex.plan({"send_player_ids": ["111"], "receive_player_ids": ["222"]},
                   team_id="8", week=4, season=2026)
    assert plan.request_payload is None
    assert any("BLOCKED" in n for n in plan.notes)


def test_plan_blocks_with_no_players(monkeypatch):
    ex = _executor(monkeypatch)
    plan = ex.plan({"counterparty_team_id": "3"}, team_id="8", week=4, season=2026)
    assert plan.request_payload is None
    assert any("BLOCKED" in n for n in plan.notes)


def test_execute_dry_run_does_not_post(monkeypatch):
    ex = _executor(monkeypatch)
    plan = ex.plan(
        {"counterparty_team_id": "3", "send_player_ids": ["111"],
         "receive_player_ids": ["222"], "send_names": ["A"], "receive_names": ["B"]},
        team_id="8", week=4, season=2026,
    )
    assert plan.request_payload is not None

    def _boom(*a, **k):
        raise AssertionError("dry run must not POST")
    monkeypatch.setattr("fantasy_gm.execute.trade_api.httpx.post", _boom)

    result = ex.execute(plan, season=2026, live=False)
    assert result.success and result.dry_run


def test_execute_unsendable_plan_fails(monkeypatch):
    ex = _executor(monkeypatch)
    plan = ex.plan({"counterparty_team_id": "3"}, team_id="8", week=4, season=2026)
    result = ex.execute(plan, season=2026, live=True)
    assert not result.success
    assert "No sendable payload" in result.error
