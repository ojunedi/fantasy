"""Waiver decision page and API routes.

GET  /waiver              — main page (all six states)
POST /api/waiver/scan     — trigger a waiver scan run
GET  /api/waiver/status   — htmx polling partial (every 5 s)
POST /api/waiver/decide   — record APPROVED or DECLINED, redirect to /waiver
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from fantasy_gm.db.store import DecisionStore
from fantasy_gm.models import DecisionType, HumanResponse
from fantasy_gm.web import context, reads
from fantasy_gm.web.deps import get_reads, get_settings, get_store
from fantasy_gm.web.runs import RunManager
from fantasy_gm.web.settings import WebSettings

router = APIRouter()


def _get_runs(request: Request) -> RunManager:
    return request.app.state.runs


def _current_waiver_record(store: DecisionStore, week: int, season: int):
    """The newest waiver decision this week — a re-run supersedes a stale scan."""
    records = store.list_week(week, season)  # oldest first
    return next((r for r in reversed(records) if r.decision_type == DecisionType.WAIVER), None)


@router.get("/waiver", response_class=HTMLResponse)
def waiver_page(request: Request,
                settings: WebSettings = Depends(get_settings),
                store: DecisionStore = Depends(get_store)) -> HTMLResponse:
    week = _week(request, settings)
    season = settings.season
    record = _current_waiver_record(store, week, season)
    active_run = request.app.state.runs.get_active("waiver", week, season)
    return request.app.state.templates.TemplateResponse(request, "waiver.html", {
        "active": "waiver",
        "week": week,
        "season": season,
        "waiver": context.waiver_view(record, active_run),
    })


@router.post("/api/waiver/scan", response_class=HTMLResponse)
def start_scan(request: Request,
               settings: WebSettings = Depends(get_settings),
               store: DecisionStore = Depends(get_store)) -> HTMLResponse:
    week = _week(request, settings)
    season = settings.season
    runs: RunManager = request.app.state.runs

    if runs.get_active("waiver", week, season):
        # Already running — return the status partial
        return _status_partial(request, week, season, settings, store)

    run = runs.create(kind="waiver", week=week, season=season,
                      team_id=settings.team_id, supervised=False)
    runs.start(run, lambda r: _waiver_worker(r, settings))

    return _status_partial(request, week, season, settings, store)


@router.get("/api/waiver/status", response_class=HTMLResponse)
def scan_status(request: Request,
                settings: WebSettings = Depends(get_settings),
                store: DecisionStore = Depends(get_store)) -> HTMLResponse:
    week = _week(request, settings)
    season = settings.season
    return _status_partial(request, week, season, settings, store)


@router.post("/api/waiver/decide", response_class=RedirectResponse)
def record_decision(request: Request,
                    action: str = Form(...),
                    store: DecisionStore = Depends(get_store),
                    settings: WebSettings = Depends(get_settings)) -> RedirectResponse:
    week = _week(request, settings)
    season = settings.season
    record = _current_waiver_record(store, week, season)
    # Only an open recommendation takes a claim or a pass; anything else is
    # a stale page or a hand-built POST, and changes nothing.
    if (record is None or record.human_response is not None
            or (record.recommendation or {}).get("scan_state") != "recommendation"
            or action not in ("claim", "pass")):
        return RedirectResponse("/waiver", status_code=303)

    response = HumanResponse.APPROVED if action == "claim" else HumanResponse.DECLINED
    store.record_human_response(record.id, response)
    return RedirectResponse("/waiver", status_code=303)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _status_partial(request: Request, week: int, season: int,
                    settings: WebSettings, store: DecisionStore) -> HTMLResponse:
    record = _current_waiver_record(store, week, season)
    active_run = request.app.state.runs.get_active("waiver", week, season)
    return request.app.state.templates.TemplateResponse(
        request, "partials/waiver_status.html", {
            "waiver": context.waiver_view(record, active_run),
        }
    )


def _waiver_worker(run, settings: WebSettings) -> str | None:
    """Run the waiver scan in the worker thread and write the decision record."""
    from datetime import datetime, timezone

    from fantasy_gm.agent.subagents.base import default_llm
    from fantasy_gm.agent.waiver_agent import gather_scan_inputs, run_waiver_scan
    from fantasy_gm.db.store import DecisionStore
    from fantasy_gm.web import deps

    # Built inside the worker thread, like lineup_worker: sqlite connections
    # are bound to the thread that opened them.
    adapter = deps.build_adapter(settings)
    store = DecisionStore(settings.db_path)
    now = datetime.now(tz=timezone.utc)

    league = adapter.get_league_settings(season=run.season)
    roster, candidates, signals = gather_scan_inputs(
        adapter, settings.team_id, run.week, run.season, league, now=now)

    try:
        run_waiver_scan(
            store, run.week, run.season, league,
            candidates=candidates,
            roster=roster,
            signals=signals,
            llm=default_llm(),
            now=now,
        )
    finally:
        # A rejected brief raises after its record is written; back that up too.
        store.backup_if_dirty()

    waiver_record = _current_waiver_record(store, run.week, run.season)
    return str(waiver_record.id) if waiver_record else None


def _week(request: Request, settings: WebSettings) -> int:
    """The league's current week, derived the same way as every other page."""
    return reads.current_week(request.app.state.adapter, settings, get_reads(request))
