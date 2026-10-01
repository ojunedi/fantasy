# Discovery digest

Projected from `model/`. Do not edit — edit the model and re-sync.

## Problem

Managing a fantasy football team well requires weekly research across projections, injury reports, waiver wire, and trade market. Without a quantified basis, decisions are made on platform rankings and gut feel, and it is impossible to know at season's end whether overrides were correct.

ESPN ranks players by a single consensus number with no injury adjustment, no waiver-priority logic tied to roster need, and no trade EV case. A manager relying on it is making decisions with less information than the available signal sources already contain.

## Objectives

What this is for. A slice that does not serve one of these needs a reason.

- **O-01** Every lineup decision is made on a projection-backed recommendation, not the platform default — The platform ranking is a single number with no transparency; a projection-backed pick is auditable and improvable
- **O-02** Every waiver claim clears two bars: better than what it displaces, and worth a roster spot on its own merits — Waiver decisions are currently unassisted. Judging only against my own roster would recommend bad players whenever a position is thin
- **O-03** Trade proposals carry a quantified rest-of-season EV case before the manager engages a counterparty — Entering a trade negotiation without a number makes it harder to hold a position or walk away
- **O-04** The agent demonstrably outperforms a naive (start-platform-rank-one) baseline on lineup decisions — Without a number, "the agent is better" is a belief, not a result
- **O-05** Every decision and override is logged so the manager can see at season's end where to trust the agent — The override log is what turns a season's worth of decisions into a way to improve next year

## Success is measured by

| objective | key result | baseline | target | by |
|---|---|---|---|---|
| O-01 | Weekly lineup recommendation available before Sunday 1 PM kickoff | Ad hoc, manual | 100% of scoring weeks in 2026 season | End of 2026 season |
| O-02 | Waiver recommendation generated for each waiver window | Not built | 100% of waiver windows in 2026 season | End of 2026 season |
| O-03 | Trade EV delta surfaced for every package the agent proposes | Working — EV delta already ships | 100% of trade proposals carry EV delta | Already met — maintain |
| O-04 | Agent lineup score vs. platform-rank naive baseline, p50 per week | Platform rank beats actual decisions by ~3 pts/week over weeks 1–3 of 2026 (optimizer matches platform rank in wks 1–2; beats actual by 8.9 pts in wk 3) | Optimizer beats platform rank by +3 pts/week by end of 2026 season | End of 2026 season |
| O-05 | Override log completeness — every departure from recommendation has a written reason | Working | 100% coverage maintained | Already met — maintain |

## Out of bounds

Not in this programme. Adjacent good ideas here are candidate slices, not scope.

- Not building: **Draft tools** — Different problem, different season phase — no dependency on weekly tooling
- Not building: **Mobile app** — Single-owner tool; a web dashboard already exists
- Not building: **Multi-team or multi-user support** — Single manager, single league — generalizing adds cost with no personal benefit
- Not building: **Sleeper write API** — Sleeper's API is explicitly read-only; no write path exists
- Do not modify: **ESPN's undocumented write endpoint** — Integrated with as-is; it can be used but cannot be made reliable — dry-run is always the default
- Do not modify: **Human approval gate before any ESPN write** — Hard requirement — not a choice
- Do not modify: **FantasyCalc as trade value source** — External dependency — no write or influence path

## Delivery approach and constraints

- **Approach:** Extend in place — The domain model is sound, the agent architecture is settled, and the deterministic core already has the right extension points. The gap is feature coverage (waivers, projection quality), not a structural problem

Imposed from outside. Each one rules something out:

| id | kind | constraint | rules out |
|---|---|---|---|
| CON-01 | team | Single engineer, part-time project | No parallel tracks; new capabilities are sequential. Waiver and projection work cannot both land mid-season |
| CON-02 | commercial | ESPN's write API is reverse-engineered and undocumented | Every execution path must default to dry-run; a silent break is always possible. Playwright browser fallback exists for that case |
| CON-03 | deadline | Fantasy decisions only matter during September–January | Work done outside the season cannot be validated against real decisions until the next season |
| CON-04 | data | FantasyPros free scraping has rate-limit risk at peak times | A paid API key or a local cache strategy is needed before FantasyPros becomes the primary projection source |

