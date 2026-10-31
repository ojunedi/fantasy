"""The number check itself."""
from __future__ import annotations

import builtins

from fantasy_gm.memo.integrity import screen, traceable, untraced


def test_brief04_the_check_makes_no_model_call(monkeypatch):
    # Anything reaching for a model would have to import a provider or open a socket.
    imported = []
    real_import = builtins.__import__

    def watching(name, *args, **kwargs):
        imported.append(name)
        return real_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", watching)

    shown, bad = screen("Projects 31.5 points.", traceable({"proj": 23.09}))

    # BRIEF-04 THEN no further model call is made
    assert not [m for m in imported if m.startswith(("langchain", "anthropic", "google", "httpx"))]
    assert bad == ["31.5"]
    assert shown.startswith("Brief withheld")


def test_a_number_written_at_lower_precision_traces():
    allowed = traceable({"proj": 23.09})
    assert untraced("about 23.1, call it 23", allowed) == []
    assert untraced("23.2", allowed) == ["23.2"]


def test_numbers_inside_tool_output_text_trace():
    allowed = traceable(["Bijan Robinson | proj 23.09 | opp DEF rank #26"])
    assert untraced("Bijan (23.1) faces the #26 run defense", allowed) == []
