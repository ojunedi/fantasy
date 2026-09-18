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


def load_decision(store: DecisionStore, decision_id: str):
    """Fetch a decision or 404. A malformed id is a 404, not a 500."""
    try:
        parsed = UUID(decision_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="No such decision")
    record = store.get(parsed)
    if record is None:
        raise HTTPException(status_code=404, detail="No such decision")
    return record


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
    projections = reads.projections(adapter, cache, week, season)
    standings = reads.standings(adapter, cache, season)
    matchup = reads.matchup(adapter, cache, settings.team_id, week, season)

    # Every roster in one read: the opponent's is needed for the live score, and
    # `live_rosters` bypasses the 1h disk cache because lock state and banked
    # points both change the moment a game kicks off.
    rosters = reads.live_rosters(adapter, cache, week, season, fresh=fresh)
    roster = next((r for r in rosters if r.team_id == settings.team_id),
                  reads.roster(adapter, cache, settings.team_id, week, season))
    signals = reads.signals(adapter, cache, roster, week, season)

    view = context.roster_view(roster, projections, league, signals)
    chyron = context.chyron_view(matchup, settings.team_id, week, season,
                                 roster.team_name, standings,
                                 live_totals=context.team_live_totals(rosters, projections))

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


@router.get("/history", response_class=HTMLResponse)
def history(request: Request,
            store: DecisionStore = Depends(get_store)) -> HTMLResponse:
    records = store.list_recent(limit=50)
    return request.app.state.templates.TemplateResponse(request, "history.html", {
        "active": "history",
        "count": len(records),
        "decisions": [context.decision_summary(r) for r in records],
    })


@router.get("/decisions/{decision_id}", response_class=HTMLResponse)
def decision_detail(decision_id: str, request: Request,
                    adapter: ESPNAdapter = Depends(get_adapter),
                    settings: WebSettings = Depends(get_settings),
                    cache: ReadCache = Depends(get_reads),
                    store: DecisionStore = Depends(get_store)) -> HTMLResponse:
    record = load_decision(store, decision_id)
    # The live roster supplies the id -> name join; if it is unavailable the
    # record's own inputs_snapshot still carries names, so the page renders.
    roster = projections = None
    try:
        roster = reads.roster(adapter, cache, settings.team_id, record.week, record.season)
        projections = reads.projections(adapter, cache, record.week, record.season)
    except Exception:
        pass

    return request.app.state.templates.TemplateResponse(request, "decision.html", {
        "active": "history",
        "d": context.decision_view(record, roster, projections),
    })


@router.get("/league", response_class=HTMLResponse)
def league(request: Request,
           adapter: ESPNAdapter = Depends(get_adapter),
           settings: WebSettings = Depends(get_settings),
           cache: ReadCache = Depends(get_reads)) -> HTMLResponse:
    """Standings server-side; matchups and rosters lazy-load as HTMX fragments."""
    week = reads.current_week(adapter, settings, cache)
    rows = reads.standings(adapter, cache, settings.season)
    return request.app.state.templates.TemplateResponse(request, "league.html", {
        "active": "league",
        "week": week,
        "season": settings.season,
        "standings": context.standings_view(rows, settings.team_id),
        "stamp": context.cache_stamp(adapter, settings.season, {"view": "mTeam"}),
    })


@router.get("/team", response_class=HTMLResponse)
def team(request: Request,
         adapter: ESPNAdapter = Depends(get_adapter),
         settings: WebSettings = Depends(get_settings),
         cache: ReadCache = Depends(get_reads),
         store: DecisionStore = Depends(get_store)) -> HTMLResponse:
    ctx = build_team_context(request, adapter, settings, cache, store)
    return request.app.state.templates.TemplateResponse(request, "team.html", ctx)
