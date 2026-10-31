"""The waiver scan driven through the page: button → worker → agent → ledger.

The agent's unit tests feed it hand-built dicts. This file is the seam they
cannot see: the worker builds its inputs from the platform adapter, so a
missing adapter method or model field fails here and nowhere else.
"""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from fantasy_gm.models import (
    DecisionType,
    FreeAgent,
    Player,
    PlayerProjection,
    Position,
)

WEEK, SEASON = 3, 2026


class FakeLLM:
    def __init__(self, reply: str):
        self.reply = reply
        self.calls = 0

    def invoke(self, prompt: str):
        self.calls += 1
        return SimpleNamespace(content=self.reply)


@pytest.fixture
def waiver_adapter(fake_adapter, monkeypatch):
    """The shared fake, plus the two reads the waiver scan makes.

    Fixture projections stand in for rest-of-season points per game. One free
    agent, Jayden Reed (WR, 15.0), beats the weakest rostered WR (Rome Odunze,
    9.7), ranks third among projected WRs, and would start over Puka Nacua
    (14.0) in a fully available two-WR lineup.
    """
    reed = Player(platform_id="900", name="Jayden Reed", position=Position.WR,
                  eligible_positions=[Position.WR, Position.FLEX], nfl_team="9")

    def get_free_agents(week, season, position_filter=None, fresh=False):
        fake_adapter.calls.append("get_free_agents")
        return [FreeAgent(player=reed, percent_owned=40.0)]

    def get_ros_projections(week, season):
        fake_adapter.calls.append("get_ros_projections")
        players = [rp.player for rp in fake_adapter._roster.players]
        players += [rp.player for rp in fake_adapter._opponent_roster.players]
        projections = [
            PlayerProjection(player_id=p.platform_id, player_name=p.name,
                             projected_points=fake_adapter._projections[p.platform_id],
                             position=p.position, week=week, season=season)
            for p in players
        ]
        projections.append(PlayerProjection(player_id="900", player_name="Jayden Reed",
                                            projected_points=15.0, position=Position.WR,
                                            week=week, season=season))
        return projections

    fake_adapter.get_free_agents = get_free_agents
    fake_adapter.get_ros_projections = get_ros_projections
    from fantasy_gm.web import deps
    monkeypatch.setattr(deps, "build_adapter", lambda settings: fake_adapter)
    return fake_adapter


@pytest.fixture
def fake_llm(monkeypatch):
    llm = FakeLLM("Add Jayden Reed over Rome Odunze: 15 against 9.7, a 5.3 point margin.")
    import fantasy_gm.agent.subagents.base as subagents_base
    monkeypatch.setattr(subagents_base, "default_llm", lambda config=None: llm)
    return llm


def _wait_for_scan(app, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if app.state.runs.get_active("waiver", WEEK, SEASON) is None:
            return
        time.sleep(0.02)
    raise AssertionError("waiver scan did not finish in time")


def test_scan_from_the_page_writes_a_recommendation(client, app, store,
                                                    waiver_adapter, fake_llm):
    resp = client.post("/api/waiver/scan")
    assert resp.status_code == 200
    _wait_for_scan(app)

    records = [r for r in store.list_week(WEEK, SEASON)
               if r.decision_type == DecisionType.WAIVER]
    assert len(records) == 1, "the worker never wrote a decision"
    rec = records[0].recommendation
    assert rec["scan_state"] == "recommendation"
    assert rec["candidate"] == "Jayden Reed"
    assert rec["displaced_player"] == "Rome Odunze"
    assert rec["value_margin"] == 5.3
    assert records[0].memo == fake_llm.reply

    # WADD-10 THEN the total LLM calls made during the run is ≤ 3
    assert fake_llm.calls <= 3
    assert records[0].inputs_snapshot["llm_calls"] == fake_llm.calls

    page = client.get("/waiver").text
    assert "Add Jayden Reed" in page
    assert "Rome Odunze" in page


def test_brief_rejected_from_the_page_withholds_the_candidate(client, app, store,
                                                              waiver_adapter, fake_llm):
    fake_llm.reply = "Add Jayden Reed — 47.3 points clear of anyone you have."

    client.post("/api/waiver/scan")
    _wait_for_scan(app)

    records = [r for r in store.list_week(WEEK, SEASON)
               if r.decision_type == DecisionType.WAIVER]
    assert records[0].recommendation["scan_state"] == "brief_rejected"

    page = client.get("/waiver").text
    assert "held back" in page
    assert "Jayden Reed" not in page


def test_scan_runs_for_the_league_current_week_not_a_fixed_one(client, app, store,
                                                               waiver_adapter, fake_llm):
    # Production builds WebSettings with no week: it is derived from the league.
    app.state.settings.week = None
    waiver_adapter.get_current_week = lambda season: 11

    client.post("/api/waiver/scan")
    deadline = time.time() + 5
    while app.state.runs.get_active("waiver", 11, SEASON) and time.time() < deadline:
        time.sleep(0.02)

    weeks = {r.week for r in store.list_week(11, SEASON)
             if r.decision_type == DecisionType.WAIVER}
    assert weeks == {11}
    assert "Week 11" in client.get("/waiver").text


def test_pass_is_only_recorded_on_an_open_recommendation(client, app, store,
                                                         waiver_adapter, fake_llm):
    fake_llm.reply = "Add Jayden Reed — 47.3 points clear."  # rejected brief
    client.post("/api/waiver/scan")
    _wait_for_scan(app)

    client.post("/api/waiver/decide", data={"action": "pass"})

    record = [r for r in store.list_week(WEEK, SEASON)
              if r.decision_type == DecisionType.WAIVER][0]
    assert record.human_response is None
