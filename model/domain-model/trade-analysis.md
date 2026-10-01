---
product: Fantasy GM
stage: domain-design
aggregate: AGG-trade-analysis
---

# AGG-trade-analysis

Owned by the analysis context. Builds candidate packages, values them, and ranks them. Terminates at ranked — the brief, the gate and the offer belong to trade execution.

## Invariants

| id | aggregate | rule | enforced_in |
|----|-----------|------|-------------|
| I-07 | AGG-trade-analysis | A package cannot enter the ranked state until expected value has been computed for every candidate. Ranking before the metric exists orders by nothing | TradeAnalysis.rank |
| I-08 | AGG-trade-analysis | Both rosters are legal after the proposed trade. A package leaving either side unable to field a lineup is not a package | TradeAnalysis.evaluate |

## Transitions

| aggregate | from | to | event |
|-----------|------|----|-------|
| AGG-trade-analysis | new | candidates | E-105 |
| AGG-trade-analysis | candidates | evaluated | E-106 |
| AGG-trade-analysis | evaluated | evaluated | E-107 |
| AGG-trade-analysis | evaluated | ranked | E-115 |

## Members

| id | name | aggregate | kind | notes |
|----|------|-----------|------|-------|
| ENT-asset-value | AssetValue | AGG-trade-analysis | value-object | A market snapshot. Values move, so a stored one is evidence of what the market said then, never what it says now |
| ENT-scarcity | Positional scarcity | AGG-trade-analysis | value-object | A multiplier relative to league average — scoring-system agnostic by construction, which is why it survives a league settings change |
