# Design — decision-history-survives

How to build it, and how to test it.

## Context

`data/decisions.db` holds two tables: `decisions` and `scorecards`. Only the
first is in scope — see intent.md. `DecisionStore` (`src/fantasy_gm/db/store.py`)
commits each write immediately, so durability is already satisfied before this
slice does anything; the backup is strictly additional.

The project configures every external dependency by environment variable and
expects it to already exist — ESPN cookies, league and team, database path
(`adapters/espn.py`, `web/settings.py`). The backup repository follows that
convention: `FANTASY_GM_BACKUP_REPO` names an existing git repository with a
remote already configured. Nothing in this slice creates a repository or
chooses whether it is private.

---

# Build approach

## Where the code goes

| Concern | Location | Pattern it follows |
| --- | --- | --- |
| Dump, commit, push | `src/fantasy_gm/db/backup.py` | New module beside `db/store.py`; module-level default path, class holding state |
| Dirty tracking | `src/fantasy_gm/db/store.py` | Existing `DecisionStore` methods |
| Startup week check | `src/fantasy_gm/db/backup.py`, called from `cli.main()` | `cli.main()` already configures logging before dispatch |
| Config | `FANTASY_GM_BACKUP_REPO` read in `backup.py` | `os.environ.get` with a default, as in `agent/config.py` |

## Components

| Component | Action | Notes |
| --- | --- | --- |
| `DecisionBackup` | CREATE | Dump, commit, push; `missing_weeks()` for the startup check |
| `dump_decisions` | CREATE | Raw-text SQL dump of the `decisions` table only |
| `DecisionStore` | MODIFY | Sets a dirty flag on decision writes, not on `save_scorecard` |
| `DecisionStore.backup_if_dirty` | CREATE | Called at run end; no-op when nothing was written |
| `cli.main` | MODIFY | Startup missing-week report; backup after each command |
| `web.runs` | MODIFY | Backs up after its two decision writes — a web run is a run |

## Domain

| Aggregate | Invariant it enforces here | Transaction boundary |
| --- | --- | --- |
| `LineupDecision` (read only) | I-10 — snapshot copied verbatim | None. The backup runs wholly outside the decision transaction, after it has committed |

The dump reads `inputs_snapshot` as the raw stored TEXT and writes it as a SQL
string literal. It never passes through `json.loads`/`json.dumps`, and never
through `_row_to_record`. That single rule is what makes a snapshot survive the
round trip byte for byte; `sqlite3.Connection.iterdump` is rejected below for
the same reason it would be tempting.

## Contracts

None. Nothing external is involved.

## Data and migrations

| Change | Forward | Rollback |
| --- | --- | --- |
| None to the schema | — | — |
| `decisions.sql` in the backup repository | Written on each decision write | Delete the file; the local database is untouched |

## Decisions

| Decision | Chosen | Rejected, and why |
| --- | --- | --- |
| What triggers a backup | A decision write marks the store dirty; the backup runs when the command finishes | Backing up inside `save()` — a run writing several decisions would produce several commits for one run, and would put a network push inside the write path NFR-10 protects |
| What the dump contains | The `decisions` table only, rows ordered by `id` | Whole-database `iterdump` — pulls in scorecards, so a backtest writing 17 of them would produce a commit, which LEDGBAK-02 forbids. Unordered rows also churn the file and produce commits with no change in them |
| How values are written | Raw column text, quoted as SQL literals | Reconstructing rows through the model layer — re-serialises JSON and normalises timestamps, which is exactly the corruption AC-2 exists to prevent |
| Who owns the repository | Pointed at by environment variable, expected to exist with a remote | Creating and pushing a repository on first run — puts remote creation, authentication and the privacy decision inside the tool, and a repository wrongly made public is not recoverable |
| Whether the push is read back | Trusted on its exit status, no read-back | Re-reading the remote to confirm the commit, as ADR-002 requires of ESPN writes. That decision rests on endpoints that return success without having done anything; `git push` does not — it exits non-zero on a rejected or unreachable push, and the local commit is still there either way. The read-back would cost a round trip per decision to confirm something the exit status already proves. ADR-002 stands; this is outside the class of write it was written about |
| How failure is reported | Logged as a warning naming the week, run continues | Raising — would abort a run over a copy of a decision that is already durable locally |
| Startup comparison | Restore the dump into an in-memory database and compare weeks | Parsing the dump text with a regular expression — a second, weaker reader of a format already readable by SQLite |

## Risks

