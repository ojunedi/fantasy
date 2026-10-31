"""Filing an approved waiver claim from the page.

The real `ESPNWaiverApiExecutor` runs against the fake adapter with
`httpx.post` patched, so the payload, the legality re-check, the read-back
match and the three filing states are production code; only the network is
faked.
"""
from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from fantasy_gm.execute.waiver_api import ESPNWaiverApiExecutor
from fantasy_gm.models import (
    DecisionRecord,
    DecisionType,
    FreeAgent,
    HumanResponse,
    Player,
    Position,
)

WEEK, SEASON = 3, 2026
ADD_ID, ADD_NAME = "900", "Jayden Reed"
DROP_ID, DROP_NAME = "109", "Rome Odunze"   # on the fixture roster


def _pending(team="8", add=ADD_ID, drop=DROP_ID) -> dict:
    """A pending claim in ESPN's own shape, as read back from mTransactions2."""
    return {"type": "WAIVER", "status": "PENDING", "executionType": "EXECUTE",
            "teamId": int(team), "isPending": True, "bidAmount": 0,
            "items": [
                {"playerId": int(add), "type": "ADD", "fromTeamId": 0, "toTeamId": int(team)},
                {"playerId": int(drop), "type": "DROP", "fromTeamId": int(team), "toTeamId": 0},
            ]}


@pytest.fixture
def espn(app, fake_adapter, monkeypatch):
    """The fake league: Reed is on waivers, Odunze is mine, I am 9th of 12."""
    monkeypatch.setenv("ESPN_SWID", "{swid}")
    monkeypatch.setenv("ESPN_S2", "s2")
    state = SimpleNamespace(pending=[], posts=[], status=200, pool=[ADD_ID], swallow=False,
                            connect_error=False, read_timeout=False, on_post=None)

    reed = Player(platform_id=ADD_ID, name=ADD_NAME, position=Position.WR,
                  eligible_positions=[Position.WR])
    state.fresh_reads = []
    original_get_roster = fake_adapter.get_roster

    def get_roster(team_id, week, season, fresh=False):
        state.fresh_reads.append(("roster", fresh))
        return original_get_roster(team_id, week, season, fresh=fresh)

    def get_free_agents(week, season, position_filter=None, fresh=False):
        state.fresh_reads.append(("free_agents", fresh))
        return [FreeAgent(player=reed) for pid in state.pool if pid == ADD_ID]

    fake_adapter.get_roster = get_roster
    fake_adapter.get_free_agents = get_free_agents
    fake_adapter.get_pending_waiver_claims = lambda season: list(state.pending)
    fake_adapter.get_waiver_rank = lambda team_id, season: (9, 12)

    def post(url, json=None, **kwargs):
        state.posts.append(json)
        if state.on_post:
            state.on_post()
        if state.connect_error:
            raise httpx.ConnectError("connection refused")
        if state.status >= 400:
            return SimpleNamespace(status_code=state.status, text="Internal Server Error")
        sent = {i["type"]: str(i["playerId"]) for i in json["items"]}
        state.pending.append({**_pending(add=sent["ADD"], drop=sent["DROP"]),
                              "scoringPeriodId": json["scoringPeriodId"]})  # ESPN files it…
        if state.swallow:
            state.pending.pop()          # …or accepts it without acting
        if state.read_timeout:
            raise httpx.ReadTimeout("timed out waiting for ESPN")
        return SimpleNamespace(status_code=state.status, text="{}")

    monkeypatch.setattr("fantasy_gm.execute.waiver_api.httpx.post", post)
    app.state.waiver_executor = ESPNWaiverApiExecutor(fake_adapter)
    return state


def _decision(store, response=HumanResponse.APPROVED) -> DecisionRecord:
    record = DecisionRecord(
        week=WEEK, season=SEASON, decision_type=DecisionType.WAIVER,
        inputs_snapshot={}, signals_staleness={}, memo="", confidence=1.0,
        recommendation={"scan_state": "recommendation", "candidate": ADD_NAME,
                        "displaced_player": DROP_NAME, "candidate_id": ADD_ID,
                        "displaced_id": DROP_ID, "value_margin": 5.3},
    )
    store.save(record)
    if response is not None:
        store.record_human_response(record.id, response)
    return record


def _file(client, confirm, **extra):
    return client.post("/api/waiver/file", data={"confirm": confirm, **extra})


