---
id: S-006
slice_id: claim-outcome-recorded
status: todo
---

# I find out whether my claim cleared or lost to priority

## Outcome

After a waiver window closes, each filed claim is resolved to cleared or lost, with the priority position it was filed under, and recorded. The manager can see which recommendations were actionable rather than only which were made.

## Contexts

| id | why |
|----|-----|
| BC-waiver | Owns the claim and its terminal states |
| BC-signal | Reads the league back to find out what happened |
| BC-ledger | Records the outcome against the original recommendation |

## Invariants

| id | risk |
|----|------|
| I-18 | The claim must record the priority position it was filed under. Without it a lost claim cannot be distinguished from a bad recommendation, which is the entire point of this slice |
| I-23 | The outcome must be established by reading the league back, not inferred from the absence of an error on submission |

## NFRs

| id | applies |
|----|---------|
| NFR-09 | Same read-back principle as the write paths: the claim's fate is a fact to be observed, never assumed |

## Contracts

No external contracts. This system publishes no API and no messages — the
`Contracts` table is for endpoints and published events, and there are none to
reference. The domain events this slice introduces are internal and already
mapped in `event-maps/`.

## Open questions

| id | question | owner |
|----|----------|-------|
| — | Does ESPN report a *failed* claim at all, or only successful transactions? If failures are silent, "lost" has to be inferred from the player appearing on another roster — which is weaker evidence and worth knowing before building on it | R-01 |

<!--
This is the slice that makes the waiver scorer improvable, and it is the reason
the priority-modelling slice is sequenced after it rather than guessed at. A scorer that keeps naming
players claimed by someone with better priority produces advice that reads well
and cannot be used, and nothing before this slice would reveal that.
-->