## Bounded contexts

- **BC-signal** Signal Kernel — Fetch, normalise, and freshness-check every external source. One vocabulary across all three decision types, and the only place that knows what ESPN's undocumented shapes look like
- **BC-analysis** Decision Analysis — The deterministic core. `optimize_lineup` is the shared kernel at its centre — trade valuation and waiver scoring both resolve to it, so it is one context by evidence, not convenience
- **BC-lineup** Lineup Execution — Own the lineup brief, the approval gate, and the ESPN write. Reversible until kickoff, which is what makes it the safer of the two write paths
- **BC-waiver** Waiver Execution — Own the waiver brief, the gate, and the claim instructions. Cannot be written by the system, and the outcome is decided by snake priority rather than by us
- **BC-trade** Trade Execution — Own the trade brief, the gate, and the send. The system *can* write here — and this is the only write it cannot undo. The outcome, however, belongs to the counterparty
- **BC-ledger** Decision Ledger — Every decision with its input snapshot, every override with its reason, and the backtest that replays history against the naive baseline

## Context map

| upstream | downstream | pattern | integration |
|---|---|---|---|
| SYS-ESPN | BC-signal | acl | sync · ESPN's undocumented read shapes translated into league types at the adapter boundary; nothing above BC-signal may see a raw ESPN payload |
| BC-signal | BC-analysis | published-language | async · scored signal bundle with per-source freshness stamps |
| BC-analysis | BC-lineup | customer-supplier | async · optimized lineup with per-player reasoning |
| BC-analysis | BC-waiver | customer-supplier | async · candidates ranked by value above replacement |
| BC-analysis | BC-trade | customer-supplier | async · packages with EV delta, fairness, and lineup impact |
| BC-lineup | BC-ledger | customer-supplier | async · decision record after every approval or override |
| BC-waiver | BC-ledger | customer-supplier | async · decision record, including no-claim decisions |
| BC-trade | BC-ledger | customer-supplier | async · decision record naming which package was acted on |
| BC-ledger | BC-analysis | conformist | async · the backtest replays the live optimizer and must conform to its interface — a second implementation would measure something else |
| BC-lineup | BC-trade | shared-kernel | sync · both resolve roster legality and starting-lineup value through `optimize_lineup`; trade valuation calls it directly to compute roster impact |

## Aggregates and invariants

Every invariant a slice could violate needs an acceptance criterion.

- **AGG-signal-bundle** SignalBundle (BC-signal) — identity: week + season + decisionType
    - I-01: Every signal in the bundle carries a source and an as-of timestamp; a signal without provenance cannot enter it
    - I-02: The bundle reports complete only if every member is within its own type's freshness threshold; otherwise it reports stale and names which members failed
- **AGG-lineup-analysis** LineupAnalysis (BC-analysis) — identity: week + season
    - I-03: Every optimized lineup is legal: each player occupies a slot their position is eligible for, and every starter slot is filled
    - I-04: A locked player keeps the slot they are already in. A lineup that moves one is not a better lineup, it is a write ESPN rejects with 409
    - I-05: An abstention names which signals were stale and by how much. An abstention with no evidence is indistinguishable from a crash
- **AGG-waiver-analysis** WaiverAnalysis (BC-analysis) — identity: week + season
    - I-06: A candidate clears the *relative* bar only if it beats the worst rostered player — the one it would displace — on rest-of-season value
    - I-30: A candidate must additionally project as startable within the next three weeks, measured against a roster assumed **fully available**. A bye week or a short-term injury creating the opening does not count as a path to starting
    - I-28: A candidate clears the *absolute* bar only if it ranks inside the league-wide startable tier at its position — team count × starting slots at that position, derived from league settings rather than hardcoded
    - I-29: A candidate is recommended only if it clears **both** bars. Clearing one is not a weaker recommendation — it is not a recommendation
    - I-17: The no-candidate outcome names the closest candidate, which bar it failed, and by how much. "Nothing available" with no numbers cannot be reviewed later
