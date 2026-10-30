# Tasks — pre-kickoff-nudge

<!--
Checkbox format is parsed. `- [ ] N.M description` or it is not tracked.
Test task before implementation task. Every scenario id appears at least once.
-->

## 1. Data

- [x] 1.1 Write and apply the `nudge_log` migration (UP + DOWN) to `decisions.db`
- [x] 1.2 Verify migration rolls back cleanly with the DOWN script

## 2. Core logic — tests first

- [x] 2.1 Write `PKICK-01`: nudge fires when recommendation is unread at threshold (integration, `tests/nudge/test_check.py`) — annotate each THEN/AND clause above its assertion
- [x] 2.2 Write `PKICK-02`: nudge fires for briefed-but-not-presented recommendation (integration)
- [x] 2.3 Write `PKICK-03`: no nudge when recommendation is approved (integration)
- [x] 2.4 Write `PKICK-04`: no nudge when recommendation is overridden (integration)
- [x] 2.5 Write `PKICK-05`: no nudge when recommendation is unactioned (integration)
- [x] 2.6 Write `PKICK-06`: no nudge when no recommendation exists for the current week (integration)
- [x] 2.7 Write `PKICK-07`: no nudge when kickoff has already passed (integration)
- [x] 2.8 Write `PKICK-08`: delivery failure logged without changing decision state (integration — mock `MacNotifier` to raise; assert `nudge_log` row written and `LineupDecision` state unchanged)
- [x] 2.9 Write `PKICK-09`: custom threshold is respected (integration — configure 60 min; assert no nudge at 75 min, nudge at 55 min)
- [x] 2.10 Implement `NudgeChecker` in `gm/nudge/check.py` — reads `LineupDecision` state from SQLite, applies threshold, returns whether to nudge; all 2.1–2.9 must pass
- [x] 2.11 Implement `MacNotifier` in `gm/nudge/notify.py` — wraps `osascript`, raises `NudgeDeliveryFailed` on failure; failure path exercised by 2.8

## 3. Scheduler

- [x] 3.1 Write `resources/com.fantasygm.nudge.plist` — launchd plist firing the check every 15 min, Sunday 9 AM–1 PM ET
- [x] 3.2 Write `scripts/install-nudge-agent.sh` — copies plist to `~/Library/LaunchAgents/` and loads it; documents uninstall step

## 4. UI — web banner

- [x] 4.1 Implement `GET /api/nudge/status` in `gm/routes/nudge.py` — returns `{active: bool, minutes_remaining: int}`; no library component
- [x] 4.2 Build `templates/partials/nudge_banner.html` — NEW COMPONENT (hand-rolled Jinja2 + htmx); amber background; polls `/api/nudge/status` every 60 s; states: banner-visible, banner-hidden
- [x] 4.3 Modify `templates/base.html` to include the nudge banner partial
- [ ] 4.4 Verify banner-visible state: manual check with an unread recommendation in DB within threshold
- [ ] 4.5 Verify banner-hidden state: confirm banner does not appear when recommendation is approved

## 5. E2E

- [ ] 5.1 Write manual acceptance-signal test: seed an unread recommendation, run the check script, confirm macOS notification fires and the web banner appears; set the lineup; confirm the banner disappears

## 6. Verification

- [x] 6.1 Run the full pytest suite; all tests must pass
- [x] 6.2 Run `node scripts/trace.mjs check --phase delivery` and resolve every CRITICAL finding
- [x] 6.3 For each PKICK scenario, confirm the test would fail if its scenario were violated (remove one assertion and watch it fail; restore)

## 7. Code review

- [x] 7.1 Run `/frictionless:slice-review` and resolve all CRITICAL findings before marking this slice done
