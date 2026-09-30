---
id: SCN-001
scenario_id: lineup-happy-path
journey: J-01
kind: happy-path
status: agreed
---

# Manager sets the weekly lineup — happy path

The week opens Tuesday after the prior week's games. The agent fetches the
manager's roster and then gathers signals in parallel: ESPN projections, nflverse
injury and schedule data, and ESPN news. All four converge before the optimizer
runs. The agent recommends a lineup with per-player reasoning; the manager
approves; the lineup is submitted to ESPN via the write API.

## Events

| id | event | scenario | after | actor | context | pivotal | hotspot | notes |
|----|-------|----------|-------|-------|---------|---------|---------|-------|
| E-001 | WeekOpened | SCN-001 | | Agent | | yes | | Tuesday — decision cycle starts for this scoring week |
| E-002 | RosterFetched | SCN-001 | E-001 | SYS-ESPN | | | | Current roster with player statuses and bye weeks |
| E-003 | ProjectionsFetched | SCN-001 | E-002 | SYS-ESPN | | | | Weekly ESPN projections for all rostered players |
| E-004 | InjuryReportFetched | SCN-001 | E-002 | SYS-NFLVERSE | | | | Runs in parallel with E-003 and E-005 |
| E-005 | ScheduleAndMatchupFetched | SCN-001 | E-002 | SYS-NFLVERSE | | | | Runs in parallel with E-003 and E-004 |
| E-006 | NewsAndPracticeReportFetched | SCN-001 | E-002 | SYS-ESPN-NEWS | | | | Runs in parallel with E-003, E-004, E-005 |
| E-007 | PlayerScoresComputed | SCN-001 | E-003,E-004,E-005,E-006 | Agent | | | | Join on all signals; blends projection + matchup + schedule + usage |
| E-008 | LineupOptimized | SCN-001 | E-007 | Agent | | yes | | Backtracking optimizer picks legal lineup that maximises projected score |
| E-009 | LineupBriefGenerated | SCN-001 | E-008 | Agent | | | | Per-player reasoning with signal citations and confidence notes |
| E-010 | LineupRecommendationPresentedToManager | SCN-001 | E-009 | R-01 | | yes | | Manager sees full brief before any decision is recorded |
| E-011 | ManagerApprovedLineup | SCN-001 | E-010 | R-01 | | yes | | Approval gate — no ESPN write without this |
| E-012 | DecisionLogged | SCN-001 | E-011 | Agent | | | | DecisionRecord written to SQLite with full input snapshot |
| E-013 | LineupChangeSubmittedToESPN | SCN-001 | E-011 | SYS-ESPN | | yes | | Runs in parallel with E-012; dry-run unless LIVE confirmed |
| E-014 | LineupConfirmed | SCN-001 | E-013 | SYS-ESPN | | | | ESPN acknowledges the roster move |

## Assumptions

| id | assumption | source |
|----|------------|--------|
| ASM-001 | ESPN projections are available and not stale for this week | assumed |
| ASM-002 | nflverse data has refreshed since the prior week's games | assumed |
| ASM-003 | The ESPN write API is reachable and accepts the transaction | assumed |
| ASM-004 | The manager reviews the brief before the Sunday 1 PM kickoff deadline | assumed |

## Commands

<!-- Filled in during tactical storming -->

## Policies

<!-- Filled in during tactical storming -->
