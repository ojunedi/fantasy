---
id: S-011
slice_id: brief-integrity
status: todo
---

# A brief cannot contain a number the analysis never computed

## Outcome

Every figure appearing in a generated brief is traceable to the analysis output it came from. A brief that introduces a number is rejected rather than shown.

## Contexts

| id | why |
|----|-----|
| BC-lineup | Generates the lineup brief |
| BC-waiver | Generates the waiver brief |
| BC-trade | Generates the trade brief and the counterparty pitch |

## Invariants

| id | risk |
|----|------|
| I-27 | The counterparty pitch is the real exposure. It is persuasive writing aimed at another person, which is exactly where an invented supporting figure would read most naturally and do the most damage — a number nobody computed, used to argue someone into a trade |
| I-25 | Lineup briefs quote many numbers per player, so the check has to cover every one rather than a headline figure |
| I-26 | Waiver briefs must state *which bar* a candidate failed and by how much, so the margin is a number the check has to trace too |

## NFRs

| id | applies |
|----|---------|
| NFR-04 | A post-generation check costs no LLM calls. A regenerate-on-failure loop would, so a rejection must not silently retry |

## Contracts

No external contracts. This system publishes no API and no messages — the
`Contracts` table is for endpoints and published events, and there are none to
reference. The domain events this slice introduces are internal and already
mapped in `event-maps/`.

## Open questions

| id | question | owner |
|----|----------|-------|
| H-08 | Template the prose so numbers can only be interpolated, or check after generation that every number in the brief appears in the analysis output? Templating prevents the failure; checking detects it and keeps the prose natural | R-01 |

<!--
The single failure the thin-LLM design exists to prevent, and it had no
invariant at all until the storm was challenged. Every number in this product is
computed deterministically precisely so the model cannot invent one — and then
the briefs are generated prose, which is the one place an invented number would
appear and look entirely at home.

Eighth because the consequence is a wrong number in text the manager reads
before acting, rather than a wrong action. That is a real mitigation, not an
excuse: it is why this is not first.
-->
