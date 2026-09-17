"""HTMX fragment handlers.

These render the same read models the full pages do, so a fragment refresh can
never drift from a page reload. All plain `def` — threadpool, not the loop.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from fantasy_gm.adapters.espn import ESPNAdapter
from fantasy_gm.db.store import DecisionStore
from fantasy_gm.web import context, reads
from fantasy_gm.web.deps import ReadCache, get_adapter, get_reads, get_settings, get_store
from fantasy_gm.web.routes.pages import build_team_context
from fantasy_gm.web.settings import WebSettings

router = APIRouter(prefix="/partials")


def _render(request: Request, template: str, ctx: dict) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, template, ctx)


@router.get("/roster", response_class=HTMLResponse)
def roster_partial(request: Request,
                   adapter: ESPNAdapter = Depends(get_adapter),
                   settings: WebSettings = Depends(get_settings),
                   cache: ReadCache = Depends(get_reads),
                   store: DecisionStore = Depends(get_store)) -> HTMLResponse:
    ctx = build_team_context(request, adapter, settings, cache, store)
    return _render(request, "partials/roster_table.html", ctx)


@router.post("/refresh", response_class=HTMLResponse)
def refresh(request: Request,
            adapter: ESPNAdapter = Depends(get_adapter),
            settings: WebSettings = Depends(get_settings),
            cache: ReadCache = Depends(get_reads),
            store: DecisionStore = Depends(get_store)) -> HTMLResponse:
    """The explicit cache bypass: drop the read memo and re-fetch from ESPN."""
    cache.invalidate()
    ctx = build_team_context(request, adapter, settings, cache, store, fresh=True)
    return _render(request, "partials/roster_table.html", ctx)


@router.get("/standings", response_class=HTMLResponse)
def standings_partial(request: Request,
                      adapter: ESPNAdapter = Depends(get_adapter),
                      settings: WebSettings = Depends(get_settings),
                      cache: ReadCache = Depends(get_reads)) -> HTMLResponse:
    rows = reads.standings(adapter, cache, settings.season)
    stamp = context.cache_stamp(adapter, settings.season, {"view": "mTeam"})
    return _render(request, "partials/standings.html", {
        "standings": context.standings_view(rows, settings.team_id),
        "stamp": stamp,
    })


@router.get("/matchups", response_class=HTMLResponse)
def matchups_partial(request: Request,
                     adapter: ESPNAdapter = Depends(get_adapter),
                     settings: WebSettings = Depends(get_settings),
                     cache: ReadCache = Depends(get_reads)) -> HTMLResponse:
    week = reads.current_week(adapter, settings, cache)
    rows = reads.standings(adapter, cache, settings.season)
    games = reads.all_matchups(adapter, cache, week, settings.season, rows)
    stamp = context.cache_stamp(adapter, settings.season,
                                {"view": "mMatchup", "scoringPeriodId": week})
    return _render(request, "partials/matchups.html", {
        "matchups": context.matchups_view(games, rows, settings.team_id),
        "week": week,
        "stamp": stamp,
    })


@router.get("/rosters", response_class=HTMLResponse)
def rosters_partial(request: Request,
                    adapter: ESPNAdapter = Depends(get_adapter),
                    settings: WebSettings = Depends(get_settings),
                    cache: ReadCache = Depends(get_reads)) -> HTMLResponse:
    week = reads.current_week(adapter, settings, cache)
    rosters = reads.all_rosters(adapter, cache, week, settings.season)
    projections = reads.projections(adapter, cache, week, settings.season)
    standings = reads.standings(adapter, cache, settings.season)
    stamp = context.cache_stamp(adapter, settings.season,
                                {"view": "mRoster", "scoringPeriodId": week})
    return _render(request, "partials/rosters.html", {
        "rosters": context.rosters_view(rosters, projections, settings.team_id,
                                        standings),
        "week": week,
        "stamp": stamp,
    })


@router.get("/history", response_class=HTMLResponse)
def history_partial(request: Request,
                    store: DecisionStore = Depends(get_store)) -> HTMLResponse:
    records = store.list_recent(limit=50)
    return _render(request, "partials/history.html", {
        "decisions": [context.decision_summary(r) for r in records],
    })
