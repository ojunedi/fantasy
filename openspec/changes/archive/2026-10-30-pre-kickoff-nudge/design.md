# Design — pre-kickoff-nudge

How to build it, and how to test it. See intent.md for motivation and specs for
the full requirement statements.

---

## Build approach

### Where the code goes

| Concern | Location | Pattern it follows |
|---|---|---|
| Nudge check logic | `gm/nudge/check.py` | New module; follows `gm/lineup/` structure |
| macOS notification delivery | `gm/nudge/notify.py` | `subprocess` calling `osascript`; stubbed in tests |
| launchd plist | `scripts/install-nudge-agent.sh` + `resources/com.fantasygm.nudge.plist` | One-shot install; fires check every 15 min on Sunday mornings |
| Failure log writer | `gm/nudge/check.py` | Writes to existing `decisions.db` via existing SQLite writer |
| Web banner partial | `templates/partials/nudge_banner.html` | Jinja2 partial; injected into `templates/base.html` |
| Banner status endpoint | `gm/routes/nudge.py` | GET `/api/nudge/status` → JSON `{active: bool, minutes_remaining: int}` |

### Components

| Component | Action | Notes |
|---|---|---|
| `should_nudge()` function | CREATE | Reads LineupDecision state from SQLite; applies threshold; returns whether to nudge |
| `MacNotifier` | CREATE | Wraps `osascript` call; raises `NudgeDeliveryFailed` on failure |
| `nudge_banner.html` | CREATE | htmx partial; polls `/api/nudge/banner` every 60 s; returns HTML fragment |
| `GET /api/nudge/status` | CREATE | Returns `{active, minutes_remaining}` JSON; for programmatic consumers |
| `GET /api/nudge/banner` | CREATE | Returns HTML fragment for htmx outerHTML swap; used by base.html polling |
| `base.html` | MODIFY | Include nudge banner polling div (polls `/api/nudge/banner`) |
| `decisions.db` | MODIFY | Add `nudge_log` table (see migration below) |

### UI approach

> Design system: **none registered** — no library components. All UI decisions
> are assumptions.
> Prototype: **none covering this slice.**

| UI element | Approach | Import / source | Notes |
|---|---|---|---|
| macOS notification | `subprocess` + `osascript` | stdlib | NEW COMPONENT — stubbed in tests |
| Web alert banner | Hand-rolled Jinja2 + htmx | inline template | NEW COMPONENT — amber background, dismiss button |
| Countdown text | Server-rendered on each poll | Jinja2 | Minutes remaining, computed at request time |
| "Review now" link | `<a href="/history">` | htmx boost | Points to the Decisions list page (/history) |

### Aggregate and transaction boundary

`NudgeChecker` reads `LineupDecision` state from SQLite — **read-only**. The
input snapshot (I-10) is never touched. The only write this slice makes is
appending a row to `nudge_log` on delivery failure. No transaction spans both
reads and writes; the failure log is append-only and idempotent.

### Data and migration

```sql
-- UP
CREATE TABLE IF NOT EXISTS nudge_log (
    id        INTEGER PRIMARY KEY,
    week      INTEGER NOT NULL,
    season    INTEGER NOT NULL,
    failed_at TEXT NOT NULL,  -- ISO-8601
    reason    TEXT NOT NULL
);

-- DOWN
DROP TABLE IF EXISTS nudge_log;
```

### Key decisions

| Decision | Chosen | Rejected | Why |
|---|---|---|---|
| Check scheduler | launchd plist (fires every 15 min, Sunday 9 AM – 1 PM) | cron | launchd survives reboots without user intervention; cron requires a running terminal session |
| Notification mechanism | `osascript` | `terminal-notifier`, `plyer` | No extra dependency; available on every Mac |
| Web poll interval | 60 s via `hx-trigger="every 60s"` | WebSocket, SSE | Simplest fit for htmx; SSE overkill for a personal tool |
| Dismiss behaviour | Visual hide only, no log entry | Log dismiss as a decision | A dismiss that logs creates noise in the decision ledger without actionable signal |

### Risks

| Risk | Mitigation |
|---|---|
| Notification permission not granted | `MacNotifier` catches the `osascript` error, logs `NUDGE_DELIVERY_FAILED`, continues. Web banner is the fallback. |
| launchd plist not installed | Install script is manual but documented. The web banner works without it. |
| Threshold misconfigured to 0 or negative | `NudgeChecker` treats a non-positive threshold as disabled and fires nothing. |

---

## Test approach

### Scenario coverage

| Scenario | AC | Level | Test file | Test name | Status |
|---|---|---|---|---|---|
| PKICK-01 | AC-1, AC-4 | integration | `tests/nudge/test_check.py` | `PKICK-01: nudge fires when recommendation is unread at threshold` | required |
| PKICK-02 | AC-1 | integration | `tests/nudge/test_check.py` | `PKICK-02: nudge fires for briefed-but-not-presented recommendation` | required |
| PKICK-03 | AC-2 | integration | `tests/nudge/test_check.py` | `PKICK-03: no nudge when recommendation is approved` | required |
| PKICK-04 | AC-2 | integration | `tests/nudge/test_check.py` | `PKICK-04: no nudge when recommendation is overridden` | required |
| PKICK-05 | AC-2 | integration | `tests/nudge/test_check.py` | `PKICK-05: no nudge when recommendation is unactioned` | required |
| PKICK-06 | AC-3 | integration | `tests/nudge/test_check.py` | `PKICK-06: no nudge when no recommendation exists` | required |
| PKICK-07 | AC-5 | integration | `tests/nudge/test_check.py` | `PKICK-07: no nudge when kickoff has already passed` | required |
| PKICK-08 | AC-6 | integration | `tests/nudge/test_check.py` | `PKICK-08: delivery failure logged without changing decision state` | required |
| PKICK-09 | AC-7 | integration | `tests/nudge/test_check.py` | `PKICK-09: custom threshold is respected` | required |
| PKICK-10 | AC-1 | manual | `tests/nudge/test_check.py` | `PKICK-10: acceptance signal — manager sets lineup on time after nudge` | required |

All integration tests use a real in-memory SQLite instance and mock `MacNotifier`
to avoid `osascript` at test time.

### NFR measurement

| NFR | How measured | Where it runs |
|---|---|---|
| NFR-06 — decision executable before 1 PM | Check fires at 11 AM (2 h before), giving 2 h to act — verified by launchd schedule in code review | Manual / plist inspection |
| NFR-08 — no uptime requirement | Check runs from launchd, not from the app process — verified architecturally | Design review |
| NFR-10 — every decision written to SQLite before run reports completion | PKICK-08 asserts nudge_log row before function returns | integration |

### Not covered by automated tests

| Gap | Reason |
|---|---|
| Actual `osascript` delivery on CI | No display server in CI; `MacNotifier` is stubbed for all automated tests |
| launchd plist scheduling accuracy | OS-level scheduler; verified manually at install time |
| Web banner htmx poll in browser | No e2e browser suite exists; covered by manual acceptance signal |
