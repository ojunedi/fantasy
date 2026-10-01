---
product: Fantasy GM
stage: domain-design
aggregate: AGG-backtest-report
---

# AGG-backtest-report

## Invariants

| id | aggregate | rule | enforced_in |
|----|-----------|------|-------------|
| I-14 | AGG-backtest-report | Every projection used to score a past week predates that week's first kickoff. A single post-hoc value invalidates the whole report | BacktestReport.replay |

## Transitions

| aggregate | from | to | event |
|-----------|------|----|-------|
| AGG-backtest-report | new | replayed | E-304 |
| AGG-backtest-report | replayed | scored | E-308 |
| AGG-backtest-report | scored | reviewed | E-310 |

## Members

| id | name | aggregate | kind | notes |
|----|------|-----------|------|-------|
| ENT-scorecard | WeeklyScorecard | AGG-backtest-report | entity | Accumulates: created at replay, gains the actual outcome after the week resolves |


<!--
A rule requiring the replay to reproduce a recorded decision was considered and
rejected as an invariant: nothing can reject a transition on it, so it is a test
of the implementation rather than a constraint on the aggregate's state. It
belongs in the delivery slice's acceptance criteria, where it is assertable.
-->
