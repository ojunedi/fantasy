---
product: Fantasy GM
stage: domain-design
aggregate: AGG-waiver-analysis
---

# AGG-waiver-analysis

Owned by the analysis context. Scores the available players against the roster's replacement baseline and terminates — either with a candidate worth claiming or with the finding that none clears the bar.

## Invariants

| id | aggregate | rule | enforced_in |
|----|-----------|------|-------------|
| I-06 | AGG-waiver-analysis | A candidate is only scored as worth claiming if it clears the replacement baseline *after* the cost of the drop it requires, never before | WaiverAnalysis.score |
| I-17 | AGG-waiver-analysis | The no-candidate outcome names the closest candidate and the margin it fell short by. "Nothing available" with no numbers cannot be reviewed later | WaiverAnalysis.recommendHold |

## Transitions

| aggregate | from | to | event |
|-----------|------|----|-------|
| AGG-waiver-analysis | new | scored | E-207 |
| AGG-waiver-analysis | scored | candidate-found | E-208 |
| AGG-waiver-analysis | scored | none-cleared | E-220 |

## Members

| id | name | aggregate | kind | notes |
|----|------|-----------|------|-------|
| ENT-replacement-baseline | Replacement baseline | AGG-waiver-analysis | value-object | Recomputed per week. 🔴 Whether it spans the whole roster or only startable slots is unresolved (H-05), and the answer changes every number this aggregate produces |
