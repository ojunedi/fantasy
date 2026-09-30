---
scope: Fantasy GM
substep: consolidate
---

# Bounded Contexts

Re-cut from the events after the first proposal was blocked for reproducing the archetype's lifecycle rather than deriving boundaries from what the events actually say. The evidence that settled it came from the code: `optimize_lineup` is imported by eight modules and is *called by* trade valuation, so lineup and trade analysis cannot be peer contexts — one invokes the other. What does differ per decision type is execution: whether the system can write the outcome at all, whether it is reversible, and whether the outcome is even ours to decide.

## Contexts

| id | name | purpose | primary_actor | cut_on | classification | status |
|----|------|---------|---------------|--------|----------------|--------|
| BC-signal | Signal Kernel | Fetch, normalise, and freshness-check every external source. One vocabulary across all three decision types, and the only place that knows what ESPN's undocumented shapes look like | R-02 | E-007,E-105,E-207 | generic | candidate |
| BC-analysis | Decision Analysis | The deterministic core. `optimize_lineup` is the shared kernel at its centre — trade valuation and waiver scoring both resolve to it, so it is one context by evidence, not convenience | R-02 | E-009,E-108,E-209 | core | candidate |
| BC-lineup | Lineup Execution | Own the lineup brief, the approval gate, and the ESPN write. The only decision the system can execute itself, and reversible until kickoff | R-01 | E-013 | core | candidate |
| BC-waiver | Waiver Execution | Own the waiver brief, the gate, and the claim instructions. Cannot be written by the system, and the outcome is decided by snake priority rather than by us | R-01 | E-215 | core | candidate |
| BC-trade | Trade Execution | Own the trade brief, the gate, and the offer instructions. Cannot be written, cannot be reversed once accepted, and the outcome belongs to the counterparty | R-01 | E-114 | core | candidate |
| BC-ledger | Decision Ledger | Every decision with its input snapshot, every override with its reason, and the backtest that replays history against the naive baseline | R-02 | E-308 | supporting | candidate |

## Relationships

| id | upstream | downstream | pattern | integration |
|----|----------|------------|---------|-------------|
| REL-01 | SYS-ESPN | BC-signal | acl | sync · ESPN's undocumented read shapes translated into league types at the adapter boundary; nothing above BC-signal may see a raw ESPN payload |
| REL-02 | BC-signal | BC-analysis | published-language | async · scored signal bundle with per-source freshness stamps |
| REL-03 | BC-analysis | BC-lineup | customer-supplier | async · optimized lineup with per-player reasoning |
| REL-04 | BC-analysis | BC-waiver | customer-supplier | async · candidates ranked by value above replacement |
| REL-05 | BC-analysis | BC-trade | customer-supplier | async · packages with EV delta, fairness, and lineup impact |
| REL-06 | BC-lineup | BC-ledger | customer-supplier | async · decision record after every approval or override |
| REL-07 | BC-waiver | BC-ledger | customer-supplier | async · decision record, including no-claim decisions |
| REL-08 | BC-trade | BC-ledger | customer-supplier | async · decision record naming which package was acted on |
| REL-09 | BC-ledger | BC-analysis | conformist | async · the backtest replays the live optimizer and must conform to its interface — a second implementation would measure something else |
| REL-10 | BC-lineup | BC-trade | shared-kernel | sync · both resolve roster legality and starting-lineup value through `optimize_lineup`; trade valuation calls it directly to compute roster impact |

## Grouping delta

| Capability | Became | Moved? | Why |
|---|---|---|---|
| CAP-01 Signal Gathering | BC-signal | reclassified | Survives as a boundary but not as a peer. It speaks one identical language across all three decision tracks, which makes it a generic subdomain underneath them rather than the first stage of a pipeline. It also gained the anti-corruption layer the first cut missed entirely — ESPN's undocumented shapes have to stop somewhere, and this is the only sensible place |
| CAP-02 Decision Analysis | BC-analysis | no — but for a new reason | Held together, and the first cut was right by accident. The reason is `trade_value.roster_starting_total()` calling `optimize_lineup()`: trade analysis depends on lineup analysis as a subroutine. Splitting by decision type would put a synchronous cross-context call inside trade evaluation |
| CAP-03 Recommendation | dissolved | yes | Folded into each execution context. It held only "turn numbers into prose" plus one query per decision type — a presentation layer promoted to a peer. The brief belongs with the gate that consumes it, because a brief the manager cannot act on is not a deliverable |
| CAP-04 Human Approval | split three ways | yes | The finding that forced the re-cut. Lineup forfeits at a hard deadline and is reversible until then; a waiver claim can be lost to higher priority; a trade is irreversible the moment a counterparty clicks accept. Three consistency regimes were sharing one boundary |
| CAP-05 Execution | split with approval | yes | Stays married to the gate it follows, but now three times over. `execute/` had already split this way in code — `lineup_plan.py`, `trade_plan.py`, `trade_api.py` — which is the strongest available evidence that the boundary is real |
| CAP-06 Audit & Evaluation | BC-ledger | no | The only capability that survived unexamined and deserved to. Read-only consumer of everything else, on its own weekly and end-of-season clock, with a different audience |

**Five of six moved.** The first pass had five of six holding, which was the signal that consolidation had not actually run.
