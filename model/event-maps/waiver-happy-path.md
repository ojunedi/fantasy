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
| E-201 | WaiverWireOpened | SCN-008 | | R-02 | BC-signal | yes | | Tuesday night after Monday Night Football |
| E-202 | AvailablePlayersScanned | SCN-008 | E-201 | SYS-ESPN | BC-signal | | | Free agents fetched; filtered to positions where roster has need |
| E-203 | ProjectionsForCandidatesFetched | SCN-008 | E-202 | SYS-ESPN | BC-signal | | | Runs in parallel with E-204 and E-205 |
| E-204 | InjuryStatusForCandidatesFetched | SCN-008 | E-202 | SYS-NFLVERSE | BC-signal | | | Runs in parallel with E-203 and E-205 |
| E-205 | ScheduleStrengthForCandidatesFetched | SCN-008 | E-202 | SYS-NFLVERSE | BC-signal | | | Runs in parallel with E-203 and E-204 |
| E-206 | ReplacementBaselineComputed | SCN-008 | E-202 | R-02 | BC-analysis | | | Minimum value a new player must beat on current roster |
| E-207 | WaiverCandidatesScored | SCN-008 | E-203,E-204,E-205,E-206 | R-02 | BC-analysis | | | Join — value above replacement per candidate under league scoring rules |
| E-208 | BestAddIdentified | SCN-008 | E-207 | R-02 | BC-analysis | yes | | Top candidate named with position, projected value, and roster fit |
| E-209 | WaiverRecommendationGenerated | SCN-008 | E-208 | R-02 | BC-waiver | | | Rationale with projected value, roster impact, and player to drop |
| E-210 | WaiverRecommendationPresentedToManager | SCN-008 | E-209 | R-01 | BC-waiver | yes | | Manager sees recommendation before waiver deadline |
| E-211 | ManagerApprovedWaiverClaim | SCN-008 | E-210 | R-01 | BC-waiver | yes | | Approval gate — manager confirms add and drop |
| E-212 | DecisionLogged | SCN-008 | E-211 | R-02 | BC-ledger | | | DecisionRecord with full input snapshot |
| E-213 | InAppStepsGenerated | SCN-008 | E-211 | R-02 | BC-waiver | | | Runs in parallel with E-212 — steps to submit claim in ESPN waiver UI |
| E-214 | WaiverClaimReadyToSubmit | SCN-008 | E-213 | R-01 | BC-waiver | | | Manager has what they need before the deadline |
| E-215 | WaiverClaimSubmitted | SCN-008 | E-214 | R-01 | BC-waiver | yes | | Filed in the ESPN app. The outcome is now decided by priority order, not by us |
| E-216 | WaiverClaimCleared | SCN-008 | E-215 | SYS-ESPN | BC-waiver | yes | | Nobody ahead in priority claimed the same player — this is the happy path, not the default |
| E-217 | WaiverOutcomeLogged | SCN-008 | E-216 | R-02 | BC-ledger | | | Whether a claim cleared is the only way to learn whether the priority read was right |

## Assumptions

| id | assumption | source |
|----|------------|--------|
| ASM-020 | The league uses snake waiver priority — no FAAB budget to model | kb |
| ASM-021 | The agent does not need to model priority order for v1 — just surface the best target | kb |
| ASM-022 | The manager submits the claim manually in the ESPN app before the deadline | assumed |

## Commands

| id | command | event | actor | aggregate | context |
|----|---------|-------|-------|-----------|---------|
| C-201 | FetchWaiverSignals | E-202 | R-02 | AGG-signal-bundle | BC-signal |
| C-202 | ScoreWaiverCandidates | E-207 | R-02 | AGG-waiver-rec | BC-analysis |
| C-203 | ApproveWaiverClaim | E-211 | R-01 | AGG-decision-record | BC-waiver |

## Policies

| id | when | then | crosses_context |
|----|------|------|-----------------|
| P-201 | E-207 | Identify the best add and generate the waiver recommendation (BC-analysis → BC-recommendation) | yes |
| P-202 | E-211 | Log the decision record AND generate in-app steps (BC-approval → BC-audit) | yes |
