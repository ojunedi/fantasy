# Tasks — unread-recommendation-surfaced

## 1. Recording a miss

- [x] 1.1 Write `LMISS-01`…`LMISS-07` (unit) in `tests/nudge/test_missed.py` — real `DecisionStore` in tmp, fake adapter (roster per week, actual scores), injected clock; clause-annotate every THEN/AND (AC-1–AC-8)
- [x] 1.2 Create `nudge/missed.py` — `kickoff_for`, `missed_cost`, `record_missed_lineups`, and a `main()` CLI entry

## 2. Showing it

- [x] 2.1 Write `LMISS-08: history shows missed with the projected cost` (integration) in `tests/web/test_history_missed.py`; clause-annotate (AC-9)
- [x] 2.2 Call `record_missed_lineups` from the `/history` route (errors never block the page); add `missed` to `decision_summary`; show the tag and cost in `partials/history.html`

## 3. Verification

- [x] 3.1 Run `uv run pytest`
- [x] 3.2 Run `node scripts/trace.mjs check --phase delivery --change unread-recommendation-surfaced`
