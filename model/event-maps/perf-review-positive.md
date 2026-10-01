---
id: SCN-010
scenario_id: perf-review-positive
journey: J-04
kind: happy-path
status: agreed
---

# Manager reviews agent performance — positive delta

Games finish Tuesday. The agent retrieves the prior decisions from the log and
in parallel fetches the as-of projections used at decision time (strict data
isolation — no post-hoc data). It replays the optimizer on each historical week,
computes the naive baseline, and produces a scorecard showing the delta and every
week where the manager departed from the recommendation. The manager reviews,
identifies any systematic override patterns, and calibrates their trust in the agent.

## Events

| id | event | scenario | after | actor | context | pivotal | hotspot | notes |
|----|-------|----------|-------|-------|---------|---------|---------|-------|
| E-301 | WeekResultsAvailable | SCN-010 | | R-02 | BC-ledger | yes | | Games complete; actual scores final in ESPN |
| E-302 | DecisionHistoryRetrieved | SCN-010 | E-301 | R-02 | BC-ledger | | | Prior DecisionRecords fetched from SQLite — includes override reasons |
| E-303 | AsOfProjectionsFetched | SCN-010 | E-301 | R-02 | BC-ledger | | | Runs in parallel with E-302 — projections timestamped before each decision's game week |
| E-304 | OptimizerReplayedOnHistory | SCN-010 | E-302,E-303 | R-02 | BC-ledger | yes | | Join — optimizer run on each historical week using only pre-game data |
| E-305 | NaiveBaselineComputed | SCN-010 | E-304 | R-02 | BC-ledger | | | Start-platform-rank-one score per week |
| E-306 | PerformanceDeltaComputed | SCN-010 | E-304,E-305 | R-02 | BC-ledger | | | Optimizer vs. naive vs. actual per week; p50 across season |
| E-307 | OverridePatternsIdentified | SCN-010 | E-302,E-306 | R-02 | BC-ledger | | | Weeks where manager departed from recommendation and the outcome |
| E-308 | BacktestScorecardGenerated | SCN-010 | E-306,E-307 | R-02 | BC-ledger | yes | | Full scorecard with delta, override log, and systematic patterns |
| E-309 | ScorecardPresentedToManager | SCN-010 | E-308 | R-01 | BC-ledger | yes | | Manager sees the evidence before calibrating trust |
| E-310 | ManagerReviewedOverrideLog | SCN-010 | E-309 | R-01 | BC-ledger | | | Systematic override patterns identified and noted for next season |

## Assumptions

| id | assumption | source |
|----|------------|--------|
| ASM-030 | As-of projections can be reconstructed with strict timestamp isolation — no post-hoc data leaks | kb |
| ASM-031 | The override log is complete — every departure from recommendation has a written reason | kb |
| ASM-032 | The backtest delta is positive in this scenario — optimizer outperforms naive baseline | assumed |

## Commands

| id | command | event | actor | aggregate | context |
|----|---------|-------|-------|-----------|---------|
| C-301 | RunBacktest | E-304 | R-02 | AGG-backtest-report | BC-ledger |
| C-302 | ReviewOverrideLog | E-310 | R-01 | AGG-backtest-report | BC-ledger |

## Policies

| id | when | then | crosses_context |
|----|------|------|-----------------|
| P-301 | E-308 | Present scorecard to manager (within BC-ledger) | |
