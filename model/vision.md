---
product: Fantasy GM
stage: vision
---

# Vision

## Problem

Managing a fantasy football team well requires weekly research across projections, injury reports, waiver wire, and trade market. Without a quantified basis, decisions are made on platform rankings and gut feel, and it is impossible to know at season's end whether overrides were correct.

ESPN ranks players by a single consensus number with no injury adjustment, no waiver-priority logic tied to roster need, and no trade EV case. A manager relying on it is making decisions with less information than the available signal sources already contain.

**Falsifiable:** if ESPN's built-in rankings already outperform any projection-based approach on a like-for-like backtest, this problem statement is wrong and the scope changes.

## Objectives

| id | objective | why_it_matters |
|----|-----------|----------------|
| O-01 | Every lineup decision is made on a projection-backed recommendation, not the platform default | The platform ranking is a single number with no transparency; a projection-backed pick is auditable and improvable |
| O-02 | Every waiver claim clears two bars: better than what it displaces, and worth a roster spot on its own merits | Waiver decisions are currently unassisted. Judging only against my own roster would recommend bad players whenever a position is thin |
| O-03 | Trade proposals carry a quantified rest-of-season EV case before the manager engages a counterparty | Entering a trade negotiation without a number makes it harder to hold a position or walk away |
| O-04 | The agent demonstrably outperforms a naive (start-platform-rank-one) baseline on lineup decisions | Without a number, "the agent is better" is a belief, not a result |
| O-05 | Every decision and override is logged so the manager can see at season's end where to trust the agent | The override log is what turns a season's worth of decisions into a way to improve next year |

## Key Results

| id | objective | key_result | baseline | target | by | measured_how |
|----|-----------|------------|----------|--------|----|--------------|
| KR-01 | O-01 | Weekly lineup recommendation available before Sunday 1 PM kickoff | Ad hoc, manual | 100% of scoring weeks in 2026 season | End of 2026 season | Decision log in decisions.db |
| KR-02 | O-02 | Waiver recommendation generated for each waiver window | Not built | 100% of waiver windows in 2026 season | End of 2026 season | Decision log in decisions.db |
| KR-03 | O-03 | Trade EV delta surfaced for every package the agent proposes | Working — EV delta already ships | 100% of trade proposals carry EV delta | Already met — maintain | DecisionRecord in decisions.db |
| KR-04 | O-04 | Agent lineup score vs. platform-rank naive baseline, p50 per week | Platform rank beats actual decisions by ~3 pts/week over weeks 1–3 of 2026 (optimizer matches platform rank in wks 1–2; beats actual by 8.9 pts in wk 3) | Optimizer beats platform rank by +3 pts/week by end of 2026 season | End of 2026 season | backtest runner |
| KR-05 | O-05 | Override log completeness — every departure from recommendation has a written reason | Working | 100% coverage maintained | Already met — maintain | override_reason column in decisions.db |

## Scope

| id | item | boundary | why |
|----|------|----------|-----|
| SC-01 | Lineup recommendations | in | Core capability — working |
| SC-02 | Waiver wire evaluation | in | Highest-priority gap |
| SC-03 | Trade proposals with EV | in | Working |
| SC-04 | ESPN write API execution — lineup | in | Working — dry-run default, requires LIVE, confirmed by reading the roster back |
| SC-14 | ESPN write API execution — trade send | in | Working as of 2026-09-25, behind dry-run and LIVE. The only irreversible write in the product, and it does not yet confirm by read-back |
| SC-05 | FantasyPros consensus projections | in | ESPN projections are the current source; FantasyPros is the planned upgrade — architecture must keep the projection source pluggable |
| SC-06 | Web dashboard | in | Working — lineup and trades pages |
| SC-07 | Draft tools | out | Different problem, different season phase — no dependency on weekly tooling |
| SC-08 | Mobile app | out | Single-owner tool; a web dashboard already exists |
| SC-09 | Multi-team or multi-user support | out | Single manager, single league — generalizing adds cost with no personal benefit |
| SC-10 | Sleeper write API | out | Sleeper's API is explicitly read-only; no write path exists |
| SC-11 | ESPN's undocumented write endpoint | unchanged | Integrated with as-is; it can be used but cannot be made reliable — dry-run is always the default |
| SC-12 | Human approval gate before any ESPN write | unchanged | Hard requirement — not a choice |
| SC-13 | FantasyCalc as trade value source | unchanged | External dependency — no write or influence path |

## Open questions

1. Does waiver v1 need to model priority order (who picks before me), or just surface which player to target?
2. FantasyPros: scraping or paid API? The free scraping path has rate-limit risk during peak season.
