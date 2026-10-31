# Tasks — signals-declare-staleness

## 1. Freshness

- [x] 1.1 Write `SIGSTALE-01`–`03` (unit) in `tests/signals/test_freshness.py`; clause-annotate (AC-1–AC-3, AC-5)
- [x] 1.2 Create `signals/freshness.py`

## 2. Abstaining

- [x] 2.1 Write `SIGSTALE-04`, `SIGSTALE-05` (integration) in `tests/agent/test_stale_abstain.py` — a stub context with a prepared bundle; assert whether the LLM builder is reached; clause-annotate (AC-4, AC-6)
- [x] 2.2 Add `precheck` to `GraphAgent.decide` and implement it on `LineupGraphAgent`
- [x] 2.3 Write `SIGSTALE-06` (integration) in `tests/web/test_stale_abstention_page.py`; clause-annotate (AC-7)

## 3. Verification

- [x] 3.1 Run `uv run pytest`
- [x] 3.2 Run `node scripts/trace.mjs check --phase delivery --change signals-declare-staleness`