def test_wadd12_anything_but_live_is_a_dry_run(client, store, espn):
    record = _decision(store)

    resp = _file(client, "live")

    # WADD-12 THEN the page shows the transaction that would be sent
    assert resp.status_code == 200
    assert "Dry run — nothing was sent. Add Jayden Reed · Drop Rome Odunze" in resp.text
    # WADD-12 AND nothing is transmitted to ESPN
    assert espn.posts == []
    # WADD-12 AND no filing is recorded on the decision
    assert store.get(record.id).outcome is None


@pytest.mark.parametrize("response", [None, HumanResponse.DECLINED])
def test_wadd13_a_decision_that_is_not_approved_is_refused(client, store, espn, response):
    _decision(store, response)

    resp = _file(client, "LIVE")

    # WADD-13 THEN the response is a refusal with status 409
    assert resp.status_code == 409
    assert "not approved — nothing was sent" in resp.text
    # WADD-13 AND nothing is transmitted to ESPN
    assert espn.posts == []


def test_wadd19_the_players_come_from_the_decision_log_not_the_request(client, store, espn):
    _decision(store)

    _file(client, "LIVE", candidate_id="1", displaced_id="2", add="1", drop="2")

    # WADD-19 THEN the transaction holds the players from the stored decision
    assert [i["playerId"] for i in espn.posts[0]["items"]] == [int(ADD_ID), int(DROP_ID)]


@pytest.mark.parametrize("moved,named", [("drop", "Rome Odunze is no longer on your roster"),
                                          ("add", "Jayden Reed is no longer available")])
def test_wadd14_a_roster_that_changed_since_the_scan_refuses_the_filing(
        client, store, espn, fake_adapter, moved, named):
    record = _decision(store)
    if moved == "drop":
        fake_adapter._roster.players = [rp for rp in fake_adapter._roster.players
                                        if rp.player.platform_id != DROP_ID]
    else:
        espn.pool = []

    resp = _file(client, "LIVE")

    # WADD-14 THEN the filing is refused
    assert resp.status_code == 409
    # WADD-14 AND the message names the player who moved
    assert named in resp.text
    # WADD-14 AND nothing is transmitted to ESPN
    assert espn.posts == []
    assert store.get(record.id).outcome is None


def test_wadd15_a_claim_found_pending_on_read_back_is_confirmed(client, store, espn,
                                                               web_settings):
    from fantasy_gm.db.store import DecisionStore

    record = _decision(store)
    espn.pending.append(_pending(add="4696044", drop="4428850"))  # an older claim of mine
    seen_before_post = []
    # The send runs on the app's thread; sqlite connections cannot cross threads.
    espn.on_post = lambda: seen_before_post.append(
        DecisionStore(web_settings.db_path).get(record.id).outcome["filing"]["state"])

    resp = _file(client, "LIVE")

    # the attempt was in the log before anything left for ESPN (NFR-10)
    assert seen_before_post == ["sending"]

    # the cache is bypassed for the legality reads (I-12)
    assert espn.fresh_reads[-2:] == [("roster", True), ("free_agents", True)]
    # WADD-15 THEN the page reports the claim filed and pending, with my waiver priority position
    assert "Claim filed — ESPN shows it as pending." in resp.text
    assert "You are 9 of 12 in waiver priority." in resp.text
    # WADD-15 AND the decision log records the transaction, the state confirmed, and the priority position
    filing = store.get(record.id).outcome["filing"]
    assert filing["state"] == "confirmed"
    assert filing["transaction"] == espn.posts[0]
    assert (filing["waiver_rank"], filing["team_count"]) == (9, 12)


def test_wadd16_an_accepted_send_the_read_back_cannot_find_is_not_confirmed(client, store, espn):
    record = _decision(store)
    espn.swallow = True
    espn.pending.append(_pending(add="4696044", drop="4428850"))  # mine, other players

    resp = _file(client, "LIVE")

    # WADD-16 THEN the page reports the claim filed but not confirmed and tells the manager to check the ESPN app
    assert "doesn&#39;t show on the league yet" in resp.text or "doesn't show on the league yet" in resp.text
    assert "Check the ESPN app" in resp.text
    # WADD-16 AND the filing form is not offered again
    assert "File claim" not in resp.text
    # WADD-16 AND the decision log records the state unconfirmed
    assert store.get(record.id).outcome["filing"]["state"] == "unconfirmed"


