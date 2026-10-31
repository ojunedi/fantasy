---
id: S-015
slice_id: player-card
status: complete
---

# Any player's name opens a card with his photo, season stats and recent news

## Outcome

Clicking a player's name on the team, waiver, news or decision pages opens a
card with his photo, his fantasy points week by week, his season's real stats
(yards, touchdowns, targets, carries and the like) and his recent headlines.

## Contexts

| id | why |
|----|-----|
| BC-signal | Owns the stats (nflverse season player stats, already loaded) and the news feed |
| BC-lineup | Hosts the pages the names appear on |

## Invariants

| id | risk |
|----|------|
| I-01 | The stats show what week they run through and where they came from; a card that looks current but stops two weeks ago misleads |
| I-14 | Fantasy points are the league-scored actuals ESPN reports, never projections dressed as results |

## NFRs

| id | applies |
|----|---------|
| NFR-11 | Local-only web app; the photo is fetched by the manager's browser from ESPN's image server, so no cookie or credential travels with it |

## Contracts

None external. ESPN's player images are a public CDN keyed by the ESPN player
id the app already holds.

## Open questions

| id | question | owner |
|----|----------|-------|
| — | Weekly fantasy points: ESPN's per-week actuals (league scoring, one read per week) or computed from nflverse stats with the league's rules? The first is authoritative, the second is cheaper | R-01 |
| — | Players with no ESPN photo (rookies, defenses): placeholder or nothing? | R-01 |

<!--
Added through /frictionless:extend on 2026-10-31 with the news feed. Depends on
it only so the card can show the player's recent headlines.
-->
