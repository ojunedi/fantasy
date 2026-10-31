# Design — write-failure-reaches-me

## Context

Both lineup write surfaces — the web write step (`web/routes/approve.py`) and
the command line (`memo/cli.py`) — call `executor.execute(plan, live=…)` on a
plan built from the approved decision, after the shared approval gate. The
pre-kickoff nudge delivers through `nudge/notify.MacNotifier` (osascript).
`ESPNAdapter.get_raw_lineup_slots` already reads the lineup with the cache
bypassed. See `intent.md` for scope.

---

# Build approach

## Where the code goes

| Concern | Location | Pattern it follows |
| --- | --- | --- |
| Handling an exhausted write | `src/fantasy_gm/execute/failure.py` — `report_failed_write(...)` | `nudge/check.py`: clock and notifier injected, never raises |
| Delivering it | `nudge/notify.MacNotifier.send(body, subtitle)`; the nudge's `notify` becomes a call to it | The existing notifier, one channel |
| Calling it | After a live execute in `approve.execute` and `cli._execute_approved_lineup` | Next to the existing failure display on each surface |

## Components

| Component | Action | Notes |
| --- | --- | --- |
| `execute/failure.py` — `report_failed_write(store, record, plan, result, adapter, team_id, notifier, now)` | CREATE | Returns what it did: `none` / `landed` / `notified` / `recorded` |
| `nudge/notify.py` — `MacNotifier.send` | MODIFY | Generic message; quotes escaped for AppleScript; `notify` delegates to it |
| `web/routes/approve.py` — `execute` | MODIFY | Calls it after a failed live write; notifier from `app.state.notifier` |
| `memo/cli.py` — `_execute_approved_lineup` | MODIFY | Same call |
| `web/app.py` — `app.state.notifier`; `memo/cli.py` — `notifier` parameter | MODIFY | So tests inject a recording notifier on both surfaces |
| `tests/execute/test_write_failure.py`, `tests/web/test_execute.py` | CREATE / MODIFY | |

## Domain

| Aggregate | Invariant it enforces here | Transaction boundary |
| --- | --- | --- |
| `Decision` | I-16 — notify only after a read-back shows a move missing (or the read-back fails); I-11 — moves come from the plan that was sent | One `record_outcome` merge per handled failure, key `write_failure` |

Read-back: `get_raw_lineup_slots(team, week, season)`; a move is in place
when the player's slot equals the move's `to_slot`. Deadline:
`nudge.missed.week_kickoff(season, week)`.

The moves listed are only those the read-back shows still missing (all of
them when the read-back fails), worded from the plan's own steps.

Recorded: `outcome["write_failure"] = {at, error, moves, read_back: "missing" |
"unreadable", notified: bool, notify_error, minutes_to_kickoff}`, or
`outcome["write_landed"] = {at, error}` when the read-back shows it landed.

## Decisions

| Decision | Chosen | Rejected, and why |
| --- | --- | --- |
| Read-back failed | Notify, saying it could not be checked | Stay silent: with nothing checkable, missing the deadline costs more than one false alarm |
| Channel | The nudge's notifier | A second channel: H-01 says reuse |
| Waiver / trade failures | Out of scope | Single path, filed with the manager on the page, manual steps already shown |
| Wire the browser fallback now | No | It refuses live writes; wiring it changes nothing until it is built |

## Risks

| Risk | Mitigation |
| --- | --- |
| AppleScript string breaks on a player name with a quote | Quotes and backslashes escaped in `send` |
| A notifier exception breaks the write step | Caught and recorded (WFAIL-07) |

---

# Test approach

## Scenario coverage

| Scenario | AC | Level | Test file | Test name | Status |
| --- | --- | --- | --- | --- | --- |
| WFAIL-01 | AC-1 | unit | `tests/execute/test_write_failure.py` | `WFAIL-01: a failed write whose moves landed anyway is not reported` | required |
| WFAIL-02 | AC-3 | unit | `tests/execute/test_write_failure.py` | `WFAIL-02: a failed read-back still notifies, and says so` | required |
| WFAIL-03 | AC-6 | integration | `tests/web/test_execute.py` | `WFAIL-03: a dry run, a success or a refusal never notifies` | required |
| WFAIL-04 | AC-2, AC-5, AC-8 | integration | `tests/web/test_execute.py` | `WFAIL-04: a confirmed failure before kickoff notifies with the moves and time left` | required |
| WFAIL-05 | AC-4 | unit | `tests/execute/test_write_failure.py` | `WFAIL-05: after kickoff the failure is recorded, not notified` | required |
| WFAIL-06 | AC-7 | unit | `tests/execute/test_write_failure.py` | `WFAIL-06: the failure and the notification attempt are recorded on the decision` | required |
| WFAIL-07 | AC-7 | unit | `tests/execute/test_write_failure.py` | `WFAIL-07: a notification that cannot be delivered is recorded, not raised` | required |

## Fixtures and test data

| Fixture | Why it must be realistic |
| --- | --- |
| The `FakeExecutor` plan from `tests/web/test_execute.py` (Hall BENCH→RB, Bigsby RB→BENCH, ESPN slot ids) | The read-back compares real ESPN slot ids |
| A recording notifier | Asserts the message without running osascript |

## NFR verification

| NFR | Budget | Measured how | Where it runs |
| --- | --- | --- | --- |
| NFR-06 before kickoff | No notification after Sunday 1 PM ET | WFAIL-05 with an injected clock | `pytest` |

## Not covered by automated tests

| What | Why | How it is checked instead |
| --- | --- | --- |
| The notification appearing on screen | osascript is not run in tests | `python -c "from fantasy_gm.nudge.notify import MacNotifier; MacNotifier().send('test', 'test')"` by hand |
