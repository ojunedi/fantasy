# Tasks — claim-outcome-recorded

## 1. Resolving a claim

- [x] 1.1 Write `WADD-24: any other failure is not a priority loss` and `WADD-26: a cancelled claim is recorded as cancelled` (unit) in `tests/execute/test_claim_result.py`, using ESPN's real status names; clause-annotate (AC-4, AC-5)
- [x] 1.2 Add `get_waiver_transactions(season, week)` to `adapters/espn.py` (cache bypassed, every status, scoped to the claim's week)
- [x] 1.3 Add `ClaimResult` and `resolve_claim(transactions, filing, team_id, week)` to `execute/waiver_api.py`

## 2. Checking from the page

- [x] 2.1 Write `WADD-22`, `WADD-23`, `WADD-25`, `WADD-27`, `WADD-28` (integration) in `tests/web/test_claim_result_page.py` — fake adapter serving transactions in ESPN's shape; assert page text and `outcome["result"]` read from the store; clause-annotate (AC-1–AC-3, AC-5–AC-8)
- [x] 2.2 Add `POST /api/waiver/result` to `web/routes/waiver.py`: refuse if no filing; return the recorded result without reading if one exists; otherwise read, resolve, record, back up, render
- [x] 2.3 Extend `waiver_view` and `partials/waiver_status.html` with Check result and the result states from `ux/claim-result.md`; list earlier weeks' unresolved claims on the page, each with its own Check result; refuse a new scan once this week's claim is filed

## 3. Verification

- [x] 3.1 Run `uv run pytest`
- [x] 3.2 Run `node scripts/trace.mjs check --phase delivery --change claim-outcome-recorded`; only the known false positives for existing WADD ids may remain
