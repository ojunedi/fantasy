---
product: Fantasy GM
stage: target-arch
---

# Performance

Nothing here is under load. The budgets that matter are about *cost* and *deadlines*, not throughput — one user making a handful of decisions a week, against free-tier providers that meter aggressively.

## Caches

| id | what | where | strategy | ttl | invalidated_by |
|----|------|-------|----------|-----|----------------|
| CACHE-01 | Stats, snaps, schedules, injuries, Vegas lines | `data/cache/nflverse/*.parquet` | cache-aside | 6h | Time only. nflverse publishes a few times a day |
| CACHE-02 | Weekly fantasy rankings | same | cache-aside | 1h | Time only — these move during the week |
| CACHE-03 | ESPN ↔ nflverse ↔ Sleeper id crosswalk | same | cache-aside | 7d | Time only. Identity mappings are near-static within a season |
| CACHE-04 | ESPN read responses | `data/cache/espn/` | cache-aside | per-entry | Time, or an explicit `fresh=True` on the roster read |

<!--
Every cache here is time-invalidated and nothing is event-invalidated, which is
correct: there is no event that tells us nflverse republished. The one explicit
bypass that exists is the roster read, and the one write-confirmation path
bypasses the cache outright — confirming a write against a cached read would
only echo back what we already believed.
-->

## Scaling

| service | trigger | min | max | concurrency |
|---------|---------|-----|-----|-------------|
| SVC-gm | none — scaling is not a dimension of this system | 1 | 1 | 1 uvicorn worker, by requirement rather than by default |

<!--
The single worker is load-bearing and is the one thing on this page that would
break if someone "optimised" it. The run registry lives in process memory, so a
second worker would serve a browser a run it cannot see. D-020 states this; it
is repeated here because the next person to meet a slow page will reach for
`--workers 4` first.

Agent runs execute on a dedicated daemon thread rather than the Starlette
threadpool: a run takes minutes and must outlive the request that began it.
-->

## Hot Paths

| path | budget | risk | mitigation |
|------|--------|------|------------|
| Weekly lineup run, end to end | NFR-01 | LLM latency dominates; the deterministic core is milliseconds | Hard call budget. Runs on a daemon thread so the browser is never blocked |
| Backtest across a season | NFR-02 | Re-reads cached parquet per week; no LLM in the loop | Parquet cache means a warmed run is CPU-only |
| ESPN read burst at run start | NFR-03 | Four to six sequential calls at one per second | Self-imposed spacing is the mitigation, not the problem — it exists to stay welcome |
| Trade package generation | NFR-04 | Combinatorial over roster pairs, then an optimizer run per candidate | Capped at three ranked packages; the optimizer is a bounded backtracking search over ≤16 players |
