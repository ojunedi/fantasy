# lineup-execution Specification

## Purpose
TBD - created by archiving change pre-kickoff-nudge. Update Purpose after archive.

## Requirements

### Requirement: Pre-kickoff nudge fires for an unread recommendation

When the time remaining until the first-game kickoff of the current week falls
within the configured threshold (default 2 hours), and the week's lineup
decision is in a state that has not yet received the manager's response
(briefed or presented), the system SHALL deliver a nudge to the manager naming
the time remaining and the action needed.

Serves: AC-1, AC-4, AC-7

#### Scenario: PKICK-01 — Nudge fires when recommendation is unread at threshold

- **GIVEN** a LineupDecision for the current week in `presented` state
- **AND** the first-game kickoff is exactly 2 hours away
- **WHEN** the pre-kickoff check runs
- **THEN** a nudge is delivered containing the time remaining until kickoff
- **AND** the nudge includes the URL or CLI command to open the recommendation
- **AND** the LineupDecision remains in `presented` state (the nudge is not a state transition)

#### Scenario: PKICK-02 — Nudge fires for a briefed-but-not-yet-presented recommendation

- **GIVEN** a LineupDecision for the current week in `briefed` state
- **AND** the first-game kickoff is 90 minutes away
- **WHEN** the pre-kickoff check runs
- **THEN** a nudge is delivered
- **AND** the LineupDecision remains in `briefed` state

#### Scenario: PKICK-03 — No nudge when recommendation is already approved

- **GIVEN** a LineupDecision for the current week in `approved` state
- **AND** the first-game kickoff is 90 minutes away
- **WHEN** the pre-kickoff check runs
- **THEN** no nudge is delivered

#### Scenario: PKICK-04 — No nudge when recommendation is overridden

- **GIVEN** a LineupDecision for the current week in `overridden` state
- **AND** the first-game kickoff is 90 minutes away
- **WHEN** the pre-kickoff check runs
- **THEN** no nudge is delivered

#### Scenario: PKICK-05 — No nudge when recommendation is recorded as unactioned

- **GIVEN** a LineupDecision for the current week in `unactioned` state
- **AND** the first-game kickoff is 90 minutes away
- **WHEN** the pre-kickoff check runs
- **THEN** no nudge is delivered

#### Scenario: PKICK-06 — No nudge when no recommendation exists for the current week

- **GIVEN** no LineupDecision exists for the current week
- **AND** the first-game kickoff is 90 minutes away
- **WHEN** the pre-kickoff check runs
- **THEN** no nudge is delivered
- **AND** no error is raised

#### Scenario: PKICK-07 — No nudge when kickoff has already passed

- **GIVEN** a LineupDecision for the current week in `presented` state
- **AND** the first-game kickoff was 5 minutes ago
- **WHEN** the pre-kickoff check runs
- **THEN** no nudge is delivered

### Requirement: Nudge delivery failures are logged without altering decision state

If the nudge cannot be delivered, the system SHALL write a failure record to
decisions.db with a timestamp, and SHALL NOT change the LineupDecision's state
or the input snapshot associated with it.

Serves: AC-6, invariant I-10 (LineupDecision)

#### Scenario: PKICK-08 — Delivery failure is logged; decision state is unchanged

- **GIVEN** a LineupDecision for the current week in `presented` state
- **AND** the nudge delivery mechanism is unavailable (e.g. notification permission denied)
- **WHEN** the pre-kickoff check runs
- **THEN** a failure record is written to decisions.db with an `as_of` timestamp
- **AND** the LineupDecision remains in `presented` state
- **AND** the input snapshot is not modified

### Requirement: Nudge threshold is configurable

The threshold before kickoff at which a nudge fires SHALL be read from
configuration (default: 120 minutes). No code change is required to adjust it.

Serves: AC-7

#### Scenario: PKICK-09 — Custom threshold is respected

- **GIVEN** the nudge threshold is configured to 60 minutes
- **AND** a LineupDecision for the current week is in `presented` state
- **AND** the first-game kickoff is 75 minutes away
- **WHEN** the pre-kickoff check runs
- **THEN** no nudge is delivered
- **AND** when checked again with 55 minutes remaining, a nudge is delivered

#### Scenario: PKICK-10 — Acceptance signal: manager sets lineup on time after nudge

- **GIVEN** an unread lineup recommendation exists within the nudge threshold
- **AND** the pre-kickoff check fires
- **WHEN** the manager follows the nudge and opens the recommendation
- **THEN** the lineup is set before kickoff

Serves: AC-1 (end-to-end acceptance signal — manual only)

---

| Error | When | Retryable |
|---|---|---|
| `NUDGE_DELIVERY_FAILED` | Notification channel unavailable | No — log and continue |
