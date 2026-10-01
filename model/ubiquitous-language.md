---
product: Fantasy GM
stage: domain-design
---

# Ubiquitous Language

The same words in conversation, in this model, and in the code. When they diverge, one of the three is a bug.

Grounded in `src/fantasy_gm/models.py` and the event maps. The `is_not` column does most of the work here — it is easier to agree on than a definition, and it is what stops two contexts quietly merging. The `trap` flag marks terms a builder would get wrong, and it decides what every downstream delivery artifact sees.

Homonyms are kept as separate context-scoped rows on purpose. One word meaning two things in two contexts is evidence of a boundary, not a naming problem to tidy away.

## Terms

| id | term | context | definition | is_not | trap |
|----|------|---------|------------|--------|------|
| T-001 | Score | BC-ledger | Ambiguous on its own and must always be qualified. The weekly scorecard carries five: actual, optimizer, optimal, agent-projected, and per-baseline | Never use bare "score" in a spec or a brief. Five things answer to it | yes |
| T-002 | Actual score | BC-ledger | What the lineup really scored once games finished | Not the projection, not the optimal | |
| T-003 | Optimizer score | BC-ledger | What the optimizer's chosen lineup scored, judged against actuals, using only pre-game data to choose | Not the optimal score — the optimizer could not see the future when it chose | yes |
| T-004 | Hindsight ceiling | BC-ledger | The best lineup that *could* have been set, computed after the fact with actual results. Unreachable in advance by construction | Not a target, and not a benchmark the agent can be judged against. The code still calls this `optimal_score` — renaming it is pending | yes |
| T-005 | Decision regret | BC-ledger | Hindsight ceiling minus actual score. How much the week cost against perfect hindsight | Not a measure of whether the agent was wrong — regret is non-zero even for a perfect decision | yes |
| T-006 | Value | BC-analysis | Ambiguous and always needs qualifying. Means projected points, trade currency, or value above replacement depending on where you are | Never use bare "value" across a context boundary | yes |
| T-007 | Asset value | BC-trade | Rest-of-season projected points scaled by positional scarcity. The currency trades are compared in | Not weekly projected points, and not a market price unless the source says market | yes |
| T-008 | Value above replacement | BC-waiver | How much a candidate beats the worst roster slot it would displace, after the drop cost | Not raw projected points. A high-projection player can have zero value above replacement | yes |
| T-009 | Replacement baseline | BC-waiver | The bar a waiver add must clear to be worth a claim | 🔴 Not yet settled whether it is computed over the whole roster or only startable slots (H-05) | yes |
| T-010 | Locked | BC-lineup | A player whose NFL game has kicked off. ESPN refuses any lineup change involving them | Applies to players only, never to the lineup as a whole. Players lock one at a time through Sunday; use "deadline passed" for the lineup | yes |
| T-011 | Projection | BC-signal | A pre-game estimate of points, stamped with its source and the time it was taken | Not a forecast of the final result and never updated in place — a refresh replaces it wholesale | |
| T-012 | Staleness | BC-signal | The age of a signal at the moment a decision was made, recorded per source | Not whether the data is wrong. Fresh data can be wrong and stale data can be right | yes |
| T-013 | Abstain | BC-analysis | A deliberate refusal to recommend, because the signals cannot support one. A valid outcome | Not an error, not a crash, and not an empty result. An abstention carries evidence | yes |
| T-014 | Proposal | BC-analysis | What the agent produces for the manager to act on, before anything has been sent anywhere | Never a sent trade — that is an offer (T-043). The distinction is load-bearing: a proposal is reversible, an offer is not | yes |
| T-016 | Decision | BC-lineup | A recommendation the manager has responded to, with the response recorded. Includes rejections and holds | Not the same as the agent's output, and not the same as an executed action | |
| T-017 | Override | BC-lineup | The manager departing from the recommendation, with a written reason. Mandatory reason | Not a rejection — an override substitutes something else, a rejection asks for nothing | yes |
| T-018 | Dry run | BC-lineup | A full execution that computes the exact ESPN transaction body and sends nothing. The default | Not a simulation or an approximation — the payload is real, it is simply not transmitted | yes |
| T-019 | LIVE | BC-lineup | The literal, case-sensitive string the manager types to permit a real ESPN write. Required for both the lineup write and the trade send | Not a flag, not a setting, and never persisted — it is typed per execution, every time | yes |
| T-020 | EV delta | BC-trade | Received asset value minus sent asset value, from my side of the trade | Not a probability, and not expected points for the week | |
| T-021 | Fairness | BC-trade | The ratio of the smaller package value to the larger, 0 to 1 | Not advice. A perfectly fair trade can be one I should refuse, and a lopsided one can be right | yes |
| T-022 | Verdict | BC-trade | The win/fair/lose label on a package, judged relative to the size of what I send | Not a recommendation to act, and not the manager's decision | |
| T-023 | Positional scarcity | BC-trade | A multiplier reflecting how steep the drop from starter to replacement is at a position | Not a measure of how good a player is | |
| T-024 | Waiver priority | BC-waiver | Our position in the snake order, which decides who wins a contested claim | Not urgency, not a bid, and not a budget. This league has no FAAB | yes |
| T-025 | Claim cleared | BC-waiver | Nobody ahead in priority wanted the same player, so the add went through | Not the normal outcome. Losing a claim to higher priority is ordinary | yes |
| T-026 | Free agent | BC-waiver | An unrostered player. May or may not require a waiver claim depending on when they were dropped | Not the same as "available" — some free agents are claimable immediately, others sit on waivers | yes |
| T-027 | Naive baseline | BC-ledger | Starting whoever the platform ranks highest, every week, with no analysis | Not a straw man. It is currently ahead of actual decisions by roughly 3 points a week | yes |
| T-028 | Signal | BC-signal | A typed value with a source and an as-of timestamp, inseparable from both | Not raw API data — raw ESPN shapes stop at the adapter and never travel upward | |
| T-030 | FLEX | BC-lineup | A roster slot accepting more than one position, which is what makes lineup assignment a search rather than a sort | Not a position a player has | |
| T-031 | Brief | BC-lineup | The readable document explaining a recommendation, with reasoning per player and signals cited | 🔴 Not a place where a new number may appear. Every number in a brief must come from the analysis (H-08) | yes |
| T-032 | Deadline passed | BC-lineup | The kickoff moment after which the standing lineup is what plays, whatever was recommended | Not "locked" — that is a per-player state. This is a single moment for the week | yes |
| T-033 | Declined | BC-waiver | Us choosing not to file a claim the agent surfaced | Not a rejection by anyone else. The actor is the manager | yes |
| T-034 | Refused | BC-trade | The counterparty turning down an offer we sent | Not "declined" — that word is taken by the waiver case, where *we* are the one saying no | yes |
| T-040 | Signal bundle | BC-signal | Every signal one decision needs, gathered for a week, each member carrying its own source and timestamp | Not a cache. A bundle is per decision type — a lineup bundle holds no trade values | |
| T-041 | Lineup decision | BC-lineup | The manager's response to a lineup proposal, plus the write and the log entry that follow | Not the proposal itself, and not shared with waivers or trades — each has its own | yes |
| T-042 | Waiver claim | BC-waiver | A filed request for an unrostered player, with the drop it requires and the priority it was filed under | Not a decision record. Its outcome is written by other managers' priority, not by us | yes |
| T-043 | Offer | BC-trade | A package actually sent to a counterparty, awaiting their answer. The system can send one; only they can accept it | Not a proposal. Crossing from proposal to offer is the point past which nothing can be undone | yes |
| T-044 | Backtest report | BC-ledger | A replay of past decisions against the naive baseline, using only data available at the time | Not a scorecard for one week — a report spans weeks | |
| T-046 | Input snapshot | BC-lineup | Everything the agent saw, frozen when the decision was recorded | Never updated. A refreshed snapshot destroys the replay guarantee | yes |

