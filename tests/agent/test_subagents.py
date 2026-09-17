"""Tests for the single-shot LLM sub-agents (injury, news) with a fake model."""
from langchain_core.messages import AIMessage

from fantasy_gm.agent.subagents.base import parse_json_object
from fantasy_gm.agent.subagents.injury import interpret_injuries, interpret_injury
from fantasy_gm.agent.subagents.news import interpret_news, interpret_news_batch


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


# ---- Batched news --------------------------------------------------------

class CountingLLM:
    """Returns scripted content and records how many calls it received."""
    def __init__(self, *contents):
        self._contents = list(contents)
        self.calls = 0
        self.prompts = []

    def invoke(self, messages):
        self.prompts.append("\n".join(str(m.content) for m in messages))
        content = self._contents[min(self.calls, len(self._contents) - 1)]
        self.calls += 1
        return AIMessage(content=content)


_BATCH_REPLY = ('{"players": {'
                '"RB Y": {"events": [{"type": "role_change", "impact": "up", '
                '"summary": "Lead back."}], "net_outlook": "up", "note": "Rising."},'
                '"WR Z": {"events": [], "net_outlook": "neutral", "note": "Quiet."}'
                '}}')


def test_batch_interprets_many_players_in_one_call():
    """The whole point: N players must cost ONE model call, not N."""
    llm = CountingLLM(_BATCH_REPLY)
    out = interpret_news_batch(["RB Y", "WR Z"], llm=llm, news_text="news")
    assert llm.calls == 1
    assert out["RB Y"]["net_outlook"] == "up"
    assert out["WR Z"]["net_outlook"] == "neutral"
    # Both names were offered to the model in the single prompt.
    assert "RB Y" in llm.prompts[0] and "WR Z" in llm.prompts[0]


def test_batch_degrades_only_the_missing_player():
    """One absent key must not poison the players the model did answer."""
    llm = CountingLLM(_BATCH_REPLY)
    out = interpret_news_batch(["RB Y", "Nobody At All"], llm=llm, news_text="news")
    assert out["RB Y"]["net_outlook"] == "up"          # survived
    assert out["Nobody At All"]["events"] == []        # degraded alone
    assert "No entry" in out["Nobody At All"]["note"]


def test_batch_tolerates_recapitalized_keys():
    llm = CountingLLM('{"players": {"rb y": {"events": [], "net_outlook": "down"}}}')
    out = interpret_news_batch(["RB Y"], llm=llm, news_text="news")
    assert out["RB Y"]["net_outlook"] == "down"


def test_batch_chunks_past_the_size_cap():
    from fantasy_gm.agent.subagents import news as news_mod
    names = [f"Player {i}" for i in range(news_mod.BATCH_SIZE + 1)]
    llm = CountingLLM('{"players": {}}')
    out = interpret_news_batch(names, llm=llm, news_text="news")
    assert llm.calls == 2                  # chunked, not one oversized call
    assert set(out) == set(names)          # every player still accounted for


def test_batch_fetches_the_shared_feed_once(monkeypatch):
    """The ESPN feed is league-wide — it must not be re-fetched per player."""
    fetches = []
    monkeypatch.setattr("fantasy_gm.agent.subagents.news.get_nfl_news",
                        lambda limit=15: fetches.append(1) or "league news")
    monkeypatch.setattr("fantasy_gm.agent.subagents.news.tavily_available",
                        lambda: False)
    llm = CountingLLM('{"players": {}}')
    interpret_news_batch(["A", "B", "C"], llm=llm)
    assert len(fetches) == 1


def test_batch_degrades_every_player_without_an_llm(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out = interpret_news_batch(["A", "B"], llm=None, news_text="x")
    assert set(out) == {"A", "B"}
    assert all(v["net_outlook"] == "neutral" for v in out.values())


def test_batch_deduplicates_and_ignores_blanks():
    llm = CountingLLM('{"players": {}}')
    out = interpret_news_batch(["RB Y", "RB Y", ""], llm=llm, news_text="news")
    assert list(out) == ["RB Y"]


# ---- Batched injuries ----------------------------------------------------

_INJ_REPLY = ('{"players": {'
              '"RB A": {"availability_pct": 0, "role_change_flag": false, "note": "Out."},'
              '"RB B": {"availability_pct": 95, "role_change_flag": true, "note": "Inherits work."}'
              '}}')


def _inj(name, status="QUESTIONABLE", **kw):
    return {"player_name": name, "status": status, **kw}


def test_injuries_batch_uses_one_call_for_many_players():
    llm = CountingLLM(_INJ_REPLY)
    out = interpret_injuries([_inj("RB A", "OUT"), _inj("RB B", "ACTIVE")], llm=llm)
    assert llm.calls == 1
    assert out["RB A"]["availability_pct"] == 0
    # The teammate read that per-player calls structurally cannot make.
    assert out["RB B"]["role_change_flag"] is True


def test_injuries_batch_preserves_each_raw_status():
    llm = CountingLLM(_INJ_REPLY)
    out = interpret_injuries([_inj("RB A", "OUT"), _inj("RB B", "ACTIVE")], llm=llm)
    assert out["RB A"]["raw_status"] == "OUT"
    assert out["RB B"]["raw_status"] == "ACTIVE"


def test_injuries_batch_degrades_only_the_missing_player():
    llm = CountingLLM(_INJ_REPLY)
    out = interpret_injuries([_inj("RB A", "OUT"), _inj("Ghost", "DOUBTFUL")], llm=llm)
    assert out["RB A"]["availability_pct"] == 0          # survived
    assert out["Ghost"]["availability_pct"] is None      # degraded alone
    assert out["Ghost"]["raw_status"] == "DOUBTFUL"


def test_injuries_batch_sends_only_the_fields_we_have():
    """Absent practice/snap data must not appear as 'None' in the prompt."""
    llm = CountingLLM(_INJ_REPLY)
    interpret_injuries([_inj("RB A", "OUT")], llm=llm)
    assert "None" not in llm.prompts[0]
    llm2 = CountingLLM(_INJ_REPLY)
    interpret_injuries([_inj("RB A", "OUT", snap_share_last3=0.62)], llm=llm2)
    assert "62%" in llm2.prompts[0]


def test_injuries_batch_chunks_past_the_size_cap():
    from fantasy_gm.agent.subagents import injury as injury_mod
    players = [_inj(f"P{i}") for i in range(injury_mod.BATCH_SIZE + 1)]
    llm = CountingLLM('{"players": {}}')
    out = interpret_injuries(players, llm=llm)
    assert llm.calls == 2
    assert len(out) == injury_mod.BATCH_SIZE + 1


def test_injuries_batch_degrades_every_player_on_error():
    out = interpret_injuries([_inj("RB A"), _inj("RB B")], llm=RaisingLLM())
    assert set(out) == {"RB A", "RB B"}
    assert all("error" in v["note"].lower() for v in out.values())


def test_injuries_batch_deduplicates_by_name():
    llm = CountingLLM(_INJ_REPLY)
    out = interpret_injuries([_inj("RB A"), _inj("RB A")], llm=llm)
    assert list(out) == ["RB A"]
