# Intent — claim-outcome-recorded

## Outcome

After the waiver window runs, the manager opens the waiver page and sees
whether the claim they filed cleared, lost to someone with better waiver
priority, or failed for another reason — and the result is recorded against
the recommendation, with the priority position it was filed under.

## Who

**Actor:** the manager
**What changes for them:** today a filed claim ends at "ESPN shows it as
pending". After this slice they learn its fate, and the decision log can tell
a recommendation that was right but unwinnable from one that was wrong.

## Why now

The waiver scorer cannot be improved without it: a scorer that keeps naming
players someone with better priority takes reads well and cannot be used,
and nothing before this slice would show that. The priority-aware scoring
slice is sequenced after this one for exactly that reason.

ESPN's transaction history answered the slice's open question. A lost claim is
reported, not silent: it reads back `FAILED_INVALIDPLAYERSOURCE` (the player
was no longer in the pool), and the winning claim for the same player reads
`EXECUTED` in the same window — seen in week 4, where team 10 won a player
that teams 7 and 3 had also claimed.

## Acceptance criteria

| # | Criterion | Source |
| --- | --- | --- |
| AC-1 | A filed claim (confirmed or unconfirmed) is resolved by reading the league's transactions with the cache bypassed and finding this team's waiver claim for the same add and drop in the same week | invariant I-23; NFR-09 |
| AC-2 | A claim that reads back `EXECUTED` is recorded as **cleared** | outcome; glossary *Claim cleared* |
| AC-3 | A claim that reads back failed because the player left the pool, where another team's waiver claim for the same player executed, is recorded as **lost to priority**, naming the team that won it | outcome |
| AC-4 | A claim that reads back failed for any other reason (for example the drop player was already gone) is recorded as **failed**, with ESPN's reason, and is never counted as lost to priority | outcome; the slice's distinction between a bad pick and an unwinnable one |
| AC-5 | A claim still pending, or not found on the read-back, is left **unresolved** and nothing is recorded; a cancelled claim is recorded as **cancelled** | invariant I-23 — absence of evidence is not an outcome |
| AC-6 | Every recorded result carries the waiver priority position the claim was filed under, copied from the filing, and is written to the decision log before the page shows it | invariant I-18; NFR-10 |
| AC-7 | A result once recorded is not re-read or overwritten | outcome |
| AC-8 | The waiver page shows a filed, unresolved claim with a **Check result** button, and a resolved claim with its result in words | outcome |

## Acceptance signal

- At season's end, every claim filed from the page has a recorded result, and
  the lost ones name who beat us and where we sat in priority.

## Out of scope

- Changing the scorer to account for priority (the priority-aware slice).
- Resolving claims filed by hand in the ESPN app — only filings this system
  recorded are resolved.
- Running the check on a schedule; it runs when the manager presses the button.

## Carried context

| | |
| --- | --- |
| **Bounded contexts** | Waiver Execution (the claim's terminal states); Signal (the read-back); Ledger (the record) |
| **Aggregates touched** | WaiverClaim — recorded on the waiver decision's `outcome` |
| **Invariants at risk** | Priority position recorded (I-18); outcome from the read-back only (I-23) |
| **Contracts** | None external |
| **NFRs that apply** | Read-back (NFR-09); logged before reported (NFR-10) |
| **Depends on** | Waiver claim filing (shipped) |

## Interface impact

**Does this slice touch a user interface?** Yes — the waiver page's filed
states gain the result. The `ux` artifact is required.

## Open questions

| # | Question | Owner | Blocking? |
| --- | --- | --- | --- |
| Q-1 | Does ESPN report a lost claim at all? **Resolved: yes** — `FAILED_INVALIDPLAYERSOURCE`, with the winner's claim `EXECUTED` in the same window | — | No |
