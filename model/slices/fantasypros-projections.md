---
id: S-013
slice_id: fantasypros-projections
status: todo
---

# Projections come from FantasyPros rather than ESPN

## Outcome

The primary projection source becomes FantasyPros consensus, with ESPN remaining as the fallback. Every downstream number improves slightly; nothing changes shape.

## Contexts

| id | why |
|----|-----|
| BC-signal | Owns the projection source and its pluggability |

## Invariants

| id | risk |
|----|------|
| I-01 | FantasyPros values must carry their own source and as-of stamp. A scraped number with a fabricated timestamp would quietly break the replay guarantee |
| I-14 | Historical backtests must keep using the projections that were actually available at the time. Switching sources must not retroactively rewrite what past decisions are scored against |

## NFRs

| id | applies |
|----|---------|
| NFR-03 | Scraping needs its own pacing, independent of the ESPN limit |

## Contracts

No external contracts. This system publishes no API and no messages — the
`Contracts` table is for endpoints and published events, and there are none to
reference. The domain events this slice introduces are internal and already
mapped in `event-maps/`.

## Open questions

| id | question | owner |
|----|----------|-------|
| — | Scrape or paid API? The free path has rate-limit risk at peak times, which is exactly when a lineup decision is being made | R-01 |
| — | What happens to a backtest that spans the switch? Mixed-source history is defensible if each row records its source, and misleading if it does not | R-01 |

<!--
Last, and genuinely last. It improves every number slightly, unblocks nothing,
has a working fallback already in place, and has no deadline. The vision asks
for the projection source to stay pluggable so that this stays a small change
whenever it happens — which is the actual requirement, and it is already met.

The backtest question is the interesting one and is easy to get wrong: scoring
past weeks against a source that did not exist then would invalidate the whole
comparison, which is the one thing I-14 exists to prevent.
-->
