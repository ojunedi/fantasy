# Tasks — S-003 (waiver-add-worth-making)

## 1. Models

- [x] 1.1 Add `WaiverScanResult` model to `src/fantasy_gm/models.py` — fields: `candidate`, `displaced_player`, `value_margin`, `bars_cleared` (list), `closest_miss`, `failed_bar`, `failed_by`, `scan_state` (enum: recommendation / no_candidate / stale / provenance_error) (AC-1, AC-6)
- [x] 1.2 Add `HumanResponse.DECLINED` to the `HumanResponse` enum in `src/fantasy_gm/models.py` — distinct from `REJECTED` (which means lineup override); `DECLINED` means the manager chose not to file a waiver claim the agent surfaced; matches the UL term "Declined" in BC-waiver context

## 2. Signal validation tests and implementation

- [x] 2.1 Write `WADD-05: signal missing provenance halts run before scoring` (integration) in `tests/waiver/test_agent.py`, with unit cases in `tests/waiver/test_signals.py` — assert the scorer is never called; annotate clause by clause: `# WADD-05 THEN the run halts before any candidate is scored`, `# WADD-05 AND no recommendation is produced`, `# WADD-05 AND the error names the signal that failed` (AC-8)
- [x] 2.2 Write `WADD-06: stale signal halts run and writes decision record` (integration) in `tests/waiver/test_agent.py`, with unit cases in `tests/waiver/test_signals.py` — assert the persisted record carries the stale state and failing source; annotate: `# WADD-06 THEN the run reports stale and names the failing source`, `# WADD-06 AND no recommendation is produced`, `# WADD-06 AND the WaiverDecision record is written before the run reports completion` (AC-9, AC-10)
- [x] 2.3 Implement signal-validation node in `src/fantasy_gm/agent/waiver_agent.py` — I-01 (provenance): each signal must carry a source identifier and an `as-of` timestamp; a timestamp in the future fails provenance; I-02 (freshness): compare each signal's `as-of` timestamp against the current wall clock and its source's threshold; a source with no threshold fails as stale; raises named errors `SIGNAL_MISSING_PROVENANCE` and `SIGNAL_STALE`

## 3. Scoring tests and implementation

- [x] 3.1 Write `WADD-02: candidate clearing fewer than all bars is not recommended` (unit) in `tests/waiver/test_scoring.py` — annotate: `# WADD-02 THEN the candidate does not appear as a recommendation` (AC-2, AC-3, AC-4, AC-5)
- [x] 3.2 Implement scoring node in `src/fantasy_gm/agent/waiver_agent.py` — evaluates I-06 (relative bar), I-28 (absolute bar), I-30 (startability); enforces I-29 (all-or-nothing); records closest miss per I-17

## 4. Brief validation tests and implementation

- [x] 4.1 Write `WADD-09: brief with untraced number is rejected before presentation` (integration) in `tests/waiver/test_agent.py`, with unit cases in `tests/waiver/test_brief.py` — annotate: `# WADD-09 THEN the brief is rejected`, `# WADD-09 AND the run fails with a brief-integrity error`, `# WADD-09 AND no recommendation is surfaced` (AC-7)
- [x] 4.2 Implement brief-validator node in `src/fantasy_gm/agent/waiver_agent.py` — asserts every number in the generated brief appears in `WaiverScanResult` or is the week or season, compared by value; raises `BRIEF_INTEGRITY_VIOLATION` on mismatch, after logging the outcome as `brief_rejected`

## 5. Agent integration tests and full agent wiring

- [x] 5.1 Write `WADD-01: candidate clearing all bars produces recommendation` (integration) in `tests/waiver/test_agent.py` — annotate: `# WADD-01 THEN the candidate is included in the recommendation`, and assert candidate name, displaced player, and value margin present (AC-1, AC-2, AC-3, AC-4, AC-5)
- [x] 5.2 Write `WADD-04: no-candidate output names closest miss and which bar failed` (integration) in `tests/waiver/test_agent.py` — annotate: `# WADD-04 THEN the output names the closest candidate`, `# WADD-04 AND which condition it failed`, `# WADD-04 AND by how much`, `# WADD-04 AND no recommendation is produced`, `# WADD-04 AND no error is raised` (AC-6)
- [x] 5.3 Write `WADD-07: recommendation record written to SQLite before run reports completion` (integration) in `tests/waiver/test_agent.py` — annotate: `# WADD-07 THEN the WaiverDecision record is written before the run reports completion`, `# WADD-07 AND the record includes candidate, displaced player, and value margin` (AC-10)
- [x] 5.4 Write `WADD-08: no-add record written with same weight as recommendation` (integration) in `tests/waiver/test_agent.py` — annotate: `# WADD-08 THEN a WaiverDecision record is written before run completes`, `# WADD-08 AND the record includes closest candidate, failed condition, and margin` (AC-11)
- [x] 5.5 Write `WADD-10: waiver scan uses at most 3 LLM calls` (integration) in `tests/waiver/test_agent.py` — a fake chat model counts `.invoke` calls; the record's `llm_calls` must match; a zero budget makes no call; annotate: `# WADD-10 THEN the total LLM calls is ≤ 3` (AC-12)
- [x] 5.6 Wire the pipeline in `src/fantasy_gm/agent/waiver_agent.py` as a linear function — order: signal-validate → score → brief-generate (1 LLM call, through a capped budget counter) → brief-validate → store.save(); expose `run_waiver_scan(...) -> WaiverScanResult`

