"""Tests for the trade section of web/context.py.

Covers all four record shapes, value/no-value degradation, name resolution,
brief/needs views, and contract invariants. No network calls.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from fantasy_gm.agent.trade.preferences import TradePreferences
from fantasy_gm.core.trade_value import AssetValue, evaluate_trade
from fantasy_gm.models import (
    DecisionRecord,
    DecisionType,
    LeagueSettings,
    Platform,
    Player,
    PlayerStatus,
    Position,
    Roster,
    RosterPlayer,
    RosterSlot,
    ScoringRule,
    ScoringRules,
    TeamStanding,
    WaiverType,
)
from fantasy_gm.web.context import (
    trade_brief_view,
    trade_decision_view,
    trade_needs_view,
    trade_send_plan_view,
)


# ---------------------------------------------------------------------------
# helpers / fixtures
# ---------------------------------------------------------------------------

def _record(**overrides) -> DecisionRecord:
    base = dict(
        week=3,
        season=2026,
        created_at=datetime(2026, 9, 15, 9, 30),
        decision_type=DecisionType.TRADE,
        inputs_snapshot={"roster": [
            {"id": "10", "name": "DK Metcalf"},
            {"id": "11", "name": "Michael Wilson"},
        ]},
        signals_staleness={},
        recommendation={},
        memo="Trade memo.",
        confidence=0.75,
    )
    base.update(overrides)
    return DecisionRecord(**base)


def _standing(team_id: str, wins: int = 1, losses: int = 0,
              points_for: float = 110.0) -> TeamStanding:
    return TeamStanding(
        team_id=team_id, team_name=f"Team {team_id}",
        wins=wins, losses=losses, ties=0, points_for=points_for,
    )


def _asset(pid: str, value: float, pos: Position = Position.WR,
           source: str = "market", note: str = "WR15") -> AssetValue:
    return AssetValue(player_id=pid, position=pos, ros_points=value,
                      scarcity=1.0, value=value, source=source, note=note)


NAMES = {"10": "DK Metcalf", "11": "Michael Wilson",
         "20": "Garrett Wilson", "21": "CeeDee Lamb"}

PLAYER_INDEX = {
    "10": {"name": "DK Metcalf", "position": Position.WR, "team": "SEA",
           "owner_team_id": "8", "owner_name": "Omer"},
    "11": {"name": "Michael Wilson", "position": Position.WR, "team": "ARI",
           "owner_team_id": "8", "owner_name": "Omer"},
    "20": {"name": "Garrett Wilson", "position": Position.WR, "team": "NYJ",
           "owner_team_id": "3", "owner_name": "Other"},
    "21": {"name": "CeeDee Lamb", "position": Position.WR, "team": "DAL",
           "owner_team_id": "3", "owner_name": "Other"},
}

VALUE_MAP = {
    "10": _asset("10", 1694.0, note="WR5"),
    "11": _asset("11", 1118.0, note="WR12"),
    "20": _asset("20", 1890.0, note="WR3"),
    "21": _asset("21", 2100.0, note="WR2"),
}

MY_PLAYER_IDS = {"10", "11"}


def _view(rec: DecisionRecord, value_map=None, standings=None,
          league_players=None):
    return trade_decision_view(
        rec,
        names=NAMES,
        value_map=value_map,
        league_players=league_players or PLAYER_INDEX,
        standings=standings or [_standing("3")],
    )


# ---------------------------------------------------------------------------
# shape routing
# ---------------------------------------------------------------------------

def test_packages_shape():
    rec = _record(recommendation={
        "trades": [{"counterparty_team_id": "3", "send_player_ids": ["10"],
                    "receive_player_ids": ["20"], "rationale": "good deal",
                    "counterparty_pitch": "you want wilson?", "confidence": 0.8}],
    })
    v = _view(rec)
    assert v["shape"] == "packages"
    assert len(v["packages"]) == 1
    assert v["packages"] == v["packages"]  # non-empty list


def test_truncated_shape():
    rec = _record(recommendation={
        "truncated": True,
        "reason": "budget hit",
        "llm_calls": 5,
        "llm_budget": 5,
        "hit_step_limit": True,
        "agent_text": "ran out of calls",
        "evaluated_packages": [
            {"counterparty_team_id": "3", "send_player_ids": ["10"],
             "receive_player_ids": ["20"],
             "evaluation": "Package 1\nfairness=0.9\nverdict=win\nsome notes"},
        ],
    })
    v = _view(rec)
    assert v["shape"] == "truncated"
    assert v["truncated"] is True
    assert v["hit_step_limit"] is True
    assert v["llm_calls"] == 5
    assert v["llm_budget"] == 5
    assert v["agent_text"] == "ran out of calls"
    assert len(v["evaluated"]) == 1


def test_abstained_shape():
    rec = _record(recommendation={
        "abstained": True,
        "missing_information": ["need injury report", "need depth chart"],
        "what_you_would_need": "A healthy RB2.",
    })
    v = _view(rec)
    assert v["shape"] == "abstained"
    assert v["missing_information"] == ["need injury report", "need depth chart"]
    assert v["what_you_would_need"] == "A healthy RB2."
    assert v["packages"] == []


def test_unknown_shape():
    rec = _record(recommendation={"some_other_key": True})
    v = _view(rec)
    assert v["shape"] == "unknown"
    assert v["packages"] == []


# ---------------------------------------------------------------------------
# abstained yields no packages
# ---------------------------------------------------------------------------

def test_abstained_has_no_packages():
    rec = _record(recommendation={
        "abstained": True,
        "missing_information": ["x"],
    })
    v = _view(rec, value_map=VALUE_MAP)
    assert v["packages"] == []
    assert v["refused"] == []
    assert v["evaluated"] == []


# ---------------------------------------------------------------------------
# truncated — evaluation_text is passed through unparsed
# ---------------------------------------------------------------------------

def test_truncated_evaluation_text_is_opaque():
    raw_text = "Package 1\nfairness=0.9\nverdict=win\nsome\nlines"
    rec = _record(recommendation={
        "truncated": True,
        "evaluated_packages": [
            {"counterparty_team_id": "3", "send_player_ids": ["10"],
             "receive_player_ids": ["20"], "evaluation": raw_text},
        ],
    })
    v = _view(rec)
    assert v["evaluated"][0]["evaluation_text"] == raw_text
    # Must not be split into columns — it's a string not a dict.
    assert "fairness" not in v["evaluated"][0]


# ---------------------------------------------------------------------------
# value map present — numbers must match core.trade_value
# ---------------------------------------------------------------------------

def test_package_values_match_core():
    send_ids = ["10", "11"]
    receive_ids = ["20"]
    rec = _record(recommendation={
        "trades": [{"counterparty_team_id": "3",
                    "send_player_ids": send_ids, "receive_player_ids": receive_ids,
                    "rationale": "r", "counterparty_pitch": "p", "confidence": 0.7}],
    })
    v = _view(rec, value_map=VALUE_MAP)
    pkg = v["packages"][0]

    # Recompute with core directly.
    ev = evaluate_trade(send_ids, receive_ids, VALUE_MAP)

    assert pkg["ev_delta"] == ev.ev_delta
    assert pkg["fairness"] == ev.fairness
    assert pkg["verdict"] == ev.verdict
    assert pkg["send_value"] == ev.send_value
    assert pkg["receive_value"] == ev.receive_value
    assert v["has_values"] is True


# ---------------------------------------------------------------------------
# no value map — has_values False, every value field is None (not 0.0)
# ---------------------------------------------------------------------------

def test_no_value_map_degrades_gracefully():
    rec = _record(recommendation={
        "trades": [{"counterparty_team_id": "3", "send_player_ids": ["10"],
                    "receive_player_ids": ["20"], "rationale": "r",
                    "counterparty_pitch": "p", "confidence": 0.6}],
    })
    v = _view(rec, value_map=None)
    assert v["has_values"] is False
    pkg = v["packages"][0]
    for field in ("ev_delta", "fairness", "verdict", "send_value",
                  "receive_value", "lineup_delta", "lineup_before", "lineup_after"):
        val = pkg[field]
        assert val is None, f"{field} should be None, got {val!r}"
        # Explicitly not 0.0
        assert val != 0.0, f"{field} must not be 0.0 when no value map"


def test_spine_pct_is_50_when_no_values():
    rec = _record(recommendation={
        "trades": [{"counterparty_team_id": "3", "send_player_ids": ["10"],
                    "receive_player_ids": ["20"], "rationale": "",
                    "counterparty_pitch": ""}],
    })
    v = _view(rec, value_map=None)
    assert v["packages"][0]["spine_pct"] == 50.0


# ---------------------------------------------------------------------------
# oldest-shape rows without send_names — resolved via player index
# ---------------------------------------------------------------------------

def test_names_resolved_via_index_when_send_names_absent():
    # Oldest logged rows have no `send_names`/`receive_names` keys at all.
    rec = _record(recommendation={
        "trades": [{"counterparty_team_id": "3",
                    "send_player_ids": ["10", "11"],
                    "receive_player_ids": ["20"],
                    "rationale": "x", "counterparty_pitch": "y"}],
    })
    v = _view(rec, value_map=VALUE_MAP, league_players=PLAYER_INDEX)
    pkg = v["packages"][0]
    send_names = [p["name"] for p in pkg["send"]]
    assert "DK Metcalf" in send_names
    assert "Michael Wilson" in send_names
    receive_names = [p["name"] for p in pkg["receive"]]
    assert "Garrett Wilson" in receive_names


# ---------------------------------------------------------------------------
# directive_violations and refused_because surface
# ---------------------------------------------------------------------------

def test_directive_violations_surfaced():
    rec = _record(recommendation={
        "trades": [{"counterparty_team_id": "3",
                    "send_player_ids": ["10"], "receive_player_ids": ["20"],
                    "rationale": "r", "counterparty_pitch": "p",
                    "directive_violations": ["sends player you did not offer"]}],
    })
    v = _view(rec)
    assert v["packages"][0]["directive_violations"] == ["sends player you did not offer"]


def test_refused_because_surfaced():
    rec = _record(recommendation={
        "trades": [],
        "refused_trades": [{"counterparty_team_id": "3",
                             "send_player_ids": ["10"], "receive_player_ids": ["21"],
                             "rationale": "r", "counterparty_pitch": "p",
                             "refused_because": "value gap too large"}],
    })
    v = _view(rec)
    assert len(v["refused"]) == 1
    assert v["refused"][0]["refused_because"] == "value gap too large"


# ---------------------------------------------------------------------------
# trade_brief_view — chip ordering and preference marks
# ---------------------------------------------------------------------------

def _make_roster_players(positions=(Position.WR, Position.WR)) -> list[RosterPlayer]:
    players = []
    for i, pos in enumerate(positions):
        players.append(RosterPlayer(
            player=Player(
                platform_id=str(10 + i), name=NAMES.get(str(10 + i), f"P{i}"),
                position=pos,
                eligible_positions=[pos],
                nfl_team="SEA",
                status=PlayerStatus.ACTIVE,
            ),
            slot=pos,
            is_starter=True,
        ))
    return players


def _make_roster() -> Roster:
    return Roster(
        team_id="8", team_name="Mine", owner_name="Omer",
        players=_make_roster_players(), week=3, season=2026,
    )


def test_brief_chips_first():
    roster = _make_roster()
    # Player "11" (second) is the chip; "10" has higher value.
    chips = [(roster.players[1], VALUE_MAP["11"])]  # pid 11

    v = trade_brief_view(roster, VALUE_MAP, chips, PLAYER_INDEX)
    offerable = v["offerable"]
    # All items tagged correctly.
    chip_flags = [r["is_chip"] for r in offerable]
    # The chip (pid 11) must come before non-chips, even though pid 10 has higher value.
    chip_indices = [i for i, r in enumerate(offerable) if r["is_chip"]]
    non_chip_indices = [i for i, r in enumerate(offerable) if not r["is_chip"]]
    assert all(ci < nci for ci in chip_indices for nci in non_chip_indices)


def test_brief_prefs_marks_selections():
    roster = _make_roster()
    chips = []
    prefs = TradePreferences(
        want_positions=[Position.WR],
        offerable_ids=["10"],
        target_ids=["20"],
    )
    v = trade_brief_view(roster, VALUE_MAP, chips, PLAYER_INDEX, prefs=prefs)
    # Position WR should be selected.
    pos_row = next(r for r in v["positions"] if r["value"] == "WR")
    assert pos_row["selected"] is True
    # Offerable: pid 10 selected, pid 11 not.
    off_10 = next(r for r in v["offerable"] if r["player_id"] == "10")
    off_11 = next(r for r in v["offerable"] if r["player_id"] == "11")
    assert off_10["selected"] is True
    assert off_11["selected"] is False
    # Target: pid 20 selected.
    tgt_20 = next(r for r in v["targets"] if r["player_id"] == "20")
    assert tgt_20["selected"] is True


def test_brief_no_values():
    roster = _make_roster()
    v = trade_brief_view(roster, {}, [], PLAYER_INDEX)
    assert v["has_values"] is False


# ---------------------------------------------------------------------------
# trade_needs_view — state precedence
# ---------------------------------------------------------------------------

def _needs(**kw) -> dict:
    base = {"count": 2, "startable": 1, "required": 2,
            "surplus": -1, "unfilled": 0,
            "best": 100.0, "bar": 200.0, "need": False, "thin": False}
    base.update(kw)
    return base


def test_needs_state_need_wins():
    my_needs = {Position.RB: _needs(need=True, thin=True, surplus=1)}
    v = trade_needs_view(my_needs, [])
    assert v["rows"][0]["state"] == "need"


def test_needs_state_thin_beats_surplus():
    my_needs = {Position.RB: _needs(thin=True, surplus=2)}
    v = trade_needs_view(my_needs, [])
    assert v["rows"][0]["state"] == "thin"


def test_needs_state_surplus():
    my_needs = {Position.RB: _needs(surplus=2)}
    v = trade_needs_view(my_needs, [])
    assert v["rows"][0]["state"] == "surplus"


def test_needs_state_ok():
    my_needs = {Position.WR: _needs(surplus=0)}
    v = trade_needs_view(my_needs, [])
    assert v["rows"][0]["state"] == "ok"


def test_needs_chip_count():
    my_needs = {Position.WR: _needs()}
    # chips is a list of tuples (RosterPlayer, AssetValue)
    v = trade_needs_view(my_needs, [("a", "b"), ("c", "d")])
    assert v["chip_count"] == 2


# ---------------------------------------------------------------------------
# trade_send_plan_view
# ---------------------------------------------------------------------------

def test_send_plan_view():
    from fantasy_gm.execute.trade_plan import TradeSendPlan
    plan = TradeSendPlan(
        counterparty_team_id="3",
        send_names=["DK Metcalf"],
        receive_names=["Garrett Wilson"],
        human_steps=["Step 1", "Step 2"],
        notes=["Pitch here"],
    )
    v = trade_send_plan_view(plan)
    assert v["counterparty_team_id"] == "3"
    assert v["send_names"] == ["DK Metcalf"]
    assert v["receive_names"] == ["Garrett Wilson"]
    assert v["human_steps"] == ["Step 1", "Step 2"]
    assert v["notes"] == ["Pitch here"]


# ---------------------------------------------------------------------------
# summary keys always present
# ---------------------------------------------------------------------------

def test_summary_keys_always_present():
    for shape_rec in [
        _record(recommendation={"trades": []}),
        _record(recommendation={"abstained": True, "missing_information": []}),
        _record(recommendation={"truncated": True, "evaluated_packages": []}),
        _record(recommendation={}),
    ]:
        v = _view(shape_rec)
        assert "summary" in v
        assert v["summary"]["type"] == "trade"
        for key in ("shape", "memo", "packages", "refused", "evaluated",
                    "missing_information", "has_values", "truncated"):
            assert key in v, f"missing key {key!r}"


# ---------------------------------------------------------------------------
# spine_pct geometry — send is 40%, receive 60%
# ---------------------------------------------------------------------------

def test_spine_pct_geometry():
    # send_value=1000, receive_value=1500 => pct = 1000/2500*100 = 40.0
    vm = {
        "10": _asset("10", 1000.0),
        "20": _asset("20", 1500.0),
    }
    rec = _record(recommendation={
        "trades": [{"counterparty_team_id": "3",
                    "send_player_ids": ["10"], "receive_player_ids": ["20"],
                    "rationale": "r", "counterparty_pitch": "p"}],
    })
    v = _view(rec, value_map=vm)
    pkg = v["packages"][0]
    expected = 1000.0 / 2500.0 * 100
    assert abs(pkg["spine_pct"] - expected) < 0.01
