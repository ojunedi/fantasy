---
id: S-014
slice_id: news-feed
status: todo
---

# I can read the latest news on my players and their teams

## Outcome

A News page shows recent NFL headlines, with the ones about my rostered
players and their teams surfaced first, each linked to its source and stamped
with when it was published.

## Contexts

| id | why |
|----|-----|
| BC-signal | Already reads ESPN's public news feed as one input to the analysis; this exposes it for browsing |

## Invariants

| id | risk |
|----|------|
| I-01 | Every headline shows its source and published time. A story with no date reads as current when it may be days old |

## NFRs

| id | applies |
|----|---------|
| NFR-11 | A new page on the same local-only web app; nothing about it is reachable from the network |

## Contracts

None external. ESPN's news feed is an integration already in use, not a
contract this system publishes.

## Open questions

| id | question | owner |
|----|----------|-------|
| — | Does ESPN's news feed filter by athlete or team, or must stories be matched to players by name and tags? Decides how "about my players" is found | R-01 |

<!--
Added through /frictionless:extend on 2026-10-31 from the manager's request
(.frictionless/intake/2026-10-30-extend-player-news-cards.md). Read-only: no
decision, no write, no change to any aggregate — which is why it enters at the
slicing stage rather than reopening discovery.
-->
