---
id: SCN-004
scenario_id: lineup-espn-api-fails
journey: J-01
kind: exception
status: agreed
---

# ESPN write API rejects the lineup submission

The manager has approved. The agent sends the roster transaction to ESPN's
undocumented write endpoint and it fails — a changed payload shape, a rotated
cookie, a silent 200 that did not actually move anything. The browser fallback
takes over. If that also fails, the manager is told explicitly and in time to
act by hand.

This is the highest-consequence failure in the system: the analysis was right,
the approval happened, and the lineup still did not change.

## Events

| id | event | scenario | after | actor | context | pivotal | hotspot | notes |
|----|-------|----------|-------|-------|---------|---------|---------|-------|
| E-040 | ESPNSubmissionFailed | SCN-004 | | SYS-ESPN | BC-lineup | yes | | Branches from the API write; covers explicit errors and silent no-ops |
| E-041 | SubmissionFailureLogged | SCN-004 | E-040 | R-02 | BC-ledger | | | The payload sent and the response received, for diagnosing the break |
| E-042 | BrowserFallbackAttempted | SCN-004 | E-040 | SYS-ESPN | BC-lineup | yes | | Runs in parallel with E-041; Playwright drives the ESPN UI |
| E-043 | LineupConfirmedViaFallback | SCN-004 | E-042 | SYS-ESPN | BC-lineup | | | Rejoins the happy path — the lineup did change |
| E-044 | FallbackAlsoFailed | SCN-004 | E-042 | SYS-ESPN | BC-lineup | yes | H-01 | Both write paths exhausted. Unresolved: is the manager notified out-of-band, or only on next visit? |
| E-045 | ManualActionRequested | SCN-004 | E-044 | R-01 | BC-lineup | yes | | Path terminates — the manager must set the lineup in the app before kickoff |

## Assumptions

| id | assumption | source |
|----|------------|--------|
| ASM-009 | A silent no-op is detectable — the agent reads back the roster to confirm the move landed | assumed |
| ASM-013 | Playwright selectors are current for this season's ESPN DOM | assumed |
| ASM-014 | The failure is discovered with enough time left before kickoff to act manually | assumed |

## Commands

| id | command | event | actor | aggregate | context |
|----|---------|-------|-------|-----------|---------|
| C-007 | RetryViaBrowser | E-042 | R-02 | AGG-decision-record | BC-lineup |

## Policies

| id | when | then | crosses_context |
|----|------|------|-----------------|
| P-007 | E-040 | Log the failure detail AND attempt the browser fallback (BC-approval → BC-audit) | yes |
| P-008 | E-044 | Tell the manager they must act manually, with the exact moves (BC-approval → BC-recommendation) | yes |
