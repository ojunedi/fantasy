# Intent — one-approval-gate

## Outcome

Whether a write to ESPN goes ahead is decided by one rule, and the command
line and the web app both call it — so the manager gets the same answer to
"will this write for real?" whichever surface they use.

## Who

**Actor:** the manager
**What changes for them:** nothing they can see when everything is in order.
What changes is that the two surfaces can no longer disagree. Today they
already do: the command line accepts `LIVE ` with a trailing space as a real
write, and the web app treats it as a dry run. And the web app's write step
never checks that the decision was approved at all — a hand-built request
carrying `LIVE` would write without one.

## Why now

Filing waiver claims is next, and it needs this gate. Building it on top of
three copies of the rule — the command line's lineup write, its trade send,
and the web's lineup write — would make a fourth. Merging now, while no copy
is known to be wrong in a way that has cost anything, is the cheapest this
will ever be.

## Acceptance criteria

| # | Criterion | Source |
| --- | --- | --- |
| AC-1 | A write runs live only when the decision is approved or overridden **and** the confirmation is exactly `LIVE`. Every other combination is a dry run or a refusal, never a live write | invariant I-11, invariant I-24 (`Decision`) |
| AC-2 | A decision that is pending, rejected or declined is refused at the gate on both surfaces: the executor is not called, not even for a dry run, and the refusal names the decision's state | invariant I-11 (`Decision`); unhappy path — the web write step skips this check today |
| AC-3 | The confirmation is compared exactly and case-sensitively, with no trimming: `LIVE` is live; `live`, `Live`, `LIVE ` , ` LIVE`, an empty string and anything else are a dry run — identically on both surfaces | glossary *LIVE*; invariant I-24; the stricter of today's two copies |
| AC-4 | An overridden decision whose written reason is missing or only whitespace is refused at the gate, with the refusal saying the reason is missing | invariant I-09 (`Decision`) |
| AC-5 | Authorisation is worked out fresh for every execution from the stored decision and the confirmation typed for that execution. Nothing about it is saved: a second execution of the same decision without `LIVE` is a dry run, even straight after a live one | invariant I-24 (`Decision`) |
| AC-6 | The command line's lineup write, the command line's trade send and the web app's lineup write all decide through the same function, and no other code compares anything against the `LIVE` string | outcome |
| AC-7 | On the web, the decision's approval state comes from the decision log, never from the request: no form field or header can make an unapproved decision pass the gate | NFR-11 (the web is the less-protected caller) |
| AC-8 | For every combination of decision state (pending, approved, overridden with a reason, overridden without one, rejected, declined) and confirmation (the AC-3 list), the gate gives the same verdict whichever surface asks | outcome; resolves the slice's open question |

## Acceptance signal

- A lineup or trade written for real always has an approved or overridden
  decision behind it in the decision log — checked at season's end by
  matching ESPN transactions against the log.
- When the waiver filing slice starts, it adds no new `LIVE` comparison of
  its own.

## Out of scope

- Filing waiver claims (the next slice; it becomes this gate's first new caller).
- Changing the approval step itself — how a decision becomes approved,
  overridden or rejected.
- Changing the executors' signatures or how a dry run is built.
- Sending trades from the web app, which does not exist today.

## Carried context

| | |
| --- | --- |
| **Bounded contexts** | Lineup Execution (owns the gate, and two of today's copies); Trade Execution (the third copy); Waiver Execution (next caller) |
| **Aggregates touched** | Decision — read only; this slice changes no decision state |
| **Invariants at risk** | No write without a recorded approval (I-11); a written reason on every departure (I-09); authorisation per execution, never persisted (I-24) |
| **Contracts** | None external |
| **NFRs that apply** | The web surface is the less-protected caller and must not be trusted (NFR-11) |
| **Depends on** | Nothing |

## Interface impact

**Does this slice touch a user interface?** No.

The manager interacts through the existing command-line prompt and the
existing web write step. The only visible change is a refusal message where
an unapproved decision used to go through; it reuses the existing execution
result display.

## Open questions

| # | Question | Owner | Blocking? |
| --- | --- | --- | --- |
| Q-1 | Merge into one function, or keep the copies and test them for equivalence? **Resolved: merge** — the manager chose it, and the waiver filing slice would otherwise add another copy | manager | No — resolved |
