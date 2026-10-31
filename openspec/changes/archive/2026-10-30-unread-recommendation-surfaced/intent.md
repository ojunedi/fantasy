# Intent — unread-recommendation-surfaced

## Outcome

When a week's lineup recommendation was never approved or overridden before
kickoff, the decision history shows that week as **missed**, with how many
projected points the recommendation would have gained over the lineup that
actually played.

## Who

**Actor:** the manager
**What changes for them:** a week they never got to stops looking the same as
a week nothing was recommended. Across a season they can see what inattention
cost — the case for doing something more about it, or for not bothering.

## Why now

Sequenced after the pre-kickoff nudge, which may stop misses happening. It is
still wanted: reminders get ignored, and only a measured cost says whether
that matters.

## Acceptance criteria

| # | Criterion | Source |
| --- | --- | --- |
| AC-1 | A week none of whose lineup decisions got a human response before that week's kickoff (Sunday 1 PM ET of the NFL week) is recorded as missed once the week is settled (Tuesday 6 AM ET), on the newest run made before kickoff that recommended starters; a run made after kickoff is never charged | outcome; NFR-06 (kickoff is the trigger); invariant I-14 |
| AC-2 | A week with any lineup decision responded to before kickoff is never recorded as missed, even if other runs that week were left unactioned; a response after kickoff does not erase a miss | outcome |
| AC-3 | A missed decision gets no human response and no override reason; the miss is recorded only in the decision's outcome, so it can never be counted as an override | invariant I-09 |
| AC-4 | The cost is the recommended starters' projected total minus the standing starters' projected total, both taken from the projections saved on the decision when it was made — never from projections or scores published after kickoff | invariant I-14 |
| AC-5 | A standing starter with no saved projection counts as 0 and is listed as unprojected on the miss, so the cost never silently depends on a missing number | invariant I-14 |
| AC-6 | When the week's actual points are available they are recorded beside the cost, labelled as hindsight, and are never used as the cost | invariant I-14 |
| AC-7 | A week is recorded as missed at most once; a recorded miss is not recomputed | outcome |
| AC-8 | Before the week is settled, nothing is recorded as missed — so the lineup read and the actual points are final | NFR-06; review finding |
| AC-9 | The decision history shows a missed week as "missed" with its cost in projected points, distinct from approved, overridden, rejected and abstained | outcome |

## Acceptance signal

- At season's end the history shows how many weeks were missed and the
  projected points they cost, and that number is the one that decides
  whether the nudge needs to be louder.

## Out of scope

- Preventing the miss (the nudge slice).
- Misses for waiver or trade decisions.
- Installing or changing any background job: the check runs when the history
  page loads, or by hand.
- Thursday and Monday games: kickoff is the Sunday 1 PM slate.

## Carried context

| | |
| --- | --- |
| **Bounded contexts** | Lineup Execution (the unactioned terminal state); Ledger (records the forgone value) |
| **Aggregates touched** | Decision — outcome only |
| **Invariants at risk** | Silence must not look like an override (I-09); pre-kickoff projections only (I-14) |
| **Contracts** | None external |
| **NFRs that apply** | Sunday 1 PM kickoff is the trigger (NFR-06) |
| **Depends on** | Nothing |

## Interface impact

**Does this slice touch a user interface?** Yes — one cell in the decision
history. The `ux` artifact is required.

## Open questions

| # | Question | Owner | Blocking? |
| --- | --- | --- | --- |
| Q-1 | The slice's outcome compares against "what the standing lineup actually did", which would be hindsight. **Resolved:** the pre-kickoff projection rule wins; actual points are recorded as labelled context only | — | No |
