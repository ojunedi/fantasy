"""Bridge between the tracer's event stream and a Run.

`agent/tracer.py` calls `emit(event)` for each classified message. This wraps
that callback so the event lands in the run's buffer and reaches subscribers,
and so a cancel request is noticed: the adapter raises `RunCancelled`, which
`RunManager._guard` catches. That is why cancelling needs no tracer change —
the tracer just calls emit, and emit is where we get to say no.
"""
from __future__ import annotations

from typing import Callable

from fantasy_gm.web.runs import Run, RunCancelled, RunManager


def make_emit_adapter(run: Run, manager: RunManager) -> Callable[[dict], None]:
    def emit(event: dict) -> None:
        if run.cancel.is_set():
            raise RunCancelled(f"run {run.id} cancelled")
        manager.publish(run, event)

    return emit