- **AGG-trade-analysis** TradeAnalysis (BC-analysis) — identity: week + season + counterparty
    - I-07: A package cannot enter the ranked state until expected value has been computed for every candidate. Ranking before the metric exists orders by nothing
    - I-08: Both rosters are legal after the proposed trade. A package leaving either side unable to field a lineup is not a package
- **AGG-lineup-decision** LineupDecision (BC-lineup) — identity: decisionId
    - I-09: A decision that departs from the proposal carries a non-empty written reason. The transition to overridden is rejected without one
    - I-10: The input snapshot is written once, when the decision is recorded, and never updated. A replayed decision must see exactly what the agent saw
    - I-11: No ESPN write occurs from a decision that is not in the approved or overridden state
    - I-16: A write is confirmed only by reading the roster back. A success response alone does not move the decision to confirmed
    - I-25: Every number in a brief appears in the analysis output it was generated from. A brief may rephrase a number, never introduce one
- **AGG-waiver-claim** WaiverClaim (BC-waiver) — identity: claimId
    - I-12: The roster stays legal: an add requires a drop whenever the roster is already at maximum size
    - I-18: A claim records the priority position it was filed under. Without it, a lost claim cannot be distinguished from a bad recommendation
    - I-19: A hold decision is recorded with the same weight as a claim. Choosing not to act is a decision and belongs in the log
    - I-26: Every number in a brief appears in the analysis output it was generated from. A brief may rephrase a number, never introduce one
- **AGG-trade-offer** TradeOffer (BC-trade) — identity: offerId
    - I-13: An offer's terms are immutable once it reaches sent. Revising it creates a new offer with a new identity
    - I-20: A sent offer records which of the proposed packages was chosen, and keeps the ones that were not
    - I-21: Acceptance is terminal. No transition out of it exists, and none may be added
    - I-22: A package the counterparty has already refused is never offered again. The refusal is the reason the unchosen packages are kept
    - I-23: A send is confirmed only by reading the league's transaction state back. A non-error response is not evidence the offer exists
    - I-24: No send occurs without an explicit per-send confirmation from the manager. Dry run is the default and authorisation is never persisted
    - I-27: Every number in a brief appears in the analysis output it was generated from. A brief may rephrase a number, never introduce one
- **AGG-backtest-report** BacktestReport (BC-ledger) — identity: season + throughWeek
    - I-14: Every projection used to score a past week predates that week's first kickoff. A single post-hoc value invalidates the whole report

## Language traps

Terms a builder would otherwise get wrong. Full glossary is in the model.

