---
id: SCN-009
scenario_id: waiver-no-add
journey: J-03
kind: alternate
status: agreed
---

# No waiver candidate clears the replacement baseline

The agent scores every available player and none of them beats what is already
on the roster once the drop cost is counted. It recommends holding. This is
expected to be the common case in most weeks — a waiver wire that always
produces an add is a waiver wire being scored against too low a bar.

## Events

| id | event | scenario | after | actor | context | pivotal | hotspot | notes |
|----|-------|----------|-------|-------|---------|---------|---------|-------|
| E-220 | NoCandidateClearedBaseline | SCN-009 | | R-02 | BC-analysis | yes | | Branches at the scoring join; best candidate is below the drop cost |
| E-221 | HoldRecommendationGenerated | SCN-009 | E-220 | R-02 | BC-waiver | | | Names the closest candidate and how far short it fell |
| E-222 | HoldRecommendationPresentedToManager | SCN-009 | E-221 | R-01 | BC-waiver | yes | | Manager sees the near-misses, not a blank page |
| E-223 | ManagerConfirmedHold | SCN-009 | E-222 | R-01 | BC-waiver | yes | | Path terminates — no claim is filed this week |
| E-224 | NoClaimDecisionLogged | SCN-009 | E-223 | R-02 | BC-ledger | | | A decision not to act is still a decision worth reviewing |

## Assumptions

| id | assumption | source |
|----|------------|--------|
| ASM-023 | The replacement baseline accounts for the drop cost, not just the add's projected value | assumed |
| ASM-024 | The manager may still override and claim a player the agent passed on | assumed |

## Commands

| id | command | event | actor | aggregate | context |
|----|---------|-------|-------|-----------|---------|
| C-204 | RecommendHold | E-221 | R-02 | AGG-waiver-rec | BC-analysis |

## Policies

| id | when | then | crosses_context |
|----|------|------|-----------------|
| P-203 | E-223 | Log the no-claim decision with the near-miss candidates (BC-approval → BC-audit) | yes |
