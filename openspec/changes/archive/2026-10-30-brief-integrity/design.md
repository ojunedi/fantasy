# Design — brief-integrity

## Context

`LineupGraphAgent.build_record` (`agent/graph.py`) and
`TradeGraphAgent.build_record` (`agent/trade/graph.py`) take the brief text
straight from the terminal tool. Every tool call's output is on
`ctx.call_log`, including the prefetched reads. The waiver agent already
checks its brief (`agent/waiver_agent.validate_brief`). See `intent.md`.

---

# Build approach

## Where the code goes

| Concern | Location | Pattern it follows |
| --- | --- | --- |
| The check | `src/fantasy_gm/memo/integrity.py` — `numbers_in`, `traceable`, `untraced`, `screen` | Pure functions, like `waiver_agent.validate_brief` |
| Lineup | `LineupGraphAgent.build_record` — screens `memo` and `what_would_change_this` | Applied where the record is assembled |
| Trade | `TradeGraphAgent.build_record` — screens `memo`, each `rationale`, each `counterparty_pitch` | Same |

## Components

| Component | Action | Notes |
| --- | --- | --- |
| `memo/integrity.py` | CREATE | |
| `agent/graph.py` — `build_record` | MODIFY | Withheld originals under `recommendation["withheld"]` |
| `agent/trade/graph.py` — `build_record` | MODIFY | Same, per trade |
| `tests/memo/test_integrity.py`, `tests/agent/test_brief_integrity.py` | CREATE | |

## Domain

| Aggregate | Invariant it enforces here | Transaction boundary |
| --- | --- | --- |
| `LineupAnalysis`, `TradeAnalysis` | I-25, I-27 | Part of building the one record the caller saves |

Allowed numbers: every number appearing in any `ctx.call_log` output or
input, the saved projections, the week, the season, the recommendation's own
numeric fields, and confidence as a percentage. A brief number with *d*
decimals traces when some allowed value rounds to it at *d* decimals.

Notice text: `"Brief withheld — it quoted numbers the analysis never
computed: 31.5."`

## Decisions

| Decision | Chosen | Rejected, and why |
| --- | --- | --- |
| Template vs check | Check (H-08) | Templating: stiff prose and a rewrite of every prompt |
| Rounding | Allowed to the written precision | Exact only: "23.1" from 23.09 is a restatement, not an invention |
| On failure | Withhold, keep original on the record | Regenerate: costs calls (NFR-04); show anyway: the failure this slice exists to stop |
| Waiver | Untouched | It already enforces a stricter, result-only allow-list |

## Risks

| Risk | Mitigation |
| --- | --- |
| A number traces by coincidence when the same value appears anywhere in the run's analysis | Accepted and measured: an invented figure planted in each of the 29 real lineup briefs in the log was caught 29/29 (47.3), 29/29 (6.25), 27/29 (12.8), 16/29 (31.5 — a value common in tool output). Tying each number to the claim it supports would close this and is not attempted here |
| False alarms on honest briefs | Measured: 0 of the 29 real lineup briefs would be withheld |
| A tool output not on `call_log` | Prefetched reads go through `ctx.dispatch`, which logs them |

---

# Test approach

## Scenario coverage

| Scenario | AC | Level | Test file | Test name | Status |
| --- | --- | --- | --- | --- | --- |
| BRIEF-01 | AC-1 | integration | `tests/agent/test_brief_integrity.py` | `BRIEF-01: a lineup brief that only restates computed numbers is shown as written` | required |
| BRIEF-02 | AC-2, AC-4, AC-5 | integration | `tests/agent/test_brief_integrity.py` | `BRIEF-02: one invented number among many withholds the lineup brief` | required |
| BRIEF-03 | AC-3, AC-4, AC-5 | integration | `tests/agent/test_brief_integrity.py` | `BRIEF-03: an invented number in a counterparty pitch withholds that pitch only` | required |
| BRIEF-04 | AC-6 | unit | `tests/memo/test_integrity.py` | `BRIEF-04: the check makes no model call` | required |

The waiver brief's check (I-26) is out of scope; WADD-09 already covers it.

## Not covered by automated tests

| What | Why | How it is checked instead |
| --- | --- | --- |
| Live model briefs | Tests never call a model | The first withheld brief in the history shows it working |
