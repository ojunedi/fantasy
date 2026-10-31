# Design — fantasypros-projections

## Context

`signals/sources/nflverse.load_ff_rankings()` already loads FantasyPros'
weekly consensus rankings (cached 1 h): per page (`ppr-rb`, `ppr-wr`,
`ppr-te`, `qb`, …) each player's `fantasypros_id`, `ecr`, `sd`, `best`,
`worst`, `pos_rank`, `scrape_date`. `load_ff_playerids()` maps
`fantasypros_id` ↔ `espn_id`. ESPN projections with positions come from
`ESPNAdapter.get_player_projections` (same cached read as `get_projections`).

---

# Build approach

## Where the code goes

| Concern | Location | Pattern it follows |
| --- | --- | --- |
| Reading and matching | `nflverse.expert_rankings_by_espn()` | The other nflverse helpers: normalised dicts out, no Polars leaking |
| Model | `models.ExpertRanking` | Beside `UsageTrend` |
| Collecting | `collector._collect_expert_rankings` — `expert_rankings` availability, bundle map, ESPN positional ranks | The nflverse enrichment, best effort, never raises |
| Freshness | `signals/freshness.THRESHOLDS["expert_rankings"] = 48h`, optional | The existing thresholds |
| Showing it | `LineupToolContext._tool_get_signals` — ranks and disagreement flags | The existing signal summary |
| Recording it | `LineupGraphAgent.build_record` — `inputs_snapshot["expert_rankings"]` | The existing snapshot |

## Components

| Component | Action | Notes |
| --- | --- | --- |
| `signals/sources/nflverse.py` — `expert_rankings_by_espn` | MODIFY | PPR pages for skill positions, plain pages for QB/K/DST |
| `models.py` — `ExpertRanking` | MODIFY | |
| `signals/base.py` — `SignalBundle.expert_rankings` | MODIFY | |
| `signals/collector.py` | MODIFY | |
| `signals/freshness.py` | MODIFY | |
| `agent/tools.py` — `_tool_get_signals`, `disagreements` | MODIFY | |
| `agent/graph.py` — `build_record` | MODIFY | |
| `tests/signals/test_expert_rankings.py`, `tests/agent/test_expert_signal.py` | CREATE | |

## Domain

| Aggregate | Invariant it enforces here | Transaction boundary |
| --- | --- | --- |
| `SignalBundle` | I-01 — as-of is the feed's `scrape_date`; I-02 — optional member | Computed |
| `LineupAnalysis` | I-14 — optimizer and backtests unchanged; rankings recorded with date | The record the caller saves |

Disagreement: `|espn_pos_rank − ecr| ≥ 6` and `> 2 × sd`. ESPN positional
rank is the player's rank by projected points among every projected player
at his position this week.

## Decisions

| Decision | Chosen | Rejected, and why |
| --- | --- | --- |
| Source | Free nflverse feed of FantasyPros rankings (manager's call) | Paid API: cost; scraping: terms of service and Sunday rate limits |
| Role | Signal beside ESPN points | Replacing points: rankings are not points |
| Threshold for a flag | 6 spots and 2 spreads | Any difference: noise; spread alone: tight consensus would flag tiny gaps |

## Risks

| Risk | Mitigation |
| --- | --- |
| Feed's page names change | Unknown pages are ignored; a missing signal is named, never blocking |
| ID map gaps | Unmatched players simply have no expert rank |

---

# Test approach

## Scenario coverage

| Scenario | AC | Level | Test file | Test name | Status |
| --- | --- | --- | --- | --- | --- |
| FPRANK-01 | AC-1, AC-2, AC-6 | unit | `tests/signals/test_expert_rankings.py` | `FPRANK-01: a rostered player gets his consensus rank and the feed's date` | required |
| FPRANK-02 | AC-3 | unit | `tests/agent/test_expert_signal.py` | `FPRANK-02: a sharp disagreement is flagged with both ranks` | required |
| FPRANK-03 | AC-3 | unit | `tests/agent/test_expert_signal.py` | `FPRANK-03: a small difference is not flagged` | required |
| FPRANK-04 | AC-4 | unit | `tests/signals/test_expert_rankings.py` | `FPRANK-04: missing rankings never stop a lineup run` | required |
| FPRANK-05 | AC-5 | integration | `tests/agent/test_expert_signal.py` | `FPRANK-05: the decision records the rankings it saw, and the optimizer is unchanged` | required |

## Not covered by automated tests

| What | Why | How it is checked instead |
| --- | --- | --- |
| The live feed's shape over the season | Changes outside our control | A live read during the build, recorded in the change log |
