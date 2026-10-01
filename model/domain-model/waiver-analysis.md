---
product: Fantasy GM
stage: domain-design
aggregate: AGG-waiver-analysis
---

# AGG-waiver-analysis

Owned by the analysis context. Scores the available players and terminates — either with a candidate worth claiming or with the finding that none is.

**There are two bars, and both must clear.** A candidate must beat what it would displace on my roster (relative), *and* rank inside the startable tier at its position league-wide (absolute). Only having the relative bar is how a thin position produces a confident recommendation for a player nobody should roster: the roster being weak somewhere does not make a bad player good.

**A bye does not create a path to starting.** The relative bar includes a forward-looking test — does this player project to crack my lineup in the next three weeks — and that test is evaluated against a roster assumed fully available. Otherwise every bye week would manufacture an opening and the scorer would churn the bench filling holes that close by themselves. Filling a bye-week hole is a real need, and a different one; it is deliberately not what this aggregate answers.

## Invariants

| id | aggregate | rule | enforced_in |
|----|-----------|------|-------------|
| I-06 | AGG-waiver-analysis | A candidate clears the *relative* bar only if it beats the worst rostered player — the one it would displace — on rest-of-season value | WaiverAnalysis.score |
| I-30 | AGG-waiver-analysis | A candidate must additionally project as startable within the next three weeks, measured against a roster assumed **fully available**. A bye week or a short-term injury creating the opening does not count as a path to starting | WaiverAnalysis.score |
| I-28 | AGG-waiver-analysis | A candidate clears the *absolute* bar only if it ranks inside the league-wide startable tier at its position — team count × starting slots at that position, derived from league settings rather than hardcoded | WaiverAnalysis.score |
| I-29 | AGG-waiver-analysis | A candidate is recommended only if it clears **both** bars. Clearing one is not a weaker recommendation — it is not a recommendation | WaiverAnalysis.score |
| I-17 | AGG-waiver-analysis | The no-candidate outcome names the closest candidate, which bar it failed, and by how much. "Nothing available" with no numbers cannot be reviewed later | WaiverAnalysis.recommendHold |

## Transitions

| aggregate | from | to | event |
|-----------|------|----|-------|
| AGG-waiver-analysis | new | scored | E-207 |
| AGG-waiver-analysis | scored | candidate-found | E-208 |
| AGG-waiver-analysis | scored | none-cleared | E-220 |

## Members

| id | name | aggregate | kind | notes |
|----|------|-----------|------|-------|
| ENT-replacement-baseline | Replacement baseline | AGG-waiver-analysis | value-object | The relative bar: the worst rostered player's rest-of-season value, which is who a claim would displace. Recomputed per week |
| ENT-roster-worthiness | Startable-tier cutoff | AGG-waiver-analysis | value-object | The absolute bar: team count × starting slots at the position, from league settings. Survives a scoring or roster-shape change because it is derived, not fixed |
| ENT-starting-path | Path to starting | AGG-waiver-analysis | value-object | Whether the candidate projects into my lineup within three weeks, with the roster assumed fully available so byes do not manufacture one |
