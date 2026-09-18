"""Starting agent runs and streaming their trace.

`POST /runs` is sync (it only registers a run and spawns a thread); the stream
is the one `async def` on the site, because it is the only handler that waits.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from fantasy_gm.web import runs as runs_mod
from fantasy_gm.web.deps import get_settings
from fantasy_gm.web.settings import WebSettings

router = APIRouter(prefix="/runs")

KEEPALIVE_SECONDS = 15


def _manager(request: Request) -> runs_mod.RunManager:
    return request.app.state.runs


def render_panel(request: Request, run: runs_mod.Run, status_code: int = 200) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(
        request, "partials/run_panel.html", {"run": run}, status_code=status_code,
    )


def _render_event(request: Request, run: runs_mod.Run, event: dict) -> str:
    """One trace row as a single SSE data line: newlines would end the frame."""
    html = request.app.state.templates.get_template("partials/trace.html").render(
        event=event, run=run, request=request)
    return " ".join(html.split())


def _render_status(request: Request, run: runs_mod.Run) -> str:
    html = request.app.state.templates.get_template("partials/run_status.html").render(
        run=run, request=request)
    return " ".join(html.split())


WORKERS = {
    "lineup": runs_mod.lineup_worker,
    "trade": runs_mod.trade_worker,
}


@router.post("", response_class=HTMLResponse)
def start_run(request: Request,
              week: int = Form(...),
              season: int = Form(...),
              supervised: str = Form(default=""),
              kind: str = Form(default="lineup"),
              want_positions: list[str] = Form(default=[]),
              offerable_ids: list[str] = Form(default=[]),
              target_ids: list[str] = Form(default=[]),
              notes: str = Form(default=""),
              settings: WebSettings = Depends(get_settings)) -> HTMLResponse:
    manager = _manager(request)

    if kind not in WORKERS:
        return HTMLResponse('<p class="note">Unknown run type.</p>', status_code=400)

    # Single-flight is about cost and UI clarity, not correctness: the agents
    # already give each run its own checkpoint thread. But a second click should
    # not spend another eight LLM calls, so it gets the live panel and a 409.
    # Keyed by kind as well as week, so a trade run and a lineup run can overlap.
    existing = manager.get_active(kind, week, season)
    if existing is not None:
        return render_panel(request, existing, status_code=409)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:                   # sync context (TestClient) — no live loop
        loop = None

    brief = None
    if kind == "trade":
        # The four interview fields, straight off the form. All optional: an
        # empty brief runs the unconstrained scan, exactly as skipping every
        # CLI interview question does.
        brief = {
            "want_positions": want_positions,
            "offerable_ids": offerable_ids,
            "target_ids": target_ids,
            "notes": notes,
        }

    run = manager.create(kind, week, season, settings.team_id,
                         supervised=bool(supervised), loop=loop, brief=brief)

    factory = getattr(request.app.state, f"{kind}_agent_factory",
                      getattr(request.app.state, "agent_factory", None))
    worker_fn = WORKERS[kind]

    def worker(r: runs_mod.Run) -> str | None:
        return worker_fn(settings, r, manager, agent_factory=factory)

    manager.start(run, worker)
    return render_panel(request, run)


@router.get("/{run_id}/panel", response_class=HTMLResponse)
def run_panel(run_id: str, request: Request) -> HTMLResponse:
    run = _manager(request).get(run_id)
    if run is None:
        return HTMLResponse('<p class="note">That run is no longer in memory. '
                            'Check the decision history.</p>', status_code=404)
    return render_panel(request, run)


@router.post("/{run_id}/cancel", response_class=HTMLResponse)
def cancel_run(run_id: str, request: Request) -> HTMLResponse:
    manager = _manager(request)
    run = manager.get(run_id)
    if run is None:
        return HTMLResponse('<p class="note">No such run.</p>', status_code=404)
    manager.request_cancel(run)
    return render_panel(request, run)


@router.get("/{run_id}/stream")
async def stream(run_id: str, request: Request, after: int = -1) -> StreamingResponse:
    """Server-sent events: backlog first, then live.

    `Last-Event-ID` (sent by the browser automatically on a dropped connection)
    takes precedence over the `after` query param, which is what a deliberate
    reload uses. Either way the buffer decides what is owed.
    """
    manager = _manager(request)
    run = manager.get(run_id)
    if run is None:
        return StreamingResponse(iter(["event: close\ndata: \n\n"]),
                                 media_type="text/event-stream")

    last_event_id = request.headers.get("last-event-id")
    if last_event_id is not None:
        try:
            after = int(last_event_id)
        except ValueError:
            pass

    run.loop = asyncio.get_running_loop()

    async def frames():
        queue: asyncio.Queue = asyncio.Queue()
        backlog = manager.subscribe(run, queue, after_seq=after)
        try:
            for event in backlog:
                for frame in _frames_for(request, run, event):
                    yield frame
                if event["kind"] in (runs_mod.DONE, runs_mod.ERROR, runs_mod.CANCELLED):
                    yield "event: close\ndata: \n\n"
                    return

            while True:
                if await request.is_disconnected():
                    return
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_SECONDS)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                for frame in _frames_for(request, run, event):
                    yield frame
                if event["kind"] in (runs_mod.DONE, runs_mod.ERROR, runs_mod.CANCELLED):
                    yield "event: close\ndata: \n\n"
                    return
        finally:
            manager.unsubscribe(run, queue)

    return StreamingResponse(frames(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


def _frames_for(request: Request, run: runs_mod.Run, event: dict) -> list[str]:
    """The SSE frames one event produces: a trace row, and on a terminal event
    a refreshed status header."""
    seq = event["seq"]
    out = [f"id: {seq}\nevent: trace\ndata: {_render_event(request, run, event)}\n\n"]
    if event["kind"] in (runs_mod.DONE, runs_mod.ERROR, runs_mod.CANCELLED):
        out.append(f"event: status\ndata: {_render_status(request, run)}\n\n")
    return out
