---
id: S-004
slice_id: one-approval-gate
status: todo
---

# There is one approval gate, not two that can silently disagree

## Outcome

The rule that decides whether a write is authorised exists in exactly one place, and both the CLI and the web surface call it. A change to the rule cannot apply to one surface and not the other.

## Contexts

| id | why |
|----|-----|
| BC-lineup | Owns the gate, and currently owns two copies of it |
| BC-waiver | Will need the same gate; a third copy is the alternative to this slice |
| BC-trade | Already gates its send the same way |

## Invariants

| id | risk |
|----|------|
| I-11 | No write without a recorded approval. With two implementations, this holds only as long as both are correct — and only one of them is tested |
| I-24 | Authorisation is per-execution and never persisted. The risk in consolidating is a shared helper that caches the answer |
| I-09 | A written reason is mandatory on any departure. Both surfaces require it today; a merge must not relax the stricter one |

## NFRs

| id | applies |
|----|---------|
| NFR-11 | The web surface is the less-protected caller. Shared logic must not assume a trusted client |

## Contracts

No external contracts. This system publishes no API and no messages — the
`Contracts` table is for endpoints and published events, and there are none to
reference. The domain events this slice introduces are internal and already
mapped in `event-maps/`.

## Open questions

| id | question | owner |
|----|----------|-------|
| — | Consolidate, or test for equivalence? A shared function is better but touches two working paths mid-season. A property test asserting both accept and reject identical inputs is cheaper and retires most of the risk | R-01 |

<!--
The drift the single-service folding predicted, already arrived. `memo/cli.py:49`
and `web/routes/approve.py:170` each implement the `LIVE` comparison, neither
imports the other, and only the web copy has a test.

Both are correct today. That is the argument for doing this now rather than
after they diverge — there is no bug to fix yet, which makes this the cheapest
it will ever be.
-->
