# Intent — pre-kickoff-nudge

## Outcome

The manager sees a time-sensitive alert when kickoff is within 30 minutes and
the lineup recommendation for that week has not been approved or overridden.

## Who

**Actor:** The manager (R-01)
**What changes for them:** A recommendation that would otherwise sit unread until
kickoff now produces a visible signal before the window closes.

## Why now

The measured gap in weeks 1–3 of 2026 is adherence, not analysis quality. In
week 3 the optimizer was right by 8.9 points and was not followed. The naive
baseline (start whoever the platform ranks first, every week) is ahead of actual
decisions by roughly 3 points per week. No new capability closes that gap; a
nudge that fires before the window closes might. This also retires the open
question of whether anything watches the clock before kickoff.

## Acceptance criteria

| # | Criterion | Source |
|---|---|---|
| AC-1 | When a lineup recommendation exists in an unacted-on state — not yet approved, overridden, or recorded as unactioned — and the first-game kickoff for the week is within the configured threshold (default 2 hours), a nudge is delivered to the manager | outcome, hotspot H-06 |
| AC-2 | No nudge fires when the week's recommendation has already been approved, overridden, or recorded as unactioned | outcome |
| AC-3 | No nudge fires when no lineup recommendation has been generated for the current week | outcome |
| AC-4 | The nudge message states the time remaining until kickoff and the command or URL to open the recommendation | outcome |
| AC-5 | A nudge never fires for a kickoff that has already passed | outcome — past the deadline the week is forfeited and the alert is noise |
| AC-6 | If the nudge cannot be delivered, the failure is written to decisions.db with a timestamp; the recommendation remains pending and no state is changed | invariant I-10 (LineupDecision) — the input snapshot is written once and never updated; a failed nudge must not trigger a re-analysis |
| AC-7 | The threshold (default 2 hours) is configurable without a code change | NFR-06 — the 1 PM kickoff deadline is fixed; the manager's preferred lead time is not |

## Acceptance signal

The manager sets the lineup on time in a week where they would otherwise have
missed the window. Over the remainder of the season, no week ends with a
recommendation that went unread.

## Out of scope

- Nudges for trade or waiver deadlines — those have their own deadline shapes and their own slices
- Nudging when no analysis has been run yet — this fires on an existing unread recommendation, not on its absence
- Automatic lineup submission if the nudge goes unanswered — the human approval gate is not negotiable

## Carried context

| | |
|---|---|
| **Bounded contexts** | Lineup Execution (BC-lineup), Decision Ledger (BC-ledger) |
| **Aggregates touched** | LineupDecision (AGG-lineup-decision) |
| **Invariants at risk** | I-10 — input snapshot written once, never updated; a nudge must not trigger re-analysis that would overwrite it |
| **Contracts** | None external — nudge delivery is local |
| **NFRs that apply** | NFR-06 — lineup decision must be executable before Sunday 1 PM kickoff |
| **Depends on** | None |

## Interface impact

**Does this slice touch a user interface?** Yes

The nudge must surface outside the web UI, because the app may not be open
when the window arrives (NFR-08: the tool is started when needed and is not a
persistent service). Delivery channel — macOS system notification, terminal
banner on next CLI invocation, or both — is a decision for the specs artifact.

## Open questions

| # | Question | Owner | Blocking? |
|---|---|---|---|
| Q-1 | How is "the current week" determined? The recommendation is keyed by week + season — which source of truth establishes what week it is right now? | R-01 | Yes — specs need this to know which recommendation to check |
| Q-2 | What is the delivery channel given the app only runs when needed (NFR-08)? macOS notification via a cron or launch agent, terminal banner on next invocation, or both? | R-01 | Yes — shapes UX and implementation |
| Q-3 | What happens if the manager is reviewing the recommendation when kickoff passes and locks the lineup? | R-01 | No — the lineup is locked; nothing to do. System records the decision as unactioned and moves on. |
