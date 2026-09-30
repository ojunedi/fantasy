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
| E-001 | WeekOpened | SCN-001 | | R-02 | BC-signal | yes | | Tuesday — decision cycle starts for this scoring week |
| E-002 | RosterFetched | SCN-001 | E-001 | SYS-ESPN | BC-signal | | | Current roster with player statuses and bye weeks |
| E-003 | ProjectionsFetched | SCN-001 | E-002 | SYS-ESPN | BC-signal | | | Weekly ESPN projections for all rostered players |
| E-004 | InjuryReportFetched | SCN-001 | E-002 | SYS-NFLVERSE | BC-signal | | | Runs in parallel with E-003 and E-005 |
| E-005 | ScheduleAndMatchupFetched | SCN-001 | E-002 | SYS-NFLVERSE | BC-signal | | | Runs in parallel with E-003 and E-004 |
| E-006 | NewsAndPracticeReportFetched | SCN-001 | E-002 | SYS-ESPN-NEWS | BC-signal | | | Runs in parallel with E-003, E-004, E-005 |
| E-007 | PlayerScoresComputed | SCN-001 | E-003,E-004,E-005,E-006 | R-02 | BC-analysis | | | Join on all signals; blends projection + matchup + schedule + usage |
| E-008 | LineupOptimized | SCN-001 | E-007 | R-02 | BC-analysis | yes | | Backtracking optimizer picks legal lineup that maximises projected score |
| E-009 | LineupBriefGenerated | SCN-001 | E-008 | R-02 | BC-lineup | | | Per-player reasoning with signal citations and confidence notes |
| E-010 | LineupRecommendationPresentedToManager | SCN-001 | E-009 | R-01 | BC-lineup | yes | | Manager sees full brief before any decision is recorded |
| E-011 | ManagerApprovedLineup | SCN-001 | E-010 | R-01 | BC-lineup | yes | | Approval gate — no ESPN write without this |
| E-012 | DecisionLogged | SCN-001 | E-011 | R-02 | BC-ledger | | | DecisionRecord written to SQLite with full input snapshot |
| E-013 | LineupChangeSubmittedToESPN | SCN-001 | E-011 | SYS-ESPN | BC-lineup | yes | | Runs in parallel with E-012; dry-run unless LIVE confirmed |
| E-014 | LineupConfirmed | SCN-001 | E-013 | SYS-ESPN | BC-lineup | | | ESPN acknowledges the roster move |

## Assumptions

| id | assumption | source |
|----|------------|--------|
| ASM-001 | ESPN projections are available and not stale for this week | assumed |
| ASM-002 | nflverse data has refreshed since the prior week's games | assumed |
| ASM-003 | The ESPN write API is reachable and accepts the transaction | assumed |
| ASM-004 | The manager reviews the brief before the Sunday 1 PM kickoff deadline | assumed |

## Commands

| id | command | event | actor | aggregate | context |
|----|---------|-------|-------|-----------|---------|
| C-001 | FetchWeeklySignals | E-002 | R-02 | AGG-signal-bundle | BC-signal |
| C-002 | OptimizeLineup | E-008 | R-02 | AGG-lineup-rec | BC-analysis |
| C-003 | ApproveLineup | E-011 | R-01 | AGG-decision-record | BC-lineup |
| C-004 | SubmitLineupToESPN | E-013 | SYS-ESPN | AGG-decision-record | BC-lineup |

## Policies

| id | when | then | crosses_context |
|----|------|------|-----------------|
| P-001 | E-007 | Run the lineup optimizer with the blended scores (BC-signal → BC-analysis) | yes |
| P-002 | E-008 | Generate the lineup brief with per-player reasoning (BC-analysis → BC-recommendation) | yes |
| P-003 | E-011 | Submit lineup to ESPN AND log the decision record (BC-approval → BC-audit) | yes |
