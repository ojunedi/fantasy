# Fantasy GM

An agentic general manager for ESPN fantasy football. It recommends weekly lineups, proposes trades with quantified EV, logs every decision and override to SQLite, and executes approved lineup changes through ESPN's write API.

**Autonomy is Level 1: the human approves, then the agent acts.**

League `1660218687` · Team `8` · 12-team PPR · 2026 season

---

## How it works

One rule explains most of the structure: **a thin LLM over a thick deterministic layer.** Every number — projections, optimal lineup, trade value, EV delta, schedule strength — is computed in `core/` by ordinary Python. The model supplies judgment and turns English into structured signals; it never does arithmetic.

Both the lineup and trade agents run the same LangGraph `StateGraph`: two nodes (`agent` → `tools`), looping until a *terminal tool* fires (`propose_lineup`, `propose_trades`, or `abstain`). The model cannot end a run by simply deciding to stop talking.

```
Surfaces (CLI / web)
      ↓
GMSupervisor — sets risk posture, routes to a specialist
      ↓
LineupGraphAgent (15 tools)   TradeGraphAgent (13 tools)
      ↓                              ↓
Deterministic core (optimizer, scoring, trade_value, matchup, schedule, usage)
      ↓
Approval gate → ESPN API executor
```

The agent takes zero irreversible actions. Execution lives below two human gates, and the plan is always recomputed server-side so the browser can never supply moves directly.

---

## Setup

Requires Python 3.11 via `uv`.

```bash
export PATH="$HOME/.local/bin:$PATH"   # uv is not on the default PATH
make install
```

Set your ESPN credentials in the environment (or `.env`):

```
ESPN_S2=<your espn_s2 cookie>
ESPN_SWID=<your swid cookie>
```

---

## Usage

**Run the web dashboard**

```bash
make web
# → http://127.0.0.1:8000
```

Four pages: team overview, league standings, decision history, trades ledger.

**Recommend a lineup (CLI)**

```bash
make run-week WEEK=3 SEASON=2026
```

The agent analyses your roster, runs the optimizer, and proposes a starting lineup. You approve, modify with a reason, or reject. If approved and you type `LIVE` at the second gate, it POSTs the lineup to ESPN.

**Propose trades (CLI)**

```bash
make propose-trades WEEK=3 SEASON=2026
```

Runs a preference interview, then the trade agent evaluates all rosters and proposes ranked packages with EV. Approved packages render as in-app steps — no automated send (ESPN requires counterparty acceptance).

**Backtest**

```bash
make backtest SEASON=2024 WEEKS=1-14
```

Runs the agent in strict as-of-date isolation across historical weeks and scores decisions against actual outcomes.

---

## Testing and lint

```bash
make test       # all 247 tests
make test-core  # deterministic core only
make test-web   # web layer only
make lint       # syntax check
```

---

## Structure

| Path | Role |
|---|---|
| `core/` | All analytics — optimizer, scoring, trade_value, matchup, schedule, usage, projection_engine, waivers. Pure Python, no I/O, no LLM. |
| `agent/base.py` | `ToolContext` and `GraphAgent` — the loop, terminal routing, SqliteSaver, LLM build |
| `agent/trade/` | Trade specialist — graph, tools, prompts, preferences |
| `agent/subagents/` | Single-shot injury and news interpreters (the only other LLM units) |
| `adapters/` | `FantasyPlatform` implementations — ESPN (primary), Sleeper |
| `signals/` | Typed, timestamped signal collection over keyless sources |
| `execute/` | `lineup_plan` (deterministic planner), `espn_api`, `trade_plan` |
| `web/` | FastAPI + Jinja2 + HTMX — routes, run registry, SSE trace, context builder, templates |
| `db/store.py` | `decisions` and `scorecards` tables (SQLite) |
| `eval/` | Backtest harness and baselines — built before any LLM work |
| `memo/` | CLI approval gates and the trade preferences interview |

---

## Data sources

All keyless.

| Source | Provides |
|---|---|
| ESPN adapter | Roster, league settings, weekly projections, current week, write endpoint |
| nflreadpy / nflverse | Player stats, snaps, opportunity, schedules with Vegas lines, injuries, ID map |
| Sleeper | Alternative platform adapter, secondary projections |
| FantasyCalc | Market trade values |
| Open-Meteo | Weather |
| ESPN news / Tavily | Research — `search_web` degrades gracefully with no key |

nflverse data caches to `data/cache/nflverse/*.parquet` with a TTL.

---

## Known gaps

- **`cli.py:cmd_backtest` hardcodes `position=WR`** for every player in the projection fetcher — backtest output is not currently a valid eval signal.
- **`PlaywrightExecutor` raises `NotImplementedError`** at `execute/browser.py:107`. The ESPN API path is the live route.
- **The trade agent has not been validated on a live week.** Run `make propose-trades WEEK=N SEASON=2026` before relying on trade output.
- **`make lint` is only `py_compile`** — ruff is not installed.

---

## Design decisions

`DECISIONS.md` tracks D-001 through D-021. Key rules the code holds to:

- **D-017** Numbers come from `core/`. The LLM gets judgment and language, never arithmetic.
- **D-011** No tool the agent can call takes an irreversible action.
- **D-003** Scoring rules and roster structure are read from the API, never hardcoded.
- **D-005** The backtest enforces strict as-of-date isolation.
- **D-016** New specialists supply only a prompt, tools, thread id and record builder. The loop is written once.
- **D-009** The override log is the primary evaluation artifact — training data for the manager, not the model.
