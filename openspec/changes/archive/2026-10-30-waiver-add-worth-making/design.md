# Design — S-003 (waiver-add-worth-making)

## Build approach

**No prototype exists.** No prototype mode to record.
**No design system registered.** Component choices are assumptions per `ux.md`.

### Where the code goes

| What | File | Pattern |
| --- | --- | --- |
| Waiver agent (gather → signal check → scoring → brief) | `src/fantasy_gm/agent/waiver_agent.py` | A linear function pipeline, not a LangGraph tool loop — one model call, so it follows the single-shot sub-agents (`agent/subagents/`), built through `default_llm()` |
| Scan inputs from the platform | `waiver_agent.gather_scan_inputs()` | Reads roster, free agents and rest-of-season projections through the adapter, from the same projections read the lineup agent uses |
| ESPN cache key includes the filter header; fresh free-agent read; rest-of-season projections | `src/fantasy_gm/adapters/espn.py` — `cache_key()`, `PROJECTIONS_FILTER_HEADERS`, `get_free_agents(fresh=)`, `get_ros_projections()` | Free agents and projections share view and week params; a params-only key served one's payload as the other's. `fresh=` mirrors `get_roster(fresh=)` |
| Page + API routes (`/waiver`, `/api/waiver/*`) | `src/fantasy_gm/web/routes/waiver.py` | Matches `routes/approve.py` — plain `def` page handlers, `Form` POST handlers |
| Main page template | `src/fantasy_gm/web/templates/waiver.html` | Matches `history.html` layout and `base.html` include |
| htmx polling partial (scan status) | `src/fantasy_gm/web/templates/partials/waiver_status.html` | Matches `partials/nudge_banner.html` — empty div when inactive, content when active |
| View builder | `src/fantasy_gm/web/context.py` — add `waiver_view()` | Matches existing `decision_summary()` shape |
| WaiverScanResult model | `src/fantasy_gm/models.py` — add model | Alongside existing `WaiverConstraintResult`; carries the figures scoring worked from so the brief can be traced |
| Router registration | `src/fantasy_gm/web/app.py` | Add `from fantasy_gm.web.routes import waiver` and `app.include_router(waiver.router)` |

### Domain — invariant enforcement and transaction boundary

All invariants are enforced inside `waiver_agent.py` before anything is written:
- Signal freshness (I-01, I-02): first node; halts run if any signal lacks a source, carries a future timestamp, is older than its source's threshold, or comes from a source with no threshold (it cannot be shown to be fresh). The as-of timestamp itself is required by the `Signal` model, so a signal without one is rejected where it is built
- Three bars (I-06, I-28, I-30) and all-or-nothing rule (I-29): scoring node; candidacy returns explicit pass/fail per bar
- Closest-miss calculation (I-17): scoring node output for no-candidate case
- Brief traceability (I-26): brief-validator node rejects any number not in the analysis output — the result's figures plus the week and season, compared by value so `12.50` traces to `12.5`; digits inside labels (`WR3`) must trace too. A rejected brief is logged as `brief_rejected`, then the run fails; the page shows no candidate

One `store.save()` call writes the `DecisionRecord` (type `WAIVER`) before the agent reports completion or raises — recommendation, no-add, stale, provenance failure and brief rejection alike (I-19). No multi-aggregate transaction. A failed brief call (provider down) leaves the recommendation standing with no brief and the error on the record.

LLM budget (NFR-04): every model call goes through a counter capped at `AgentConfig.max_llm_calls`; with no budget left the brief is skipped rather than overspent. Calls made are recorded on the decision.

### Where the scan's numbers come from

ESPN's projections read (the one the lineup agent uses) carries a rest-of-season projection per player alongside the weekly one. Its per-game average is the value: per game, so a bye or a short absence does not lower it — the bars compare against a fully available roster (I-30).

| Input | Built as |
| --- | --- |
| Value (relative bar) | Rest-of-season projected points per game (`ESPNAdapter.get_ros_projections`) |
| Tier rank (absolute bar) | Rank by that value among every projected player at the position, league-wide |
| Startable (startability) | Beats my N-th best at the position on a fully available roster, N = my starting slots there. A per-game rate does not change week to week, so starting now stands for starting within three weeks. FLEX slots are not counted |
| Start gap | Points per game short of that N-th best — the amount reported when startability is the failed bar |
| Baseline roster | Every rostered player, injured or on bye, at their rest-of-season rate; a player ESPN has no projection for counts as 0.0 |
| Closest miss | Most bars cleared, then the latest failing bar, then the smallest gap on it — points and rank spots are never compared with each other |
| Week | The league's current week, derived like every other page (`reads.current_week`) |
| Signals | `roster` and `free_agents` read fresh (stamped at read time); `projections` stamped with ESPN's cache time |