- **Score** (BC-ledger) — Ambiguous on its own and must always be qualified. The weekly scorecard carries five: actual, optimizer, optimal, agent-projected, and per-baseline. NOT: Never use bare "score" in a spec or a brief. Five things answer to it
- **Optimizer score** (BC-ledger) — What the optimizer's chosen lineup scored, judged against actuals, using only pre-game data to choose. NOT: Not the optimal score — the optimizer could not see the future when it chose
- **Hindsight ceiling** (BC-ledger) — The best lineup that *could* have been set, computed after the fact with actual results. Unreachable in advance by construction. NOT: Not a target, and not a benchmark the agent can be judged against. The code still calls this `optimal_score` — renaming it is pending
- **Decision regret** (BC-ledger) — Hindsight ceiling minus actual score. How much the week cost against perfect hindsight. NOT: Not a measure of whether the agent was wrong — regret is non-zero even for a perfect decision
- **Value** (BC-analysis) — Ambiguous and always needs qualifying. Means projected points, trade currency, or value above replacement depending on where you are. NOT: Never use bare "value" across a context boundary
- **Asset value** (BC-trade) — Rest-of-season projected points scaled by positional scarcity. The currency trades are compared in. NOT: Not weekly projected points, and not a market price unless the source says market
- **Value above replacement** (BC-waiver) — How much a candidate beats the worst roster slot it would displace, after the drop cost. NOT: Not raw projected points. A high-projection player can have zero value above replacement
- **Replacement baseline** (BC-waiver) — The bar a waiver add must clear to be worth a claim. NOT: 🔴 Not yet settled whether it is computed over the whole roster or only startable slots (H-05)
- **Locked** (BC-lineup) — A player whose NFL game has kicked off. ESPN refuses any lineup change involving them. NOT: Applies to players only, never to the lineup as a whole. Players lock one at a time through Sunday; use "deadline passed" for the lineup
- **Staleness** (BC-signal) — The age of a signal at the moment a decision was made, recorded per source. NOT: Not whether the data is wrong. Fresh data can be wrong and stale data can be right
- **Abstain** (BC-analysis) — A deliberate refusal to recommend, because the signals cannot support one. A valid outcome. NOT: Not an error, not a crash, and not an empty result. An abstention carries evidence
- **Proposal** (BC-analysis) — What the agent produces for the manager to act on, before anything has been sent anywhere. NOT: Never a sent trade — that is an offer (T-043). The distinction is load-bearing: a proposal is reversible, an offer is not
- **Override** (BC-lineup) — The manager departing from the recommendation, with a written reason. Mandatory reason. NOT: Not a rejection — an override substitutes something else, a rejection asks for nothing
- **Dry run** (BC-lineup) — A full execution that computes the exact ESPN transaction body and sends nothing. The default. NOT: Not a simulation or an approximation — the payload is real, it is simply not transmitted
- **LIVE** (BC-lineup) — The literal, case-sensitive string the manager types to permit a real ESPN write. Required for both the lineup write and the trade send. NOT: Not a flag, not a setting, and never persisted — it is typed per execution, every time
- **Fairness** (BC-trade) — The ratio of the smaller package value to the larger, 0 to 1. NOT: Not advice. A perfectly fair trade can be one I should refuse, and a lopsided one can be right
- **Waiver priority** (BC-waiver) — Our position in the snake order, which decides who wins a contested claim. NOT: Not urgency, not a bid, and not a budget. This league has no FAAB
- **Claim cleared** (BC-waiver) — Nobody ahead in priority wanted the same player, so the add went through. NOT: Not the normal outcome. Losing a claim to higher priority is ordinary
- **Free agent** (BC-waiver) — An unrostered player. May or may not require a waiver claim depending on when they were dropped. NOT: Not the same as "available" — some free agents are claimable immediately, others sit on waivers
- **Naive baseline** (BC-ledger) — Starting whoever the platform ranks highest, every week, with no analysis. NOT: Not a straw man. It is currently ahead of actual decisions by roughly 3 points a week
- **Brief** (BC-lineup) — The readable document explaining a recommendation, with reasoning per player and signals cited. NOT: 🔴 Not a place where a new number may appear. Every number in a brief must come from the analysis (H-08)
- **Deadline passed** (BC-lineup) — The kickoff moment after which the standing lineup is what plays, whatever was recommended. NOT: Not "locked" — that is a per-player state. This is a single moment for the week
- **Declined** (BC-waiver) — Us choosing not to file a claim the agent surfaced. NOT: Not a rejection by anyone else. The actor is the manager
- **Refused** (BC-trade) — The counterparty turning down an offer we sent. NOT: Not "declined" — that word is taken by the waiver case, where *we* are the one saying no
- **Lineup decision** (BC-lineup) — The manager's response to a lineup proposal, plus the write and the log entry that follow. NOT: Not the proposal itself, and not shared with waivers or trades — each has its own
- **Waiver claim** (BC-waiver) — A filed request for an unrostered player, with the drop it requires and the priority it was filed under. NOT: Not a decision record. Its outcome is written by other managers' priority, not by us
- **Offer** (BC-trade) — A package actually sent to a counterparty, awaiting their answer. The system can send one; only they can accept it. NOT: Not a proposal. Crossing from proposal to offer is the point past which nothing can be undone
- **Input snapshot** (BC-lineup) — Everything the agent saw, frozen when the decision was recorded. NOT: Never updated. A refreshed snapshot destroys the replay guarantee

