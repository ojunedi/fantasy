"""Pre-kickoff nudge status endpoint.

Returns whether a nudge is active and how many minutes remain until kickoff.
Polled by the nudge banner partial every 60 seconds via htmx.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse

from fantasy_gm.db.store import DecisionStore
from fantasy_gm.models import DecisionType
from fantasy_gm.nudge.check import next_sunday_kickoff_utc, _DEFAULT_THRESHOLD
from fantasy_gm.web.deps import get_settings, get_store
from fantasy_gm.web.settings import WebSettings

router = APIRouter(prefix="/api/nudge")


def _nudge_status(store: DecisionStore, settings: WebSettings) -> dict:
    week = settings.week
    if week is None:
        return {"active": False, "minutes_remaining": 0}

    kickoff = next_sunday_kickoff_utc()
    now = datetime.utcnow()

    if now >= kickoff:
        return {"active": False, "minutes_remaining": 0}

    minutes_remaining = (kickoff - now).total_seconds() / 60
    threshold = int(getattr(settings, "nudge_threshold_minutes", _DEFAULT_THRESHOLD))

    if minutes_remaining > threshold:
        return {"active": False, "minutes_remaining": int(minutes_remaining)}

    decisions = store.list_week(week, settings.season)
    unread = any(
        d for d in decisions
        if d.decision_type == DecisionType.LINEUP and d.human_response is None
    )
    return {"active": unread, "minutes_remaining": int(minutes_remaining)}


@router.get("/status")
def nudge_status(
    request: Request,
    store: DecisionStore = Depends(get_store),
    settings: WebSettings = Depends(get_settings),
) -> JSONResponse:
    return JSONResponse(_nudge_status(store, settings))


@router.get("/banner", response_class=HTMLResponse)
def nudge_banner(
    request: Request,
    store: DecisionStore = Depends(get_store),
    settings: WebSettings = Depends(get_settings),
) -> HTMLResponse:
    status = _nudge_status(store, settings)
    return request.app.state.templates.TemplateResponse(
        request, "partials/nudge_banner.html", status
    )
