# ADR-002: A write is believed only after reading the state back

**Status:** accepted · **Date:** 2026-10-01

## Context

ESPN's write endpoints are reverse-engineered and undocumented. They can return a non-error status without having done anything — a silent no-op that is indistinguishable from success at the HTTP layer.

The lineup path already read the roster back. The trade send did not: it returned success on any non-4xx response. The asymmetry ran the wrong way, because the trade path is the one whose outcome cannot be undone once a counterparty accepts.

Discovery also found the surrounding documents asserting that trades could not be written at all — true when D-019 was recorded, false since the send path shipped on 2026-09-25.

## Decision

No write is reported as successful on the strength of its response. After a successful POST, the system re-reads the relevant state with the cache bypassed and confirms the change is really there.

The trade result carries a three-state `confirmed` rather than folding into a boolean, because the middle state is the one that needs distinct handling:

- **confirmed** — POSTed and verified present
- **unconfirmed** — POSTed, not found on read-back. Check the app; do *not* re-send
- **not attempted** — dry run, or the POST failed outright

## Options rejected

**Trust the status code.** Rejected on evidence. ACL mapping notes already recorded that a 200 from this endpoint proves nothing, and the lineup path had already stopped trusting it.

**Retry on an unconfirmed send.** Rejected, and this is the important one. Two identical pending offers is a worse state than one unverified offer — the counterparty can accept either, and nothing in the system would reconcile the duplicate. Re-sending is the obvious wrong reflex, so the failure message says not to.

**Report an unconfirmed send as a failure.** Rejected because it invites exactly that re-send. The POST did happen; claiming otherwise is a different lie from the one we were trying to fix.

## Consequences

Every live write now costs one extra read. At one decision per week this is free.

Confirmation matches on the set of player ids, not a transaction id, because the POST response does not reliably carry one. Two structurally identical offers to the same counterparty are therefore indistinguishable to the check. For one manager in a 12-team league this has no practical consequence; trusting an id that may not arrive would be worse.

The unconfirmed state needs somewhere to live in the decision record. It currently surfaces only in the CLI output.
