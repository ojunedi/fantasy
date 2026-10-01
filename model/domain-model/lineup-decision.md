---
product: Fantasy GM
stage: domain-design
aggregate: AGG-lineup-decision
---

# AGG-lineup-decision

The manager's response to a lineup proposal, and everything that follows from it: the brief, the gate, the ESPN write, and the log entry. Owned by lineup execution.

This is the aggregate that was wrong before the consistency pass. It was a single decision record shared across lineup, waiver and trade — three different lifecycles with three different terminal states, one of which is written by a counterparty and another by a rival's waiver priority. Each execution context now owns its own.

## Invariants

| id | aggregate | rule | enforced_in |
|----|-----------|------|-------------|
| I-09 | AGG-lineup-decision | A decision that departs from the proposal carries a non-empty written reason. The transition to overridden is rejected without one | LineupDecision.override |
| I-10 | AGG-lineup-decision | The input snapshot is written once, when the decision is recorded, and never updated. A replayed decision must see exactly what the agent saw | LineupDecision.record |
| I-11 | AGG-lineup-decision | No ESPN write occurs from a decision that is not in the approved or overridden state | LineupDecision.execute |
| I-16 | AGG-lineup-decision | A write is confirmed only by reading the roster back. A success response alone does not move the decision to confirmed | LineupDecision.confirm |
| I-25 | AGG-lineup-decision | Every number in a brief appears in the analysis output it was generated from. A brief may rephrase a number, never introduce one | LineupDecision.brief |

## Transitions

| aggregate | from | to | event |
|-----------|------|----|-------|
| AGG-lineup-decision | new | briefed | E-009 |
| AGG-lineup-decision | briefed | presented | E-010 |
| AGG-lineup-decision | presented | approved | E-011 |
| AGG-lineup-decision | presented | overridden | E-021 |
| AGG-lineup-decision | presented | unactioned | E-051 |
| AGG-lineup-decision | approved | recorded | E-012 |
| AGG-lineup-decision | overridden | recorded | E-022 |
| AGG-lineup-decision | unactioned | recorded | E-052 |
| AGG-lineup-decision | recorded | executed | E-013 |
| AGG-lineup-decision | recorded | executed | E-023 |
| AGG-lineup-decision | executed | confirmed | E-014 |
| AGG-lineup-decision | executed | confirmed | E-024 |
| AGG-lineup-decision | executed | failed | E-040 |
| AGG-lineup-decision | failed | confirmed | E-043 |
| AGG-lineup-decision | failed | exhausted | E-044 |
| AGG-lineup-decision | confirmed | invalidated | E-125 |

Identity is an opaque decision id. Week plus season cannot represent the second
decision for a week, and there is one: a mid-week trade acceptance invalidates a
confirmed lineup (E-125) and forces a re-decide. Keying on the week would have the
replacement overwrite the snapshot I-10 depends on.

<!--
The override reason is captured at E-021, which is also the transition into
`overridden` — that is what makes I-09 enforceable. Before the consistency pass
the reason capture was a bare notification with no state change behind it, so
the rule had nothing to attach to.

`unactioned` is a terminal-ish state that still records: the manager never
looked, the deadline passed, and the forgone value is worth computing even
though nothing was submitted.

`invalidated` is reachable only from `confirmed`, and only via a trade
acceptance mid-week. A lineup that was correctly submitted can still be made
wrong by a roster change underneath it.
-->

## Members

| id | name | aggregate | kind | notes |
|----|------|-----------|------|-------|
| ENT-override-reason | Override reason | AGG-lineup-decision | entity | An entity rather than a value object precisely because who said what and when must survive everything downstream. This is the season-review artifact the whole evaluation objective rests on |
| ENT-input-snapshot | Input snapshot | AGG-lineup-decision | value-object | Frozen at record time by I-10, immutable by definition |
