"""The two gates.

Gate 1 records what you decided. Gate 2 sends it. They are separate requests on
purpose — the same separation `memo/cli.py` enforces at the prompt — because the
second one is an irreversible outward-facing write.

The plan is always recomputed server-side from the stored record. The client
never supplies moves or a payload; it supplies only a decision id and, at gate 2,
a confirmation string.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse

from fantasy_gm.adapters.espn import ESPNAdapter
from fantasy_gm.db.store import DecisionStore
from fantasy_gm.execute.base import Executor
from fantasy_gm.models import HumanResponse
from fantasy_gm.web import context, reads
from fantasy_gm.web.deps import (
    ReadCache,
    get_adapter,
    get_executor,
    get_reads,
    get_settings,
    get_store,
)
from fantasy_gm.web.routes.pages import load_decision
from fantasy_gm.web.settings import WebSettings

router = APIRouter(prefix="/decisions")


def _decision_context(record, adapter, settings, cache) -> dict:
    roster = projections = None
    try:
        roster = reads.roster(adapter, cache, settings.team_id, record.week, record.season)
        projections = reads.projections(adapter, cache, record.week, record.season)
    except Exception:
        pass
    return context.decision_view(record, roster, projections)


def _render_gate(request: Request, record, adapter, settings, cache,
                 error: str | None = None, status_code: int = 200) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(
        request, "partials/gate.html",
        {"d": _decision_context(record, adapter, settings, cache), "error": error},
        status_code=status_code,
    )


def _effective_starters(record) -> list[str]:
    rec = record.modified_recommendation or record.recommendation or {}
    return list(rec.get("starter_player_ids") or [])


def _build_plan(executor: Executor, record, team_id: str):
    return executor.plan_set_lineup(team_id, record.week, record.season,
                                    _effective_starters(record))


def _render_plan(request: Request, plan, executor: Executor,
                 decision_id: str, status_code: int = 200) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(
        request, "partials/plan.html",
        {"plan": context.plan_view(plan), "executor_name": executor.name,
         "decision_id": decision_id},
        status_code=status_code,
    )


@router.post("/{decision_id}/respond", response_class=HTMLResponse)
def respond(decision_id: str, request: Request,
            action: str = Form(...),
            override_reason: str = Form(default=""),
            starter_player_ids: list[str] = Form(default=[]),
            adapter: ESPNAdapter = Depends(get_adapter),
            settings: WebSettings = Depends(get_settings),
            cache: ReadCache = Depends(get_reads),
            store: DecisionStore = Depends(get_store),
            executor: Executor = Depends(get_executor)) -> HTMLResponse:
    record = load_decision(store, decision_id)
    reason = override_reason.strip()

    if action == "reject":
        if not reason:
            return _render_gate(request, record, adapter, settings, cache,
                                error="Say why you're rejecting — that reason is "
                                      "the point of the log.",
                                status_code=422)
        store.record_human_response(record.id, HumanResponse.REJECTED,
                                    override_reason=reason)
        record.human_response = HumanResponse.REJECTED
        record.override_reason = reason
        return _render_gate(request, record, adapter, settings, cache)

    if action == "modify":
        if not starter_player_ids:
            return _render_gate(request, record, adapter, settings, cache,
                                error="Tick the starters you want before saving.",
                                status_code=422)
        if not reason:
            return _render_gate(request, record, adapter, settings, cache,
                                error="Say why you're overriding — that reason is "
                                      "the point of the log.",
                                status_code=422)
        # Exactly the shape memo/cli.py records: the agent's recommendation with
        # the starter list replaced, so nothing else about it is lost.
        modified = {**(record.recommendation or {}),
                    "starter_player_ids": list(starter_player_ids)}
        store.record_human_response(record.id, HumanResponse.MODIFIED,
                                    override_reason=reason,
                                    modified_recommendation=modified)
        record.human_response = HumanResponse.MODIFIED
        record.override_reason = reason
        record.modified_recommendation = modified
        return _render_gate(request, record, adapter, settings, cache)

    if action != "approve":
        return _render_gate(request, record, adapter, settings, cache,
                            error="Unknown action.", status_code=422)

    # Approve. If the ticked starters differ from the agent's, this is a
    # modification and is logged as one — silently approving a changed lineup
    # would corrupt the agreement record.
    agent_starters = list((record.recommendation or {}).get("starter_player_ids") or [])
    if starter_player_ids and sorted(starter_player_ids) != sorted(agent_starters):
        modified = {**(record.recommendation or {}),
                    "starter_player_ids": list(starter_player_ids)}
        if not reason:
            return _render_gate(request, record, adapter, settings, cache,
                                error="These starters differ from the agent's. Say why "
                                      "before approving.", status_code=422)
        store.record_human_response(record.id, HumanResponse.MODIFIED,
                                    override_reason=reason,
                                    modified_recommendation=modified)
        record.human_response = HumanResponse.MODIFIED
        record.override_reason = reason
        record.modified_recommendation = modified
    else:
        store.record_human_response(record.id, HumanResponse.APPROVED,
                                    override_reason=reason or None)
        record.human_response = HumanResponse.APPROVED

    plan = _build_plan(executor, record, settings.team_id)
    return _render_plan(request, plan, executor, decision_id)


@router.post("/{decision_id}/plan", response_class=HTMLResponse)
def plan_only(decision_id: str, request: Request,
              settings: WebSettings = Depends(get_settings),
              store: DecisionStore = Depends(get_store),
              executor: Executor = Depends(get_executor)) -> HTMLResponse:
    """Re-plan an already-approved decision. Pure — computes, writes nothing."""
    record = load_decision(store, decision_id)
    plan = _build_plan(executor, record, settings.team_id)
    return _render_plan(request, plan, executor, decision_id)