def test_wadd17_a_send_espn_rejects_is_reported_as_not_filed(client, store, espn):
    record = _decision(store)
    espn.status = 500

    resp = _file(client, "LIVE")

    # WADD-17 THEN the page reports the claim not filed, with ESPN's error and the manual steps
    assert "The claim was not filed — ESPN API 500" in resp.text
    assert "add Jayden Reed, drop Rome Odunze" in resp.text
    # WADD-17 AND the decision log records the state failed
    assert store.get(record.id).outcome["filing"]["state"] == "failed"
    # WADD-17 AND the filing form is offered again
    assert "File claim" in resp.text


@pytest.mark.parametrize("state", ["confirmed", "unconfirmed"])
def test_wadd18_a_decision_already_filed_live_cannot_be_filed_again(client, store, espn, state):
    record = _decision(store)
    filing = {"filing": {"state": state, "transaction": {"items": []}, "waiver_rank": 9}}
    store.record_outcome(record.id, filing)

    resp = _file(client, "LIVE")

    # WADD-18 THEN the response is a refusal with status 409
    assert resp.status_code == 409
    assert "already filed" in resp.text
    # WADD-18 AND nothing is transmitted to ESPN
    assert espn.posts == []
    # WADD-18 AND the recorded filing is unchanged
    assert store.get(record.id).outcome == filing


def test_a_failed_write_to_the_log_is_never_reported_as_filed(client, store, espn, monkeypatch):
    _decision(store)
    from fantasy_gm.db.store import DecisionStore
    monkeypatch.setattr(DecisionStore, "record_outcome",
                        lambda self, *a, **k: (_ for _ in ()).throw(RuntimeError("disk full")))

    with pytest.raises(RuntimeError, match="disk full"):
        _file(client, "LIVE")


def test_wadd17_a_connection_that_never_opened_is_not_filed_and_can_be_filed_again(
        client, store, espn):
    record = _decision(store)
    espn.connect_error = True

    resp = _file(client, "LIVE")

    # WADD-17 THEN the page reports the claim not filed, with ESPN's error and the manual steps
    assert "The claim was not filed — could not reach ESPN" in resp.text
    # WADD-17 AND the decision log records the state failed
    assert store.get(record.id).outcome["filing"]["state"] == "failed"
    # WADD-17 AND the filing form is offered again
    espn.connect_error = False
    again = _file(client, "LIVE")
    assert len(espn.posts) == 2
    assert "Claim filed — ESPN shows it as pending." in again.text
    attempts = store.get(record.id).outcome["attempts"]
    assert [a["state"] for a in attempts] == ["failed", "confirmed"]


@pytest.mark.parametrize("landed,state", [(True, "confirmed"), (False, "unconfirmed")])
def test_wadd20_a_send_that_may_have_reached_espn_is_never_reported_not_filed(
        client, store, espn, landed, state):
    record = _decision(store)
    espn.read_timeout = True
    espn.swallow = not landed

    resp = _file(client, "LIVE")

    # WADD-20 THEN the league is read back before anything is reported
    # WADD-20 AND the state is confirmed if the claim is pending, otherwise unconfirmed — never failed
    assert store.get(record.id).outcome["filing"]["state"] == state
    # WADD-20 AND the filing form is not offered again
    assert "File claim" not in resp.text
    assert "not filed" not in resp.text


def test_wadd21_a_rescan_after_filing_does_not_reopen_the_claim(client, store, espn):
    first = _decision(store)
    _file(client, "LIVE")
    assert store.get(first.id).outcome["filing"]["state"] == "confirmed"
    _decision(store)  # a re-run scan for the same week, marked Intend to claim again

    resp = _file(client, "LIVE")

    # WADD-21 THEN the response is a refusal with status 409
    assert resp.status_code == 409
    assert "already filed" in resp.text
    # WADD-21 AND nothing is transmitted to ESPN
    assert len(espn.posts) == 1


def test_a_roster_change_refusal_offers_a_rescan(client, store, espn):
    _decision(store)
    espn.pool = []

    resp = _file(client, "LIVE")

    assert resp.status_code == 409
    assert "Re-run scan" in resp.text


def test_a_failed_league_read_is_shown_not_swallowed(client, store, espn, fake_adapter):
    _decision(store)
    fake_adapter.get_free_agents = lambda *a, **k: (_ for _ in ()).throw(httpx.ReadTimeout("slow"))

    resp = _file(client, "LIVE")

    assert resp.status_code == 409
    assert "Couldn&#39;t read the league" in resp.text or "Couldn't read the league" in resp.text
    assert espn.posts == []
