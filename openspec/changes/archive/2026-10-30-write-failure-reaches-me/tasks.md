# Tasks — write-failure-reaches-me

## 1. Handling an exhausted write

- [x] 1.1 Write `WFAIL-01`, `WFAIL-02`, `WFAIL-05`, `WFAIL-06`, `WFAIL-07` (unit) in `tests/execute/test_write_failure.py` — real store in tmp, fake adapter with raw slots, recording notifier, injected clock; clause-annotate (AC-1, AC-3, AC-4, AC-7)
- [x] 1.2 Add `MacNotifier.send(body, subtitle)` with AppleScript escaping; make `notify` use it
- [x] 1.3 Create `execute/failure.py` — `report_failed_write`

## 2. Both surfaces

- [x] 2.1 Write `WFAIL-03` and `WFAIL-04` (integration) in `tests/web/test_execute.py` — recording notifier on `app.state`; clause-annotate (AC-2, AC-5, AC-6, AC-8)
- [x] 2.2 Add `app.state.notifier` / `get_notifier`; call `report_failed_write` after a failed live write in `approve.execute` and in `cli._execute_approved_lineup`

## 3. Verification

- [x] 3.1 Run `uv run pytest`
- [x] 3.2 Run `node scripts/trace.mjs check --phase delivery --change write-failure-reaches-me`
