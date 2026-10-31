## Purpose

The single rule that decides whether an execution writes to ESPN for real,
runs as a Dry run, or is refused — called by every surface that can write.

<!-- trace-prefix: APPGATE -->

## ADDED Requirements

### Requirement: A write runs live only from an approved or overridden decision confirmed with LIVE

The system SHALL transmit a write to ESPN only when the decision is approved
or overridden and the confirmation typed for that execution is exactly `LIVE`.
Every other approved or overridden execution SHALL be a Dry run.

Serves: AC-1, AC-3

#### Scenario: APPGATE-01 — Approved decision confirmed with LIVE writes

- **GIVEN** a lineup decision in the approved state
- **WHEN** the manager executes it and types `LIVE`
- **THEN** the gate authorises a live write
- **AND** the executor is called with live set

#### Scenario: APPGATE-02 — Overridden decision with a reason, confirmed with LIVE, writes

- **GIVEN** a lineup decision in the overridden state with a written reason
- **WHEN** the manager executes it and types `LIVE`
- **THEN** the gate authorises a live write

#### Scenario: APPGATE-03 — Anything but exactly LIVE is a Dry run

- **GIVEN** a lineup decision in the approved state
- **WHEN** the manager executes it and types `live`, `Live`, `LIVE ` (trailing space), ` LIVE` (leading space), or nothing
- **THEN** the gate authorises a Dry run
- **AND** the executor is called with live unset
- **AND** nothing is transmitted to ESPN

### Requirement: A decision without a recorded approval is refused

The system SHALL refuse to execute a decision that is pending, rejected or
declined, and an overridden decision with no written reason. A refused
execution SHALL NOT call the executor, not even for a Dry run.

Serves: AC-2, AC-4

#### Scenario: APPGATE-04 — Pending, rejected or declined decision is refused

- **GIVEN** a decision with no human response, or one that was rejected, or one that was declined
- **WHEN** an execution is requested with the confirmation `LIVE`
- **THEN** the gate refuses it
- **AND** the refusal names the decision's state
- **AND** the executor is not called

#### Scenario: APPGATE-05 — Override without a written reason is refused

- **GIVEN** a decision in the overridden state whose written reason is missing or only whitespace
- **WHEN** an execution is requested with the confirmation `LIVE`
- **THEN** the gate refuses it
- **AND** the refusal says the written reason is missing
- **AND** the executor is not called

### Requirement: Authorisation is decided per execution and never persisted

The system SHALL decide authorisation from the stored decision and the
confirmation typed for that execution, every time, and SHALL NOT save or
reuse the result.

Serves: AC-5

#### Scenario: APPGATE-06 — A live execution does not authorise the next one

- **GIVEN** an approved decision that has just been executed with `LIVE`
- **WHEN** it is executed again with an empty confirmation
- **THEN** the second execution is a Dry run
- **AND** the decision log holds no record of the earlier authorisation

### Requirement: Every surface that can write asks the same gate

The system SHALL route the command line's lineup write, the command line's
trade send and the web app's lineup write through one gate, and no other code
SHALL compare a confirmation against `LIVE`. On the web, the approval state
SHALL come from the decision log, never from the request.

Serves: AC-6, AC-7, AC-8

#### Scenario: APPGATE-07 — Web write step refuses an unapproved decision whatever the request says

- **GIVEN** a lineup decision with no human response
- **WHEN** a request to the web write step carries `confirm=LIVE` and extra fields claiming approval
- **THEN** the response is a refusal with status 409
- **AND** the executor is not called
- **AND** the decision's state in the decision log is unchanged

#### Scenario: APPGATE-08 — Both surfaces give the same verdict for every state and confirmation

- **GIVEN** every combination of decision state (pending, approved, overridden with a reason, overridden without one, rejected, declined) and confirmation (`LIVE`, `live`, `Live`, `LIVE `, ` LIVE`, empty)
- **WHEN** the command line and the web app each decide whether to execute
- **THEN** both reach the same verdict — live, Dry run or refused — for every combination

#### Scenario: APPGATE-10 — Web write step refuses an approved decision that is not a lineup

- **GIVEN** an approved trade or waiver decision
- **WHEN** a request to the web lineup write step carries `confirm=LIVE`
- **THEN** the response is a refusal with status 409
- **AND** no lineup is planned or written

#### Scenario: APPGATE-09 — No code outside the gate compares against LIVE

- **GIVEN** the application source
- **WHEN** it is searched for comparisons against the string `LIVE`
- **THEN** the only one is inside the gate

---

| Verdict | When | Web status | Manager sees |
| --- | --- | --- | --- |
| live | approved or overridden-with-reason, confirmation exactly `LIVE` | 200 | the execution result |
| Dry run | approved or overridden-with-reason, any other confirmation | 200 | "Dry run" result |
| refused `NOT_APPROVED` | pending, rejected or declined | 409 | "This decision is <state>, not approved — nothing was sent." |
| refused `OVERRIDE_REASON_MISSING` | overridden with no written reason | 409 | "This override has no written reason — nothing was sent." |
| refused `NOT_A_LINEUP` | web lineup write step, decision is not a lineup with starters | 409 | "This decision is not a lineup with starters — nothing was sent." |