### UI approach

No design system. All component choices below are assumptions.

| UX element | Build as | Import / location |
| --- | --- | --- |
| Loading spinner | `<div class="spinner">` + CSS | New CSS rule in `static/app.css`; NEW COMPONENT |
| Empty / no-scan state | Inline `<p>` + `<form>` | Inline in `waiver.html`; no library match |
| Recommendation block | `<article class="waiver-rec">` | NEW COMPONENT; hairline-ruled like the tables — the stylesheet's house rule is no cards |
| Collapsible brief | `<details><summary>` | Native HTML; no JS or htmx needed |
| "Intend to claim" / "Pass" | `<button type="submit">` in `<form>` | Same form, different `name="action"` value; matches `approve.py` pattern |
| Stale signal / brief rejected banner | `<div class="banner banner--warn">` | NEW COMPONENT; add `--warn` variant alongside existing `.banner` in CSS |
| Scan status polling | `hx-get="/api/waiver/status" hx-trigger="every 5s" hx-swap="outerHTML"` on `#waiver-status` | Matches `nudge_banner.html`; every action targets `#waiver-status`, which each response replaces whole |

Style rules: inherit spacing and colour from the existing `static/app.css`; no new tokens introduced.

### Risks

| Risk | Mitigation |
| --- | --- |
| LLM call budget (NFR-04) exceeded | Only brief generation calls the model; the validator is deterministic Python. Calls pass through a capped counter |
| Stale signal writes a `DecisionRecord` before halting — two records if re-run | Re-run on a week with an existing stale record creates a second row; this is correct ledger behaviour but DQ-1 in `ux.md` needs resolving before implementing the Already-decided gate |

---

## Test approach

**Prototype validation:** no prototype exists; section omitted.

### Scenario coverage

| Scenario | AC | Level | File | Test name |
| --- | --- | --- | --- | --- |
| WADD-01 | AC-1, AC-2, AC-3, AC-4, AC-5 | integration | `tests/waiver/test_agent.py` | `WADD-01: candidate clearing all bars produces recommendation` |
| WADD-02 | AC-2, AC-3, AC-4, AC-5 | unit | `tests/waiver/test_scoring.py` | `WADD-02: candidate clearing fewer than all bars is not recommended` |
| WADD-04 | AC-6 | integration | `tests/waiver/test_agent.py` | `WADD-04: no-candidate output names closest miss and which bar failed` |
| WADD-05 | AC-8 | integration | `tests/waiver/test_agent.py` | `WADD-05: signal missing provenance halts run before scoring` |
| WADD-06 | AC-9 | integration | `tests/waiver/test_agent.py` | `WADD-06: stale signal halts run and writes decision record` |
| WADD-07 | AC-10 | integration | `tests/waiver/test_agent.py` | `WADD-07: recommendation record written to SQLite before run reports completion` |
| WADD-08 | AC-11 | integration | `tests/waiver/test_agent.py` | `WADD-08: no-add record written with same weight as recommendation` |
| WADD-09 | AC-7 | integration | `tests/waiver/test_agent.py` | `WADD-09: brief with untraced number is rejected before presentation` |
| WADD-10 | AC-12 | integration | `tests/waiver/test_agent.py` | `WADD-10: waiver scan uses at most 3 LLM calls` |

Every AC from `intent.md` appears in at least one row. No `waived` rows.

### NFR measurement

| NFR | How measured | Where |
| --- | --- | --- |
| NFR-04 (≤3 LLM calls) | A fake chat model counts `.invoke` calls on the production path (scan started from the page); the record's `llm_calls` must match. A zero budget must make no call | `WADD-10` in `test_agent.py` and `test_waiver_page.py` |
| NFR-07 (before Tuesday deadline) | Not enforced in code this slice; trigger is on-demand. Scheduling is a follow-on | — |
| NFR-10 (SQLite before completion) | The record is readable when the run returns, and a run whose write fails raises instead of returning | `WADD-07`, `WADD-08` |

### Not covered by automated tests

| What | Why |
| --- | --- |
| Browser rendering of all six states on `/waiver` | No browser test harness; manual walkthrough required after implementation |
| htmx polling swap correctness | Requires a browser; covered by the manual walkthrough. The worker path from the scan button to the ledger is covered by `tests/web/test_waiver_page.py` |
