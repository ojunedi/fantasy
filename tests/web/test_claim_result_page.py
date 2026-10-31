"""Checking a filed claim's result from the waiver page.

Transactions are served in ESPN's shape, modelled on the week-4 contested
claim in this league: the winner EXECUTED, the others FAILED_INVALIDPLAYERSOURCE.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from fantasy_gm.execute.waiver_api import ESPNWaiverApiExecutor
from fantasy_gm.models import DecisionRecord, DecisionType, HumanResponse

WEEK, SEASON = 3, 2026
ADD_ID, DROP_ID = "900", "109"


def _claim(status, team="8", add=ADD_ID, drop=DROP_ID, week=WEEK):
    return {"type": "WAIVER", "status": status, "teamId": int(team), "scoringPeriodId": week,
            "items": [{"playerId": int(add), "type": "ADD"},
                      {"playerId": int(drop), "type": "DROP"}]}


@pytest.fixture
def league(app, fake_adapter):
    state = SimpleNamespace(transactions=[], reads=0, weeks=[])

    def get_waiver_transactions(season, week):
        state.weeks.append(week)  # asserted by the tests; an assert here would be swallowed
        state.reads += 1
        return list(state.transactions)

    fake_adapter.get_waiver_transactions = get_waiver_transactions
    app.state.waiver_executor = ESPNWaiverApiExecutor(fake_adapter)
    return state


def _filed(store, filing_state="confirmed", result=None, week=WEEK, rank=9) -> DecisionRecord:
    record = DecisionRecord(
        week=week, season=SEASON, decision_type=DecisionType.WAIVER,
        inputs_snapshot={}, signals_staleness={}, memo="", confidence=1.0,
        recommendation={"scan_state": "recommendation", "candidate": "Jayden Reed",
                        "displaced_player": "Rome Odunze", "candidate_id": ADD_ID,
                        "displaced_id": DROP_ID},
    )
    store.save(record)
    store.record_human_response(record.id, HumanResponse.APPROVED)
    outcome = {"filing": {"state": filing_state, "waiver_rank": rank, "team_count": 12,
                          "transaction": {"scoringPeriodId": week, "items": [
                              {"playerId": int(ADD_ID), "type": "ADD"},
                              {"playerId": int(DROP_ID), "type": "DROP"}]}}}
    if result:
        outcome["result"] = result
    store.record_outcome(record.id, outcome)
    return record


def _check(client):
    return client.post("/api/waiver/result")


def test_wadd22_an_executed_claim_is_recorded_as_cleared(client, store, league):
    record = _filed(store)
    league.transactions = [_claim("EXECUTED")]

    resp = _check(client)

    # WADD-22 THEN the result is recorded as cleared
    assert store.get(record.id).outcome["result"]["state"] == "cleared"
    assert league.weeks == [WEEK]  # read for the claim's own week
    # WADD-22 AND the page says the claim cleared
    assert "Claim cleared — Jayden Reed is on your roster and Rome Odunze was dropped." in resp.text


def test_wadd23_a_claim_beaten_by_another_team_is_recorded_as_lost_to_priority(
        client, store, league):
    record = _filed(store, filing_state="unconfirmed")
    league.transactions = [_claim("FAILED_INVALIDPLAYERSOURCE"),
                           _claim("EXECUTED", team="6", drop="555")]

    resp = _check(client)

    # WADD-23 THEN the result is recorded as lost to priority
    result = store.get(record.id).outcome["result"]
    assert result["state"] == "lost"
    # WADD-23 AND it names the team that won the player
    assert result["winner_team_id"] == "6"
    assert "Claim lost to priority — Team Six got Jayden Reed." in resp.text


@pytest.mark.parametrize("transactions", [[_claim("PENDING")], []])
def test_wadd25_a_pending_or_missing_claim_stays_unresolved(client, store, league, transactions):
    record = _filed(store)
    league.transactions = transactions

    resp = _check(client)

    # WADD-25 THEN no result is recorded
    assert "result" not in store.get(record.id).outcome
    # WADD-25 AND the page says ESPN hasn't processed the claim yet and offers the check again
    assert "hasn&#39;t processed the claim yet" in resp.text or "hasn't processed the claim yet" in resp.text
    assert "Check result" in resp.text


def test_wadd27_the_result_records_the_filings_priority_position_before_the_page_shows_it(
        client, store, league):
    record = _filed(store)
    league.transactions = [_claim("EXECUTED")]

    resp = _check(client)

    # WADD-27 THEN the recorded result carries that priority position and the team count
    result = store.get(record.id).outcome["result"]
    assert (result["waiver_rank"], result["team_count"]) == (9, 12)
    # WADD-27 AND it is in the decision log when the page renders
    assert "Filed 9 of 12 in priority." in resp.text


def test_wadd28_a_recorded_result_is_not_read_again(client, store, league):
    recorded = {"state": "cleared", "waiver_rank": 9, "team_count": 12}
    record = _filed(store, result=recorded)
    league.transactions = [_claim("FAILED_INVALIDPLAYERSOURCE")]

    resp = _check(client)

    # WADD-28 THEN the league is not read
    assert league.reads == 0
    # WADD-28 AND the recorded result is unchanged
    assert store.get(record.id).outcome["result"] == recorded
    assert "Claim cleared" in resp.text


def test_a_filed_claim_offers_check_result(client, store, league):
    _filed(store)
    assert "Check result" in client.get("/waiver").text


def test_checking_with_nothing_filed_is_refused(client, store, league):
    resp = _check(client)
    assert resp.status_code == 409
    assert league.reads == 0


def test_a_claim_from_an_earlier_week_can_still_be_checked(client, store, league):
    # Filed in week 2; the league has moved on to week 3 before the manager looks.
    record = _filed(store, week=2)
    league.transactions = [_claim("EXECUTED", week=2)]

    page = client.get("/waiver").text
    assert "Week 2 claim — add Jayden Reed, drop Rome Odunze." in page

    resp = client.post("/api/waiver/result", data={"decision_id": str(record.id)})

    assert league.weeks == [2]
    assert store.get(record.id).outcome["result"]["state"] == "cleared"
    assert "Claim cleared" in resp.text
    assert "Week 2 claim" not in client.get("/waiver").text  # resolved, no longer listed


def test_a_cancelled_copy_does_not_settle_a_claim_still_pending(client, store, league):
    record = _filed(store, filing_state="unconfirmed")
    league.transactions = [_claim("CANCELED"), _claim("PENDING")]

    _check(client)

    assert "result" not in store.get(record.id).outcome


def test_a_cancelled_claim_is_recorded_and_shown(client, store, league):
    record = _filed(store)
    league.transactions = [_claim("CANCELED")]

    resp = _check(client)

    assert store.get(record.id).outcome["result"]["state"] == "cancelled"
    assert "Claim was cancelled in ESPN." in resp.text


def test_a_failed_claim_is_recorded_with_its_reason_in_words(client, store, league):
    record = _filed(store)
    league.transactions = [_claim("FAILED_PLAYERALREADYDROPPED")]

    resp = _check(client)

    assert store.get(record.id).outcome["result"]["reason"] == "FAILED_PLAYERALREADYDROPPED"
    assert ("Claim failed — the player you were dropping was no longer on your roster. "
            "This wasn&#39;t a priority loss.") in resp.text or \
           ("Claim failed — the player you were dropping was no longer on your roster. "
            "This wasn't a priority loss.") in resp.text


def test_a_loss_with_no_recorded_priority_says_so(client, store, league):
    _filed(store, rank=None)
    league.transactions = [_claim("FAILED_INVALIDPLAYERSOURCE"),
                           _claim("EXECUTED", team="6", drop="555")]

    resp = _check(client)

    assert "waiver position wasn" in resp.text


def test_a_new_scan_is_refused_once_this_weeks_claim_is_filed(client, store, league):
    _filed(store)

    resp = client.post("/api/waiver/scan")

    assert resp.status_code == 409
    assert "already filed" in resp.text
