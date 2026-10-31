# Intent — news-feed

## Outcome

The manager opens a News page and sees recent NFL stories grouped as: about
my players, about my players' teams, and around the league — each headline
linked to ESPN, with its summary and when it was published.

## Who

**Actor:** the manager, doing research rather than receiving a recommendation.
**What changes for them:** player and team news is one click from the team
page instead of a separate app.

## Why now

Added by the manager after the risk-retiring slices shipped. ESPN's public
news feed is already read for the agent; this exposes it for browsing.

ESPN's feed settled the slice's open question: it does not filter by player
(the `athletes` parameter is ignored and there is no per-player endpoint),
but it filters by team, and every story is tagged with the ESPN ids of the
players and teams it covers — the same ids the roster uses.

## Acceptance criteria

| # | Criterion | Source |
| --- | --- | --- |
| AC-1 | A story tagged with a rostered player's ESPN id appears under "Your players", naming which of my players it is about | outcome |
| AC-2 | A story tagged with a rostered player's team, and not already under "Your players", appears under "Your teams" | outcome |
| AC-3 | Every other story from the league feed appears under "Around the league"; no story appears twice | outcome |
| AC-4 | Every story shows its headline linked to the article, its summary, ESPN as its source, and its published time; stories are newest first in each group | invariant I-01 |
| AC-5 | ESPN is asked at most once per feed (league, and each rostered team) per 15 minutes | NFR-03 (pacing for a new source) |
| AC-6 | If the feed cannot be reached, the page still renders and says the news could not be loaded; a team feed that fails leaves the others shown | outcome |
| AC-7 | The page is reached from the navigation bar | outcome |

## Acceptance signal

- On a Sunday morning the manager checks News for injury notes on his
  players before approving the lineup.

## Out of scope

- The player card (the next slice).
- Feeding news into the agent differently — the agent's `nfl_news` tool is unchanged.
- Non-ESPN sources.

## Carried context

| | |
| --- | --- |
| **Bounded contexts** | Signal (ESPN news) |
| **Aggregates touched** | None — read only |
| **Invariants at risk** | Every item carries its source and as-of time (I-01) |
| **Contracts** | None external |
| **NFRs that apply** | Local-only web app (NFR-11); pacing for a source (NFR-03) |
| **Depends on** | Nothing |

## Interface impact

**Does this slice touch a user interface?** Yes — a new News page and a nav
link. The `ux` artifact is required.

## Open questions

| # | Question | Owner | Blocking? |
| --- | --- | --- | --- |
| Q-1 | Filter by player, or match stories? **Resolved:** match by the athlete and team tags ESPN puts on every story; fetch per-team feeds for my teams | — | No |
