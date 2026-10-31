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

### Requirement: An approved claim is filed as one waiver transaction behind the approval gate

The system SHALL file an approved waiver decision as a single ESPN waiver
transaction for the manager's team holding the recommended add and the
displaced drop, taken from the stored decision. It SHALL send it only when the
shared approval gate returns live; any other confirmation SHALL be a Dry run,
and a decision that is not approved SHALL be refused.

Serves: AC-1, AC-2, AC-9

#### Scenario: WADD-11 — Filing builds one transaction with the add and the drop

- **GIVEN** an approved waiver decision recommending an add and naming the player it displaces
- **WHEN** the manager files it
- **THEN** exactly one waiver transaction is built for the manager's team
- **AND** it holds one ADD item for the recommended player and one DROP item for the displaced player

#### Scenario: WADD-12 — Anything but LIVE is a Dry run

- **GIVEN** an approved waiver decision
- **WHEN** the manager files it with a confirmation other than exactly `LIVE`
- **THEN** the page shows the transaction that would be sent
- **AND** nothing is transmitted to ESPN
- **AND** no filing is recorded on the decision

#### Scenario: WADD-13 — A decision that is not approved is refused

- **GIVEN** a waiver decision that is pending or declined
- **WHEN** a filing request arrives with the confirmation `LIVE`
- **THEN** the response is a refusal with status 409
- **AND** nothing is transmitted to ESPN

#### Scenario: WADD-19 — The players come from the decision log, not the request

- **GIVEN** an approved waiver decision
- **WHEN** a filing request carries extra fields naming other players to add and drop
- **THEN** the transaction holds the players from the stored decision

### Requirement: The add and drop are re-checked against the league at the moment of filing

Immediately before a live send, the system SHALL read the league fresh and
SHALL refuse the filing if the drop is no longer on the manager's roster or
the add is no longer a free agent or on waivers.

Serves: AC-3

#### Scenario: WADD-14 — A roster that changed since the scan refuses the filing

- **GIVEN** an approved waiver decision whose drop player has since left the manager's roster, or whose add player has since been rostered elsewhere
- **WHEN** the manager files it with `LIVE`
- **THEN** the filing is refused
- **AND** the message names the player who moved
- **AND** nothing is transmitted to ESPN

### Requirement: A filing is believed only after reading the league back, and is logged before it is reported

After a live send, the system SHALL read the league's transactions with the
cache bypassed and SHALL report the claim confirmed only when a pending waiver
transaction for the manager's team holds the same add and drop. Every live
attempt SHALL be written to the decision log — the transaction, the
confirmation state, and the waiver priority position read at filing — before
the page reports it.

Serves: AC-4, AC-5, AC-6, AC-7, AC-8

#### Scenario: WADD-15 — A claim found pending on read-back is confirmed

- **GIVEN** a live send that ESPN accepts
- **WHEN** the league's transactions, read with the cache bypassed, include a pending waiver claim for my team with the same add and drop
- **THEN** the page reports the claim filed and pending, with my waiver priority position
- **AND** the decision log records the transaction, the state confirmed, and the priority position

#### Scenario: WADD-16 — An accepted send the read-back cannot find is not confirmed

- **GIVEN** a live send that ESPN accepts
- **WHEN** the read-back finds no pending waiver claim for my team with the same players
- **THEN** the page reports the claim filed but not confirmed and tells the manager to check the ESPN app
- **AND** the filing form is not offered again
- **AND** the decision log records the state unconfirmed

#### Scenario: WADD-17 — A send ESPN rejects is reported as not filed

- **GIVEN** a live send that ESPN rejects with an error status, or whose connection to ESPN never opened
- **WHEN** the filing completes
- **THEN** the page reports the claim not filed, with ESPN's error and the manual steps
- **AND** the decision log records the state failed
- **AND** the filing form is offered again

#### Scenario: WADD-20 — A send that may have reached ESPN is never reported as not filed

- **GIVEN** a live send whose connection opened but whose response never arrived (a timeout or dropped response)
- **WHEN** the filing completes
- **THEN** the league is read back before anything is reported
- **AND** the state is confirmed if the claim is pending, otherwise unconfirmed — never failed
- **AND** the filing form is not offered again

### Requirement: A claim filed live is not filed twice

A live filing SHALL be recorded as in progress before anything is sent, and
no further live filing SHALL be accepted for any waiver decision that week
while one is in progress, confirmed or unconfirmed.

Serves: AC-8

#### Scenario: WADD-21 — A re-run scan after filing does not reopen the claim

- **GIVEN** a claim filed live this week, and a newer scan for the same week marked "Intend to claim"
- **WHEN** a filing request arrives with `LIVE`
- **THEN** the response is a refusal with status 409
- **AND** nothing is transmitted to ESPN

#### Scenario: WADD-18 — A decision already filed live cannot be filed again

- **GIVEN** a waiver decision whose live filing is recorded as confirmed or unconfirmed
- **WHEN** a filing request arrives with `LIVE`
- **THEN** the response is a refusal with status 409
- **AND** nothing is transmitted to ESPN
- **AND** the recorded filing is unchanged

---

| Verdict / state | When | Web status | Manager sees |
| --- | --- | --- | --- |
| Dry run | approved, confirmation not `LIVE` | 200 | "Dry run — nothing was sent. …" |
| confirmed | live send found pending on read-back | 200 | "Claim filed — ESPN shows it as pending. …" |
| unconfirmed | live send accepted, not found | 200 | "ESPN accepted the claim but it doesn't show …" |
| failed | ESPN error status, or the connection never opened | 200 | "The claim was not filed — {error}. …" |
| refused `NOT_APPROVED` | decision not approved | 409 | "This decision is {state}, not approved — nothing was sent." |
| refused `ROSTER_CHANGED` | drop or add moved since the scan | 409 | "Nothing was sent — {player} …" |
| refused `ALREADY_FILED` | a live filing this week is in progress, confirmed or unconfirmed | 409 | "This week's claim was already filed — nothing was sent." |
| refused `LEAGUE_UNREADABLE` | the fresh legality read failed | 409 | "Couldn't read the league to re-check the claim — nothing was sent. …" |
