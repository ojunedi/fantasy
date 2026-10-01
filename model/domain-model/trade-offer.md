---
product: Fantasy GM
stage: domain-design
aggregate: AGG-trade-offer
---

# AGG-trade-offer

The trade brief, the gate, the sent offer, and the counterparty's answer. Owned by trade execution.

**This is the only irreversible action in the product, and the system can perform it.** `execute/trade_api.py` sends real ESPN trade transactions behind a dry-run default and a typed `LIVE` confirmation. The first version of this model said trades could not be written, which was true when the decision record was first written and has not been true since September — the discovery pass caught the drift.

Identity is an opaque offer id, not week plus counterparty. A revised offer to the same manager in the same week is a *new* offer by I-13, and keying on the natural tuple would make it an edit of the one already sent.

## Invariants

| id | aggregate | rule | enforced_in |
|----|-----------|------|-------------|
| I-13 | AGG-trade-offer | An offer's terms are immutable once it reaches sent. Revising it creates a new offer with a new identity | TradeOffer.send |
| I-20 | AGG-trade-offer | A sent offer records which of the proposed packages was chosen, and keeps the ones that were not | TradeOffer.send |
| I-21 | AGG-trade-offer | Acceptance is terminal. No transition out of it exists, and none may be added | TradeOffer.accept |
| I-22 | AGG-trade-offer | A package the counterparty has already refused is never offered again. The refusal is the reason the unchosen packages are kept | TradeOffer.send |
| I-23 | AGG-trade-offer | A send is confirmed only by reading the league's transaction state back. A non-error response is not evidence the offer exists | TradeOffer.confirm |
| I-24 | AGG-trade-offer | No send occurs without an explicit per-send confirmation from the manager. Dry run is the default and authorisation is never persisted | TradeOffer.send |
| I-27 | AGG-trade-offer | Every number in a brief appears in the analysis output it was generated from. A brief may rephrase a number, never introduce one | TradeOffer.brief |

<!--
I-23 is the invariant the code does not yet satisfy, and it is the reason this
aggregate was challenged. The lineup write has the equivalent rule and honours
it; the trade write currently returns success on any non-4xx response. The
asymmetry runs the wrong way — the reversible action verifies itself and the
irreversible one does not.

I-22 exists because the agent feeds rejected proposals back into the next run's
prompt to stop it re-proposing them. That behaviour is real and load-bearing, and
nothing stated it as a rule until now.
-->

## Transitions

| aggregate | from | to | event |
|-----------|------|----|-------|
| AGG-trade-offer | new | briefed | E-108 |
| AGG-trade-offer | briefed | presented | E-109 |
| AGG-trade-offer | presented | approved | E-110 |
| AGG-trade-offer | approved | recorded | E-111 |
| AGG-trade-offer | recorded | ready | E-112 |
| AGG-trade-offer | ready | ready | E-113 |
| AGG-trade-offer | ready | sent | E-114 |
| AGG-trade-offer | sent | accepted | E-120 |
| AGG-trade-offer | sent | refused | E-121 |
| AGG-trade-offer | sent | expired | E-122 |
| AGG-trade-offer | accepted | accepted | E-123 |
| AGG-trade-offer | accepted | closed | E-124 |
| AGG-trade-offer | refused | closed | E-124 |
| AGG-trade-offer | expired | closed | E-124 |

<!--
`closed` is the terminal state; `recorded` is the mid-flight one where the
decision is logged but nothing has been sent. The two were the same word in the
first draft, which made an offer in `recorded` unreadable — nobody could tell
whether it still needed sending.

The counterparty's answer is `refused`, not `declined`. On a waiver claim
"declined" means we chose not to file; two different actors need two different
words.

`accepted → accepted` on E-123 is the roster change landing. The offer is already
final; what changes is the world around it, which is why E-125 invalidates a
lineup decision rather than anything here.
-->

## Members

| id | name | aggregate | kind | notes |
|----|------|-----------|------|-------|
| ENT-counterparty-pitch | Counterparty pitch | AGG-trade-offer | entity | An entity, not a value object: its whole purpose is attribution. Which pitch produced which answer is the one thing the value model cannot predict, and answering it later requires the pitch to be individually addressable — the same argument that makes the override reason an entity |
