# waiver-execution Specification

## Purpose
Waiver-wire candidate scoring for the Waiver Execution context: candidates are
scored against the relative bar, the absolute bar and the startability
condition; signal provenance and freshness are enforced before scoring; and a
decision record is written for every outcome, whether or not a recommendation
is produced.

<!-- trace-prefix: WADD -->

## Requirements

### Requirement: Waiver candidates are scored against both bars and the startability condition

A candidate earns a recommendation only if it clears all three conditions:
beats the player it would displace (relative bar), ranks inside the
league-wide startable tier (absolute bar), and projects to start within three
weeks against a fully available roster. Clearing one or two is not a weaker
recommendation — it is no recommendation.

Serves: AC-1, AC-2, AC-3, AC-4, AC-5, AC-6

#### Scenario: WADD-01 — Candidate clears all three conditions

- **GIVEN** a waiver candidate whose rest-of-season projected value exceeds the
  worst rostered player at its position
- **AND** the candidate ranks inside the league-wide startable tier (team count
  × starting slots at that position, from league settings)
- **AND** the candidate projects to start within the next three weeks against a
  fully available roster
- **WHEN** the waiver scan runs
- **THEN** the candidate is included in the recommendation with the player it
  displaces and the value margin over that player named

#### Scenario: WADD-02 — Candidate clears fewer than all three conditions

- **GIVEN** a waiver candidate that clears the relative bar but not the absolute
  bar, or clears both bars but does not project to start within three weeks
  against a fully available roster
- **WHEN** the waiver scan runs
- **THEN** the candidate does not appear as a recommendation

#### Scenario: WADD-04 — No candidate clears all conditions

- **GIVEN** no waiver candidate clears all three conditions
- **WHEN** the waiver scan runs
- **THEN** the output names the closest candidate, which condition it failed,
  and by how much
- **AND** no recommendation is produced
- **AND** no error is raised

---

### Requirement: Signal freshness is enforced before analysis begins

A stale or unprovenanced signal stops the run before any candidate is scored.

Serves: AC-8, AC-9

#### Scenario: WADD-05 — Signal missing provenance is rejected

- **GIVEN** a signal in the bundle that carries no source identifier or no
  as-of timestamp
- **WHEN** the waiver scan runs
- **THEN** the run halts before any candidate is scored
- **AND** no recommendation is produced
- **AND** the error names the signal that failed provenance validation

#### Scenario: WADD-06 — Stale signal halts the run

- **GIVEN** a signal whose age at the moment of the scan exceeds its freshness
  threshold
- **WHEN** the waiver scan runs
- **THEN** the run reports stale and names the failing source
- **AND** no recommendation is produced
- **AND** the WaiverDecision record is still written to decisions.db with the
  stale-signal reason before the run reports completion

---

### Requirement: Every waiver decision is written to the ledger before the run completes

Both outcomes — recommendation and no-add — are written to decisions.db as a
WaiverDecision before the run reports completion. A hold carries the same weight
as a recommendation.

Serves: AC-10, AC-11

#### Scenario: WADD-07 — Recommendation outcome written before run completes

- **GIVEN** at least one candidate clears all three conditions
- **WHEN** the waiver scan runs and produces a recommendation
- **THEN** the WaiverDecision record is written to decisions.db before the run
  reports completion
- **AND** the record includes the recommended candidate, the displaced player,
  and the value margin

#### Scenario: WADD-08 — No-add outcome written with same weight

- **GIVEN** no candidate clears all three conditions
- **WHEN** the waiver scan runs and produces no recommendation
- **THEN** a WaiverDecision record is still written to decisions.db before the
  run reports completion
- **AND** the record includes the closest candidate, which condition it failed,
  and by how much

---

### Requirement: Brief numbers are traceable to the analysis output

Every number in the waiver brief must appear in the analysis output. The brief
may restate; it may not introduce.

Serves: AC-7

#### Scenario: WADD-09 — Brief containing an untraced number is rejected

- **GIVEN** a generated brief containing a projected-value figure that does not
  appear in the WaiverAnalysis output
- **WHEN** the brief is validated before being presented
- **THEN** the brief is rejected and the run fails with a brief-integrity error
- **AND** no recommendation is surfaced to the manager

---

### Requirement: Waiver scan uses at most 3 LLM calls per run

Serves: AC-12

#### Scenario: WADD-10 — Run completes within budget

- **GIVEN** a waiver scan that runs to completion
- **WHEN** the run ends
- **THEN** the total LLM calls made during the run is ≤ 3

---

| Error | When | Retryable |
|---|---|---|
| `SIGNAL_MISSING_PROVENANCE` | Signal has no source or timestamp | No — fix the signal source |
| `SIGNAL_STALE` | Signal exceeds freshness threshold | No — re-fetch the signal |
| `BRIEF_INTEGRITY_VIOLATION` | Brief number not in analysis output | No — fix the brief generator |
