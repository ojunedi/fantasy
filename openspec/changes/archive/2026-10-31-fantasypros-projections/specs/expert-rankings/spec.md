## Purpose

FantasyPros consensus rankings sit beside ESPN's projections as an optional,
date-stamped signal, and sharp disagreements between the two are flagged to
the lineup agent.

<!-- trace-prefix: FPRANK -->

## ADDED Requirements

### Requirement: Rostered players carry the experts' consensus rank, stamped with its own date

The system SHALL attach to each rostered player FantasyPros ranks his
consensus rank, spread, best and worst from the PPR position page, matched to
ESPN by player id, with FantasyPros as the source and the feed's scrape date
as the as-of time.

Serves: AC-1, AC-2, AC-6

#### Scenario: FPRANK-01 — A rostered player gets his consensus rank and the feed's date

- **GIVEN** a FantasyPros PPR running-back page scraped on 2026-10-30 ranking a rostered back RB2 (ecr 2.16, spread 0.67)
- **WHEN** signals are collected
- **THEN** that player carries ecr 2.16, spread 0.67, best and worst
- **AND** the signal's source is FantasyPros and its as-of time is 2026-10-30

### Requirement: Sharp disagreements are flagged; the rankings never decide or block

The agent's signal summary SHALL flag a player whose ESPN positional rank and
expert rank differ by at least 6 spots and by more than twice the spread. The
rankings SHALL be an optional signal (48 hours), and ESPN's projected points
SHALL remain the optimizer's only input; each decision SHALL record the
rankings with their scrape date.

Serves: AC-3, AC-4, AC-5

#### Scenario: FPRANK-02 — A sharp disagreement is flagged with both ranks

- **GIVEN** a back ESPN ranks 18th at his position whom the experts rank 7th with a spread of 2.0
- **WHEN** the agent reads its signals
- **THEN** the summary flags him with ESPN's rank and the experts' rank

#### Scenario: FPRANK-03 — A small difference is not flagged

- **GIVEN** a receiver ESPN ranks 12th whom the experts rank 9th
- **WHEN** the agent reads its signals
- **THEN** he is not flagged

#### Scenario: FPRANK-04 — Missing rankings never stop a lineup run

- **GIVEN** the rankings feed failed to load
- **WHEN** freshness is assessed
- **THEN** the bundle reports fresh
- **AND** names the expert rankings as missing

#### Scenario: FPRANK-05 — The decision records the rankings it saw, and the optimizer is unchanged

- **GIVEN** a lineup run with expert rankings available
- **WHEN** the record is built
- **THEN** it records each ranked player's expert rank and the scrape date
- **AND** the projections the optimizer used are ESPN's
