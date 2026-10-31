# signal-freshness Specification

## Purpose
A lineup decision's signals are checked against per-type freshness
thresholds before analysis; a stale required signal makes the agent abstain
with the evidence.

<!-- trace-prefix: SIGSTALE -->

## Requirements

### Requirement: The bundle reports stale and names every failing signal

The system SHALL assess each signal against its type's threshold —
projections 6 h and injuries 1 h (required); usage trends 7 days, Vegas lines
24 h, weather 12 h (optional). The bundle SHALL report fresh only when every
required signal is available, has an as-of time, and is within threshold. An
unavailable signal, or one without an as-of time, SHALL count as stale.

Serves: AC-1, AC-2, AC-3, AC-5

#### Scenario: SIGSTALE-01 — A required signal past its threshold makes the bundle stale

- **GIVEN** projections 7 hours old and injuries 10 minutes old
- **WHEN** the bundle is assessed
- **THEN** it reports stale
- **AND** it names projections, its age, and its 6-hour threshold

#### Scenario: SIGSTALE-02 — A missing or unstamped signal is stale, never fresh

- **GIVEN** projections that failed to load, or that carry no as-of time
- **WHEN** the bundle is assessed
- **THEN** it reports stale
- **AND** names projections as missing

#### Scenario: SIGSTALE-03 — A stale optional signal is named but does not make the bundle stale

- **GIVEN** fresh projections and injuries, and weather 20 hours old
- **WHEN** the bundle is assessed
- **THEN** it reports fresh
- **AND** names weather as stale

### Requirement: A stale bundle ends the lineup run in an abstention with the evidence

When the bundle is stale, the lineup run SHALL abstain without calling the
model, recording each failing signal's name, age or absence, and threshold.

Serves: AC-4, AC-6, AC-7

#### Scenario: SIGSTALE-04 — A stale run abstains before any model call

- **GIVEN** a lineup run whose projections failed to load
- **WHEN** the agent decides
- **THEN** the decision is an abstention
- **AND** the model was not called
- **AND** the abstention names projections as missing, with its threshold

#### Scenario: SIGSTALE-05 — A fresh run proceeds as before

- **GIVEN** a lineup run whose required signals are fresh
- **WHEN** the agent decides
- **THEN** the model is called as before

#### Scenario: SIGSTALE-06 — The history shows the stale abstention and why

- **GIVEN** a stale-signal abstention in the decision log
- **WHEN** the manager opens its decision page
- **THEN** it reads as abstained
- **AND** the memo names the stale signal
