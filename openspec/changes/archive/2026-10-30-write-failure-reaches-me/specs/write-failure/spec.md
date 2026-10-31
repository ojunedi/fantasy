## Purpose

A live lineup write that fails on every path, and that a read-back confirms
did not land, reaches the manager before kickoff with the moves to make by hand.

<!-- trace-prefix: WFAIL -->

## ADDED Requirements

### Requirement: An exhausted write is confirmed by reading the lineup back before anyone is told

After a failed live lineup write, the system SHALL read the lineup back with
the cache bypassed. It SHALL notify only when a planned move is not in place,
or when the read-back itself fails, and SHALL record a write whose moves are
all in place as landed.

Serves: AC-1, AC-3, AC-6

#### Scenario: WFAIL-01 — A failed write whose moves landed anyway is not reported

- **GIVEN** a live lineup write that returned an error
- **AND** the read-back shows every planned move in place
- **WHEN** the failure is handled
- **THEN** no notification is sent
- **AND** the decision records the write as landed

#### Scenario: WFAIL-02 — A failed read-back still notifies, and says so

- **GIVEN** a live lineup write that returned an error
- **AND** the read-back itself fails
- **WHEN** the failure is handled before kickoff
- **THEN** a notification is sent
- **AND** it says the lineup could not be checked

#### Scenario: WFAIL-03 — A dry run, a success or a refusal never notifies

- **GIVEN** an execution that was a dry run, succeeded, or was refused by the gate
- **WHEN** it completes
- **THEN** no notification is sent
- **AND** nothing is recorded as a write failure

### Requirement: The manager is told in time, with the approved moves

Before that week's Sunday 1 PM ET kickoff, the system SHALL notify the
manager through the nudge's notifier with the moves from the plan that was
sent and the time left. After kickoff it SHALL record the failure only.

Serves: AC-2, AC-4, AC-5, AC-8

#### Scenario: WFAIL-04 — A confirmed failure before kickoff notifies with the moves and time left

- **GIVEN** a live lineup write that failed, and a read-back showing a planned move not in place
- **AND** kickoff is 2 hours 10 minutes away
- **WHEN** the failure is handled
- **THEN** the notification lists the moves from the plan that was sent
- **AND** it says kickoff is in 2h 10m

#### Scenario: WFAIL-05 — After kickoff the failure is recorded, not notified

- **GIVEN** a confirmed failed lineup write after that week's kickoff
- **WHEN** the failure is handled
- **THEN** no notification is sent
- **AND** the failure is recorded on the decision

### Requirement: Every exhausted write is recorded, and delivery problems never raise

Serves: AC-7

#### Scenario: WFAIL-06 — The failure and the notification attempt are recorded on the decision

- **GIVEN** a confirmed failed lineup write before kickoff
- **WHEN** the failure is handled
- **THEN** the decision records when it failed, the error, the moves, and that the manager was notified

#### Scenario: WFAIL-07 — A notification that cannot be delivered is recorded, not raised

- **GIVEN** a confirmed failed lineup write before kickoff, and a notifier that fails
- **WHEN** the failure is handled
- **THEN** no error is raised
- **AND** the decision records that the notification was not delivered, and why
