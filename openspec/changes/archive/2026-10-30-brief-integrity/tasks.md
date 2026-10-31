# Tasks — brief-integrity

## 1. The check

- [x] 1.1 Write `BRIEF-04` (unit) in `tests/memo/test_integrity.py`, plus rounding and token cases; clause-annotate (AC-6)
- [x] 1.2 Create `memo/integrity.py`

## 2. Applying it

- [x] 2.1 Write `BRIEF-01`, `BRIEF-02`, `BRIEF-03` (integration) in `tests/agent/test_brief_integrity.py` — build records from fake terminal messages and a prepared `call_log`; clause-annotate (AC-1–AC-5)
- [x] 2.2 Screen the lineup brief in `agent/graph.py` and the trade texts in `agent/trade/graph.py`

## 3. Verification

- [x] 3.1 Run `uv run pytest`
- [x] 3.2 Run `node scripts/trace.mjs check --phase delivery --change brief-integrity`
