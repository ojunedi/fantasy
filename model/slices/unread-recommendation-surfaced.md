---
id: S-007
slice_id: unread-recommendation-surfaced
status: todo
---

# A missed recommendation is recorded with what it cost

## Outcome

When a lineup recommendation is never actioned before kickoff, that is recorded as its own outcome — distinct from an override and from an abstention — with what the recommended lineup would have scored against what the standing lineup actually did.

## Contexts

| id | why |
|----|-----|
| BC-lineup | Owns the unactioned terminal state |
| BC-ledger | Computes and records the forgone value |

## Invariants

| id | risk |
|----|------|
| I-09 | An unactioned decision carries no override reason and must not be made to resemble one. The risk is recording silence as a human choice, which would corrupt the override log — the artifact the whole evaluation story rests on |
| I-14 | The forgone-value comparison must use the projections available before kickoff. Scoring it with hindsight would make every miss look worse than it was and overstate the cost of inattention |

## NFRs

| id | applies |
|----|---------|
| NFR-06 | The kickoff deadline is the trigger |

## Contracts

No external contracts.

## Open questions

None. The nudge slice owns the question of preventing the miss; this slice only measures it.

<!--
Sequenced after the nudge rather than before it, because the nudge may stop the
miss happening. Still wanted: reminders get ignored, and knowing what
inattention actually costs across a season is what makes the case for doing
something further about it.
-->
