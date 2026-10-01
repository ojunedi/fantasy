---
id: S-005
slice_id: waiver-claim-filed
status: todo
---

# An approved claim is filed through the API and confirmed, not typed by hand

## Outcome

An approved waiver claim is submitted through ESPN's write endpoint behind the dry-run default and the typed `LIVE`, then confirmed by reading the league back. The system knows a claim was filed, and what it was.

## Contexts

| id | why |
|----|-----|
| BC-waiver | Owns the gate and the filing |
| BC-signal | Reads the league back to confirm |
| BC-ledger | Records the filed claim and its confirmation state |

## Invariants

| id | risk |
|----|------|
| I-12 | The add and drop must still pair legally at the moment of filing, not only at the moment of scoring. A roster that changed in between could make the pairing illegal |
| I-23 | Confirmation must come from reading the league back. The trade write was found returning success without acting, on this same undocumented endpoint — the risk here is identical and already demonstrated |
| I-24 | Dry run is the default and the confirmation is typed per filing. The risk is reusing an authorisation across the add and the drop if they become two requests |
| I-18 | The priority position must be captured at filing time, because that is what makes a later loss interpretable |

## NFRs

| id | applies |
|----|---------|
| NFR-07 | Filing must complete before the Tuesday deadline |
| NFR-09 | Read-back confirmation, same as both existing write paths |
| NFR-11 | Reachable from the web surface, which is the less-protected caller |

## Contracts

No external contracts. The ESPN write endpoint is an integration, already recorded, not a contract this system publishes.

## Open questions

| id | question | owner |
|----|----------|-------|
| — | Is a waiver claim one `ROSTER` transaction with add and drop items, or two requests? One is atomic and preferable; two opens a window where the drop succeeded and the add did not, leaving the roster short | R-01 |
| — | Does a *pending* claim appear on a read before the window processes? If not, confirmation can only verify submission rather than acceptance, and the two must not be conflated in what the manager is told | R-01 |

<!--
Second half of the walking skeleton, and the half that carries the risk. The
first half stops at the brief; this is the layer where a write either happens or
silently does not.

`execute/base.py:32` already declares `waiver_claim` as an action type, so the
executor interface anticipated this. The lineup write posts a `ROSTER`
transaction — a claim is plausibly the same endpoint with add and drop items,
which is why filing by hand was a choice rather than a constraint.

The three-state confirmation from the trade send applies here unchanged:
filed-and-confirmed, filed-but-unconfirmed, and not attempted. Re-filing on an
unconfirmed claim risks a duplicate, and a duplicate waiver claim is worse than
an unverified one.
-->
