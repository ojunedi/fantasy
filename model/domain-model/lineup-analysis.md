---
product: Fantasy GM
stage: domain-design
aggregate: AGG-lineup-analysis
---

# AGG-lineup-analysis

Owned by the analysis context and terminating there. It produces an optimized lineup or declines to, and then it is done — the brief, the gate and the write all belong to lineup execution.

This boundary moved during the consistency pass. It originally ran all the way through to the ESPN write, which made it an aggregate written from two contexts.

## Invariants

| id | aggregate | rule | enforced_in |
|----|-----------|------|-------------|
| I-03 | AGG-lineup-analysis | Every optimized lineup is legal: each player occupies a slot their position is eligible for, and every starter slot is filled | LineupAnalysis.optimize |
| I-04 | AGG-lineup-analysis | A locked player keeps the slot they are already in. A lineup that moves one is not a better lineup, it is a write ESPN rejects with 409 | LineupAnalysis.optimize |
| I-05 | AGG-lineup-analysis | An abstention names which signals were stale and by how much. An abstention with no evidence is indistinguishable from a crash | LineupAnalysis.abstain |

## Transitions

| aggregate | from | to | event |
|-----------|------|----|-------|
| AGG-lineup-analysis | new | optimized | E-008 |
| AGG-lineup-analysis | new | abstained | E-031 |

## Members

| id | name | aggregate | kind | notes |
|----|------|-----------|------|-------|
| ENT-roster-slot | RosterSlot | AGG-lineup-analysis | value-object | Slot id, position, and whether it starts |
| ENT-lock | Lock state | AGG-lineup-analysis | value-object | Derived from whether the player's game has kicked off — never a user-set flag. Distinct from the lineup deadline having passed |
