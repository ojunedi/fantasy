## Purpose

<New capabilities only. One or two sentences on what this capability is for.
Omit this section entirely when writing a delta for an existing capability.>

<!-- trace-prefix: INVSUB -->

<!--
Declare the prefix ONCE per capability, on the file that creates it. Every
scenario in this capability is numbered under it, and that id is what a test
is named after. Pick something short and recognisable — 5 to 8 letters from
the capability path. It must not already be in use: `trace.mjs check` fails a
prefix two capabilities share, because an id under it means two things.

A delta against an EXISTING capability inherits the prefix from the live spec
and does not redeclare it.
-->

## ADDED Requirements

### Requirement: <Name>

The system SHALL <normative statement>. Use SHALL/MUST; avoid should/may.

Serves: AC-1, AC-2

#### Scenario: INVSUB-01 — <Happy path name>

- **GIVEN** an Invoice in Draft state with 2 line items and a verified supplier
- **WHEN** the Billing Clerk submits it
- **THEN** the Invoice transitions to Submitted
- **AND** an `InvoiceSubmitted` event is published with `{invoiceId, supplierId, total}`
- **AND** the Drafts read model no longer contains it

#### Scenario: INVSUB-02 — <Failure path name>

- **GIVEN** an Invoice in Draft state with 0 line items
- **WHEN** the Billing Clerk submits it
- **THEN** the request is rejected with `INVOICE_EMPTY`
- **AND** the Invoice remains in Draft
- **AND** no event is published

<!--
Say what does NOT happen — the absent event, the unchanged state. Those
assertions are what catch partial failures.

Scenarios MUST use exactly four hashtags. Three fails silently.
Every requirement needs at least one scenario.

EVERY SCENARIO CARRIES AN ID: `#### Scenario: PREFIX-NN — <name>`.

The id is the anchor the whole pipeline hangs on. It is globally unique, so
`grep -rn INVSUB-02` has exactly one meaning repo-wide. It survives archiving,
because OpenSpec carries the scenario header into `openspec/specs/**` verbatim
— which makes the live spec self-tracing long after this change is archived.
And it survives rewording, because it is not derived from the scenario text.

An AC number could never do any of that: `AC-2` means something different in
every slice, so it collides the moment a repo has more than a few.

Ids are APPEND-ONLY within a capability. Never renumber to close a gap, and
never reuse the id of a scenario you removed — a retired id must stay retired,
or an old test silently starts claiming a new behaviour.

`trace.mjs backfill --change <id>` assigns ids to a spec that has none.
-->

## MODIFIED Requirements

<!--
Copy the ENTIRE requirement block from openspec/specs/<capability-path>/spec.md,
then edit. Partial content loses detail at archive time. Header text must match
the original exactly.

Copy the scenario ids with it, unchanged. A scenario you add to a modified
requirement takes the NEXT free id for this capability — count from the live
spec and every change still in flight, not from this file, or two slices in
parallel will both allocate the same number.

If you are adding a new concern without changing existing behaviour, use ADDED.
-->

## REMOVED Requirements

### Requirement: <Name>

**Reason**: <why it is going>
**Migration**: <what consumers should do instead>

---

<!--
Interfaces, errors, and data belong here too when they are part of the
observable contract:

| Code | When | HTTP | Retryable | User-facing message |
| --- | --- | --- | --- | --- |
| `INVOICE_EMPTY` | Submit with no line items | 422 | no | "Add at least one line item." |

Event payloads: fields, types, ordering key, delivery semantics. At-least-once
is the default — state what makes the consumer safe under duplicates.

Keep implementation out. If the implementation can change without changing
externally visible behaviour, it does not belong in the spec.
-->
