---
product: Fantasy GM
stage: target-arch
---

# Components

The module map, and where it agrees and disagrees with the context boundaries. Import discipline is the only thing enforcing those boundaries — there is no network between them — so the disagreements are where drift will start.

## Components

| id | name | service | kind | responsibility | path |
|----|------|---------|------|----------------|------|
| CMP-models | Type vocabulary | SVC-gm | library | Every Pydantic type the layers exchange. The contract that makes the rest substitutable | `src/fantasy_gm/models.py` |
| CMP-adapters | Platform adapters | SVC-gm | adapter | ESPN and Sleeper behind one `FantasyPlatform` interface. The only place raw ESPN shapes exist. Sleeper is not a second supported league — it exists because its API is documented and read-only, which makes it a cheap test surface for the interface (D-002) | `src/fantasy_gm/adapters/` |
| CMP-signals | Signal sources | SVC-gm | adapter | nflverse, FantasyCalc, ESPN news, odds, weather. Normalises to dicts so nothing downstream needs Polars | `src/fantasy_gm/signals/` |
| CMP-core | Deterministic core | SVC-gm | module | Optimizer, scoring, trade value, matchup, schedule, usage, projection blending, waiver constraints. Pure functions, no I/O, no LLM | `src/fantasy_gm/core/` |
| CMP-agent | Agent loop | SVC-gm | module | The shared `GraphAgent` base plus the lineup and trade specialists. Turns language into tool calls and nothing else | `src/fantasy_gm/agent/` |
| CMP-supervisor | GM supervisor | SVC-gm | module | Computes a deterministic risk posture from record and weeks remaining, then routes to a specialist and passes the posture in as an input. The posture shifts what the agent weighs and is deliberately not baked into the optimizer objective | `src/fantasy_gm/agent/supervisor.py` |
| CMP-tracer | Run tracer | SVC-gm | module | Streams tool calls and model turns out of a run through an `emit` callback. One code path consumed two ways — the CLI prints it, the web layer turns it into SSE | `src/fantasy_gm/agent/tracer.py` |
| CMP-collector | Signal collector | SVC-gm | module | Assembles the per-run signal set and carries each source's freshness alongside its value | `src/fantasy_gm/signals/collector.py` |
| CMP-preferences | Trade brief intake | SVC-gm | module | Turns the manager's stated wants — positions to acquire, who is offerable, specific targets — into the structure that narrows the package search. An empty brief narrows nothing | `src/fantasy_gm/agent/trade/preferences.py` |
| CMP-trace | SSE transport | SVC-gm | module | The append-only run event buffer and `Last-Event-ID` resumption. The buffer is the source of truth, not the subscriber queue | `src/fantasy_gm/web/trace.py` |
| CMP-subagents | Language interpreters | SVC-gm | module | Single-shot injury and news interpretation. The only LLM units outside the main loop, and the only place unstructured English becomes a structured signal | `src/fantasy_gm/agent/subagents/` |
| CMP-execute | Executors | SVC-gm | module | Lineup plan and write, trade plan and send, browser fallback. Every irreversible action lives here and nowhere else | `src/fantasy_gm/execute/` |
| CMP-db | Decision store | SVC-gm | module | SQLite persistence for decision records and their outcomes | `src/fantasy_gm/db/` |
| CMP-eval | Evaluation harness | SVC-gm | module | Backtest runner, naive baselines, scorecard metrics. Enforces as-of isolation | `src/fantasy_gm/eval/` |
| CMP-memo | CLI approval surface | SVC-gm | ui | The interview prompts, the brief rendering, and both approval gates | `src/fantasy_gm/memo/` |
| CMP-cli | CLI entry point | SVC-gm | ui | Command parsing and wiring. `fantasy-gm` | `src/fantasy_gm/cli.py` |
| CMP-web | Web surface | SVC-gm | ui | Localhost dashboard. Presents and orchestrates; computes nothing | `src/fantasy_gm/web/` |

## Where the modules and the contexts disagree

Not parsed — recorded because this is the finding, and because an import-enforced boundary with no test behind it drifts quietly.

| Context | Should live in | Actually lives in | Verdict |
|---|---|---|---|
| Signal Kernel | `signals/` + `adapters/` | matches | Clean. The ACL really does stop at the adapter |
| Decision Analysis | `core/` | matches, **except** `core/waivers.py` | `core/waivers.py` is dead code — nothing imports it, and its one constraint function admits in a comment that it cannot enforce the roster-size rule it claims to check. The waiver analysis context is, in code, empty |
| Lineup Execution | `execute/lineup_plan.py` + the gate | **split across three places** | The plan is in `execute/`, the gate is in `memo/cli.py:49`, and an independent second implementation is in `web/routes/approve.py:170`. Neither imports the other. D-020 says the web gates are "preserved verbatim" — verbatim means copied, and the copy is only tested on the web side (`tests/web/test_execute.py`). Nothing asserts the two agree |
| Waiver Execution | its own module | **does not exist, but the socket does** | No waiver gate, brief, or claim submission. The web run dispatcher rejects any kind outside its worker registry (`web/routes/runs_routes.py:64`) and the test for that uses `waivers` as its example of an unknown kind (`tests/web/test_trade_runs.py:185`) — so adding waivers means registering a worker, not inventing a dispatch. The gap this discovery pass exists to close |
| Trade Execution | `execute/trade_api.py` + `trade_plan.py` | matches | Clean, and now confirms its own writes |
| Decision Ledger | `db/` + `eval/` | matches | Clean separation: `db/` records, `eval/` interprets |

Two things the first pass of this file did not mention at all, and both are inputs to a recommendation: **the risk posture** the supervisor computes and passes into every supervised run, and **the trade brief** the manager fills in before a trade run. Neither had a component entry, an invariant, or a line in cross-cutting concerns — a deterministic value that changes what the agent weighs should not be invisible to the architecture.

Two of these are worth acting on. **The duplicated approval gate** is the riskier one: two implementations of the only thing standing between the agent and an irreversible write, with nothing asserting they agree. **The dead waiver module** is the more misleading one — it looks like waiver support exists.
