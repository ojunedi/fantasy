---
scope: Fantasy GM
substep: strategic
---

# Event Maps

One event map per **scenario**. A scenario is one way a journey can go: its
base use case — the happy path — or one of the alternate use cases that branch off it.

This file is routing only. The flow itself lives in `event-maps/<scenario_id>.md`.

## Scenarios

| id | scenario_id | name | journey | kind | branches_from | rejoins | status |
|----|-------------|------|---------|------|---------------|---------|--------|
| SCN-001 | lineup-happy-path | Lineup recommendation accepted and executed | J-01 | happy-path | | | agreed |
| SCN-002 | lineup-manager-override | Manager starts a different player with a written reason | J-01 | alternate | E-010 | E-014 | agreed |
| SCN-003 | lineup-agent-abstains | Insufficient signal quality — agent refuses to commit to a recommendation | J-01 | alternate | E-007 | | agreed |
| SCN-004 | lineup-espn-api-fails | Lineup submission fails — Playwright browser fallback used | J-01 | exception | E-013 | E-014 | agreed |
| SCN-005 | trade-happy-path | Agent proposes packages, manager selects one, in-app steps delivered | J-02 | happy-path | | | agreed |
| SCN-006 | trade-agent-abstains | No favorable trade found — agent abstains with the evidence it was missing | J-02 | alternate | | | assumed |
| SCN-007 | trade-manager-rejects-all | Manager rejects all packages — re-run with a different brief | J-02 | alternate | | | assumed |
| SCN-008 | waiver-happy-path | Best add identified, claim approved, in-app steps delivered | J-03 | happy-path | | | agreed |
| SCN-009 | waiver-no-add | Agent recommends no change — manager confirms hold | J-03 | alternate | E-207 | | agreed |
| SCN-010 | perf-review-positive | Backtest shows optimizer outperforming naive baseline | J-04 | happy-path | | | agreed |
| SCN-011 | perf-review-underperforming | Backtest shows flat or negative delta — root cause identified | J-04 | alternate | | | assumed |
| SCN-012 | waiver-claim-lost-to-priority | Someone ahead in snake order claimed the same player | J-03 | alternate | E-215 | | agreed |
| SCN-013 | lineup-deadline-missed | Kickoff arrives with the recommendation unread | J-01 | exception | E-010 | | agreed |
| SCN-014 | trade-offer-resolved | Counterparty accepts, declines, or lets the offer expire | J-02 | alternate | E-114 | | agreed |

## Aggregates

| id | aggregate | context | emits |
|----|-----------|---------|-------|
| AGG-signal-bundle | SignalBundle | BC-signal | E-002,E-003,E-004,E-005,E-006,E-030,E-102,E-103,E-104,E-202,E-203,E-204,E-205 |
| AGG-lineup-analysis | LineupAnalysis | BC-analysis | E-007,E-008,E-031 |
| AGG-waiver-analysis | WaiverAnalysis | BC-analysis | E-206,E-207,E-208,E-220,E-232 |
| AGG-trade-analysis | TradeAnalysis | BC-analysis | E-105,E-106,E-107,E-115 |
| AGG-lineup-decision | LineupDecision | BC-lineup | E-009,E-010,E-011,E-012,E-013,E-014,E-020,E-021,E-022,E-023,E-024,E-040,E-041,E-042,E-043,E-044,E-050,E-051,E-052,E-053,E-125 |
| AGG-waiver-claim | WaiverClaim | BC-waiver | E-209,E-210,E-211,E-212,E-213,E-214,E-215,E-216,E-217,E-221,E-222,E-223,E-224,E-230,E-231 |
| AGG-trade-offer | TradeOffer | BC-trade | E-108,E-109,E-110,E-111,E-112,E-113,E-114,E-120,E-121,E-122,E-123,E-124 |
| AGG-backtest-report | BacktestReport | BC-ledger | E-301,E-302,E-303,E-304,E-305,E-306,E-307,E-308 |

<!--
The first pass had one DecisionRecord spanning all three decision types and a
BacktestReport wrongly claiming the decision-logged events. Both were symptoms
of the same mistake: approval modelled as one context. A waiver claim and a
trade offer have different lifecycles — a claim can be lost to priority, an
offer can be accepted by someone else — so they are separate consistency
boundaries, not rows in a shared one.
-->

## Queries

| id | query | read_model | actor | context |
|----|-------|-----------|-------|---------|
| Q-001 | Current roster with projections and injury status | RosterView | R-01 | BC-signal |
| Q-002 | This week's lineup recommendation with per-player reasoning | LineupBrief | R-01 | BC-lineup |
| Q-003 | Trade packages with EV delta, fairness, and lineup impact | TradeBrief | R-01 | BC-trade |
| Q-004 | Waiver candidates ranked by value above replacement | WaiverBrief | R-01 | BC-waiver |
| Q-005 | Optimizer vs. naive baseline delta by week | BacktestScorecard | R-01 | BC-ledger |
| Q-006 | Every decision where the manager departed from the recommendation | OverrideLog | R-01 | BC-ledger |
| Q-007 | Recommendations presented but never actioned, with forgone value | UnactionedLog | R-01 | BC-ledger |
| Q-008 | Waiver claims filed and whether they cleared | ClaimHistory | R-01 | BC-waiver |
