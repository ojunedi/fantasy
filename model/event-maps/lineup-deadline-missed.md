---
id: SCN-013
scenario_id: lineup-deadline-missed
journey: J-01
kind: exception
status: agreed
---

# Kickoff arrives with the recommendation unread

The agent ran, the brief was generated, and the manager never looked. Sunday
1 PM passes and whatever lineup was already set is the lineup that plays.

This is the highest-frequency failure available and the first draft assumed it
away — the happy path quietly took for granted that the manager reviews in
time. Nothing in the system currently notices the silence, which means the
first sign of it is a lost week.

## Events

| id | event | scenario | after | actor | context | pivotal | hotspot | notes |
|----|-------|----------|-------|-------|---------|---------|---------|-------|
| E-050 | RecommendationWentUnread | SCN-013 | | R-02 | BC-lineup | yes | H-06 | Branches from the recommendation being presented. Unresolved whether anything is watching the clock at all |
| E-051 | KickoffDeadlinePassed | SCN-013 | E-050 | SYS-ESPN | BC-lineup | yes | | Slots holding a started player are locked; the lineup is now whatever it already was |
| E-052 | UnactionedRecommendationLogged | SCN-013 | E-051 | R-02 | BC-ledger | yes | | Logged as its own outcome, distinct from an override and from an abstention — the agent was right or wrong and nobody found out |
| E-053 | ForgoneValueComputed | SCN-013 | E-051 | R-02 | BC-ledger | | | Runs alongside the logging. What the recommended lineup would have scored against what the standing lineup did |
| E-054 | MissSurfacedInReview | SCN-013 | E-052,E-053 | R-01 | BC-ledger | | | Path terminates in the weekly review rather than in the lineup cycle — the week is already gone |

## Assumptions

| id | assumption | source |
|----|------------|--------|
| ASM-015 | The standing lineup is legal — ESPN does not leave empty starter slots | assumed |
| ASM-016 | A presented-but-unactioned recommendation is distinguishable in the log from one never generated | assumed |

## Commands

| id | command | event | actor | aggregate | context |
|----|---------|-------|-------|-----------|---------|
| C-008 | ComputeForgoneValue | E-053 | R-02 | AGG-backtest-report | BC-ledger |

## Policies

| id | when | then | crosses_context |
|----|------|------|-----------------|
| P-009 | E-051 | Log the unactioned recommendation and compute what it would have been worth (BC-lineup → BC-ledger) | yes |