| Risk | Mitigation |
| --- | --- |
| A push blocks the end of a run on a slow network | Failure path is non-fatal and already tested; the decision is durable before the push is attempted |
| Credentials reach the backup through a future column | LEDGBAK-07 scans the full dump text for live cookie and key values on every run of the suite |
| The remote is public by mistake | Out of the tool's hands by design — the manager creates the repository. Named in the setup step, not enforced in code |
| Startup slows on every command | The comparison reads one file into an in-memory database; measured by NFR-10's row below |

## Sequence

```mermaid
sequenceDiagram
  actor Manager
  participant CLI
  participant Store
  participant DB
  participant Backup
  participant Remote
  CLI->>Backup: missing_weeks()
  Backup-->>Manager: weeks held off-machine but not locally
  CLI->>Store: save(decision)
  Store->>DB: INSERT + commit (durable — NFR-10)
  CLI->>Store: backup_if_dirty()
  Store->>Backup: dump decisions, commit, push
  Backup-->>Remote: push
  Backup-->>Manager: warning if unreachable; run still completes
```

---

# Test approach

## Scenario coverage

| Scenario | AC | Level | Test file | Test name | Status |
| --- | --- | --- | --- | --- | --- |
| LEDGBAK-01 | AC-1 | integration | `tests/db/test_backup.py` | `LEDGBAK-01: a recorded decision is committed off-machine` | required |
| LEDGBAK-02 | AC-1 | integration | `tests/db/test_backup.py` | `LEDGBAK-02: computed scorecards are not committed` | required |
| LEDGBAK-03 | AC-2 | integration | `tests/db/test_backup_restore.py` | `LEDGBAK-03: input snapshots survive a round trip unchanged` | required |
| LEDGBAK-04 | AC-6 | integration | `tests/db/test_backup_restore.py` | `LEDGBAK-04: the backtest runs against a restored database` | required |
| LEDGBAK-05 | AC-3 | integration | `tests/db/test_backup.py` | `LEDGBAK-05: the remote is unreachable` | required |
| LEDGBAK-06 | AC-3 | integration | `tests/db/test_backup.py` | `LEDGBAK-06: the backup repository is missing or has no remote configured` | required |
| LEDGBAK-06 | AC-3 | integration | `tests/db/test_backup.py` | `LEDGBAK-06: the backup repository is missing or has no remote configured (nothing configured)` | required |
| LEDGBAK-07 | AC-4 | integration | `tests/db/test_backup.py` | `LEDGBAK-07: the dump is inspected for secrets` | required |
| LEDGBAK-08 | AC-5 | unit | `tests/db/test_backup_weeks.py` | `LEDGBAK-08: the local log is missing weeks the backup holds` | required |
| LEDGBAK-09 | AC-5 | unit | `tests/db/test_backup_weeks.py` | `LEDGBAK-09: the local log is level with or ahead of the backup` | required |
| LEDGBAK-01 | AC-1, AC-2, AC-6 | e2e | `tests/db/test_backup_restore.py` | `LEDGBAK-01: AC-SIGNAL — a season restored into an empty database keeps every week and rebuilds its scorecards` | required |

Unit covers week comparison and dump text; integration drives a real
`tmp_path` repository pushing to a local bare remote; e2e is the acceptance
signal, once.

## Fixtures and test data

| Fixture | Why it must be realistic |
| --- | --- |
| A decision whose `inputs_snapshot` holds unsorted keys, unicode, embedded quotes and a non-UTC timestamp | A snapshot that is already tidy passes a byte-identity test that any re-serialising implementation would also pass, which makes LEDGBAK-03 worthless |
| A bare git repository in `tmp_path` used as the remote | Lets push succeed and fail for real, rather than against a mock that agrees with the implementation |
| Environment holding a cookie-shaped `ESPN_S2` and an API key | LEDGBAK-07 scans for the live values; placeholder strings would not catch a real leak |

## NFR verification

| NFR | Budget | Measured how | Where it runs |
| --- | --- | --- | --- |
| NFR-10 — the decision is durable before its run reports complete | No decision lost on backup failure | LEDGBAK-05 asserts the decision is readable from a freshly opened connection while the remote is unreachable and the run completes | `make test`, every run |

## Not covered by automated tests

| What | Why | How it is checked instead |
| --- | --- | --- |
| The remote repository is actually private | The tool does not create it and cannot see its visibility | The manager confirms it once, when creating it |
| Recovery onto a genuinely new machine | A test asserting a clone works on the machine that wrote it is asserting nothing | Done by hand once, after this slice ships |

## Open questions

None — both of intent.md's are now resolved there.
