# Intent — write-failure-reaches-me

## Outcome

When an approved lineup's live write fails on every write path, and reading
the lineup back confirms ESPN does not have it, the manager gets a Mac
notification — the same channel as the pre-kickoff nudge — listing the moves
to make by hand and the time left before kickoff.

## Who

**Actor:** the manager
**What changes for them:** a failed write no longer depends on them still
watching the screen it failed on. The notification stays in Notification
Centre with the moves and the deadline.

## Why now

The twin of the missed recommendation: everything upstream worked and the
lineup still did not change. That one shipped; this one had no slice until
the slicing was challenged.

**What "both paths" means today.** The ESPN API write is the only path wired
in; the browser fallback exists but refuses live writes until it is built
out. So the exhausted state is "every write path that can write has failed" —
today the API alone — and nothing here changes when the browser path is
wired in later.

## Acceptance criteria

| # | Criterion | Source |
| --- | --- | --- |
| AC-1 | After a live lineup write fails, the lineup is read back from ESPN with the cache bypassed; if every planned move is already in place, no notification is sent and the write is recorded as landed | invariant I-16 |
| AC-2 | If the read-back shows any planned move not in place, the manager is notified with the moves to make by hand and the minutes left before that week's kickoff (Sunday 1 PM ET) | outcome; NFR-06 |
| AC-3 | If the read-back itself fails, the manager is still notified, and the message says the lineup could not be checked | outcome; NFR-06 — a missed deadline costs more than a false alarm when nothing can be checked |
| AC-4 | After kickoff no notification is sent; the failure is recorded on the decision | NFR-06 — after kickoff it is a log entry |
| AC-5 | The moves come from the plan built from the approved decision for this execution — the plan that was sent — never from a plan recomputed when notifying | invariant I-11 |
| AC-6 | A dry run, a successful write, and a refused execution never notify | invariant I-16; outcome |
| AC-7 | Every exhausted write is recorded on the decision (when, the error, the moves, whether the manager was notified); a notification that cannot be delivered is recorded, never raised | outcome |
| AC-8 | The notification goes through the nudge's notifier; no second channel is added | open question H-01 |

## Acceptance signal

- A lineup write that fails on a Sunday morning gets set by hand before
  kickoff because the notification said what to do.

## Out of scope

- Waiver claim and trade send failures: each has a single path, is filed with
  the manager on the page, and already shows the manual steps there.
- Building the browser write path.
- Retrying the write automatically.

## Carried context

| | |
| --- | --- |
| **Bounded contexts** | Lineup Execution (the exhausted state) |
| **Aggregates touched** | Decision — outcome only |
| **Invariants at risk** | Confirmed only by read-back (I-16); manual steps describe the approved decision (I-11) |
| **Contracts** | None external |
| **NFRs that apply** | Before Sunday 1 PM kickoff (NFR-06) |
| **Depends on** | The pre-kickoff nudge's notifier (shipped) |

## Interface impact

**Does this slice touch a user interface?** No screen changes. The manager
sees a macOS notification, delivered through the nudge's existing notifier;
the write step's existing failure banner is unchanged.

## Open questions

| # | Question | Owner | Blocking? |
| --- | --- | --- | --- |
| H-01 | Which channel? **Resolved:** the nudge's Mac notification, reused | — | No |
