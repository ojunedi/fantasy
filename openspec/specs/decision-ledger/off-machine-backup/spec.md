# decision-ledger/off-machine-backup Specification

## Purpose

Keep a committed copy of the decision log in a private repository off this machine, so the season's record of what the agent recommended and what the manager overrode survives the loss of the laptop.

The decision log is the irreplaceable half of the ledger. The weekly scorecards sitting beside it are recomputed by replaying historical league data, so they are deliberately not copied; the decisions cannot be rebuilt from anything.

<!-- trace-prefix: LEDGBAK -->

## Requirements

### Requirement: Every decision write reaches the off-machine copy

The system SHALL, after any write to the decision log, produce a SQL dump of the decision log and commit it to the configured private backup repository, with a commit message naming the week and season just written.

Serves: AC-1

#### Scenario: LEDGBAK-01 — A recorded decision is committed off-machine

- **GIVEN** a configured backup repository with a reachable remote
- **AND** a lineup decision for week 5 of the 2026 season recorded in the decision log
- **WHEN** the run that recorded it completes
- **THEN** a SQL dump of the decision log exists in the backup repository
- **AND** the dump contains the week 5 decision
- **AND** a commit exists whose message names week 5 and season 2026
- **AND** the commit is present on the remote

#### Scenario: LEDGBAK-02 — Computed scorecards are not committed

- **GIVEN** a full-season backtest that writes 17 weekly scorecards and no decisions
- **WHEN** the backtest completes
- **THEN** no new commit is created in the backup repository
- **AND** the decision log dump is unchanged

### Requirement: A restored decision log is byte-identical and usable

The system SHALL produce a dump that, restored into an empty database, reproduces every stored input snapshot byte for byte — no re-serialisation, no timestamp normalisation, no key reordering — and yields a database the rest of the system reads and writes without error, including the backtest, which recomputes its scorecards from historical league data rather than from the decision log.

Serves: AC-2, AC-6

#### Scenario: LEDGBAK-03 — Input snapshots survive a round trip unchanged

- **GIVEN** a decision log holding decisions whose input snapshots were frozen at record time
- **WHEN** the dump is restored into an empty database
- **AND** the raw snapshot bytes of every row are compared against the original
- **THEN** every snapshot is byte-identical to the original
- **AND** no snapshot has been rewritten by the backup or restore

#### Scenario: LEDGBAK-04 — The backtest runs against a restored database

- **GIVEN** a database restored from any commit in the backup repository, holding decisions and no scorecards
- **WHEN** the backtest is run against it
- **THEN** it completes without error
- **AND** it writes a scorecard for every week it was asked to replay
- **AND** every restored decision is still readable afterwards

### Requirement: A backup failure never costs a decision or a run

The system SHALL, when the backup cannot reach its remote, leave the decision already written and durable in local storage, name the failure to the manager, and allow the run that produced the decision to complete.

Serves: AC-3 · NFR-10 — every decision is written to SQLite before its run reports completion

#### Scenario: LEDGBAK-05 — The remote is unreachable

- **GIVEN** a decision recorded in the local decision log
- **AND** a backup remote that cannot be reached
- **WHEN** the backup is attempted
- **THEN** the manager is shown a message naming the backup failure and the week it affects
- **AND** the decision remains present and readable in the local decision log
- **AND** the run reports complete
- **AND** the run is not aborted
- **AND** the decision is not rolled back

#### Scenario: LEDGBAK-06 — The backup repository is missing or has no remote configured

- **GIVEN** no backup repository configured, or one with no remote
- **WHEN** a decision is recorded
- **THEN** the manager is shown a message naming what is not configured
- **AND** the decision is written to the local decision log
- **AND** the run reports complete
- **AND** no partial or empty commit is created

### Requirement: The off-machine copy carries no credentials

The system SHALL exclude from the dump every ESPN session cookie, every API key, and every value read from the environment.

Serves: AC-4

#### Scenario: LEDGBAK-07 — The dump is inspected for secrets

- **GIVEN** a running configuration holding an ESPN session cookie and provider API keys
- **AND** a decision recorded while that configuration was in use
- **WHEN** the dump is produced and its full text is scanned
- **THEN** no ESPN session cookie value appears in it
- **AND** no API key value appears in it
- **AND** no value read from the environment appears in it

### Requirement: A local decision log behind the backup is reported at startup

The system SHALL, at startup, compare the weeks held in the backup repository against the weeks held in the local decision log, and name every week the backup holds that the local log does not.

Serves: AC-5

#### Scenario: LEDGBAK-08 — The local log is missing weeks the backup holds

- **GIVEN** a backup repository holding decisions for weeks 1 through 5 of the 2026 season
- **AND** a local decision log holding weeks 1, 2, and 5
- **WHEN** the tool starts
- **THEN** the manager is shown a message naming weeks 3 and 4 as missing locally
- **AND** no restore is performed automatically
- **AND** the local decision log is not modified

#### Scenario: LEDGBAK-09 — The local log is level with or ahead of the backup

- **GIVEN** a local decision log holding every week the backup holds
- **WHEN** the tool starts
- **THEN** no missing-week message is shown
- **AND** startup proceeds
