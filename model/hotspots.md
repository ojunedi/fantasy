---
scope: Fantasy GM
substep: strategic
---

# Hotspots

Disagreements, unknowns, and risks surfaced while storming.

## Open

| id | question | type | surfaced_in | owner | blocks | options |
|----|----------|------|-------------|-------|--------|---------|
| H-01 | When both ESPN write paths fail, how does the manager find out in time? | risk | J-01 | R-01 | E-044, waiver and trade execution | Out-of-band notification (push, email, SMS); surfaced only on next dashboard visit; block the approval until a write path is verified healthy |
| H-02 | What freshness threshold makes a signal too stale to optimise over? | unknown | J-01 | R-01 | E-030, abstention logic | Per-signal thresholds in hours; a single global threshold; abstain only when a starter's status is unresolved rather than on staleness alone |
| H-03 | Does the waiver recommendation need to model priority order, or only name the target? | unknown | J-03 | R-01 | waiver scoring, E-208 | Name the target only (v1 scope); model snake priority to predict whether the claim would clear; model priority and rank multiple fallback targets |
| H-04 | Who initiates the trade journey — does the agent scan proactively, or does the manager ask? | ownership | J-02 | R-01 | E-101 | Manager always initiates with a brief; agent scans weekly and flags opportunities unprompted; agent scans but only surfaces when EV clears a threshold |
| H-05 | Is the replacement baseline computed against the full roster or only the startable slots? | unknown | J-03 | R-01 | E-206, drop-cost arithmetic | Full roster including bench; startable slots only; startable slots plus the top bench player per position |
| H-06 | Is anything watching the clock? A recommendation can go unread until kickoff and nothing currently notices | risk | J-01 | R-01 | E-050, and the equivalent waiver deadline | Nothing watches (current state); a reminder at a fixed time before kickoff; escalate only when the standing lineup differs from the recommendation |
| H-07 | Can the system tell a declined offer from one still sitting unanswered? | unknown | J-02 | R-01 | E-122, trade outcome logging | ESPN exposes offer state on read; infer from the offer disappearing; never know, and log only acceptances |
| H-09 | The trade send reports success on any non-error response and never reads the league back to confirm the offer exists | risk | J-02 | R-01 | I-23, trade send confirmation | Read the transaction list back after sending and only then report sent; poll until the offer appears; accept the response at face value (current behaviour) |
| H-08 | What stops a generated brief from asserting something the optimizer did not compute? | risk | J-01 | R-01 | every brief-generation event (E-009, E-108, E-209) | Template the prose so numbers can only be interpolated, never written; post-generation check that every number in the brief appears in the analysis output; accept the risk and rely on review |

<!--
H-01 and H-06 are the same shape and are the two that would cost a real week:
in both, everything upstream worked and the lineup still did not change. H-01 is
the write failing; H-06 is nobody looking. Neither is currently detected.

H-02 and H-05 are arithmetic decisions that look like implementation detail and
are not: one decides when the agent refuses to answer, the other decides what
counts as an upgrade. Both belong in domain design rather than in whoever writes
the scorer.

H-09 is the live one. The irreversible write is the one that does not verify
itself, while the reversible write does — the asymmetry runs exactly the wrong
way, and it is in production now. An invariant exists for it (I-23); the code
does not satisfy it yet.

H-08 is the failure the whole thin-LLM design exists to prevent, and it had no
hotspot until the storm was challenged. Every number in the product is computed
deterministically precisely so the model cannot invent one — but the briefs are
generated prose, which is exactly where an invented number would appear.
-->

## Resolved

| id | question | resolution | decided_in | date |
|----|----------|------------|------------|------|
| H-00 | Is the waiver wire part of the weekly lineup cycle or its own journey? | Its own journey. It has a different trigger (Tuesday night wire open), a different deadline, and a different decision shape (add/drop vs. slot assignment). The 50% function overlap with the lineup journey is real but incidental — both read roster and injury data. | session-2026-09-30 | 2026-09-30 |
