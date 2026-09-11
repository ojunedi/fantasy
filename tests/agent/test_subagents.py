"""Tests for the single-shot LLM sub-agents (injury, news) with a fake model."""
from langchain_core.messages import AIMessage

from fantasy_gm.agent.subagents.base import parse_json_object
from fantasy_gm.agent.subagents.injury import interpret_injury
from fantasy_gm.agent.subagents.news import interpret_news


class FakeLLM:
    def __init__(self, content):
        self._content = content

    def invoke(self, messages):
        return AIMessage(content=self._content)


class RaisingLLM:
    def invoke(self, messages):
        raise RuntimeError("boom")


def test_parse_json_object_tolerates_prose():
    text = 'Sure! {"availability_pct": 80, "role_change_flag": false} done.'
    obj = parse_json_object(text)
    assert obj["availability_pct"] == 80


def test_parse_json_object_none_on_garbage():
    assert parse_json_object("no json here") is None


def test_interpret_injury_parses_structured_output():
    llm = FakeLLM('{"availability_pct": 40, "role_change_flag": true, "note": "DNP Wed."}')
    out = interpret_injury("WR X", "QUESTIONABLE", practice_participation="dnp", llm=llm)
    assert out["availability_pct"] == 40
    assert out["role_change_flag"] is True
    assert out["raw_status"] == "QUESTIONABLE"


def test_interpret_injury_degrades_without_llm(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    out = interpret_injury("WR X", "OUT", llm=None)
    assert out["availability_pct"] is None
    assert "unavailable" in out["note"].lower()


def test_interpret_injury_handles_llm_error():
    out = interpret_injury("WR X", "OUT", llm=RaisingLLM())
    assert out["availability_pct"] is None
    assert "error" in out["note"].lower()


def test_interpret_news_parses_events():
    llm = FakeLLM('{"events": [{"type": "role_change", "impact": "up", '
                  '"summary": "Sees 90% snaps."}], "net_outlook": "up", "note": "Rising."}')
    out = interpret_news("RB Y", llm=llm, news_text="RB Y took over the backfield.")
    assert out["net_outlook"] == "up"
    assert out["events"][0]["type"] == "role_change"


def test_interpret_news_degrades_without_llm(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    out = interpret_news("RB Y", llm=None, news_text="some news")
    assert out["events"] == []
    assert out["net_outlook"] == "neutral"
