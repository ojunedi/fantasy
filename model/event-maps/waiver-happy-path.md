---
id: SCN-008
scenario_id: waiver-happy-path
journey: J-03
kind: happy-path
status: agreed
---

# Manager claims a waiver wire player — happy path

The waiver wire opens Tuesday night after Monday Night Football. The agent scans
available players and in parallel fetches projections, injury status, and schedule
data for them. It computes the roster's replacement baseline and scores each
candidate on value above replacement. The best add is identified; the manager
approves; the agent generates the in-app steps to submit the claim in the ESPN app.

## Events

| id | event | scenario | after | actor | context | pivotal | hotspot | notes |
|----|-------|----------|-------|-------|---------|---------|---------|-------|
| E-201 | WaiverWireOpened | SCN-008 | | Agent | | yes | | Tuesday night after Monday Night Football |
| E-202 | AvailablePlayersScanned | SCN-008 | E-201 | SYS-ESPN | | | | Free agents fetched; filtered to positions where roster has need |
| E-203 | ProjectionsForCandidatesFetched | SCN-008 | E-202 | SYS-ESPN | | | | Runs in parallel with E-204 and E-205 |
| E-204 | InjuryStatusForCandidatesFetched | SCN-008 | E-202 | SYS-NFLVERSE | | | | Runs in parallel with E-203 and E-205 |
| E-205 | ScheduleStrengthForCandidatesFetched | SCN-008 | E-202 | SYS-NFLVERSE | | | | Runs in parallel with E-203 and E-204 |
| E-206 | ReplacementBaselineComputed | SCN-008 | E-202 | Agent | | | | Minimum value a new player must beat on current roster |
| E-207 | WaiverCandidatesScored | SCN-008 | E-203,E-204,E-205,E-206 | Agent | | | | Join — value above replacement per candidate under league scoring rules |
| E-208 | BestAddIdentified | SCN-008 | E-207 | Agent | | yes | | Top candidate named with position, projected value, and roster fit |
| E-209 | WaiverRecommendationGenerated | SCN-008 | E-208 | Agent | | | | Rationale with projected value, roster impact, and player to drop |
| E-210 | WaiverRecommendationPresentedToManager | SCN-008 | E-209 | R-01 | | yes | | Manager sees recommendation before waiver deadline |
| E-211 | ManagerApprovedWaiverClaim | SCN-008 | E-210 | R-01 | | yes | | Approval gate — manager confirms add and drop |
| E-212 | DecisionLogged | SCN-008 | E-211 | Agent | | | | DecisionRecord with full input snapshot |
| E-213 | InAppStepsGenerated | SCN-008 | E-211 | Agent | | | | Runs in parallel with E-212 — steps to submit claim in ESPN waiver UI |
| E-214 | WaiverClaimReadyToSubmit | SCN-008 | E-213 | R-01 | | yes | | Manager has what they need before the deadline |

## Assumptions

| id | assumption | source |
|----|------------|--------|
| ASM-020 | The league uses snake waiver priority — no FAAB budget to model | kb |
| ASM-021 | The agent does not need to model priority order for v1 — just surface the best target | kb |
| ASM-022 | The manager submits the claim manually in the ESPN app before the deadline | assumed |

## Commands

<!-- Filled in during tactical storming -->

## Policies

<!-- Filled in during tactical storming -->