## 6. Web routes

- [x] 6.1 Verify `RunManager` supports a `"waiver"` job type alongside `"lineup"` — read `web/runs.py`; extend the key scheme to `(type, week, season)` with `"waiver"` as a valid type if it does not already exist; do not create a parallel run registry
- [x] 6.2 Create `src/fantasy_gm/web/routes/waiver.py` — `GET /waiver` page handler; `POST /api/waiver/scan` triggers `RunManager` job (type `"waiver"`); `GET /api/waiver/status` htmx polling partial (returns `partials/waiver_status.html`); `POST /api/waiver/decide` records `HumanResponse.APPROVED` ("Intend to claim") or `HumanResponse.DECLINED` ("Pass") on the open `WaiverDecision` and redirects to `/waiver`
- [x] 6.3 Register `waiver.router` in `src/fantasy_gm/web/app.py` alongside existing routers
- [x] 6.5 Build scan inputs from the adapter in `gather_scan_inputs()` — value, tier rank, startability and start gap from ESPN's rest-of-season per-game projection; every rostered player stays in the baseline at that rate; one stamped signal per read; the worker passes `default_llm()`, scans the league's current week, and backs up the log afterwards
- [x] 6.6 Key the ESPN disk cache on the filter header as well as params (`adapters/espn.py`) so free agents and projections stop sharing a cache entry; add `fresh=` to `get_free_agents`
- [x] 6.8 Write `tests/waiver/test_inputs.py` — a kicker on bye and an injured starter keep their value, so neither opens a starting slot; a recommendation always names who it displaces
- [x] 6.7 Write the page-level scan test in `tests/web/test_waiver_page.py` — scan button → worker → ledger → page, against a fake adapter and fake chat model; covers a recommendation, a rejected brief, the derived current week, and that only an open recommendation takes a claim or pass
- [x] 6.4 Add `waiver_view(record) -> dict` to `src/fantasy_gm/web/context.py` — maps `WaiverScanResult` fields to template variables; mirrors `decision_summary()` shape

## 7. UI — templates

- [x] 7.1 Create `src/fantasy_gm/web/templates/waiver.html` — extends `base.html`; includes `partials/waiver_status.html` for the active scan area; no design system; all six states from `ux.md` present (no scan, running, recommendation, no-candidate, stale, already decided) — not prototyped
- [x] 7.2 Create `src/fantasy_gm/web/templates/partials/waiver_status.html` — htmx polling partial (`hx-get="/api/waiver/status" hx-trigger="every 5s" hx-swap="outerHTML"`); renders loading spinner (NEW COMPONENT: `<div class="spinner">`), recommendation block (NEW COMPONENT: `<article class="waiver-rec">`), stale signal banner (NEW COMPONENT: `<div class="banner banner--warn">`), or empty div; collapsible brief via `<details><summary>`
- [x] 7.3 Add `.spinner`, `.banner--warn` and `.waiver-rec` CSS rules to `src/fantasy_gm/web/static/app.css`

## 8. E2E acceptance signal

- [x] 8.1 Write manual acceptance-signal test stub (skip marker) in `tests/waiver/test_agent.py` — `WADD-AC-SIGNAL: manager receives waiver recommendation and records intent to claim before Tuesday deadline` — annotate: `# AC-SIGNAL THEN manager acts on a waiver recommendation each Tuesday window`; mark `@pytest.mark.skip(reason="AC-SIGNAL is a manual end-to-end test: run waiver scan, confirm recommendation appears on /waiver, record intent to claim, confirm WaiverDecision in decisions.db")`
