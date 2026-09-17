"""Tracer classification and the CLI/web split.

`message_events` is the shared classifier; `print_message` renders it to stdout
and the web layer consumes the dicts. These tests pin both halves so the split
cannot drift.
"""
from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from fantasy_gm.agent.tracer import message_events, print_message, stream_verbose

TERMINAL = frozenset({"propose_lineup"})


def test_ai_text_only():
    events = message_events(AIMessage(content="thinking about it"), TERMINAL)
    assert [e["kind"] for e in events] == ["ai_text"]
    assert events[0]["text"] == "thinking about it"


def test_ai_text_is_truncated_unless_full():
    long = "x" * 500
    assert len(message_events(AIMessage(content=long), TERMINAL)[0]["display"]) == 300
    assert len(message_events(AIMessage(content=long), TERMINAL, full=True)[0]["display"]) == 500


def test_think_tags_are_stripped():
    msg = AIMessage(content="<think>hidden</think>visible")
    assert message_events(msg, TERMINAL)[0]["text"] == "visible"


def test_tool_call():
    msg = AIMessage(content="", tool_calls=[
        {"name": "get_roster", "args": {"team_id": "8"}, "id": "c1"},
    ])
    events = message_events(msg, TERMINAL)
    assert [e["kind"] for e in events] == ["tool_call"]
    assert events[0]["name"] == "get_roster"
    assert events[0]["args"] == {"team_id": "8"}


def test_text_and_tool_calls_emit_in_order():
    msg = AIMessage(content="first I'll look", tool_calls=[
        {"name": "get_roster", "args": {}, "id": "c1"},
        {"name": "get_matchup", "args": {}, "id": "c2"},
    ])
    assert [e["kind"] for e in message_events(msg, TERMINAL)] == [
        "ai_text", "tool_call", "tool_call",
    ]


def test_tool_result_marks_terminal():
    normal = message_events(ToolMessage(content="ok", name="get_roster", tool_call_id="c1"), TERMINAL)
    terminal = message_events(ToolMessage(content="ok", name="propose_lineup", tool_call_id="c2"), TERMINAL)
    assert normal[0]["terminal"] is False
    assert terminal[0]["terminal"] is True


def test_tool_result_is_collapsed_to_one_line_unless_full():
    msg = ToolMessage(content="line one\nline two", name="get_roster", tool_call_id="c1")
    assert "\n" not in message_events(msg, TERMINAL)[0]["display"]
    assert "\n" in message_events(msg, TERMINAL, full=True)[0]["display"]


def test_no_response_is_its_own_kind():
    """Neither a tool call nor text — the failure mode worth surfacing loudly."""
    msg = AIMessage(content="", response_metadata={"finish_reason": "SAFETY"})
    events = message_events(msg, TERMINAL)
    assert [e["kind"] for e in events] == ["no_response"]
    assert events[0]["finish_reason"] == "SAFETY"


def test_human_message_yields_nothing():
    assert message_events(HumanMessage(content="go"), TERMINAL) == []


def test_print_message_still_prints(capsys):
    """Regression: the CLI path must keep writing to stdout after the refactor."""
    print_message(AIMessage(content="", tool_calls=[
        {"name": "get_roster", "args": {"team_id": "8"}, "id": "c1"},
    ]), TERMINAL)
    out = capsys.readouterr().out
    assert "get_roster" in out
    assert "team_id" in out


class _FakeApp:
    """Stands in for a compiled graph: yields accumulating message states."""

    def __init__(self, states):
        self._states = states

    def stream(self, input_msg, config, stream_mode):
        for s in self._states:
            yield {"messages": s}


@pytest.fixture
def fake_app():
    call = AIMessage(content="looking", tool_calls=[
        {"name": "optimize_lineup", "args": {}, "id": "c1"},
    ])
    result = ToolMessage(content="done", name="propose_lineup", tool_call_id="c1")
    return _FakeApp([[call], [call, result]])


def test_stream_verbose_without_emit_prints(capsys, fake_app):
    state = stream_verbose(fake_app, {}, {}, TERMINAL, label="run")
    out = capsys.readouterr().out
    assert "optimize_lineup" in out
    assert "propose_lineup" in out
    assert "reached terminal tool" in out
    assert len(state["messages"]) == 2


def test_stream_verbose_with_emit_is_silent_and_structured(capsys, fake_app):
    events = []
    stream_verbose(fake_app, {}, {}, TERMINAL, label="run", emit=events.append)
    assert capsys.readouterr().out == ""
    assert [e["kind"] for e in events] == [
        "start", "ai_text", "tool_call", "tool_result", "summary",
    ]
    assert events[-1]["reached_terminal"] is True
    assert events[-1]["tool_count"] == 1


def test_stream_verbose_emits_each_message_once(capsys):
    """The `seen` cursor must not replay earlier messages on later states."""
    msgs = [AIMessage(content=f"step {i}") for i in range(3)]
    app = _FakeApp([msgs[:1], msgs[:2], msgs[:3]])
    events = []
    stream_verbose(app, {}, {}, TERMINAL, emit=events.append)
    texts = [e["text"] for e in events if e["kind"] == "ai_text"]
    assert texts == ["step 0", "step 1", "step 2"]


def test_summary_reports_rejected_tool_calls():
    rejected = ToolMessage(content="Error invoking tool: bad schema",
                           name="optimize_lineup", tool_call_id="c1")
    events = []
    stream_verbose(_FakeApp([[rejected]]), {}, {}, TERMINAL, emit=events.append)
    summary = events[-1]
    assert summary["failed_count"] == 1
    assert summary["failed_names"] == ["optimize_lineup"]
    assert summary["reached_terminal"] is False
