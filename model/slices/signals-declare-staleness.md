---
id: S-010
slice_id: signals-declare-staleness
status: todo
---

# The agent declines to answer when its signals are too stale to trust

## Outcome

Each signal type has a freshness threshold. When any signal a decision depends on is past it, the bundle reports stale, the agent abstains instead of optimising, and the manager is told which signals were old and by how much.

## Contexts

| id | why |
|----|-----|
| BC-signal | Owns freshness and the thresholds |
| BC-analysis | Owns the decision to abstain rather than compute |

## Invariants

| id | risk |
|----|------|
| I-02 | The bundle must report complete only if *every* member is fresh, and must name the failures. The risk is a threshold so generous that nothing ever trips it, which is indistinguishable from not having one |
| I-05 | An abstention must carry the staleness evidence. An abstention with no numbers is indistinguishable from a crash |
| I-01 | Thresholds compare against the as-of stamp. A signal without provenance cannot be assessed, and must not default to fresh |

## NFRs

| id | applies |
|----|---------|
| NFR-01 | Abstaining is faster than computing. The run should end early rather than gather everything first |

## Contracts

No external contracts. This system publishes no API and no messages — the
`Contracts` table is for endpoints and published events, and there are none to
reference. The domain events this slice introduces are internal and already
mapped in `event-maps/`.

## Open questions

| id | question | owner |
|----|----------|-------|
| H-02 | The thresholds themselves. Per-signal hours, a single global figure, or abstain only when a *starter's* status is unresolved rather than on age alone — the third is narrower and may match the real risk better | R-01 |

<!--
This slice is what makes an existing claim true. The abstain tool is wired, the
invariant is written, and two documents name abstention as the degradation
strategy for ESPN read failures — but nothing computes "too stale", so it cannot
fire. A mitigation that cannot fire is not a mitigation, and the resilience
model now says so explicitly.

Sequenced after the waiver work on purpose: thresholds are easier to choose with
three decision types to choose them against than with two.
-->
