# Intent — player-card

## Outcome

Clicking a player's name on the team, waiver or news page opens a card with
his photo, his fantasy points week by week, his season's real stats and his
recent headlines — each part saying where it came from and how current it is.

## Who

**Actor:** the manager, researching a player.
**What changes for them:** one click instead of a trip to the ESPN app.

## Why now

The second half of the research surface the manager asked for; it reuses
the news feed for the card's headlines.

## Acceptance criteria

| # | Criterion | Source |
| --- | --- | --- |
| AC-1 | The card shows the player's ESPN photo; a team defense shows its team's logo; a photo that fails to load is replaced by the player's initials | outcome; slice open question 2 |
| AC-2 | Fantasy points are ESPN's league-scored actuals for every completed week; a week with no points (bye or did not play) shows a dash, never a projection | invariant I-14; slice open question 1 |
| AC-3 | Season real stats come from nflverse and are labelled with the week they run through and their source; only the stats that apply to his position are shown | invariant I-01 |
| AC-4 | The card lists up to five recent headlines tagged with the player, linked, with their published time | outcome |
| AC-5 | Player names on the team page roster, the waiver recommendation, and the news page's "Your player" lines open the card | outcome |
| AC-6 | A player the system cannot find gives a short "no card for this player" message, never an error page | outcome |
| AC-7 | Opening a card adds no ESPN request beyond the weekly reads the app already makes, each memoised; completed weeks are never re-read in the same run of the app | NFR-03 |

## Acceptance signal

- The manager checks a waiver candidate's card before claiming him.

## Out of scope

- Names on the decision and trade pages (they render from saved snapshots).
- Career or past-season stats.
- Projections on the card.

## Carried context

| | |
| --- | --- |
| **Bounded contexts** | Signal (stats, news); Lineup (pages the names appear on) |
| **Aggregates touched** | None — read only |
| **Invariants at risk** | Provenance and as-of (I-01); actuals never confused with projections (I-14) |
| **Contracts** | None external |
| **NFRs that apply** | Local-only web app (NFR-11); pacing (NFR-03) |
| **Depends on** | The news feed (shipped) |

## Interface impact

**Does this slice touch a user interface?** Yes — the card, and links on
three pages. The `ux` artifact is required.

## Open questions

| # | Question | Owner | Blocking? |
| --- | --- | --- | --- |
| Q-1 | ESPN actuals or computed points? **Resolved: ESPN's league-scored actuals** — authoritative, and the weekly read is the one the app already caches | — | No |
| Q-2 | No photo? **Resolved:** team logo for defenses, initials otherwise | — | No |
