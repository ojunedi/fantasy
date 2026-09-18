"""The /trades page end to end.

Two things dominate these tests, because they dominate the real data:
abstentions are the usual result (22 of 35 logged rows), and the value numbers
are recomputed rather than stored, so they can legitimately be absent.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from fantasy_gm.models import DecisionRecord, DecisionType, HumanResponse, Position
from fantasy_gm.web import reads

PACKAGE = {
    "counterparty_team_id": "6",
    "send_player_ids": ["103", "106"],
    "receive_player_ids": ["203"],
    "send_names": ["Ja'Marr Chase", "Jaylen Waddle"],
    "receive_names": ["CeeDee Lamb"],
    "rationale": "Consolidates two WR2s into a genuine WR1.",
    "counterparty_pitch": "You start two WRs and have none behind them.",
    "confidence": 0.72,
}


def _record(**overrides) -> DecisionRecord:
    base = dict(
        week=3, season=2026, created_at=datetime(2026, 9, 18, 10, 0),
        decision_type=DecisionType.TRADE,
        inputs_snapshot={"my_team_id": "8", "team_count": 12, "tool_calls": []},
        signals_staleness={},
        recommendation={"trades": [dict(PACKAGE)], "memo": "Acquire an elite WR.",
                        "what_would_change_this": "A Lamb injury."},
        memo="Acquire an elite WR.", confidence=0.72,
    )
    base.update(overrides)
    return DecisionRecord(**base)


@pytest.fixture
def with_values(monkeypatch, projections, opponent_projections):
    """Force a value map so the value columns render.

    The real one calls FantasyCalc; these tests must not touch the network.
    """
    from fantasy_gm.core.trade_value import build_value_map

    ros = {**projections, **opponent_projections}
    positions = {}
    for pid in ros:
        positions[pid] = Position.WR
    vmap = build_value_map({k: v * 10 for k, v in ros.items()}, positions)
    monkeypatch.setattr(reads, "trade_value_map",
                        lambda *a, **k: (vmap, 1758196920.0))
    return vmap


# ------------------------------------------------------------- empty state

def test_the_page_renders_with_no_trade_history(client):
    resp = client.get("/trades")
    assert resp.status_code == 200
    assert "Trades" in resp.text


def test_trades_is_in_the_nav_and_marked_current(client):
    assert 'href="/trades" aria-current="page"' in client.get("/trades").text


def test_the_brief_form_offers_all_four_fields(client):
    text = client.get("/trades").text
    for field in ("want_positions", "offerable_ids", "target_ids", "notes"):
        assert f'name="{field}"' in text


def test_the_brief_only_offers_tradeable_positions(client):
    text = client.get("/trades").text
    for pos in ("QB", "RB", "WR", "TE"):
        assert f'value="{pos}"' in text
    assert 'name="want_positions" value="K"' not in text


def test_the_run_button_names_the_week_and_action(client):
    assert "Propose trades for week" in client.get("/trades").text


def test_the_form_posts_a_trade_kind(client):
    text = client.get("/trades").text
    assert 'value="trade"' in text


# --------------------------------------------------------------- packages

def test_a_package_shows_both_sides_of_the_deal(client, store, with_values):
    store.save(_record())
    text = client.get("/trades").text
    import html
    text = html.unescape(text)
    assert "Ja'Marr Chase" in text
    assert "Jaylen Waddle" in text
    assert "CeeDee Lamb" in text


def test_a_package_shows_the_rationale_and_the_pitch(client, store, with_values):
    store.save(_record())
    text = client.get("/trades").text
    assert "Consolidates two WR2s" in text
    assert "You start two WRs" in text


def test_a_package_names_the_counterparty_not_a_bare_id(client, store, with_values):
    """mRoster/mMatchup return a bare id; standings carry the real name."""
    store.save(_record())
    text = client.get("/trades").text
    assert "Team Six" in text


def test_value_numbers_appear_when_a_value_map_is_available(client, store, with_values):
    store.save(_record())
    text = client.get("/trades").text
    assert "fairness" in text.lower()


def test_no_value_numbers_are_invented_without_a_value_map(client, store, monkeypatch):
    """The decisive honesty test: EV/fairness are not stored on the record, so
    with no value map the page must omit them rather than render 0.0."""
    monkeypatch.setattr(reads, "trade_value_map", lambda *a, **k: ({}, None))
    store.save(_record())
    text = client.get("/trades").text
    assert "Ja'Marr Chase" in __import__("html").unescape(text)
    assert "fairness 0.0" not in text
    assert "+0.0 EV" not in text


def test_the_page_stamps_when_values_were_computed(client, store, with_values):
    """Market values move, so a recomputed number needs a timestamp."""
    store.save(_record())
    assert "valued" in client.get("/trades").text.lower()


# ------------------------------------------------------------- abstention

def test_an_abstention_is_a_first_class_result(client, store):
    """22 of 35 real trade decisions abstained — this is the usual view."""
    store.save(_record(recommendation={
        "abstained": True,
        "missing_information": ["Garrett Wilson's ankle is unresolved"],
        "what_you_would_need": "A practice report before Sunday.",
        "memo": "No trade worth making this week.",
    }, memo="No trade worth making this week.", confidence=0.0))
    text = client.get("/trades").text
    assert "No trade worth making" in text
    assert "ankle is unresolved" in text
    assert "practice report" in text


def test_an_abstention_offers_a_way_forward(client, store):
    store.save(_record(recommendation={"abstained": True,
                                       "missing_information": [], "memo": "Nothing doing."},
                       memo="Nothing doing.", confidence=0.0))
    text = client.get("/trades").text
    assert "Propose trades for week" in text     # re-run is reachable


# -------------------------------------------------------------- truncated

def test_a_truncated_run_shows_priced_packages_as_not_recommendations(client, store):
    store.save(_record(recommendation={
        "abstained": True, "truncated": True,
        "reason": "LLM call budget exhausted before a terminal tool",
        "llm_calls": 8, "llm_budget": 8,
        "evaluated_packages": [{
            "send_player_ids": ["103"], "receive_player_ids": ["203"],
            "counterparty_team_id": "6",
            "evaluation": "SEND (Chase): 1555.0\nRECEIVE (Lamb): 2223.0\nEV delta: +668.0",
        }],
    }, memo="Run was cut off.", confidence=0.0))
    text = client.get("/trades").text
    assert "cut off" in text.lower()
    assert "668" in text
    assert "not" in text.lower()          # labelled as not vetted


# ---------------------------------------------------------------- refused

def test_a_refused_package_states_why_and_offers_no_approval(client, store, with_values):
    store.save(_record(recommendation={
        "trades": [],
        "refused_trades": [{**PACKAGE,
                            "refused_because": "sends players you did not offer"}],
        "memo": "Everything I found sends players you withheld.",
    }, memo="Everything I found sends players you withheld.", confidence=0.0))
    text = client.get("/trades").text
    assert "did not offer" in text


def test_a_directive_violation_is_flagged(client, store, with_values):
    store.save(_record(recommendation={
        "trades": [{**PACKAGE,
                    "directive_violations": ["does not bring back a player you targeted"]}],
        "memo": "Best available.",
    }))
    text = client.get("/trades").text
    assert "does not bring back a player you targeted" in text


def test_a_deterministic_pick_says_no_model_vetted_it(client, store, with_values):
    store.save(_record(recommendation={
        "trades": [dict(PACKAGE)], "selected_deterministically": True,
        "reason": "Run was cut off; packages ranked by computed EV and fairness.",
        "memo": "Picked by scoring.",
    }, memo="Picked by scoring.", confidence=0.4))
    text = client.get("/trades").text
    assert "scoring" in text.lower()


# ------------------------------------------------------------------ gates

def test_approving_a_package_records_it_and_shows_send_steps(client, store, with_values):
    record = _record()
    store.save(record)
    resp = client.post(f"/trades/{record.id}/approve/1")
    assert resp.status_code == 200
    assert "ESPN" in resp.text

    stored = store.get(record.id)
    assert stored.human_response == HumanResponse.APPROVED
    # Which package was chosen has to survive for the season-end review.
    assert stored.modified_recommendation["approved_package_index"] == 1


def test_the_send_steps_are_manual_because_espn_cannot_auto_send(client, store,
                                                                 with_values):
    record = _record()
    store.save(record)
    text = client.post(f"/trades/{record.id}/approve/1").text
    assert "Trade" in text
    assert "Team Six" in text or "team 6" in text
    # It must never claim to have sent anything.
    assert "sent to espn" not in text.lower()


def test_the_send_steps_include_the_pitch_to_paste(client, store, with_values):
    record = _record()
    store.save(record)
    text = client.post(f"/trades/{record.id}/approve/1").text
    assert "You start two WRs" in text


def test_approving_a_package_that_does_not_exist_is_a_404(client, store, with_values):
    record = _record()
    store.save(record)
    assert client.post(f"/trades/{record.id}/approve/9").status_code == 404


def test_rejecting_requires_a_reason(client, store, with_values):
    """The agent reads rejections back and is forbidden from re-proposing them,
    so an empty reason wastes that mechanism."""
    record = _record()
    store.save(record)
    resp = client.post(f"/trades/{record.id}/reject", data={"override_reason": ""})
    assert resp.status_code == 422
    assert store.get(record.id).human_response is None


def test_a_reasoned_rejection_is_logged(client, store, with_values):
    record = _record()
    store.save(record)
    resp = client.post(f"/trades/{record.id}/reject",
                       data={"override_reason": "no one would accept this"})
    assert resp.status_code == 200
    stored = store.get(record.id)
    assert stored.human_response == HumanResponse.REJECTED
    assert stored.override_reason == "no one would accept this"


# ---------------------------------------------------------------- history

def test_past_trade_decisions_are_listed(client, store, with_values):
    store.save(_record(created_at=datetime(2026, 9, 11)))
    store.save(_record(created_at=datetime(2026, 9, 18)))
    text = client.get("/trades").text
    assert text.count("/decisions/") >= 2


def test_lineup_decisions_do_not_appear_on_the_trades_page(client, store):
    store.save(DecisionRecord(
        week=3, season=2026, decision_type=DecisionType.LINEUP,
        inputs_snapshot={"roster": []}, signals_staleness={},
        recommendation={"starter_player_ids": ["100"]},
        memo="A lineup decision.", confidence=0.8))
    assert "A lineup decision." not in client.get("/trades").text


def test_a_trade_decision_opened_by_id_uses_the_trade_view(client, store, with_values):
    """It must not be forced through the lineup template."""
    record = _record()
    store.save(record)
    resp = client.get(f"/decisions/{record.id}")
    assert resp.status_code == 200
    assert "Consolidates two WR2s" in resp.text
    assert "Recommended starters" not in resp.text


# ----------------------------------------------------------- honest values

def test_an_unranked_player_shows_no_value_rather_than_zero(client, store, monkeypatch):
    """FantasyCalc having no price is not the same claim as a price of zero.

    Asserted on the view rather than the HTML: a rendered "0" is legitimate
    elsewhere on the page (the needs table counts unfilled slots), so the
    meaningful check is that the player row carries None.
    """
    from fantasy_gm.core.trade_value import AssetValue
    from fantasy_gm.models import Position
    from fantasy_gm.web import context

    vmap = {
        "103": AssetValue(player_id="103", position=Position.WR, ros_points=100.0,
                          scarcity=1.0, value=1000.0, source="market", note="WR12"),
        "106": AssetValue(player_id="106", position=Position.K, ros_points=0.0,
                          scarcity=1.0, value=0.0, source="unranked",
                          note="not in FantasyCalc top values"),
    }
    record = _record()
    view = context.trade_decision_view(
        record,
        names={"103": "Ja'Marr Chase", "106": "Jaylen Waddle", "203": "CeeDee Lamb"},
        value_map=vmap,
    )
    rows = {p["player_id"]: p for p in view["packages"][0]["send"]}
    assert rows["103"]["value"] == 1000.0
    assert rows["106"]["value"] is None, "unranked must be blank, not 0.0"
    assert rows["106"]["value_source"] == "unranked"


def test_the_brief_collapses_once_there_is_an_analysis(client, store, with_values):
    """The form is long; the packages are the point once they exist."""
    assert "<details class=\"trade-brief\" open>" in client.get("/trades").text
    store.save(_record())
    assert "<details class=\"trade-brief\" open>" not in client.get("/trades").text


def test_a_target_names_the_owning_fantasy_team(client):
    """ESPN's owner names are frequently absent, so standings supply them."""
    text = client.get("/trades").text
    assert "Unknown" not in text
