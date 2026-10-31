"""Waiver decision page and API routes.

GET  /waiver              — main page (all six states)
POST /api/waiver/scan     — trigger a waiver scan run
GET  /api/waiver/status   — htmx polling partial (every 5 s)
POST /api/waiver/decide   — record APPROVED or DECLINED, redirect to /waiver
POST /api/waiver/file     — file the approved claim with ESPN (dry run unless LIVE)
POST /api/waiver/result   — read back whether a filed claim cleared or lost
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from fantasy_gm.db.store import DecisionStore
from fantasy_gm.models import DecisionType, HumanResponse
from fantasy_gm.web import context, reads
from fantasy_gm.web.deps import get_reads, get_settings, get_store, get_waiver_executor
from fantasy_gm.web.runs import RunManager
from fantasy_gm.web.settings import WebSettings

router = APIRouter()


def _get_runs(request: Request) -> RunManager:
    return request.app.state.runs


def _filed_this_week(store: DecisionStore, week: int, season: int) -> bool:
    """Whether any waiver decision this week has a filing that may have reached ESPN."""
    return any(
        ((r.outcome or {}).get("filing") or {}).get("state") in ("sending", "confirmed", "unconfirmed")
        for r in store.list_week(week, season) if r.decision_type == DecisionType.WAIVER
    )


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
        "earlier_claims": [context.claim_check_view(r)
                           for r in _earlier_unresolved(store, season, week)],
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
    if _filed_this_week(store, week, season):
        # A new scan would put a newer decision in front of the filed claim.
        return _status_partial(request, week, season, settings, store,
                               notice={"kind": "refused", "message":
                                       "This week's claim is already filed — a new scan "
                                       "would hide it, so none was started."},
                               status_code=409)

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


@router.post("/api/waiver/file", response_class=HTMLResponse)
def file_claim(request: Request,
               confirm: str = Form(default=""),
               settings: WebSettings = Depends(get_settings),
               store: DecisionStore = Depends(get_store),
               executor=Depends(get_waiver_executor)) -> HTMLResponse:
    """File the approved claim with ESPN. Dry run unless `confirm` is exactly LIVE.

    Everything about the claim — which decision, which players — comes from the
    decision log, never from the request (NFR-11). A live attempt is recorded
    before the page reports it (NFR-10), and a claim that reached ESPN is never
    filed twice.
    """
    from datetime import datetime, timezone

    from fantasy_gm.execute.gate import authorise

    week = _week(request, settings)
    season = settings.season
    record = _current_waiver_record(store, week, season)

    def refuse(message: str) -> HTMLResponse:
        return _status_partial(request, week, season, settings, store,
                               notice={"kind": "refused", "message": message},
                               status_code=409)

    if record is None:
        return refuse("There is no waiver decision to file this week — nothing was sent.")
    # Week-wide: a re-run scan makes a newer decision with no filing on it, and
    # must not reopen a claim that already reached ESPN. "sending" is written
    # before the POST, so a crash mid-send or a second tab is blocked too.
    if _filed_this_week(store, week, season):
        return refuse("This week's claim was already filed — nothing was sent.")
    auth = authorise(record, confirm)
    if auth.refused:
        return refuse(auth.message)
    rec = record.recommendation or {}
    if not (rec.get("candidate_id") and rec.get("displaced_id")):
        return refuse("This scan has no player ids to file — nothing was sent. "
                      "File it in the ESPN app.")

    plan = executor.plan(rec["candidate_id"], rec.get("candidate") or rec["candidate_id"],
                         rec["displaced_id"], rec.get("displaced_player") or rec["displaced_id"],
                         settings.team_id, week, season)
    if not auth.live:
        result = executor.execute(plan, live=False)
        return _status_partial(request, week, season, settings, store,
                               notice={"kind": "dry_run", "message": result.message})

    try:
        problem = executor.check_still_legal(plan)
    except Exception as exc:
        return refuse(f"Couldn't read the league to re-check the claim ({type(exc).__name__}) "
                      f"— nothing was sent. Try again in a moment.")
    if problem:
        return _status_partial(request, week, season, settings, store,
                               notice={"kind": "roster_changed", "message": problem},
                               status_code=409)
    try:
        rank, team_count = executor.adapter.get_waiver_rank(settings.team_id, season)
    except Exception:
        rank, team_count = None, None  # recorded as unknown, never guessed

    def log(state: str, **extra) -> None:
        current = store.get(record.id).outcome or {}
        attempt = {
            "state": state,
            "transaction": plan.request_payload,
            "waiver_rank": rank,
            "team_count": team_count,
            "at": datetime.now(tz=timezone.utc).isoformat(),
            **extra,
        }
        attempts = [a for a in current.get("attempts", []) if a.get("state") != "sending"]
        store.record_outcome(record.id, {**current, "filing": attempt,
                                         "attempts": attempts + [attempt]})

    log("sending")  # before the POST: nothing reaches ESPN unrecorded
    result = executor.execute(plan, live=True)
    state = ("confirmed" if result.confirmed
             else "unconfirmed" if result.confirmed is False
             else "failed")
    log(state, message=result.message, error=result.error)
    store.backup_if_dirty()
    return _status_partial(request, week, season, settings, store)


@router.post("/api/waiver/result", response_class=HTMLResponse)
def check_result(request: Request,
                 decision_id: str = Form(default=""),
                 settings: WebSettings = Depends(get_settings),
                 store: DecisionStore = Depends(get_store),
                 executor=Depends(get_waiver_executor)) -> HTMLResponse:
    """Read a filed claim's fate back from the league and record it (I-23).

    With no `decision_id`, the claim filed this week; with one, an earlier
    week's claim listed on the page. Either way the league is read for the
    week the claim was filed in, and a result is recorded once and never read
    again. Still pending, or not found, records nothing.
    """
    week = _week(request, settings)
    season = settings.season

    if decision_id:
        record = _earlier_filed(store, decision_id, season)
        if record is None:
            raise HTTPException(status_code=404, detail="No such filed claim")
        notice = _resolve(record, executor, settings, store)
        return request.app.state.templates.TemplateResponse(
            request, "partials/claim_check.html",
            {"c": context.claim_check_view(store.get(record.id)), "notice": notice},
            status_code=409 if notice and notice["kind"] == "refused" else 200,
        )

    record = _filed_record(store, week, season)
    if record is None:
        return _status_partial(request, week, season, settings, store,
                               notice={"kind": "refused", "message":
                                       "No claim was filed this week, so there is no result to check."},
                               status_code=409)
    notice = _resolve(record, executor, settings, store)
    return _status_partial(request, week, season, settings, store, notice=notice,
                           status_code=409 if notice and notice["kind"] == "refused" else 200)


def _resolve(record, executor, settings: WebSettings, store: DecisionStore) -> dict | None:
    """Record a filed claim's result if the league shows one. Returns a notice, or None."""
    from datetime import datetime, timezone

    from fantasy_gm.execute.waiver_api import resolve_claim

    outcome = record.outcome or {}
    if outcome.get("result"):
        return None  # recorded once; never read again
    filing = outcome["filing"]
    claim_week = (filing.get("transaction") or {}).get("scoringPeriodId") or record.week
    try:
        transactions = executor.adapter.get_waiver_transactions(record.season, claim_week)
    except Exception:
        return {"kind": "refused", "message": "Couldn't read the league — try again in a moment."}
    found = resolve_claim(transactions, filing, settings.team_id, claim_week)
    if found is None:
        return {"kind": "pending", "message": "ESPN hasn't processed the claim yet — check "
                                              "again after the waiver window runs."}

    winner_name = None
    if found.winner_team_id:
        try:
            names = {s.team_id: s.team_name for s in executor.adapter.get_standings(record.season)}
            winner_name = names.get(found.winner_team_id)
        except Exception:
            pass
    store.record_outcome(record.id, {**outcome, "result": {
        "state": found.state,
        "reason": found.reason,
        "winner_team_id": found.winner_team_id,
        "winner_name": winner_name or (f"Team {found.winner_team_id}"
                                       if found.winner_team_id else None),
        "waiver_rank": filing.get("waiver_rank"),
        "team_count": filing.get("team_count"),
        "recorded_at": datetime.now(tz=timezone.utc).isoformat(),
    }})
    store.backup_if_dirty()
    return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_unresolved_filing(r) -> bool:
    outcome = r.outcome or {}
    return (r.decision_type == DecisionType.WAIVER
            and (outcome.get("filing") or {}).get("state") in ("confirmed", "unconfirmed")
            and not outcome.get("result"))


