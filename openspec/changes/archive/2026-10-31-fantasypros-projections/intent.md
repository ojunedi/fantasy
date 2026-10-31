# Intent — fantasypros-projections

## Outcome

The lineup agent sees, for each rostered player, FantasyPros' consensus
expert rank at his position — and is told plainly where it disagrees sharply
with ESPN's projection — while ESPN's projected points remain the numbers the
optimizer uses.

## Who

**Actor:** the manager (through the agent's brief)
**What changes for them:** a recommendation can say "ESPN has him RB18, the
experts RB7" instead of trusting a single projection source silently.

## Why now

Last, by convenience. The original outcome — FantasyPros projected points as
the primary source — needs a paid API or scraping their site. The manager
chose the free path: FantasyPros consensus rankings, already delivered
date-stamped through nflverse, beside ESPN's points.

## Acceptance criteria

| # | Criterion | Source |
| --- | --- | --- |
| AC-1 | Each rostered player FantasyPros ranks gets his consensus rank, spread, best and worst from the PPR position page (this league scores a point per reception), matched to ESPN by player id | outcome |
| AC-2 | The rankings carry FantasyPros as their source and the feed's own scrape date as their as-of time — never the time we read them | invariant I-01 |
| AC-3 | Where ESPN's positional rank and the expert rank differ by at least 6 spots and by more than twice the experts' spread, the agent's signal summary flags the player and both ranks | outcome |
| AC-4 | The rankings are an optional signal: missing or older than 48 hours, they are named in the freshness report and never stop a lineup run | outcome; invariant I-02 |
| AC-5 | ESPN's projected points remain the only numbers the optimizer and the backtests use; each decision records the rankings it saw with their scrape date | invariant I-14 |
| AC-6 | Reading the rankings adds no request to ESPN and at most one to nflverse per hour | NFR-03 |

## Acceptance signal

- A brief cites an expert disagreement on a player the manager then looks at
  twice — and the decision log shows which day's rankings it came from.

## Out of scope

- FantasyPros projected points (paid API or scraping).
- Changing the optimizer's inputs or the backtests.
- Waiver and trade agents.

## Carried context

| | |
| --- | --- |
| **Bounded contexts** | Signal (the source and its pluggability) |
| **Aggregates touched** | SignalBundle |
| **Invariants at risk** | Provenance with the source's own stamp (I-01); bundle completeness (I-02); backtests use only what was available then (I-14) |
| **Contracts** | None external |
| **NFRs that apply** | Separate pacing for the new source (NFR-03) |
| **Depends on** | Nothing |

## Interface impact

**Does this slice touch a user interface?** No — the rankings reach the
manager through the agent's brief and the decision record.

## Open questions

| # | Question | Owner | Blocking? |
| --- | --- | --- | --- |
| Q-1 | Scrape or paid API? **Resolved by the manager:** neither — the free consensus rankings | manager | No |
