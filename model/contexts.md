---
scope: Fantasy GM
substep: consolidate
---

# Bounded Contexts

Re-cut from the events after the first proposal was blocked for reproducing the archetype's lifecycle rather than deriving boundaries from what the events actually say. The evidence that settled it came from the code: `optimize_lineup` is imported by eight modules and is *called by* trade valuation, so lineup and trade analysis cannot be peer contexts — one invokes the other. What does differ per decision type is execution: whether the system can write the outcome at all, whether it is reversible, and whether the outcome is even ours to decide.

## Contexts

| id | name | purpose | primary_actor | cut_on | classification | status |
|----|------|---------|---------------|--------|----------------|--------|
| BC-signal | Signal Kernel | Fetch, normalise, and freshness-check every external source. One vocabulary across all three decision types, and the only place that knows what ESPN's undocumented shapes look like | R-02 | E-006,E-104,E-205 | generic | confirmed |
| BC-analysis | Decision Analysis | The deterministic core. `optimize_lineup` is the shared kernel at its centre — trade valuation and waiver scoring both resolve to it, so it is one context by evidence, not convenience | R-02 | E-009,E-108,E-209 | core | confirmed |
| BC-lineup | Lineup Execution | Own the lineup brief, the approval gate, and the ESPN write. Reversible until kickoff, which is what makes it the safer of the two write paths | R-01 | E-013 | core | confirmed |
| BC-waiver | Waiver Execution | Own the waiver brief, the gate, and the claim instructions. Cannot be written by the system, and the outcome is decided by snake priority rather than by us | R-01 | E-215 | core | confirmed |
| BC-trade | Trade Execution | Own the trade brief, the gate, and the send. The system *can* write here — and this is the only write it cannot undo. The outcome, however, belongs to the counterparty | R-01 | E-114 | core | confirmed |
| BC-ledger | Decision Ledger | Every decision with its input snapshot, every override with its reason, and the backtest that replays history against the naive baseline | R-02 | E-308 | supporting | confirmed |

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

## ACL Mappings

One `acl` relationship exists: everything ESPN returns passes through the adapter boundary and nothing above it ever sees a raw ESPN shape. The mappings below are what that translation actually does, and the lossy ones are where a bug will eventually come from.

| relationship | external | internal | lossy | notes |
|--------------|----------|----------|-------|-------|
| REL-01 | `statSourceId == 1` rows on a player entry | PlayerProjection | yes | ESPN mixes projections and actuals in one collection, distinguished only by this discriminator. Reading the wrong source id silently yields last week's results as this week's forecast |
| REL-01 | `lineupSlotId` integer | RosterSlot position | yes | An opaque integer per slot kind, undocumented and league-shape dependent. The mapping is a hand-maintained lookup; a new slot kind arrives as an unmapped integer rather than an error |
| REL-01 | `scoringPeriodId` | Current week | | Read straight through. Deliberately not derived from a season start date — ESPN's own notion of "this week" is authoritative, including the odd week it disagrees with the calendar |
| REL-01 | `injuryStatus` string | PlayerStatus | yes | ESPN's vocabulary does not map one-to-one onto ours and has gained values mid-season before. An unrecognised string must degrade to unknown, never to active |
| REL-01 | Player entry id | Player identity | yes | Bridges to nflverse through a third-party crosswalk. A player missing from it has no usage or injury data, and the failure mode is silent absence rather than an error |
| REL-01 | `playerPoolEntry.onTeamId` | Roster membership | | Zero means unrostered. Reliable, and it is the whole basis for whether a player is available to claim |
| REL-01 | Scoring settings collection | ScoringRules | | Read live on first run and cached, never hardcoded — multipliers vary between leagues that both call themselves PPR |
| REL-01 | Write response body | Execution outcome | yes | The worst of these. A 200 does not prove the roster moved; confirming a write requires reading the roster back. Trusting the response is how a silent no-op becomes a lost week *(H-01)* |

<!--
Six of eight mappings are lossy, which is the real cost of integrating with an
undocumented API and is worth stating plainly rather than burying.

ACL-01 and ACL-08 are the two that would cost a real week. The first can hand
the optimizer last week's actuals believing them to be this week's projections.
The second can report success for a write that did nothing.

ACL-04 and ACL-05 share a failure shape: both degrade silently. An unknown
injury string must not become "active", and a player missing from the id
crosswalk must not look like a player with no injuries.
-->

## Open questions and next steps

| # | Question | Who resolves | What breaks if it is wrong |
|---|----------|--------------|---------------------------|
| 1 | Is the replacement baseline the whole roster or only startable slots? *(H-05)* | Manager | Waiver scoring produces a number with no agreed meaning. Every waiver recommendation inherits the ambiguity, and the first one that looks wrong will be unarguable either way |
| 2 | What freshness threshold makes each signal type too stale? *(H-02)* | Manager | The freshness invariant has nothing to enforce, so the bundle can never legitimately report stale and abstention becomes unreachable |
| 3 | Does waiver scoring need to model priority order? *(H-03)* | Manager | If it does not, the scorer can keep recommending players we were never going to get, and nothing in the model notices |
| 4 | Which name wins: proposal or recommendation? | Manager | Specs diverge slice by slice. "Proposal" additionally collides with a sent trade offer, which is a different thing with a different lifecycle |
| 5 | Does "optimal score" get renamed? | Manager | The highest-risk collision in the glossary. Confusing optimizer score with optimal score reports a succeeding agent as failing |
