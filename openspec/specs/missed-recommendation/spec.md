# missed-recommendation Specification

## Purpose
A lineup recommendation never approved or overridden before kickoff is
recorded as missed, with its cost in pre-kickoff projected points.

<!-- trace-prefix: LMISS -->

## Requirements

### Requirement: A week with no actioned lineup decision by kickoff is recorded as missed

The system SHALL record a week as missed when no lineup decision for it got a
human response before that week's kickoff — Sunday 1 PM ET of the NFL week,
derived from the week number. It SHALL record the miss once the week is
settled (Tuesday 6 AM ET), on the newest run that recommended starters and was
made before kickoff, at most once. It SHALL record nothing before then,
nothing for a week with a response before kickoff, SHALL never charge a run
made after kickoff, and SHALL NOT set a human response or an override reason
on a missed decision.

Serves: AC-1, AC-2, AC-3, AC-7, AC-8

#### Scenario: LMISS-01 — An unactioned week after kickoff is recorded as missed

- **GIVEN** a week whose only lineup decision has no human response
- **AND** that week's Sunday 1 PM ET kickoff has passed
- **WHEN** missed weeks are recorded
- **THEN** the decision's outcome records it as missed
- **AND** the decision has no human response
- **AND** the decision has no override reason

#### Scenario: LMISS-02 — A week with an actioned decision is not missed

- **GIVEN** a week with one approved lineup decision and one unactioned one
- **AND** kickoff has passed
- **WHEN** missed weeks are recorded
- **THEN** neither decision is recorded as missed

#### Scenario: LMISS-03 — Nothing is recorded before the week is settled

- **GIVEN** a week whose lineup decision has no human response
- **AND** the week is not yet settled — before kickoff, or while its games are still being played
- **WHEN** missed weeks are recorded
- **THEN** nothing is recorded

#### Scenario: LMISS-09 — A run made after kickoff is never charged

- **GIVEN** a lineup run made after its week's kickoff, with no human response
- **WHEN** missed weeks are recorded after the week is settled
- **THEN** nothing is recorded for that run

#### Scenario: LMISS-10 — A response after kickoff does not erase the miss

- **GIVEN** a week whose only lineup run was approved after kickoff
- **WHEN** missed weeks are recorded after the week is settled
- **THEN** the week is recorded as missed
- **AND** the late response is kept as it was

#### Scenario: LMISS-04 — A recorded miss is not recomputed

- **GIVEN** a week already recorded as missed
- **WHEN** missed weeks are recorded again with different projections or lineup available
- **THEN** the recorded miss is unchanged
- **AND** the standing lineup is not read again

### Requirement: The cost uses only the projections saved before kickoff

The system SHALL compute the cost as the recommended starters' projected total
minus the standing starters' projected total, both from the projections saved
on the decision. A standing starter with no saved projection SHALL count as 0
and be listed as unprojected. Actual points, when available, SHALL be recorded
beside the cost as hindsight and SHALL NOT be the cost.

Serves: AC-4, AC-5, AC-6

#### Scenario: LMISS-05 — The cost is the difference in saved projections

- **GIVEN** a missed week whose recommended starters projected 120.0 and whose standing starters projected 112.5 in the saved projections
- **WHEN** the miss is recorded
- **THEN** the cost is 7.5
- **AND** the recommended and standing starters are recorded

#### Scenario: LMISS-06 — A standing starter with no saved projection counts as zero and is named

- **GIVEN** a missed week where one standing starter has no saved projection
- **WHEN** the miss is recorded
- **THEN** that starter counts as 0 in the standing total
- **AND** the miss lists that starter as unprojected

#### Scenario: LMISS-07 — Actual points are recorded as hindsight, never as the cost

- **GIVEN** a missed week whose actual points are available, and differ from the projections
- **WHEN** the miss is recorded
- **THEN** the actual totals for both lineups are recorded as hindsight
- **AND** the cost is still the difference in saved projections

### Requirement: The decision history shows a missed week and its cost

Serves: AC-1, AC-9

#### Scenario: LMISS-11 — Opening the history records a settled missed week

- **GIVEN** a settled week whose only lineup run got no response
- **WHEN** the manager opens the decision history
- **THEN** the week is recorded as missed
- **AND** the row shows it

#### Scenario: LMISS-08 — History shows missed with the projected cost

- **GIVEN** a decision recorded as missed with a cost of 7.5
- **WHEN** the manager opens the decision history
- **THEN** the decision's row shows "missed" and "−7.5 proj"
