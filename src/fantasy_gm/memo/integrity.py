"""A brief may rephrase a computed number, never introduce one (I-25, I-26, I-27).

Every number in this product is computed deterministically so the model cannot
invent one; the briefs are the one place generated prose could. So each number
in a brief must trace to the analysis the run produced — its tool outputs,
projections, week and season. Written at lower precision is a restatement:
"23.1" traces to 23.09. Pure functions: no model call, no retry (NFR-04).
"""
from __future__ import annotations

import json
import re
from typing import Any, Iterable

_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def numbers_in(text: str) -> list[str]:
    return _NUMBER.findall(text or "")


def _walk(value: Any) -> Iterable[float]:
    """Every number in a value: numeric leaves, and numbers written inside strings."""
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, (int, float)):
        yield float(value)
    elif isinstance(value, str):
        for n in numbers_in(value):
            yield float(n)
    elif isinstance(value, dict):
        for v in value.values():
            yield from _walk(v)
    elif isinstance(value, (list, tuple, set)):
        for v in value:
            yield from _walk(v)
    else:
        yield from _walk(json.loads(json.dumps(value, default=str)))


def traceable(*sources: Any) -> set[float]:
    """The numbers an analysis produced, gathered from any mix of values."""
    allowed: set[float] = set()
    for source in sources:
        allowed.update(_walk(source))
    return allowed


def untraced(text: str, allowed: set[float]) -> list[str]:
    """Numbers in `text` that no allowed value rounds to at the written precision."""
    bad = []
    for token in numbers_in(text):
        decimals = len(token.split(".")[1]) if "." in token else 0
        value = float(token)
        if not any(round(a, decimals) == value for a in allowed):
            bad.append(token)
    return list(dict.fromkeys(bad))


def screen(text: str, allowed: set[float], kind: str = "Brief") -> tuple[str, list[str]]:
    """(text to show, untraced numbers). A text with any untraced number is withheld."""
    bad = untraced(text, allowed)
    if not bad:
        return text, []
    return (f"{kind} withheld — it quoted numbers the analysis never computed: "
            f"{', '.join(bad)}."), bad
