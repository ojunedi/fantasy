# Intent — waiver-claim-filed

## Outcome

After the manager marks a waiver recommendation "Intend to claim", they can
file the claim with ESPN from the waiver page — dry run by default, for real
only when they type `LIVE` — and the page tells them whether ESPN actually
shows the claim as pending.

## Who

**Actor:** the manager
**What changes for them:** today an approved claim stops at a recommendation,
and the manager files it by hand in the ESPN app. After this slice the add and
the drop go to ESPN together, and the page says one of three things: filed and
showing as pending, filed but not found on read-back, or not attempted.

## Why now

Second half of the walking skeleton. The waiver scan stops at the brief; this
is where a write either happens or silently does not. The merged approval gate
shipped last so that this is its first new caller rather than a fourth copy
of the rule.

ESPN's own transaction history settled the slice's two open questions: a
claim is **one** waiver transaction carrying an ADD and a DROP item, so the
pair cannot half-succeed; and a filed claim **does** appear on a read as
`PENDING` until the window processes it.

## Acceptance criteria

| # | Criterion | Source |
| --- | --- | --- |
| AC-1 | From an approved waiver decision, filing builds one waiver transaction for my team holding the recommended add and the displaced drop | outcome; open question 1 (one transaction) |
| AC-2 | Filing asks the shared approval gate: only an approved decision confirmed with exactly `LIVE` is sent; any other confirmation is a dry run showing the exact transaction and sending nothing; a decision that is not approved is refused and nothing is built or sent | invariants I-11, I-24 (`WaiverClaim`) |
| AC-3 | Immediately before sending, the league is read fresh: if the drop player is no longer on my roster, or the add player is no longer a free agent or on waivers, the filing is refused, names which player moved, and nothing is sent | invariant I-12 (`WaiverClaim`) |
| AC-4 | After a live send, the league's transactions are read back with the cache bypassed. The claim counts as confirmed only if a pending waiver transaction for my team holds the same add and drop players | invariant I-23; NFR-09 |
| AC-5 | A send ESPN accepts but the read-back cannot find is reported as "filed but not confirmed", tells the manager to check the ESPN app, and does not offer to file again | invariant I-23; the slice's duplicate-claim warning |
| AC-6 | A send ESPN rejects (4xx/5xx) or that fails to reach ESPN is reported as not filed, with ESPN's error, and the manual steps to file it in the app | unhappy path |
| AC-7 | Every live filing attempt is written to the decision log on the waiver decision before the page reports it: the transaction sent, the confirmation state (confirmed / unconfirmed / failed), and my waiver priority position read at filing time | invariant I-18 (`WaiverClaim`); NFR-10 |
| AC-8 | A waiver decision already filed live (confirmed or unconfirmed) cannot be filed again from the page; the page shows the filing state instead of the form | invariant I-24; duplicate-claim warning |
| AC-9 | On the web, the add and drop players come from the stored decision, never from the request | NFR-11 |

## Acceptance signal

- Before the Tuesday deadline, the manager files the week's claim from the
  waiver page and sees it as pending in the ESPN app without typing it there.
- Every claim ESPN shows for this team has a matching filing in the decision
  log, with the priority position it was filed under.

## Out of scope

- Whether the claim cleared or lost to priority — the next slice reads that.
- FAAB bids (this league has none) and claim ordering across several claims.
- Cancelling a filed claim.
- Filing from the command line.

## Carried context

| | |
| --- | --- |
| **Bounded contexts** | Waiver Execution (owns the gate and the filing); Signal (reads the league back); Ledger (records the filing) |
| **Aggregates touched** | WaiverClaim — created by the filing, recorded on the waiver decision |
| **Invariants at risk** | Legal add/drop pair at filing (I-12); priority captured (I-18); confirmed only by read-back (I-23); per-filing `LIVE`, dry run default (I-24); no write without approval (I-11) |
| **Contracts** | None external — ESPN's write endpoint is an integration |
| **NFRs that apply** | Before the Tuesday deadline (NFR-07); read-back confirmation (NFR-09); web is the less-protected caller (NFR-11); logged before reporting (NFR-10) |
| **Depends on** | The waiver add recommendation (shipped); the single approval gate (shipped) |

## Interface impact

**Does this slice touch a user interface?** Yes — the waiver page gains the
filing step after "Intend to claim". The `ux` artifact is required.

## Open questions

| # | Question | Owner | Blocking? |
| --- | --- | --- | --- |
| Q-1 | The first live filing is the first time this payload meets ESPN. Its shape is copied from the claims ESPN's own app filed in this league, but it has never been sent by this system | manager — the first `LIVE` filing is theirs to make | No — dry run shows the exact transaction first |
