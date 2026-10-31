## Purpose

Every number in a generated lineup or trade brief traces to the analysis the
run computed; a brief that introduces one is withheld.

<!-- trace-prefix: BRIEF -->

## ADDED Requirements

### Requirement: A brief may rephrase a computed number, never introduce one

The system SHALL check every number in a lineup brief, each trade rationale
and each counterparty pitch against the run's analysis — its tool outputs,
saved projections, week and season — allowing a number written at lower
precision when the computed value rounds to it. A text with any untraced
number SHALL be withheld: replaced by a notice naming the untraced numbers,
with the original kept on the record. The recommendation itself SHALL NOT
change, and the check SHALL make no model call.

Serves: AC-1, AC-2, AC-3, AC-4, AC-5, AC-6

#### Scenario: BRIEF-01 — A lineup brief that only restates computed numbers is shown as written

- **GIVEN** a lineup run whose analysis projected a player at 23.09
- **WHEN** the brief says "23.1 projected" and quotes the week
- **THEN** the brief is shown unchanged

#### Scenario: BRIEF-02 — One invented number among many withholds the lineup brief

- **GIVEN** a lineup brief quoting several computed numbers and one, 31.5, the analysis never produced
- **WHEN** the record is built
- **THEN** the brief is replaced by a notice naming 31.5
- **AND** the original brief is kept on the record
- **AND** the recommended starters are unchanged

#### Scenario: BRIEF-03 — An invented number in a counterparty pitch withholds that pitch only

- **GIVEN** a trade proposal whose rationale quotes computed values and whose pitch quotes a number the analysis never produced
- **WHEN** the record is built
- **THEN** the pitch is replaced by a notice naming the number
- **AND** the rationale is shown as written
- **AND** the trade package is unchanged

#### Scenario: BRIEF-04 — The check makes no model call

- **GIVEN** a lineup run whose brief is withheld
- **WHEN** the record is built
- **THEN** no further model call is made
