# news-feed Specification

## Purpose
A News page groups ESPN's recent NFL stories by whether they are about my
rostered players, their teams, or neither.

<!-- trace-prefix: NEWS -->

## Requirements

### Requirement: Stories are grouped by who they are about, each shown once

The system SHALL show under "Your players" every story tagged with a rostered
player's ESPN id, naming those players; under "Your teams" every other story
tagged with a rostered player's team; and under "Around the league" every
remaining story — each story once, newest first, with its headline linked,
summary, source and published time.

Serves: AC-1, AC-2, AC-3, AC-4, AC-7

#### Scenario: NEWS-01 — A story about one of my players is under "Your players", naming him

- **GIVEN** a story tagged with the ESPN id of a rostered player
- **WHEN** the manager opens News
- **THEN** it appears under "Your players"
- **AND** it names that player

#### Scenario: NEWS-02 — A story about my player's team, not him, is under "Your teams"

- **GIVEN** a story tagged with a rostered player's team but no rostered player
- **WHEN** the manager opens News
- **THEN** it appears under "Your teams"

#### Scenario: NEWS-03 — Every other story is under "Around the league", and none appears twice

- **GIVEN** the same story returned by the league feed and a team feed, and a story about nobody on my roster
- **WHEN** the manager opens News
- **THEN** each story appears exactly once
- **AND** the unrelated story is under "Around the league"

#### Scenario: NEWS-04 — Each story shows its link, summary, source and time, newest first

- **GIVEN** two stories in one section published an hour apart
- **WHEN** the manager opens News
- **THEN** the newer is listed first
- **AND** each shows its headline linked to the article, its summary, ESPN, and its published time

### Requirement: ESPN is read sparingly, and a failed read never breaks the page

Serves: AC-5, AC-6

#### Scenario: NEWS-05 — Opening News twice within 15 minutes asks ESPN once per feed

- **GIVEN** News was opened a minute ago
- **WHEN** it is opened again
- **THEN** no feed is requested from ESPN again

#### Scenario: NEWS-06 — An unreachable feed leaves the page standing

- **GIVEN** ESPN's league feed cannot be reached
- **WHEN** the manager opens News
- **THEN** the page renders
- **AND** it says the news could not be loaded
