# Tasks — waiver-claim-filed

## 1. Player ids through the scan

- [x] 1.1 Add `candidate_id` and `displaced_id` to `WaiverScanResult` in `models.py`; carry `player_id` through `gather_scan_inputs` and `score_candidates` in `agent/waiver_agent.py`; extend the existing waiver tests to assert the ids land on a recommendation

## 2. The claim executor

- [x] 2.1 Write `WADD-11: filing builds one transaction with the add and the drop` (unit) in `tests/execute/test_waiver_api.py` — assert one transaction, type `WAIVER`, my team, one ADD and one DROP item with the right team ids; clause-annotate each THEN/AND (AC-1)
- [x] 2.2 Add `get_pending_waiver_claims(season)` and `get_waiver_rank(team_id, season)` to `adapters/espn.py`, both cache-bypassed
- [x] 2.3 Create `execute/waiver_api.py` — `build_espn_waiver_claim`, `WaiverClaimPlan`, `WaiverFilingResult` (three-state `confirmed`), `ESPNWaiverApiExecutor.plan / check_still_legal / execute / _confirm_filed`, following `execute/trade_api.py`

## 3. Filing from the page

- [x] 3.1 Write `WADD-12`, `WADD-13`, `WADD-19` (integration) in `tests/web/test_waiver_filing.py` — real executor, fake adapter, `httpx.post` patched to fail on any call for the dry-run and refusal cases; clause-annotate (AC-2, AC-9)
- [x] 3.2 Write `WADD-14: a roster that changed since the scan refuses the filing` (integration) — drop gone and add gone, each; assert 409, the player named, no POST; clause-annotate (AC-3)
- [x] 3.3 Write `WADD-15`, `WADD-16`, `WADD-17` (integration) — POST patched to 200 / 200 / 500; read-back with the matching pending claim, with only a stale different claim, and unused; assert page text, form presence, and `outcome["filing"]` (transaction, state, priority) read from the store; clause-annotate (AC-4–AC-7)
- [x] 3.4 Write `WADD-18: a decision already filed live cannot be filed again` (integration) — assert 409, no POST, recorded filing unchanged; clause-annotate (AC-8)
- [x] 3.5 Add `get_waiver_executor` to `web/deps.py` and build `app.state.waiver_executor` in `web/app.py`
- [x] 3.6 Add `POST /api/waiver/file` to `web/routes/waiver.py` in the order the design states; record the live attempt with `store.record_outcome` before rendering; `backup_if_dirty` after
- [x] 3.7 Extend `waiver_view` in `web/context.py` and `partials/waiver_status.html` with the ux states: ready to file, dry run, confirmed, not confirmed, not filed, refused; File claim button disabled while in flight (`hx-disabled-elt="find button"` on the form)

## 4. Verification

- [x] 4.1 Run `uv run pytest`
- [x] 4.2 Run `node scripts/trace.mjs check --phase delivery --change waiver-claim-filed` and resolve every finding