## Services and data ownership

Exactly one writer per aggregate.

| service | contexts | writes |
|---|---|---|
| SVC-gm | BC-signal,BC-analysis,BC-lineup,BC-waiver,BC-trade,BC-ledger | AGG-signal-bundle,AGG-lineup-analysis,AGG-waiver-analysis,AGG-trade-analysis,AGG-lineup-decision,AGG-waiver-claim,AGG-trade-offer,AGG-backtest-report |

## Tech stack

- language: **Python** 3.11 (SVC-gm)
- build: **uv** — (SVC-gm)
- framework: **LangGraph** 1.x (SVC-gm)
- framework: **LangChain** — (SVC-gm)
- runtime: **Anthropic Claude** claude-haiku-4-5 (SVC-gm)
- datastore: **SQLite** — (SVC-gm)
- cache: **Parquet on disk** — (SVC-gm)
- framework: **Polars** — (SVC-gm)
- framework: **Pydantic** v2 (SVC-gm)
- framework: **httpx** — (SVC-gm)
- framework: **tenacity** — (SVC-gm)
- framework: **FastAPI** — (SVC-gm)
- frontend: **Jinja2 + htmx** htmx vendored (SVC-gm)
- runtime: **uvicorn** — (SVC-gm)
- testing: **pytest** — (SVC-gm)
- framework: **nflreadpy** — (SVC-gm)

## NFR budgets

Copy the numbers into specs. Never paraphrase a budget.

| id | service | requirement |
|---|---|---|
| NFR-01 | SVC-gm | A weekly lineup run completes before the manager loses patience — target under 5 minutes wall clock. Unmeasured; the LLM calls dominate and the deterministic core is milliseconds |
| NFR-02 | SVC-gm | A full-season backtest completes in under 2 minutes with a warm parquet cache |
| NFR-03 | SVC-gm | At most 1 ESPN request per second, self-imposed |
| NFR-04 | SVC-gm | At most 3 LLM calls per run by default, shared between the main loop and sub-agents, with one further call reserved so the agent can always explain itself |
| NFR-05 | SVC-gm | Provider request ceilings: Anthropic 20/min, Google 4/min, Groq 1/min |
| NFR-06 | SVC-gm | The lineup decision must be executable before Sunday 1 PM kickoff. Missing it forfeits the week |
| NFR-07 | SVC-gm | The waiver claim must be filed before the Tuesday night deadline |
| NFR-08 | SVC-gm | No uptime requirement. The tool is started when needed and is expected to be absent otherwise |
| NFR-09 | SVC-gm | A write is believed only after reading state back. A provider success response is never sufficient evidence |
| NFR-10 | SVC-gm | Every decision is written to SQLite before its run reports completion |
| NFR-11 | SVC-gm | The web surface should bind loopback-only with exactly one worker |
| NFR-12 | SVC-gm | Backtest projections must predate the games they score. One post-hoc value invalidates the run |

## Open questions that affect delivery

- **H-01** When both ESPN write paths fail, how does the manager find out in time? (owner: R-01)
- **H-02** What freshness threshold makes a signal too stale to optimise over? (owner: R-01)
- **H-03** Does the waiver recommendation need to model priority order, or only name the target? (owner: R-01)
- **H-04** Who initiates the trade journey — does the agent scan proactively, or does the manager ask? (owner: R-01)
- **H-06** Is anything watching the clock? A recommendation can go unread until kickoff and nothing currently notices (owner: R-01)
- **H-07** Can the system tell a declined offer from one still sitting unanswered? (owner: R-01)
- **H-08** What stops a generated brief from asserting something the optimizer did not compute? (owner: R-01)

## Full detail

`model/` — vision, journeys, functions, event-maps, contexts, domain-model, ubiquitous-language, architecture, nfrs, slices. `decisions/` for rationale.
