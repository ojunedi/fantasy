---
product: Fantasy GM
stage: target-arch
---

# Data Model

## Stores

| id | name | kind | service | purpose |
|----|------|------|---------|---------|
| ST-decisions | decisions.db | sqlite | SVC-gm | Two tables. `decisions` holds every decision with its frozen input snapshot, the human response and the eventual outcome. `scorecards` holds the computed weekly evaluation — actual, hindsight ceiling, agent projection, points left on bench, decision regret and per-baseline scores — keyed on week and season. Together they are the artifact the whole evaluation story depends on |
| ST-checkpoints | langgraph.db | sqlite | SVC-gm | LangGraph `SqliteSaver` state per run thread. Makes a run resumable and replayable |
| ST-nflverse | data/cache/nflverse/ | parquet | SVC-gm | Columnar cache of nflverse pulls. Lets the deterministic core run offline once warmed |
| ST-espn | data/cache/espn/ | file | SVC-gm | Per-entry TTL cache of ESPN read responses, keyed by season, league and query params |

## Persistence

| aggregate | store | structure | writer |
|-----------|-------|-----------|--------|
| AGG-lineup-decision | ST-decisions | One `decisions` row. `inputs_snapshot`, `recommendation` and `modified_recommendation` are JSON columns | SVC-gm |
| AGG-waiver-claim | ST-decisions | One `decisions` row with `decision_type = WAIVER`. The claim outcome belongs in `outcome` | SVC-gm |
| AGG-trade-offer | ST-decisions | One `decisions` row with `decision_type = TRADE`. The chosen package is recorded in `modified_recommendation` as an index plus the package | SVC-gm |
| AGG-backtest-report | ST-decisions | Materialised in `scorecards`, one row per week keyed on (week, season), written by `save_scorecard` with INSERT OR REPLACE so a re-run overwrites rather than duplicating. `baseline_scores` is a JSON column | SVC-gm |
| AGG-signal-bundle | ST-nflverse | Not persisted as an aggregate. Its members are cached individually by source, with their own TTLs | SVC-gm |
| AGG-lineup-analysis | ST-checkpoints | Not persisted directly. Survives as graph state within a run thread | SVC-gm |
| AGG-waiver-analysis | ST-checkpoints | Not persisted directly | SVC-gm |
| AGG-trade-analysis | ST-checkpoints | Not persisted directly | SVC-gm |

<!--
Three aggregates share one `decisions` table, discriminated by `decision_type`
and with their payloads in JSON columns. This is the single biggest gap between
the model and the storage, and it is a deliberate acceptance rather than an
oversight: the domain model split them because their lifecycles and terminal
states genuinely differ, while the *store* is a log, and a log of
differently-shaped things is still a log.

What it costs: the claim-specific and offer-specific states the model defines
(submitted, cleared, lost, sent, accepted, refused, expired) have nowhere to go
except inside the `outcome` JSON blob, so none of them is queryable. The claim
history read model and the trade outcome log therefore both require reading
and parsing JSON rather than filtering rows.

When to revisit: the first time a question like "how many claims did I lose to
priority this season" needs answering without a full table scan and a JSON
parse. Not before — a schema migration to buy query ergonomics nobody has
needed yet is the wrong trade for one user and one season of data.

Note that `scorecards` is the counter-example in the same file: the evaluation
metrics *are* broken out into real columns, because they are the thing most
often queried across weeks. The schema already knows the difference between a
log and a dataset; the decision payloads are simply on the log side of it.
-->

## Migrations

| id | change | forward | rollback |
|----|--------|---------|----------|
| MIG-001 | Waiver and trade outcome states become queryable columns rather than `outcome` JSON | Add nullable columns, backfill by parsing existing JSON, keep writing both for one season | Drop the columns; the JSON remains authoritative throughout, so nothing is lost |

<!--
Deliberately one speculative row rather than none. It is the migration the
storage choice above makes likely, and writing the rollback down now is what
makes "accept the JSON blob for the moment" an informed decision instead of a
default.
-->
