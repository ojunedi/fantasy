# Tasks — decision-history-survives

<!--
No contract tasks: this slice changes no API and publishes no events.
No UI group: intent.md answered no to interface impact, so ux.md was skipped.
Every test is named after its scenario and annotated clause by clause — one
`# LEDGBAK-NN THEN <clause>` comment directly above the assertion that proves
each THEN/AND clause. Write the comments as you write the test; the point is to
notice the clause you have no assertion for while adding one is still cheap.
A comment is a claim to be checked at review, never evidence on its own.
-->

## 1. Scaffolding

- [x] 1.1 Add `FANTASY_GM_BACKUP_REPO` resolution in `src/fantasy_gm/db/backup.py` — path to an existing git repository, unset means not configured, following the `os.environ.get` pattern in `agent/config.py`
- [x] 1.2 Add the test fixtures from design.md: a decision whose input snapshot holds unsorted keys, unicode, embedded quotes and a non-UTC timestamp; a bare git repository in `tmp_path` serving as the remote; an environment holding cookie-shaped `ESPN_S2` and API key values

## 2. Dump

- [x] 2.1 Write `LEDGBAK-03: input snapshots survive a round trip unchanged` (integration, `tests/db/test_backup_restore.py`), one clause comment per THEN/AND — confirm it fails before implementation
- [x] 2.2 Write `LEDGBAK-07: the dump is inspected for secrets` (integration, `tests/db/test_backup.py`), one clause comment per THEN/AND — confirm it fails before implementation
- [x] 2.3 Create `dump_decisions` in `src/fantasy_gm/db/backup.py` — reads the `decisions` table only, rows ordered by `id`, each value taken as raw stored text and quoted as a SQL literal. Never through `json.loads`/`json.dumps`, never through `DecisionStore._row_to_record`, never `Connection.iterdump`

## 3. Dirty tracking

- [x] 3.1 Write `LEDGBAK-02: computed scorecards are not committed` (integration, `tests/db/test_backup.py`), one clause comment per THEN/AND — confirm it fails before implementation
- [x] 3.2 Modify `DecisionStore` — set a dirty flag in `save`, `record_human_response` and `record_outcome`; leave `save_scorecard` untouched so a backtest writing seventeen scorecards triggers nothing
- [x] 3.3 Create `DecisionStore.backup_if_dirty` — no-op when nothing was written, clears the flag only after a successful commit

## 4. Commit and push

- [x] 4.1 Write `LEDGBAK-01: a recorded decision is committed off-machine` (integration, `tests/db/test_backup.py`), one clause comment per THEN/AND — confirm it fails before implementation
- [x] 4.2 Write `LEDGBAK-05: the remote is unreachable` (integration, `tests/db/test_backup.py`), one clause comment per THEN/AND, asserting the decision is readable from a freshly opened connection and the run completes — confirm it fails before implementation
- [x] 4.3 Write `LEDGBAK-06: the backup repository is missing or has no remote configured` (integration, `tests/db/test_backup.py`), one clause comment per THEN/AND — confirm it fails before implementation
- [x] 4.4 Create `DecisionBackup` — writes `decisions.sql` into the configured repository, commits with a message naming the week and season just written, pushes
- [x] 4.5 Implement the failure path — an unreachable remote or an unconfigured repository logs a warning naming the failure and the week affected, creates no partial or empty commit, and lets the run complete. Never raises into the caller

## 5. Startup week check

- [x] 5.1 Write `LEDGBAK-08: the local log is missing weeks the backup holds` (unit, `tests/db/test_backup_weeks.py`), one clause comment per THEN/AND, asserting no restore happens and the local log is unmodified — confirm it fails before implementation
- [x] 5.2 Write `LEDGBAK-09: the local log is level with or ahead of the backup` (unit, `tests/db/test_backup_weeks.py`), one clause comment per THEN/AND — confirm it fails before implementation
- [x] 5.3 Create `DecisionBackup.missing_weeks` — restores the dump into an in-memory database and compares its weeks against the local log. No regular-expression parsing of the dump text
- [x] 5.4 Modify `cli.main` — report missing weeks at startup before dispatch, and call `backup_if_dirty` after the command completes

## 6. Restore

- [x] 6.1 Write `LEDGBAK-04: the backtest runs against a restored log` (integration, `tests/db/test_backup_restore.py`), one clause comment per THEN/AND, asserting the scorecards are rebuilt from the restored decisions — confirm it fails before implementation
- [x] 6.2 Confirm the restore path is a clone and a SQLite import with no tooling of its own, as intent.md scopes it — if it is not, that is a finding, not a licence to build tooling

## 7. E2E

- [x] 7.1 Write `LEDGBAK-01: AC-SIGNAL — a season restored into an empty database keeps every week and rebuilds its scorecards` (e2e, `tests/db/test_backup_restore.py`), one clause comment per THEN/AND
- [x] 7.2 Run the acceptance-signal test against a real repository with a real remote and record the actual output

## 8. Verification

- [x] 8.1 Run the full suite with `make test` and record real output — no "should work"
- [x] 8.2 Run `node "${CLAUDE_PLUGIN_ROOT}/scripts/trace.mjs" check --phase delivery` and resolve every CRITICAL
- [x] 8.3 Confirm each test would fail if its scenario were violated — in particular, confirm the byte-identity test fails against an implementation that re-serialises the snapshot
- [x] 8.4 Correct the architecture documentation, which currently states the decision log never leaves the machine — it now does

## 9. Code review

- [ ] 9.1 Run `/frictionless:slice-review` and resolve all CRITICAL findings before continuing
- [ ] 9.2 Accept or document any HIGH findings with a reason