<!--
Nearly every row is flagged as a trap, which is high and is correct here.
Fantasy football vocabulary is casually overloaded in ordinary speech — "value",
"score" and "locked" each mean three or four things to a manager mid-conversation
and the ambiguity never causes a problem out loud. In a spec it does.

The score cluster (Score, Actual score, Optimizer score, Hindsight ceiling,
Decision regret) is worth reading together. The distinction that will be got
wrong is optimizer score versus hindsight ceiling: the first is what the agent
achieved, the second is what an oracle would have achieved with knowledge nobody
had. Comparing the agent against the ceiling and calling the gap a failure is
the single most likely misreading of this whole model.

"Scored" as a state name is deliberately absent. It appears as a state on both
the waiver analysis and the backtest report, and rather than two more rows the
Score row carries the warning: never use it bare.
-->

## Naming decisions taken

Three collisions were arbitrated on 2026-10-01. Recorded here because each has a consequence somebody will meet later.

| # | Collision | Decision | Consequence to watch |
|---|-----------|----------|---------------------|
| 1 | Proposal vs. Recommendation | **Proposal wins**, matching the existing code. No rename. | "Proposal" now carries two meanings in trade contexts: what the agent suggested, and what was actually sent to a counterparty. The sent one is irreversible and the suggested one is not, so the two must always be qualified in trade specs. This is a known, accepted ambiguity in the highest-stakes part of the product |
| 2 | Optimizer score vs. optimal score | **Optimal becomes "hindsight ceiling."** Optimizer score unchanged. | The code still has `optimal_score` in `WeeklyScorecard` and the backtest output still prints it. The model and the code disagree until that rename happens — which is a real divergence, not a cosmetic one, because the two numbers appear one line apart in the backtest output |
| 3 | Locked, two meanings | **Locked applies to players only.** The lineup-wide meaning becomes "deadline passed." | Matches `is_locked` and `locks_from_roster` already in the code. The distinction matters because players lock individually across Sunday afternoon, long before the week's last kickoff |

