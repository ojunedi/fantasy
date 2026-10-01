---
id: S-002
slice_id: pre-kickoff-nudge
status: todo
---

# I am nudged before kickoff when a recommendation is sitting unread

## Outcome

When a lineup recommendation has been generated and not actioned, and kickoff is approaching, the manager is told — through a channel they will actually notice — that a recommendation is waiting and what it differs from the standing lineup.

## Why this is second

The backtest says the analysis is already good enough. Weeks 1–2, the optimizer picked what was actually started. Week 3, it was right by 8.9 points and was not followed. The naive baseline — start whoever ESPN ranks first — is currently ahead of actual decisions by about 3 points a week.

That is not an analysis problem. Every other slice in this list improves what the agent knows; this one is the only one that addresses whether any of it gets used.

## Contexts

| id | why |
|----|-----|
| BC-lineup | Owns the recommendation and knows whether it has been actioned |

## Invariants

| id | risk |
|----|------|
| I-11 | A nudge must not become an action. The risk is a convenience path — a one-click approve from a notification — that bypasses the brief the gate exists to make the manager read |
| I-24 | Authorisation stays per-execution and typed. A notification must not carry or cache an approval |

## NFRs

| id | applies |
|----|---------|
| NFR-06 | The nudge has to arrive with enough time left to act, which means it fires before the deadline rather than at it |
| NFR-08 | There is no uptime requirement, which is the hard part: nothing is running to notice the time passing unless something is scheduled |

## Contracts

No external contracts. The notification channel is local.

## Open questions

| id | question | owner |
|----|----------|-------|
| H-06 | Which channel? A desktop notification, writing into a file or page the manager already looks at, or an email. The decision belongs inside this slice rather than ahead of it — but the system is started on demand, so *something* has to be running or scheduled for a nudge to exist at all. That is the real design problem here, not the channel | R-01 |
| — | How long before kickoff? Too early and the injury picture is still moving; too late and there is no time to act. The last pre-game injury reports land roughly 90 minutes out | R-01 |

<!--
Promoted to second after the slicing was challenged on exactly this point: ten
slices of new capability and nothing addressing the measured loss.

The scheduling problem is the substance of this slice and should not be
underestimated. The tool runs when invoked; a nudge requires something that
notices time passing on its own. That is a genuinely new shape for this system
— the first thing in it that runs without being asked.
-->
