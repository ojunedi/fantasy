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
| SCN-002 | lineup-manager-override | Manager starts a different player with a written reason | J-01 | alternate | | | assumed |
| SCN-003 | lineup-agent-abstains | Insufficient signal quality — agent refuses to commit to a recommendation | J-01 | alternate | | | assumed |
| SCN-004 | lineup-espn-api-fails | Lineup submission fails — Playwright browser fallback used | J-01 | exception | | | assumed |
| SCN-005 | trade-happy-path | Agent proposes packages, manager selects one, in-app steps delivered | J-02 | happy-path | | | agreed |
| SCN-006 | trade-agent-abstains | No favorable trade found — agent abstains with the evidence it was missing | J-02 | alternate | | | assumed |
| SCN-007 | trade-manager-rejects-all | Manager rejects all packages — re-run with a different brief | J-02 | alternate | | | assumed |
| SCN-008 | waiver-happy-path | Best add identified, claim approved, in-app steps delivered | J-03 | happy-path | | | agreed |
| SCN-009 | waiver-no-add | Agent recommends no change — manager confirms hold | J-03 | alternate | | | assumed |
| SCN-010 | perf-review-positive | Backtest shows optimizer outperforming naive baseline | J-04 | happy-path | | | agreed |
| SCN-011 | perf-review-underperforming | Backtest shows flat or negative delta — root cause identified | J-04 | alternate | | | assumed |

## Aggregates

<!-- Filled in during tactical storming -->

## Queries

<!-- Filled in during tactical storming -->
