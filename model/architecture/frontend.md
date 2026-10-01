---
product: Fantasy GM
stage: target-arch
---

# Frontend

A localhost dashboard that presents and orchestrates and computes nothing. The defining constraint is the one in D-020: where a number does not exist in the deterministic core, the page shows nothing rather than inventing one.

## Decisions

| concern | decision | why |
|---------|----------|-----|
| Rendering | Server-rendered Jinja2, no client framework | The data is already shaped by `core/`. A client framework would need a second representation of it, and the second one drifts |
| Interactivity | htmx, vendored into `web/static/` | Partial swaps cover every interaction here. Vendoring means no Node, no build step, and no toolchain to maintain between seasons |
| Streaming | Server-sent events for run traces, via the htmx SSE extension | A run takes minutes; the manager should see it think. SSE is one-directional, which is exactly the shape of the problem |
| Resumability | An append-only event buffer is the source of truth, not the subscriber queue | A reload or a dropped connection resumes from `Last-Event-ID` with no gap and no duplicate. Making the queue authoritative would lose events to any disconnect |
| Run durability | Runs are deliberately not durable | The artifact that matters is the decision record, written to SQLite before a run reports itself done. A lost run costs a re-run; a lost decision costs the season's evidence |
| Computation | None. Every number comes from `core/`, `adapters/`, `signals/`, `execute/` or `db/` | D-017. A second implementation behind a web route would drift from the CLI and quietly become a competing source of truth |
| Missing numbers | Show nothing rather than a placeholder | The hero displays projected margin because no win-probability function exists. Writing one for a hero stat is exactly the hallucination the thin-LLM design forbids |
| Identity joins | `web/context.py` is the only place player ids become names | One join site means one place to be wrong |
| Approval parity | Both gates preserved from the CLI, reject and modify require a written reason | The web surface must not be an easier path to an irreversible action than the CLI |

## Screens

| id | screen | route | service | data_from |
|----|--------|-------|---------|-----------|
| SCR-01 | Dashboard | `/` | SVC-gm | |
| SCR-02 | Lineup decision | `/decisions/{id}` | SVC-gm | |
| SCR-03 | Trades | `/trades` | SVC-gm | |
| SCR-04 | Run trace | `/runs/{id}/events` | SVC-gm | |
| SCR-05 | Approval gate | `/decisions/{id}/approve` | SVC-gm | |
| SCR-06 | Execution gate | `/decisions/{id}/execute` | SVC-gm | |

<!--
`data_from` is empty on every row because there are no endpoints to point at —
these routes return HTML to one browser, not JSON to a consumer, which is why
`apis.md` was not written. The column exists for systems with a published API
and this is not one.

There is no waiver screen. That is the gap this discovery pass exists to close,
and it is worth noticing that the web surface will need a third decision type
added to a page structure currently shaped for two.
-->
