"""A lineup run on stale signals abstains before any model call."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from fantasy_gm.agent.graph import LineupGraphAgent
from fantasy_gm.agent.tools import LineupToolContext
from fantasy_gm.models import Roster
from fantasy_gm.signals.base import SignalAvailability, SignalBundle


class ModelReached(Exception):
    pass


def _ctx(projections_available: bool) -> LineupToolContext:
    now = datetime.utcnow()
    bundle = SignalBundle(week=9, season=2026, availability=[
        SignalAvailability(name="projections", available=projections_available,
                           as_of=now if projections_available else None,
                           note="" if projections_available else "error: ESPN 503"),
        SignalAvailability(name="injuries", available=True, as_of=now),
        SignalAvailability(name="usage_trends", available=True, as_of=now),
        SignalAvailability(name="vegas_lines", available=True, as_of=now),
        SignalAvailability(name="weather", available=True, as_of=now - timedelta(hours=1)),
    ])
    ctx = LineupToolContext(adapter=None, settings=None, team_id="8", week=9, season=2026)
    ctx._signals = bundle
    ctx._roster = Roster(team_id="8", team_name="Me", owner_name="", players=[],
                         week=9, season=2026)
    return ctx


@pytest.fixture
def agent(tmp_path, monkeypatch):
    a = LineupGraphAgent(checkpoint_path=tmp_path / "graph.db")
    a.model_builds = 0

    def no_model():
        a.model_builds += 1
        raise ModelReached
    monkeypatch.setattr(a, "_build_llm", no_model)
    return a


def test_sigstale04_a_stale_run_abstains_before_any_model_call(agent):
    record = agent.decide(_ctx(projections_available=False), verbose=False)

    # SIGSTALE-04 THEN the decision is an abstention
    assert record.recommendation["abstained"] is True
    assert "truncated" not in record.recommendation  # a stale abstention is not a cut-off run
    assert record.confidence == 0.0
    # SIGSTALE-04 AND the model was not called
    assert agent.model_builds == 0
    # SIGSTALE-04 AND the abstention names projections as missing, with its threshold
    [line] = record.recommendation["missing_information"]
    assert line == "projections: missing (error: ESPN 503) (threshold 6h)"
    assert "projections" in record.memo


def test_sigstale05_a_fresh_run_proceeds_as_before(agent):
    with pytest.raises(ModelReached):
        agent.decide(_ctx(projections_available=True), verbose=False)

    # SIGSTALE-05 THEN the model is called as before
    assert agent.model_builds == 1
