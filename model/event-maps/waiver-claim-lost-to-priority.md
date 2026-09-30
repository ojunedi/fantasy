---
id: SCN-012
scenario_id: waiver-claim-lost-to-priority
journey: J-03
kind: alternate
status: agreed
---

# Waiver claim lost to a higher priority

Someone ahead in the snake order claimed the same player. The claim fails and
the roster is unchanged. Nothing went wrong — this is the ordinary outcome of
wanting a player other people also want.

It matters because it is the *only* event in the system that tells us whether a
recommendation was actually actionable. A waiver scorer that keeps naming
players who are always claimed by someone with better priority is producing
advice that reads well and cannot be used, and without this event there is no
way to notice.

## Events

| id | event | scenario | after | actor | context | pivotal | hotspot | notes |
|----|-------|----------|-------|-------|---------|---------|---------|-------|
| E-230 | WaiverClaimLostToPriority | SCN-012 | | SYS-ESPN | BC-waiver | yes | | Branches from claim submission; someone earlier in the snake order took the same player |
| E-231 | ClaimFailureLogged | SCN-012 | E-230 | R-02 | BC-ledger | yes | | Records who we wanted and what priority we held — the input to whether priority needs modelling at all (H-03) |
| E-232 | FallbackCandidateSurfaced | SCN-012 | E-230 | R-02 | BC-waiver | | H-03 | Runs alongside the logging. Unresolved whether v1 even ranks fallbacks — if it does not, this event does not exist and the path ends at the failure |
| E-233 | ManagerNotifiedOfFailedClaim | SCN-012 | E-231,E-232 | R-01 | BC-waiver | yes | | Path terminates — the roster is unchanged and the wire has moved on |

## Assumptions

| id | assumption | source |
|----|------------|--------|
| ASM-025 | ESPN reports a failed claim in a way the system can read back, rather than the failure being silent | assumed |
| ASM-026 | Our waiver priority position is knowable before the claim is filed | assumed |

## Commands

| id | command | event | actor | aggregate | context |
|----|---------|-------|-------|-----------|---------|
| C-205 | SurfaceFallbackCandidate | E-232 | R-02 | AGG-waiver-rec | BC-waiver |

## Policies

| id | when | then | crosses_context |
|----|------|------|-----------------|
| P-204 | E-230 | Log the failed claim with the priority we held, and surface a fallback if one was ranked (BC-waiver → BC-ledger) | yes |
