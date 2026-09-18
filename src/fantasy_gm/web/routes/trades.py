"""The trades page and its two gates.

Trades are propose-only and always will be: ESPN requires the counterparty to
accept, so there is no write path here and none should be built (D-001/D-019).
The flow therefore ends at "go send this in the app", and the artifact worth
keeping is the record of what you approved or rejected and why.

Like every other page handler these are plain `def`, so Starlette runs them in
its threadpool and the synchronous adapter reads never block the event loop.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse

from fantasy_gm.adapters.espn import ESPNAdapter
from fantasy_gm.db.store import DecisionStore
from fantasy_gm.execute.trade_plan import TradeProposalExecutor
from fantasy_gm.models import DecisionType, HumanResponse
from fantasy_gm.web import context, reads
from fantasy_gm.web.deps import ReadCache, get_adapter, get_reads, get_settings, get_store
from fantasy_gm.web.routes.pages import load_decision
from fantasy_gm.web.settings import WebSettings

router = APIRouter()

TRADE_HISTORY_LIMIT = 50


def _trade_records(store: DecisionStore) -> list:
    return [r for r in store.list_recent(limit=TRADE_HISTORY_LIMIT)
            if r.decision_type == DecisionType.TRADE]


def _decision_context(record, adapter, settings: WebSettings, cache: ReadCache) -> dict:
    """Assemble a trade decision view, degrading as each input goes missing.

    Every read here is optional. The value map in particular is a FantasyCalc
    network call, and when it is unavailable the view reports `has_values=False`
    and the templates drop the value columns rather than showing invented zeros.
    """
    week, season = record.week, record.season
    value_map, valued_at = reads.trade_value_map(adapter, cache, week, season,
                                                 settings.team_id)
    index = reads.league_player_index(adapter, cache, week, season)
    names = {pid: info.get("name", pid) for pid, info in index.items()}

    my_players = projections = league = standings = None
    try:
        rosters = reads.live_rosters(adapter, cache, week, season)
        mine = next((r for r in rosters if r.team_id == settings.team_id), None)
        my_players = [rp.player for rp in mine.players] if mine else None
        names.update({rp.player.platform_id: rp.player.name
                      for r in rosters for rp in r.players})
        projections = reads.projections(adapter, cache, week, season)
        league = reads.league_settings(adapter, season)
        standings = reads.standings(adapter, cache, season)
    except Exception:
        pass

    return context.trade_decision_view(
        record, names=names, value_map=value_map, my_players=my_players,
        league_players=index, projections=projections, settings=league,
        standings=standings, valued_at=valued_at,
    )


def _brief_context(adapter, settings: WebSettings, cache: ReadCache, week: int) -> dict:
    """The four-field brief form, plus my needs and surplus beside it."""
    season = settings.season
    value_map, _ = reads.trade_value_map(adapter, cache, week, season, settings.team_id)
    index = reads.league_player_index(adapter, cache, week, season)
    needs, chips = reads.my_trade_needs(adapter, cache, week, season, settings.team_id)

    roster = standings = None
    try:
        rosters = reads.live_rosters(adapter, cache, week, season)
        roster = next((r for r in rosters if r.team_id == settings.team_id), None)
        standings = reads.standings(adapter, cache, season)
    except Exception:
        pass

    return {
        "brief": context.trade_brief_view(roster, value_map, chips, index,
                                          standings=standings),
        "needs": context.trade_needs_view(needs, chips),
    }


@router.get("/trades", response_class=HTMLResponse)
def trades(request: Request,
           adapter: ESPNAdapter = Depends(get_adapter),
           settings: WebSettings = Depends(get_settings),
           cache: ReadCache = Depends(get_reads),
           store: DecisionStore = Depends(get_store)) -> HTMLResponse:
    week = reads.current_week(adapter, settings, cache)
    records = _trade_records(store)

    # Show this week's latest trade decision if there is one, else the most
    # recent of any week — a trade proposal does not go stale the way a lineup
    # does, so last week's is still worth looking at.
    latest = next((r for r in records if r.week == week), None) or (
        records[0] if records else None)

    ctx = {
        "active": "trades",
        "week": week,
        "season": settings.season,
        "t": _decision_context(latest, adapter, settings, cache) if latest else None,
        "decisions": [context.decision_summary(r) for r in records],
        "active_run": request.app.state.runs.get_active("trade", week, settings.season),
    }
    ctx.update(_brief_context(adapter, settings, cache, week))
    return request.app.state.templates.TemplateResponse(request, "trades.html", ctx)


@router.get("/partials/trades/{decision_id}", response_class=HTMLResponse)
def trade_decision_partial(decision_id: str, request: Request,
                           adapter: ESPNAdapter = Depends(get_adapter),
                           settings: WebSettings = Depends(get_settings),
                           cache: ReadCache = Depends(get_reads),
                           store: DecisionStore = Depends(get_store)) -> HTMLResponse:
    """One decision's body, so the page can swap in a finished run's result."""
    record = load_decision(store, decision_id)
    return request.app.state.templates.TemplateResponse(
        request, "partials/trade_decision.html",
        {"t": _decision_context(record, adapter, settings, cache)},
    )


def _package_at(record, index: int) -> dict:
    trades = (record.recommendation or {}).get("trades") or []
    if not 1 <= index <= len(trades):
        raise HTTPException(status_code=404, detail="No such package")
    return trades[index - 1]


@router.post("/trades/{decision_id}/approve/{index}", response_class=HTMLResponse)
def approve_package(decision_id: str, index: int, request: Request,
                    store: DecisionStore = Depends(get_store)) -> HTMLResponse:
    """Approve one package and render the steps to send it in the ESPN app.

    A record holds a single `human_response`, but the agent proposes several
    packages, so which one you picked is recorded in `modified_recommendation`.
    That is a faithful use of the field — "of what was offered, this is the one
    I am acting on" — and it keeps the choice available for the end-of-season
    review, which is the point of the log.
    """
    record = load_decision(store, decision_id)
    package = _package_at(record, index)

    store.record_human_response(
        record.id, HumanResponse.APPROVED,
        modified_recommendation={"approved_package_index": index,
                                 "trades": [package]},
    )

    plan = TradeProposalExecutor().plan(package)
    return request.app.state.templates.TemplateResponse(
        request, "partials/trade_send_steps.html",
        {"plan": context.trade_send_plan_view(plan),
         "package_index": index, "decision_id": decision_id},
    )


@router.post("/trades/{decision_id}/reject", response_class=HTMLResponse)
def reject(decision_id: str, request: Request,
           override_reason: str = Form(default=""),
           adapter: ESPNAdapter = Depends(get_adapter),
           settings: WebSettings = Depends(get_settings),
           cache: ReadCache = Depends(get_reads),
           store: DecisionStore = Depends(get_store)) -> HTMLResponse:
    """Reject every proposal, with a reason.

    The reason is required for the same purpose it is on the lineup gate: the
    trade log already shows entries like "no one would accept this trade", and
    that is the most useful thing in the file at season's end. It also feeds the
    agent directly — `_prior_proposals_block` reads back rejected proposals and
    forbids re-proposing them.
    """
    record = load_decision(store, decision_id)
    reason = override_reason.strip()
    view = _decision_context(record, adapter, settings, cache)

    if not reason:
        view["error"] = ("Say why you're rejecting — the agent reads these back "
                         "and won't re-propose what you turned down.")
        return request.app.state.templates.TemplateResponse(
            request, "partials/trade_decision.html", {"t": view}, status_code=422)

    store.record_human_response(record.id, HumanResponse.REJECTED,
                                override_reason=reason)
    record.human_response = HumanResponse.REJECTED
    record.override_reason = reason
    return request.app.state.templates.TemplateResponse(
        request, "partials/trade_decision.html",
        {"t": _decision_context(record, adapter, settings, cache)},
    )
