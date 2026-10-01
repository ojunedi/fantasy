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


# --- read-back confirmation (D-022) ----------------------------------------
# ESPN's write endpoint can return 200 without creating anything, so a send is
# only confirmed by finding the offer on a subsequent read.

class _ReadBackAdapter:
    league_id = "999"

    def __init__(self, pending):
        self._pending = pending
        self.read_count = 0

    def get_pending_trade_proposals(self, season):
        self.read_count += 1
        return self._pending


def _sendable(ex):
    return ex.plan(
        {"counterparty_team_id": "3", "send_player_ids": ["111"],
         "receive_player_ids": ["222"], "send_names": ["A"], "receive_names": ["B"]},
        team_id="8", week=4, season=2026,
    )


def _ok_post(monkeypatch):
    class _Resp:
        status_code = 200
        text = ""
    monkeypatch.setattr("fantasy_gm.execute.trade_api.httpx.post",
                        lambda *a, **k: _Resp())


def test_live_send_confirmed_when_offer_is_found(monkeypatch):
    ex = _executor(monkeypatch)
    plan = _sendable(ex)
    ex.adapter = _ReadBackAdapter([{
        "type": "TRADE_PROPOSAL", "teamId": 8,
        "items": [{"playerId": 111}, {"playerId": 222}],
    }])
    _ok_post(monkeypatch)

    result = ex.execute(plan, season=2026, live=True)
    assert result.success and result.confirmed is True
    assert ex.adapter.read_count == 1


def test_live_send_unconfirmed_when_offer_is_absent(monkeypatch):
    """A 200 with nothing to show for it. Success stays True — the POST did
    happen — but confirmed is False, because re-sending would risk a duplicate."""
    ex = _executor(monkeypatch)
    plan = _sendable(ex)
    ex.adapter = _ReadBackAdapter([])
    _ok_post(monkeypatch)

    result = ex.execute(plan, season=2026, live=True)
    assert result.success is True
    assert result.confirmed is False
    assert "NOT" in result.message and "do not re-send" in result.message.lower()


def test_confirmation_ignores_another_teams_offer(monkeypatch):
    """Same players, different proposer — not our offer."""
    ex = _executor(monkeypatch)
    plan = _sendable(ex)
    ex.adapter = _ReadBackAdapter([{
        "type": "TRADE_PROPOSAL", "teamId": 5,
        "items": [{"playerId": 111}, {"playerId": 222}],
    }])
    _ok_post(monkeypatch)
    assert ex.execute(plan, season=2026, live=True).confirmed is False


def test_confirmation_requires_the_exact_player_set(monkeypatch):
    """A pending offer involving an overlapping but different set of players is
    a different offer, not ours."""
    ex = _executor(monkeypatch)
    plan = _sendable(ex)
    ex.adapter = _ReadBackAdapter([{
        "type": "TRADE_PROPOSAL", "teamId": 8,
        "items": [{"playerId": 111}, {"playerId": 222}, {"playerId": 999}],
    }])
    _ok_post(monkeypatch)
    assert ex.execute(plan, season=2026, live=True).confirmed is False


def test_read_back_failure_reports_unconfirmed_not_success(monkeypatch):
    """If the confirming read itself throws, the answer is 'unconfirmed'. It is
    never 'assume it worked'."""
    ex = _executor(monkeypatch)
    plan = _sendable(ex)

    class _Exploding:
        league_id = "999"
        def get_pending_trade_proposals(self, season):
            raise RuntimeError("ESPN read failed")
    ex.adapter = _Exploding()
    _ok_post(monkeypatch)

    result = ex.execute(plan, season=2026, live=True)
    assert result.success is True and result.confirmed is False


def test_dry_run_leaves_confirmed_unset(monkeypatch):
    ex = _executor(monkeypatch)
    plan = _sendable(ex)
    ex.adapter = _ReadBackAdapter([])
    result = ex.execute(plan, season=2026, live=False)
    assert result.dry_run and result.confirmed is None
    assert ex.adapter.read_count == 0


def test_failed_post_does_not_read_back(monkeypatch):
    ex = _executor(monkeypatch)
    plan = _sendable(ex)
    ex.adapter = _ReadBackAdapter([])

    class _Resp:
        status_code = 401
        text = "not authorized"
    monkeypatch.setattr("fantasy_gm.execute.trade_api.httpx.post",
                        lambda *a, **k: _Resp())

    result = ex.execute(plan, season=2026, live=True)
    assert not result.success and result.confirmed is None
    assert ex.adapter.read_count == 0
