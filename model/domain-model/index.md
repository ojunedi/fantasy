---
product: Fantasy GM
stage: domain-design
---

# Domain Model

Split by aggregate — the transitions table alone outgrew the row cap. Each aggregate's invariants, transitions and members live in `domain-model/<aggregate>.md`; this index carries only what you need to pick one.

Contexts live in `contexts.md`; the words live in `ubiquitous-language.md`.

**The aggregate boundaries here were corrected after a consistency pass.** The first version kept one decision record shared across lineup, waiver and trade, and left the three analysis aggregates running through states their own context did not own. Both were the context re-cut not being carried all the way down. Analysis now terminates where analysis ends, and each execution context owns its own decision aggregate.

## Aggregates

| id | name | context | identity | states | terminal |
|----|------|---------|----------|--------|----------|
| AGG-signal-bundle | SignalBundle | BC-signal | week + season + decisionType | gathering, complete, stale | complete, stale |
| AGG-lineup-analysis | LineupAnalysis | BC-analysis | week + season | optimized, abstained | optimized, abstained |
| AGG-waiver-analysis | WaiverAnalysis | BC-analysis | week + season | scored, candidate-found, none-cleared | candidate-found, none-cleared |
| AGG-trade-analysis | TradeAnalysis | BC-analysis | week + season + counterparty | candidates, evaluated, ranked | ranked |
| AGG-lineup-decision | LineupDecision | BC-lineup | decisionId | briefed, presented, approved, overridden, unactioned, recorded, executed, confirmed, failed, exhausted, invalidated | confirmed, exhausted, invalidated |
| AGG-waiver-claim | WaiverClaim | BC-waiver | claimId | briefed, presented, approved, declined, recorded, ready, submitted, cleared, lost, closed | closed |
| AGG-trade-offer | TradeOffer | BC-trade | offerId | briefed, presented, approved, recorded, ready, sent, accepted, refused, expired, closed | closed |
| AGG-backtest-report | BacktestReport | BC-ledger | season + throughWeek | replayed, scored, reviewed | reviewed |

<!--
Three analysis aggregates rather than one because they key differently:
a lineup is per week, a trade is per week *and* counterparty. One aggregate
would need a null counterparty for two of the three.

`AGG-signal-bundle` keys on decision type as well because the three gather
different sources — a lineup bundle holds no FantasyCalc values and a trade
bundle holds no per-candidate injury rows. A single weekly bundle would be a
union of all three and could never legitimately report complete.

The three execution aggregates all end at `recorded` or later: an outcome that
happened but was never logged is an outcome nobody can review, which is the one
failure the evaluation objective cannot tolerate.
-->

## Read Models

| id | name | context | built_from | staleness |
|----|------|---------|------------|-----------|
| RM-roster-view | RosterView | BC-signal | E-002,E-003,E-004 | ≤ 15 min — bounded by the slowest upstream refresh |
| RM-lineup-brief | LineupBrief | BC-lineup | E-008,E-009 | synchronous — generated per run, never cached across runs |
| RM-trade-brief | TradeBrief | BC-trade | E-115,E-108 | synchronous, recomputed on read: market values move, so a cached brief quotes a stale price |
| RM-waiver-brief | WaiverBrief | BC-waiver | E-208,E-209 | synchronous per run |
| RM-backtest-scorecard | BacktestScorecard | BC-ledger | E-306,E-308 | ≤ 1 week — rebuilt after each week resolves |
| RM-override-log | OverrideLog | BC-ledger | E-021,E-022 | ≤ 1 week |
| RM-unactioned-log | UnactionedLog | BC-ledger | E-052,E-053 | ≤ 1 week |
| RM-claim-history | ClaimHistory | BC-waiver | E-215,E-216,E-230 | ≤ 1 week — one waiver cycle |

<!--
The trade brief recomputing on read is a correctness requirement, not a
performance note, and it is already how the web layer behaves: when FantasyCalc
is unreachable the page drops every value column rather than showing a cached
number as though it were current.

RM-lineup-brief is synchronous because a brief that outlives its run describes a
roster that may have changed — E-125 exists precisely because a mid-week trade
acceptance can invalidate one.
-->
