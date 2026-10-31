---
id: S-012
slice_id: claim-would-clear
status: blocked
---

# Waiver recommendations account for whether the claim would actually clear

## Outcome

The waiver recommendation reflects our position in the snake order, so it stops naming players we were realistically never going to get — or names a fallback alongside the first choice.

**This slice is conditional, and the condition is not met — it is blocked.**
The claim-outcome slice now reads every claim's fate. Through week 8 of 2026
the league filed 32 waiver claims: 25 cleared, 3 lost to priority, 1 failed
for another reason, 1 cancelled, 2 pending — about one loss in ten resolved
claims, and none of the three were ours. Lost claims are rare, so this is not
built. Revisit if our own recorded results start showing priority losses.

## Contexts

| id | why |
|----|-----|
| BC-signal | Reads our priority position and, if available, other managers' |
| BC-analysis | Factors clearing likelihood into the ranking |
| BC-waiver | Surfaces a fallback when the first choice is contested |

## Invariants

| id | risk |
|----|------|
| I-29 | Both bars must still bind. The risk here is specific and worth naming: a clearing-likelihood factor could let a player who fails the absolute bar rise above one who passes it, on the grounds that we are more likely to get them. Easier to get is not the same as worth having |
| I-18 | The priority position must be the one at filing time, not at scoring time |

## NFRs

| id | applies |
|----|---------|
| NFR-07 | Still inside the Tuesday deadline, now with more computation |

## Contracts

No external contracts. This system publishes no API and no messages — the
`Contracts` table is for endpoints and published events, and there are none to
reference. The domain events this slice introduces are internal and already
mapped in `event-maps/`.

## Open questions

| id | question | owner |
|----|----------|-------|
| H-03 | Whether to model priority at all, and if so whether to predict contention or merely rank fallbacks. Ranking fallbacks is far cheaper and may capture most of the value | R-01 |
| — | Is other managers' waiver priority even observable through the API? **Yes** — the `mTeam` view carries every team's `waiverRank` | R-01 |

<!--
Explicitly sequenced by convenience rather than risk, and explicitly
conditional. Building a priority model before knowing whether claims are
actually being lost would be solving a problem by assumption — which is the
thing this whole discovery pass kept catching itself doing.
-->
