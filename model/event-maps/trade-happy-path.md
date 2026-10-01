---
id: SCN-005
scenario_id: trade-happy-path
journey: J-02
kind: happy-path
status: agreed
---

# Manager evaluates and sends a trade offer — happy path

The GM supervisor identifies a roster imbalance (surplus at one position,
deficit at another). It fetches rest-of-season trade values from FantasyCalc
and scans the league's rosters for targets in parallel with assessing roster
needs and fetching news context. Trade packages are generated with EV delta,
fairness assessment, and lineup impact for each. The manager selects a package;
the agent generates the in-app steps to send the offer in the ESPN app.

## Events

| id | event | scenario | after | actor | context | pivotal | hotspot | notes |
|----|-------|----------|-------|-------|---------|---------|---------|-------|
| E-101 | TradeOpportunityIdentified | SCN-005 | | R-02 | BC-signal | yes | H-04 | Who triggers this is unresolved — agent scanning proactively and manager asking are different processes with the same name |
| E-102 | RoSValuesRetrieved | SCN-005 | E-101 | SYS-FANTASYCALC | BC-signal | | | Rest-of-season values fetched; network call — may be unavailable |
| E-103 | RosterNeedsAssessed | SCN-005 | E-101 | R-02 | BC-signal | | | Runs in parallel with E-102 — surplus/deficit by position vs. league replacement |
| E-104 | NewsAndInjuryContextFetched | SCN-005 | E-101 | SYS-ESPN-NEWS | BC-signal | | | Runs in parallel with E-102, E-103 — recent news on trade targets |
| E-105 | TradePackagesGenerated | SCN-005 | E-102,E-103,E-104 | R-02 | BC-analysis | yes | | Join — candidate packages addressing the deficit, unranked; ranking needs the EV that does not exist yet |
| E-106 | TradeEVComputed | SCN-005 | E-105 | R-02 | BC-analysis | | | RoS projection × positional scarcity × EV delta per candidate |
| E-107 | LineupImpactAssessed | SCN-005 | E-106 | R-02 | BC-analysis | | | Optimizer re-run on post-trade roster to quantify starting lineup effect |
| E-115 | TradePackagesRanked | SCN-005 | E-107 | R-02 | BC-analysis | | | Now rankable — top 3 kept, the rest discarded |
| E-108 | TradeBriefGenerated | SCN-005 | E-115 | R-02 | BC-trade | | | Rationale + counterparty pitch per package |
| E-109 | TradeProposalPresentedToManager | SCN-005 | E-108 | R-01 | BC-trade | yes | | Manager sees all packages with EV and fairness before deciding |
| E-110 | ManagerApprovedTradePackage | SCN-005 | E-109 | R-01 | BC-trade | yes | | Manager selects one package; approval gate |
| E-111 | DecisionLogged | SCN-005 | E-110 | R-02 | BC-ledger | | | DecisionRecord with approved package index and full evaluation snapshot |
| E-112 | InAppStepsGenerated | SCN-005 | E-110 | R-02 | BC-trade | | | Runs in parallel with E-111 — step-by-step instructions for ESPN trade UI |
| E-113 | TradeOfferReadyToSend | SCN-005 | E-112 | R-01 | BC-trade | | | Manager has everything needed |
| E-114 | TradeOfferSent | SCN-005 | E-113 | R-01 | BC-trade | yes | | Manager sent it in the ESPN app. The system loses visibility here — everything after this belongs to the counterparty |

## Assumptions

| id | assumption | source |
|----|------------|--------|
| ASM-010 | FantasyCalc API is reachable when the agent runs | assumed |
| ASM-011 | The manager's brief is specific enough to narrow the search | assumed |
| ASM-012 | The offer can be sent by the system through ESPN's undocumented write endpoint, but only the counterparty can accept it. Sending is automatable; the outcome is not | kb |

## Commands

| id | command | event | actor | aggregate | context |
|----|---------|-------|-------|-----------|---------|
| C-101 | FetchTradeSignals | E-102 | R-02 | AGG-signal-bundle | BC-signal |
| C-102 | GenerateTradePackages | E-105 | R-02 | AGG-trade-analysis | BC-analysis |
| C-103 | ApproveTradePackage | E-110 | R-01 | AGG-trade-offer | BC-trade |

## Policies

| id | when | then | crosses_context |
|----|------|------|-----------------|
| P-101 | E-105 | Compute EV delta and lineup impact per candidate package, then rank (within BC-analysis) | |
| P-102 | E-115 | Generate the trade brief with a counterparty pitch (BC-analysis → BC-trade) | yes |
| P-103 | E-110 | Log the decision AND generate in-app steps (BC-trade → BC-ledger) | yes |
