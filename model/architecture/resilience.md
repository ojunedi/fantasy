---
product: Fantasy GM
stage: target-arch
---

# Resilience

Every dependency here is someone else's free service, and one of them is reverse-engineered. The design principle throughout is that a missing input is a reason to say so, never a reason to guess.

## Policies

| caller | callee | timeout | retry | breaker | on_open |
|--------|--------|---------|-------|---------|---------|
| SVC-gm | ESPN read | 20s | tenacity, exponential backoff | none | Serve from the TTL cache and mark the signal stale |
| SVC-gm | ESPN write — lineup | 20s | **none** | none | Browser fallback, then manual instructions |
| SVC-gm | ESPN write — trade | 20s | **none** | none | Report unconfirmed. Explicitly do not retry |
| SVC-gm | nflverse | default | tenacity | none | Serve stale parquet and mark it so |
| SVC-gm | FantasyCalc | default | tenacity | none | Report values unavailable; drop every value column |
| SVC-gm | ESPN news | default | tenacity | none | Skip news interpretation |
| SVC-gm | Tavily | default | none | none | Degrade with a message naming what was not researched |
| SVC-gm | LLM provider | provider default | provider SDK | per-provider rate ceiling | Budget exhausted — the agent explains with its reserved call rather than failing silently |

<!--
No retry on either write path, deliberately. A retried lineup write is at best
redundant and at worst fights a browser fallback for the same slot; a retried
trade send creates a second pending offer the counterparty can accept. Reads
retry freely because they are idempotent and free.

No circuit breakers anywhere. A breaker protects a callee from a stampede, and
one user making a handful of calls a week cannot stampede anything. The
per-provider rate ceiling on the LLM is the one real limiter, and it exists
because free tiers meter aggressively, not because of load.
-->

## Degradation

| when_down | product_still_does | product_cannot | user_sees |
|-----------|-------------------|----------------|-----------|
| ESPN reads | Nothing useful — the roster is the starting point for everything | Any recommendation at all | An explicit "cannot read the roster" and no fabricated lineup. 🔴 Abstention is named as the mechanism but is unreachable until freshness thresholds exist (H-02) — today this path is an unhandled error, not a graceful degradation |
| ESPN writes | Recommend, brief, gate, and log the decision | Execute. The decision is recorded as approved-but-unexecuted | Browser fallback attempted, then the exact moves to make by hand |
| nflverse | Recommend from ESPN projections alone | Matchup, schedule-strength and usage grades | A brief that says which grades are missing, with lower confidence |
| FantasyCalc | Lineup and waiver work untouched. Trades can still be evaluated on projections | Market-anchored asset values | Every value column dropped rather than a stale price shown as current |
| ESPN news | Everything deterministic | Interpret late-breaking news | A note that no news was available, with injury signals weighted up |
| Tavily | Everything else | Targeted per-player research | A message naming what went unresearched |
| LLM provider | Nothing — the agent cannot run | Any recommendation | A clear provider error. The deterministic core is still usable through `show-week` |
| Weather | Everything else | Game-environment adjustment for outdoor games | Nothing. The adjustment silently does not apply |

<!--
The ESPN-read row is the honest admission in this table: there is no graceful
degradation for it. Everything starts from the roster, and no amount of
layering changes that. A cache makes a brief outage survivable and a long one
is simply an outage.

The weather row is the opposite extreme, and it is the only degradation here
the manager would not notice. That is a small smell rather than a bug — a
signal whose absence is invisible is a signal nobody can tell is working.
-->

## Recovery

| failure | detection | recovery | data_loss |
|---------|-----------|----------|-----------|
| ESPN write returns success without acting | Read the roster or transaction list back and compare | Lineup: retry via browser. Trade: report unconfirmed and stop | None. The decision is recorded either way |
| A run crashes mid-flight | The LangGraph checkpoint for that thread is incomplete | Re-run the week. The checkpointer resumes rather than restarting | None — a decision is only recorded at the gate, so an abandoned run leaves nothing half-written |
| Session cookies expire | The write returns an auth error, or the plan warns that they are unset | Re-extract from a browser session and re-export | None |
| A decision is recorded but the week never resolves | The outcome column stays null past the week's end | Backfill from actual scores on the next evaluation run | None |
| The parquet cache is corrupted | A read raises on parse | Delete the file; the next call re-fetches | None — it is a cache |
| decisions.db is lost | Nothing detects this | **No recovery. There is no backup.** | Both tables: every decision and override reason, *and* the computed weekly scorecards. The raw log and the derived evaluation go together |

<!--
The last row is the real finding in this file. The decision log is the artifact
the whole product is for — D-009 calls the override log the primary evaluation
artifact — and it is a single unreplicated SQLite file on one laptop with no
backup and no detection if it disappears. Every other failure here is
recoverable or costless. This one ends the season's evidence.

It is also the cheapest thing on this page to fix: the file is small, append-
mostly, and copying it somewhere after each write would do.

One failure has no row because nobody has decided what it means: the two
SQLite files disagreeing. A LangGraph checkpoint claiming a run that left no
decision row, or a decision row whose thread is gone. Neither is detected and
neither has a stated resolution.
-->