def _earlier_unresolved(store: DecisionStore, season: int, week: int) -> list:
    """Filed claims from earlier weeks still waiting on a result, oldest first."""
    return sorted((r for r in store.list_recent(limit=500)
                   if r.season == season and r.week < week and _is_unresolved_filing(r)),
                  key=lambda r: r.week)


def _earlier_filed(store: DecisionStore, decision_id: str, season: int):
    from uuid import UUID
    try:
        record = store.get(UUID(decision_id))
    except ValueError:
        return None
    if record is None or record.season != season:
        return None
    filing = ((record.outcome or {}).get("filing") or {})
    if record.decision_type != DecisionType.WAIVER or filing.get("state") not in ("confirmed", "unconfirmed"):
        return None
    return record


def _filed_record(store: DecisionStore, week: int, season: int):
    """The waiver decision this week whose claim reached ESPN, newest first."""
    for r in reversed(store.list_week(week, season)):
        state = ((r.outcome or {}).get("filing") or {}).get("state")
        if r.decision_type == DecisionType.WAIVER and state in ("confirmed", "unconfirmed"):
            return r
    return None


def _status_partial(request: Request, week: int, season: int,
                    settings: WebSettings, store: DecisionStore,
                    notice: dict | None = None, status_code: int = 200) -> HTMLResponse:
    record = _current_waiver_record(store, week, season)
    active_run = request.app.state.runs.get_active("waiver", week, season)
    return request.app.state.templates.TemplateResponse(
        request, "partials/waiver_status.html", {
            "waiver": context.waiver_view(record, active_run),
            "notice": notice,
        },
        status_code=status_code,
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
