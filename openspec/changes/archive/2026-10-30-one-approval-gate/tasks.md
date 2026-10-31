# Tasks — one-approval-gate

## 1. The gate

- [x] 1.1 Write `APPGATE-01: approved decision confirmed with LIVE writes`, `APPGATE-02: overridden decision with a reason confirmed with LIVE writes` and `APPGATE-03: anything but exactly LIVE is a dry run` (unit) in `tests/execute/test_gate.py` — records saved to a temporary decision log and given their response through the store; annotate each THEN/AND clause with `# APPGATE-NN THEN …` above the assertion that proves it (AC-1, AC-3)
- [x] 1.2 Write `APPGATE-04: pending, rejected or declined decision is refused` and `APPGATE-05: override without a written reason is refused` (unit) in `tests/execute/test_gate.py` — assert the verdict, the refusal code and that the message names the state or the missing reason; clause-annotate (AC-2, AC-4)
- [x] 1.3 Write `APPGATE-09: no code outside the gate compares against LIVE` (unit) in `tests/execute/test_gate.py` — scan `src/fantasy_gm/**/*.py` for a comparison against the string `LIVE` and assert the only file is `execute/gate.py`; clause-annotate (AC-6)
- [x] 1.4 Create `src/fantasy_gm/execute/gate.py` — `Verdict` (live / dry_run / refused), frozen `Authorisation` (verdict, code, message, `.live`, `.refused`), and `authorise(record, confirmation)`: state first (I-11, I-09), then the exact, untrimmed comparison against `LIVE` (I-24); no module state

## 2. Web caller

- [x] 2.1 Write `APPGATE-07: web write step refuses an unapproved decision` (integration) in `tests/web/test_execute.py` — a pending decision, `confirm=LIVE` plus forged fields (`approved=1`, `human_response=approved`); assert 409, the executor's call list is empty, and the stored decision still has no response; clause-annotate (AC-2, AC-7)
- [x] 2.2 Write `APPGATE-06: a live execution does not authorise the next one` (integration) in `tests/web/test_execute.py` — execute an approved decision with `LIVE`, then with an empty confirmation; assert the executor saw `[True, False]` and the stored decision is unchanged; clause-annotate (AC-5)
- [x] 2.3 Change `execute()` in `web/routes/approve.py` to call `authorise(record, confirm)` on the record loaded from the store; on refusal return the execution result partial with status 409 and do not call the executor; otherwise pass `live=auth.live`
- [x] 2.5 Write `APPGATE-10: web write step refuses an approved decision that is not a lineup` (integration) in `tests/web/test_execute.py` and refuse such decisions in `execute()`; let htmx swap 409 and 422 responses via `htmx-config` in `base.html` (AC-7)
- [x] 2.4 Add the refused branch to `partials/execution_result.html` — "Nothing was sent" with the refusal message; no execute form

## 3. Command-line callers

- [x] 3.1 Write `APPGATE-08: both surfaces give the same verdict` (integration) in `tests/web/test_gate_parity.py` — for every decision state × confirmation in the spec's matrix, drive `_execute_approved_lineup` with `input` patched and the web write step through the test client, each against a recording executor; assert both reached the same verdict (live, dry run, or no executor call); clause-annotate (AC-6, AC-8)
- [x] 3.2 Change `_execute_approved_lineup` and `_send_approved_trade` in `memo/cli.py` to pass the raw `input()` text to `authorise`; on refusal print the message and return without calling the executor; otherwise pass `live=auth.live`

## 4. Verification

- [x] 4.1 Run `uv run pytest` — the gate, web, command-line and existing execute tests pass
- [x] 4.2 Run `node scripts/trace.mjs check --phase delivery --change one-approval-gate` and resolve every finding
