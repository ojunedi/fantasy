---
id: S-008
slice_id: write-failure-reaches-me
status: todo
---

# I find out when both write paths failed, while there is still time to act

## Outcome

When the ESPN write fails and the browser fallback also fails, the manager is told — through the same channel as the pre-kickoff nudge — with the exact moves to make by hand and the time remaining.

## Contexts

| id | why |
|----|-----|
| BC-lineup | Owns the exhausted state, which currently has no notification behind it |
| BC-waiver | Same failure shape once claims are filed by API |
| BC-trade | Same again for a send that cannot be confirmed |

## Invariants

| id | risk |
|----|------|
| I-16 | The exhausted state must be reached only after read-back actually failed, not after a non-error response. Notifying on a false failure trains the manager to ignore the notification |
| I-11 | The manual instructions must describe the approved decision, not a recomputed one. A plan regenerated at notification time could differ from what was approved |

## NFRs

| id | applies |
|----|---------|
| NFR-06 | Useful only if it arrives before the deadline. A failure notification after kickoff is a log entry, not a notification |

## Contracts

No external contracts.

## Open questions

| id | question | owner |
|----|----------|-------|
| H-01 | Shares the channel question with the pre-kickoff nudge, and should reuse whatever that slice chooses rather than inventing a second mechanism | R-01 |

<!--
The twin of the missed recommendation, and it had no slice until the slicing was
challenged. Both failures have the same shape — everything upstream worked and
the lineup still did not change — and the same consequence. One was scheduled
and the other was not, which was an inconsistency rather than a judgement.

Depends on the nudge slice in practice if not in the table: both need something
that can reach the manager, and building two channels would be the wrong answer
to the same problem.
-->
