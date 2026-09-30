---
scope: Fantasy GM
substep: scope
---

# Capabilities, Roles, and Journeys

## Process archetype

| id | archetype | lifecycle | confidence | departs_how | alternatives | source |
|----|-----------|-----------|------------|-------------|--------------|--------|
| ARCH-01 | Recurring decision cycle (brief-to-decision, weekly cadence) | Signals gathered → analysis run → recommendation generated → human approval → execution → result logged → performance reviewed | recognised | Three parallel decision tracks (lineup, waiver, trade) each complete the cycle independently in the same week. The hard external deadline (Sunday 1 PM kickoff for lineup, Tuesday night for waivers) is not negotiable — any step that misses it forfeits the decision entirely. Trades have no deadline but are permanently asymmetric: once a counterparty accepts, the roster change is irreversible. None of this is in a generic decision-support archetype. | Portfolio rebalancing (same shape but no hard deadline); incident response (time-pressure but single track, no approval gate before execution) | kb |

## Capabilities

| id | name | purpose | source |
|----|------|---------|--------|
| CAP-01 | Signal Gathering | Fetch, normalize, and assess freshness of projections, injuries, news, schedules, usage, and game environment data | kb |
| CAP-02 | Decision Analysis | Compute optimal lineups, trade package EV, and waiver-add value above replacement | kb |
| CAP-03 | Recommendation | Generate structured briefs with reasoning — lineup, trade packages with counterparty pitch, waiver rationale, performance scorecard | kb |
| CAP-04 | Human Approval | Present the recommendation, capture the manager's decision, require a written override reason on any departure | kb |
| CAP-05 | Execution | Submit approved lineup changes via ESPN's write API; generate in-app steps for trades and waiver claims the manager must perform manually | kb |
| CAP-06 | Audit & Evaluation | Log every decision with full input snapshot; run backtest against naive baseline; surface systematic override patterns at end of season | kb |

## Roles

| id | name | capability | description | source |
|----|------|------------|-------------|--------|
| R-01 | Manager (Omer) | CAP-04 | Single human actor — reviews every recommendation, approves or overrides, triggers execution, and reads end-of-season review | kb |
| R-02 | Fantasy GM Agent | CAP-02 | The system under construction — gathers signals, runs the deterministic core, generates recommendations, and logs decisions. Takes no irreversible action without R-01's approval | kb |

## Systems

| id | name | kind | description | source |
|----|------|------|-------------|--------|
| SYS-ESPN | ESPN API | system-of-record | League, roster, scoring settings, weekly projections, lineup submission endpoint (undocumented write) | kb |
| SYS-NFLVERSE | nflreadpy (nflverse) | third-party | NFL stats, snaps, usage, schedules, Vegas lines, injuries, ID bridge — keyless and cached locally | kb |
| SYS-FANTASYCALC | FantasyCalc API | third-party | Rest-of-season player trade values — network call, may be unavailable | kb |
| SYS-ESPN-NEWS | ESPN News API | third-party | Player news, injury updates, practice reports — keyless | kb |
| SYS-FANTASYPROS | FantasyPros | third-party | Consensus projections — current source is ESPN; FantasyPros is the planned upgrade, architecture keeps projection source pluggable | assumed |
| SYS-TAVILY | Tavily | third-party | Web search for targeted injury and news research — activates when API key is set, degrades gracefully without one | kb |

## Journeys

| id | name | actor | participants | capability | covers | starts_when | ends_when | status | source |
|----|------|-------|--------------|------------|--------|-------------|-----------|--------|--------|
| J-01 | Manager sets the weekly lineup | R-01 | SYS-ESPN,SYS-NFLVERSE,SYS-ESPN-NEWS,SYS-TAVILY | CAP-01,CAP-02,CAP-03,CAP-04,CAP-05,CAP-06 | FN-001,FN-002,FN-003,FN-004,FN-005,FN-006,FN-008,FN-009,FN-010,FN-011,FN-012,FN-013,FN-017,FN-021,FN-025,FN-028,FN-029,FN-030 | Week opens (Tuesday, after prior week's games finish) | Lineup change executed — or a no-change decision logged — before Sunday 1 PM kickoff | agreed | kb |
| J-02 | Manager evaluates and sends a trade offer | R-01 | SYS-FANTASYCALC,SYS-NFLVERSE,SYS-ESPN-NEWS,SYS-TAVILY | CAP-01,CAP-02,CAP-03,CAP-04,CAP-05,CAP-06 | FN-003,FN-006,FN-007,FN-008,FN-010,FN-014,FN-016,FN-018,FN-022,FN-026,FN-029,FN-030 | Manager or agent identifies a roster imbalance or market opportunity | In-app steps to send the offer delivered to manager — or agent abstains with reasoning and the evidence it was missing | agreed | kb |
| J-03 | Manager claims a waiver wire player | R-01 | SYS-ESPN,SYS-NFLVERSE,SYS-ESPN-NEWS | CAP-01,CAP-02,CAP-03,CAP-04,CAP-05,CAP-06 | FN-001,FN-003,FN-005,FN-006,FN-009,FN-010,FN-011,FN-015,FN-019,FN-023,FN-027,FN-029,FN-030 | Waiver wire opens (Tuesday night, after Monday Night Football) | Claim submitted — or no-claim decision logged — before the waiver deadline | agreed | kb |
| J-04 | Manager reviews agent performance against the naive baseline | R-01 | SYS-ESPN | CAP-02,CAP-06 | FN-012,FN-013,FN-020,FN-024,FN-031,FN-032,FN-033 | Week's games complete (Tuesday) | Optimizer-vs-baseline delta reviewed and override patterns identified | agreed | kb |
