---
id: SCN-002
scenario_id: lineup-manager-override
journey: J-01
kind: alternate
status: agreed
---

# Manager starts a different player than recommended

The agent presents its lineup. The manager disagrees — they know something the
signals do not, or they are willing to take a variance bet the optimizer will
never make. They substitute a player and write down why. The override reason is
the artifact that matters: at the end of the season it is the only record of
where the manager's judgement beat the model and where it did not.

This is a legitimate outcome, not a failure. The gate exists so the manager can
say no.

## Events

| id | event | scenario | after | actor | context | pivotal | hotspot | notes |
|----|-------|----------|-------|-------|---------|---------|---------|-------|
| E-020 | ManagerOverrodeLineup | SCN-002 | | R-01 | BC-lineup | yes | | Branches from the recommendation being presented; manager substitutes one or more players |
| E-021 | OverrideReasonCaptured | SCN-002 | E-020 | R-01 | BC-lineup | yes | | Written reason is mandatory — the decision cannot proceed without it |
| E-022 | OverrideLogged | SCN-002 | E-021 | R-02 | BC-ledger | | | Original recommendation and the override stored side by side |
| E-023 | OverriddenLineupSubmittedToESPN | SCN-002 | E-021 | SYS-ESPN | BC-lineup | yes | | Runs in parallel with E-022; the manager's lineup, not the agent's |
| E-024 | LineupConfirmed | SCN-002 | E-023 | SYS-ESPN | BC-lineup | | | Rejoins the happy path at the same end state |

## Assumptions

| id | assumption | source |
|----|------------|--------|
| ASM-005 | The manager's substitution produces a legal lineup — slot eligibility is validated before submission | assumed |
| ASM-006 | A written reason is enforced at the interface, not merely requested | kb |

## Commands

| id | command | event | actor | aggregate | context |
|----|---------|-------|-------|-----------|---------|
| C-005 | OverrideLineup | E-020 | R-01 | AGG-lineup-decision | BC-lineup |

## Policies

| id | when | then | crosses_context |
|----|------|------|-----------------|
| P-004 | E-021 | Log the override alongside the original recommendation, then submit the manager's lineup (BC-lineup → BC-ledger) | yes |
