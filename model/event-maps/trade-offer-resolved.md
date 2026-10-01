---
id: SCN-014
scenario_id: trade-offer-resolved
journey: J-02
kind: alternate
status: agreed
---

# The counterparty answers

The offer was sent and the other manager did something with it: accepted,
declined, or let it sit until it expired. All three are modelled together
because from this system's point of view they are one moment — the point at
which an outcome we do not control becomes a fact.

Acceptance is the only genuinely irreversible thing in the whole product. The
process archetype says so, and the first draft of these maps stopped one event
short of it.

## Events

| id | event | scenario | after | actor | context | pivotal | hotspot | notes |
|----|-------|----------|-------|-------|---------|---------|---------|-------|
| E-120 | CounterpartyAccepted | SCN-014 | | SYS-ESPN | BC-trade | yes | | Branches from the offer being sent. Irreversible — both rosters change and nothing can undo it |
| E-121 | CounterpartyDeclined | SCN-014 | | SYS-ESPN | BC-trade | yes | | Runs as a sibling outcome, not after acceptance. Rosters unchanged |
| E-122 | OfferExpiredUnanswered | SCN-014 | | SYS-ESPN | BC-trade | yes | H-07 | Third sibling outcome. Unresolved whether the system ever learns this happened or simply stops hearing anything |
| E-123 | RosterChangedByTrade | SCN-014 | E-120 | SYS-ESPN | BC-trade | yes | | Every downstream recommendation built on the old roster is now stale, including this week's lineup |
| E-124 | TradeOutcomeLogged | SCN-014 | E-120,E-121,E-122 | R-02 | BC-ledger | yes | | Join on all three outcomes. The only way to learn whether the pitch worked, which is the one thing the EV model cannot predict |
| E-125 | LineupRecommendationInvalidated | SCN-014 | E-123 | R-02 | BC-lineup | yes | | A mid-week roster change invalidates a lineup brief already presented. Path re-enters the lineup journey from the start |

## Assumptions

| id | assumption | source |
|----|------------|--------|
| ASM-040 | A trade acceptance is visible through ESPN's read API on the next roster fetch | assumed |
| ASM-041 | Declines and expiries may be silent — the system may only be able to infer them from the offer no longer being open | assumed |

## Commands

| id | command | event | actor | aggregate | context |
|----|---------|-------|-------|-----------|---------|
| C-104 | InvalidateStaleRecommendations | E-125 | R-02 | AGG-lineup-decision | BC-lineup |

## Policies

| id | when | then | crosses_context |
|----|------|------|-----------------|
| P-104 | E-123 | Invalidate any lineup recommendation built on the pre-trade roster and re-run (BC-trade → BC-lineup) | yes |
| P-105 | E-124 | Record which pitch produced which answer — the EV model cannot predict counterparty behaviour, so this is the only source (BC-trade → BC-ledger) | yes |
