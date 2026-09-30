# Intent — <slice-id>

## Outcome

<One sentence, user-observable. "A billing clerk can submit a draft invoice and
see it queued for approval.">

## Who

**Actor:** <the role named in the event storm — not "the user">
**What changes for them:** <…>

## Why now

<What this unblocks, or what risk it retires. If this is the walking skeleton,
say so.>

## Acceptance criteria

Numbered, independently testable. Each cites where it came from.

| # | Criterion | Source |
| --- | --- | --- |
| AC-1 | Submitting a Draft invoice with ≥1 line item transitions it to Submitted and publishes exactly one `InvoiceSubmitted` event | outcome |
| AC-2 | Submitting a Draft invoice with 0 line items returns 422 `INVOICE_EMPTY`, leaves state unchanged, and publishes no event | invariant I-1 (`Invoice`) |
| AC-3 | Submitting an already-Submitted invoice is idempotent — 200, no second event | unhappy path (event storm) |
| AC-4 | p99 of `POST /invoices/{id}/submit` stays under 300ms at 200 rps | NFR (billing-service) |

**Source** is one of: `outcome`, `invariant <id> (<Aggregate>)`, `NFR (<service>)`,
`contract (<path>)`, `unhappy path (event storm)`, `hotspot <id>`.

> Every invariant of every aggregate this slice touches, that this slice could
> violate, needs a criterion. That check is the main thing this document exists
> to force.

## Acceptance signal

How we would know it worked **in the world** — not "the tests pass".

- <e.g. clerks stop emailing support about stuck invoices>
- <e.g. submitted-to-approved median drops below 4h>

## Out of scope

Binding.

- <…>

## Carried context

Copied from `model/slices.md` so this file stands alone.

| | |
| --- | --- |
| **Bounded contexts** | |
| **Aggregates touched** | |
| **Invariants at risk** | |
| **Contracts** | |
| **NFRs that apply** | |
| **Depends on** | |

## Interface impact

**Does this slice touch a user interface?** Yes / No

<If yes, the `ux` artifact is required. If no, say what the actor interacts with
instead — API, event, CLI.>

## Open questions

| # | Question | Owner | Blocking? |
| --- | --- | --- | --- |
