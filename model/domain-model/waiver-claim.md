---
product: Fantasy GM
stage: domain-design
aggregate: AGG-waiver-claim
---

# AGG-waiver-claim

The waiver brief, the gate, the filed claim, and its outcome. Owned by waiver execution.

Its terminal states are the reason this cannot share a boundary with the lineup decision: a claim's final state is written by other managers' waiver priority, not by us. Losing is ordinary.

## Invariants

| id | aggregate | rule | enforced_in |
|----|-----------|------|-------------|
| I-12 | AGG-waiver-claim | The roster stays legal: an add requires a drop whenever the roster is already at maximum size | WaiverClaim.approve |
| I-18 | AGG-waiver-claim | A claim records the priority position it was filed under. Without it, a lost claim cannot be distinguished from a bad recommendation | WaiverClaim.submit |
| I-19 | AGG-waiver-claim | A hold decision is recorded with the same weight as a claim. Choosing not to act is a decision and belongs in the log | WaiverClaim.decline |
| I-26 | AGG-waiver-claim | Every number in a brief appears in the analysis output it was generated from. A brief may rephrase a number, never introduce one | WaiverClaim.brief |

## Transitions

| aggregate | from | to | event |
|-----------|------|----|-------|
| AGG-waiver-claim | new | briefed | E-209 |
| AGG-waiver-claim | new | briefed | E-221 |
| AGG-waiver-claim | briefed | presented | E-210 |
| AGG-waiver-claim | briefed | presented | E-222 |
| AGG-waiver-claim | presented | approved | E-211 |
| AGG-waiver-claim | presented | declined | E-223 |
| AGG-waiver-claim | approved | recorded | E-212 |
| AGG-waiver-claim | declined | closed | E-224 |
| AGG-waiver-claim | recorded | ready | E-213 |
| AGG-waiver-claim | ready | ready | E-214 |
| AGG-waiver-claim | ready | submitted | E-215 |
| AGG-waiver-claim | submitted | cleared | E-216 |
| AGG-waiver-claim | submitted | lost | E-230 |
| AGG-waiver-claim | cleared | closed | E-217 |
| AGG-waiver-claim | lost | closed | E-231 |

<!--
The hold path (E-221 → E-222 → E-223) runs through the same states as a real
claim and terminates at `declined`. That is deliberate: a week where we chose
not to claim should be as reviewable as a week where we did, and giving it a
separate aggregate would put half the waiver history somewhere else.

`cleared` and `lost` are both non-terminal because each is followed by its own
log write; the claim is finished at `closed`, not when the outcome happens.

`recorded` and `closed` are deliberately different states. The first means the
decision is logged and nothing has been filed yet — a claim sitting there still
needs submitting before the deadline, and conflating the two made that
undetectable.

Identity is an opaque claim id rather than week plus player: the hold path has no
player to add, and keying half the waiver history on a null is how a no-claim
week becomes unreviewable.
-->

## Members

| id | name | aggregate | kind | notes |
|----|------|-----------|------|-------|
| ENT-waiver-priority | Waiver priority | AGG-waiver-claim | value-object | Our position in the snake order at the time of filing. Required by I-18 |
