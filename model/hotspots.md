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
| H-06 | Is anything watching the clock? A recommendation can go unread until kickoff and nothing currently notices | risk | J-01 | R-01 | E-050, and the equivalent waiver deadline | Nothing watches (current state); a reminder at a fixed time before kickoff; escalate only when the standing lineup differs from the recommendation |
| H-07 | Can the system tell a declined offer from one still sitting unanswered? | unknown | J-02 | R-01 | E-122, trade outcome logging | ESPN exposes offer state on read; infer from the offer disappearing; never know, and log only acceptances |
| H-08 | What stops a generated brief from asserting something the optimizer did not compute? | risk | J-01 | R-01 | every brief-generation event (E-009, E-108, E-209) | Template the prose so numbers can only be interpolated, never written; post-generation check that every number in the brief appears in the analysis output; accept the risk and rely on review |

<!--
H-01 and H-06 are the same shape and are the two that would cost a real week:
in both, everything upstream worked and the lineup still did not change. H-01 is
the write failing; H-06 is nobody looking. Neither is currently detected.

H-02 remains the arithmetic decision that looks like implementation detail and
is not: it decides when the agent refuses to answer at all. The two waiver bars
that sat beside it are now settled — see Resolved.

H-08 is the failure the whole thin-LLM design exists to prevent, and it had no
hotspot until the storm was challenged. Every number in the product is computed
deterministically precisely so the model cannot invent one — but the briefs are
generated prose, which is exactly where an invented number would appear.
-->

## Resolved

| id | question | resolution | decided_in | date |
|----|----------|------------|------------|------|
| H-05 | What does a waiver candidate have to beat on my roster? | The worst rostered player — whoever the claim would displace — on rest-of-season value, **plus** a forward-looking test that the candidate projects into the starting lineup within three weeks. Bench spots are cheap enough to churn, but not for a player with no path to mattering. | session-2026-10-01 | 2026-10-01 |
| H-10 | What makes a player worth a roster spot at all? | Ranking inside the league-wide startable tier at their position: team count × starting slots at that position, derived from league settings. Chosen over a points floor (position-dependent, and becomes a rank cutoff in disguise once you add a per-position table), over "startable for me soon" (a relative test wearing an absolute hat), and over ownership percentage (circular — it cannot distinguish a bad player from an edge, and would suppress the good finds). | session-2026-10-01 | 2026-10-01 |
| H-09 | The trade send reported success without verifying it | Fixed in `f97488a`. The send now re-reads the league's pending proposals with the cache bypassed and matches on the exact player-id set, with a three-state result so "POSTed but not found" is distinguishable from both success and failure — and explicitly does not retry, because a duplicate offer is worse than an unverified one. | session-2026-10-01 | 2026-10-01 |
| H-11 | Does a bye week count as a path to starting? | **No.** The path-to-starting test assumes a fully available roster. Otherwise every bye manufactures an opening and the scorer churns the bench filling holes that close by themselves. Filling a bye-week hole is a real and separate need. | session-2026-10-01 | 2026-10-01 |
| H-00 | Is the waiver wire part of the weekly lineup cycle or its own journey? | Its own journey. It has a different trigger (Tuesday night wire open), a different deadline, and a different decision shape (add/drop vs. slot assignment). The 50% function overlap with the lineup journey is real but incidental — both read roster and injury data. | session-2026-09-30 | 2026-09-30 |
