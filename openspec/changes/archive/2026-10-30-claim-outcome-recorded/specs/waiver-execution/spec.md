## ADDED Requirements

### Requirement: A filed claim is resolved from the league's transactions, never inferred

The system SHALL resolve a filed claim only by reading the league's
transactions with the cache bypassed and finding this team's waiver claim for
the same add and drop in the same week. It SHALL record cleared when that
claim executed; lost to priority when it failed because the player left the
pool and another team's waiver claim for the same player executed; failed for
any other failure; cancelled when cancelled; and SHALL record nothing while
the claim is pending or not found.

Serves: AC-1, AC-2, AC-3, AC-4, AC-5

#### Scenario: WADD-22 — An executed claim is recorded as cleared

- **GIVEN** a filed claim, and the league's transactions show this team's waiver claim for the same add and drop in the same week as executed
- **WHEN** the manager checks the result
- **THEN** the result is recorded as cleared
- **AND** the page says the claim cleared

#### Scenario: WADD-23 — A claim beaten by another team is recorded as lost to priority

- **GIVEN** a filed claim that read back failed because the player left the pool
- **AND** another team's waiver claim for the same player executed
- **WHEN** the manager checks the result
- **THEN** the result is recorded as lost to priority
- **AND** it names the team that won the player

#### Scenario: WADD-24 — Any other failure is not a priority loss

- **GIVEN** a filed claim that read back failed for another reason, such as the drop player already being gone
- **WHEN** the manager checks the result
- **THEN** the result is recorded as failed with ESPN's reason
- **AND** it is not recorded as lost to priority

#### Scenario: WADD-25 — A pending or missing claim stays unresolved

- **GIVEN** a filed claim that still reads back pending, or that cannot be found
- **WHEN** the manager checks the result
- **THEN** no result is recorded
- **AND** the page says ESPN hasn't processed the claim yet and offers the check again

#### Scenario: WADD-26 — A cancelled claim is recorded as cancelled

- **GIVEN** a filed claim that reads back cancelled
- **WHEN** the manager checks the result
- **THEN** the result is recorded as cancelled

### Requirement: Every result carries the priority it was filed under and is logged before it is shown

Serves: AC-6, AC-7, AC-8

#### Scenario: WADD-27 — The result records the filing's priority position before the page shows it

- **GIVEN** a filed claim whose filing recorded a waiver priority position
- **WHEN** a result is recorded
- **THEN** the recorded result carries that priority position and the team count
- **AND** it is in the decision log when the page renders

#### Scenario: WADD-28 — A recorded result is not read again

- **GIVEN** a claim whose result is already recorded
- **WHEN** a check request arrives
- **THEN** the league is not read
- **AND** the recorded result is unchanged
