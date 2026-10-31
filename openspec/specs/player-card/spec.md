# player-card Specification

## Purpose
A player's name opens a card with his photo, his fantasy points week by
week, his season's real stats and his recent headlines.

<!-- trace-prefix: PCARD -->

## Requirements

### Requirement: The card shows who he is, what he scored, and what he did

The card SHALL show the player's ESPN photo (a defense shows its team logo),
ESPN's league-scored fantasy points for each completed week (a dash where
there are none, never a projection), his nflverse season stats for his
position labelled with the week they run through, and up to five recent
headlines tagged with him.

Serves: AC-1, AC-2, AC-3, AC-4

#### Scenario: PCARD-01 — A player's card shows his photo, weekly points and season stats

- **GIVEN** a running back with ESPN actuals of 21.4 in week 1 and none in week 2, and nflverse rushing and receiving rows through week 2
- **WHEN** his card is opened
- **THEN** it shows his ESPN photo
- **AND** week 1 shows 21.4 and week 2 shows a dash
- **AND** his rushing and receiving totals are shown, labelled "through week 2" and nflverse

#### Scenario: PCARD-02 — A defense shows its team logo

- **GIVEN** a team defense
- **WHEN** its card is opened
- **THEN** it shows the team's logo instead of a photo

#### Scenario: PCARD-03 — Recent headlines are those tagged with him

- **GIVEN** news stories, two tagged with the player and one not
- **WHEN** his card is opened
- **THEN** the two tagged stories are listed, linked
- **AND** the other is not

### Requirement: Names open the card, and a missing player never breaks the page

Serves: AC-5, AC-6, AC-7

#### Scenario: PCARD-04 — Names on the team, waiver and news pages open the card

- **GIVEN** a rostered player, a waiver recommendation, and a news story about my player
- **WHEN** those pages render
- **THEN** each of those names links to that player's card

#### Scenario: PCARD-05 — An unknown player gets a short message

- **GIVEN** an id the system does not know
- **WHEN** its card is requested
- **THEN** the response says there is no card for this player
- **AND** it is not an error page

#### Scenario: PCARD-06 — Completed weeks are read once

- **GIVEN** one card already opened
- **WHEN** another card is opened
- **THEN** no completed week's points are read from ESPN again
