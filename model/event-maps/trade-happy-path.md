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
| E-101 | TradeOpportunityIdentified | SCN-005 | | Agent | | yes | | Supervisor detects roster surplus/deficit or manager initiates with a brief |
| E-102 | RoSValuesRetrieved | SCN-005 | E-101 | SYS-FANTASYCALC | | | | Rest-of-season values fetched; network call — may be unavailable |
| E-103 | RosterNeedsAssessed | SCN-005 | E-101 | Agent | | | | Runs in parallel with E-102 — surplus/deficit by position vs. league replacement |
| E-104 | NewsAndInjuryContextFetched | SCN-005 | E-101 | SYS-ESPN-NEWS | | | | Runs in parallel with E-102, E-103 — recent news on trade targets |
| E-105 | TradePackagesGenerated | SCN-005 | E-102,E-103,E-104 | Agent | | yes | | Join — ranked packages that address the deficit; max 3 |
| E-106 | TradeEVComputed | SCN-005 | E-105 | Agent | | | | RoS projection × positional scarcity × EV delta per package |
| E-107 | LineupImpactAssessed | SCN-005 | E-106 | Agent | | | | Optimizer re-run on post-trade roster to quantify starting lineup effect |
| E-108 | TradeBriefGenerated | SCN-005 | E-107 | Agent | | | | Rationale + counterparty pitch per package |
| E-109 | TradeProposalPresentedToManager | SCN-005 | E-108 | R-01 | | yes | | Manager sees all packages with EV and fairness before deciding |
| E-110 | ManagerApprovedTradePackage | SCN-005 | E-109 | R-01 | | yes | | Manager selects one package; approval gate |
| E-111 | DecisionLogged | SCN-005 | E-110 | Agent | | | | DecisionRecord with approved package index and full evaluation snapshot |
| E-112 | InAppStepsGenerated | SCN-005 | E-110 | Agent | | | | Runs in parallel with E-111 — step-by-step instructions for ESPN trade UI |
| E-113 | TradeOfferReadyToSend | SCN-005 | E-112 | R-01 | | yes | | Manager has everything needed; counterparty must accept manually |

## Assumptions

| id | assumption | source |
|----|------------|--------|
| ASM-010 | FantasyCalc API is reachable when the agent runs | assumed |
| ASM-011 | The manager's brief is specific enough to narrow the search | assumed |
| ASM-012 | The counterparty must accept in the ESPN app — there is no automated send path | kb |

## Commands

<!-- Filled in during tactical storming -->

## Policies

<!-- Filled in during tactical storming -->
