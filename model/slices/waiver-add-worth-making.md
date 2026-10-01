---
id: S-003
slice_id: waiver-add-worth-making
status: todo
---

# The agent tells me whether there is a waiver add worth making, and if so which

## Outcome

On the waiver wire opening, the manager gets one of two complete answers: a named player worth claiming with the reasoning, or "nothing here is worth a roster spot" with the closest candidate and which bar it failed. Both are logged.

This slice stops at the brief. The gate, the add-drop pairing and the filing are the second half of the skeleton and belong to the filing slice — keeping them here is what made this one carry eight invariants while every other slice carried one to three.

**"No" is the expected answer most weeks.** A scanner that always finds an add is scoring against too low a bar.

## Contexts

| id | why |
|----|-----|
| BC-signal | Fetches available players, their projections, injury status and schedule |
| BC-analysis | Owns the two-bar scoring. This is the context that is currently empty in code |
| BC-waiver | Owns the brief. The gate and the filing arrive in the next slice |
| BC-ledger | Records the decision, including a decision not to claim |

## Invariants

| id | risk |
|----|------|
| I-06 | The relative bar must compare against the worst *rostered* player — who the claim actually displaces — not against a starter and not against a league average. Comparing against the wrong thing silently changes which adds qualify |
| I-28 | The absolute bar must derive its cutoff from league settings (team count × starting slots at the position), not from a hardcoded number. A hardcoded tier breaks the first time the roster shape or team count changes |
| I-29 | A candidate clearing only one bar must not be recommended at all. The risk is treating it as a weaker recommendation and surfacing it anyway, which is exactly the behaviour this slice exists to prevent |
| I-30 | The path-to-starting test must assume a fully available roster. If a bye or an injury can create the opening, every bye week manufactures a false path and the scorer churns the bench |
| I-17 | The no-candidate answer must name the closest candidate, the bar it failed, and the margin. "Nothing available" with no numbers cannot be reviewed at season end |
| I-19 | A hold must be recorded with the same weight as a claim. The risk is treating "no action" as "nothing to log", which would leave half the waiver season unreviewable |

## NFRs

| id | applies |
|----|---------|
| NFR-07 | Scoring must complete in time to leave room for filing before the Tuesday deadline |
| NFR-03 | Scanning free agents is an ESPN read burst and is subject to the one-per-second pacing |
| NFR-04 | The run shares the per-run LLM budget. The scoring is deterministic, so the model is only generating the brief |

## Contracts

No external contracts. This system publishes no API and no messages — the
`Contracts` table is for endpoints and published events, and there are none to
reference. The domain events this slice introduces are internal and already
mapped in `event-maps/`.

## Also required

A `waivers` worker registered in the web run dispatcher, which currently rejects the kind as unknown. The socket exists; nothing is plugged into it.

## Open questions

Both bars were settled on 2026-10-01 — see the resolved hotspots. One remains:

| id | question | owner |
|----|----------|-------|
| H-03 | Whether to model snake priority to predict if a claim would clear. Deliberately out of this slice: S-003 produces the evidence for whether it is needed | R-01 |

<!--
First half of the walking skeleton. Signal gathering, the two-bar scoring, the
brief and the log — the capability's full analysis path, and nothing that writes.

The slice no longer claims "one candidate considered", which contradicted its
own requirement: naming the closest miss and its margin means ranking the field,
not evaluating one player. Ranking is the work; surfacing one result is the
output.

`core/waivers.py` exists and is dead — nothing imports it, and its constraint
function cannot enforce the roster-size rule it claims to check. This slice
either fixes it or deletes it; leaving a module that looks like waiver support
beside a working one is worse than either.
-->
