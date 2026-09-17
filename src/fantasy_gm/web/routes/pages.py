"""Full-page GET handlers.

Every handler here is a plain `def`, not `async def`, so Starlette runs it in
its threadpool and the synchronous adapter calls never block the event loop.
Only the SSE endpoint in `runs_routes.py` is async.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from fantasy_gm.adapters.espn import ESPNAdapter
from fantasy_gm.db.store import DecisionStore
from fantasy_gm.web import context, reads
from fantasy_gm.web.deps import (
    ReadCache,
    get_adapter,
    get_reads,
    get_settings,
    get_store,
)
from fantasy_gm.web.settings import WebSettings

router = APIRouter()


@router.get("/", include_in_schema=False)
def index() -> RedirectResponse:
    return RedirectResponse("/team", status_code=302)


def build_team_context(request: Request, adapter, settings: WebSettings,
                       cache: ReadCache, store: DecisionStore,
                       fresh: bool = False) -> dict:
    """Everything the team page and its roster partial need.

    Shared by the page and the partial so a refresh cannot drift from a reload.
    """
    week = reads.current_week(adapter, settings, cache)
    season = settings.season
    league = reads.league_settings(adapter, season)
    roster = reads.roster(adapter, cache, settings.team_id, week, season, fresh=fresh)
    projections = reads.projections(adapter, cache, week, season)
    signals = reads.signals(adapter, cache, roster, week, season)
    standings = reads.standings(adapter, cache, season)
    matchup = reads.matchup(adapter, cache, settings.team_id, week, season)

    view = context.roster_view(roster, projections, league, signals)
    chyron = context.chyron_view(matchup, settings.team_id, week, season,
                                 roster.team_name, standings)

    stamps = {
        "projections": context.cache_stamp(
            adapter, season, {"view": "kona_player_info", "scoringPeriodId": week}),
        "roster": context.cache_stamp(
            adapter, season, {"view": "mRoster", "scoringPeriodId": week}),
    }

    return {
        "active": "team",
        "week": week,
        "season": season,
        "team_id": settings.team_id,
        "view": view,
        "chyron": chyron,
        "stamps": stamps,
        "staleness": context.staleness_view(signals),
        "week_decisions": [context.decision_summary(r)
                           for r in store.list_week(week, season)],
        "active_run": request.app.state.runs.get_active("lineup", week, season)
        if hasattr(request.app.state, "runs") else None,
    }


@router.get("/team", response_class=HTMLResponse)
def team(request: Request,
         adapter: ESPNAdapter = Depends(get_adapter),
         settings: WebSettings = Depends(get_settings),
         cache: ReadCache = Depends(get_reads),
         store: DecisionStore = Depends(get_store)) -> HTMLResponse:
    ctx = build_team_context(request, adapter, settings, cache, store)
    return request.app.state.templates.TemplateResponse(request, "team.html", ctx)
