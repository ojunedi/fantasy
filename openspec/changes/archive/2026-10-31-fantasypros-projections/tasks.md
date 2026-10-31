# Tasks — fantasypros-projections

## 1. Reading the rankings

- [x] 1.1 Write `FPRANK-01`, `FPRANK-04` (unit) in `tests/signals/test_expert_rankings.py`; clause-annotate
- [x] 1.2 Add `ExpertRanking`, `SignalBundle.expert_rankings`, `nflverse.expert_rankings_by_espn`, the collector step, and the 48 h optional threshold

## 2. Using them

- [x] 2.1 Write `FPRANK-02`, `FPRANK-03`, `FPRANK-05` in `tests/agent/test_expert_signal.py`; clause-annotate
- [x] 2.2 Show ranks and disagreement flags in `_tool_get_signals`; record rankings in `build_record`

## 3. Verification

- [x] 3.1 Run `uv run pytest`
- [x] 3.2 Run `node scripts/trace.mjs check --phase delivery --change fantasypros-projections`
