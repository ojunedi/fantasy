# Design — signals-declare-staleness

## Context

`signals/collector.collect_signals` builds a `SignalBundle` whose
`availability` lists each source's name, `available`, `as_of` and note.
`LineupGraphAgent` (`agent/graph.py`) runs the model loop from
`GraphAgent.decide` (`agent/base.py`) and builds the record in `build_record`,
which already renders `{"abstained": True, ...}`. See `intent.md`.

---

# Build approach

## Where the code goes

| Concern | Location | Pattern it follows |
| --- | --- | --- |
| Thresholds and assessment | `signals/freshness.py` — `THRESHOLDS`, `REQUIRED`, `assess(bundle, now)` → `Freshness` | Pure function over the bundle, like `signals/base.py` |
| Stopping the run | `GraphAgent.decide` asks `self.precheck(ctx)` first; `LineupGraphAgent.precheck` returns an abstention record when stale | The existing `decide` → `build_record` path; default `precheck` returns None |

## Components

| Component | Action | Notes |
| --- | --- | --- |
| `signals/freshness.py` | CREATE | `Freshness(fresh, stale: [{name, age_seconds, threshold_seconds, required, reason}])` |
| `agent/base.py` — `GraphAgent.decide`, `precheck` | MODIFY | Precheck runs before the LLM is built; an early record skips the graph |
| `agent/graph.py` — `LineupGraphAgent.precheck` | MODIFY | Abstention with `stale_signals` evidence, `missing_information`, memo |
| `tests/signals/test_freshness.py`, `tests/agent/test_stale_abstain.py`, `tests/web/test_stale_abstention_page.py` | CREATE | |

## Domain

| Aggregate | Invariant it enforces here | Transaction boundary |
| --- | --- | --- |
| `SignalBundle` | I-01 (no as-of → stale), I-02 (names every failure) | Computed, not stored |
| `LineupAnalysis` | I-05 (abstention carries name, age, threshold) | The usual single `store.save` by the caller |

Record shape: `recommendation = {"abstained": True, "stale_signals": [...],
"missing_information": ["projections: missing (threshold 6h)", ...],
"what_you_would_need": "fresh projections …", "memo": "Abstained: …"}`,
`confidence = 0`, `inputs_snapshot` as `build_record` writes it.

## Decisions

| Decision | Chosen | Rejected, and why |
| --- | --- | --- |
| Threshold model | Per signal, required vs optional | One global figure: injury news and weekly usage do not age alike |
| Optional stale | Named, not abstained on | Abstain on any: weather 13 h old would block a lineup that does not need it |
| Where it stops | Before the LLM is built | Let the model call `abstain`: spends calls and may not |

## Risks

| Risk | Mitigation |
| --- | --- |
| Thresholds never trip in practice | A failed projections fetch is the common case and trips as missing (SIGSTALE-04) |
| Precheck breaks the trade agent | Default `precheck` returns None; only the lineup agent overrides it |

---

# Test approach

## Scenario coverage

| Scenario | AC | Level | Test file | Test name | Status |
| --- | --- | --- | --- | --- | --- |
| SIGSTALE-01 | AC-1, AC-2 | unit | `tests/signals/test_freshness.py` | `SIGSTALE-01: a required signal past its threshold makes the bundle stale` | required |
| SIGSTALE-02 | AC-3 | unit | `tests/signals/test_freshness.py` | `SIGSTALE-02: a missing or unstamped signal is stale, never fresh` | required |
| SIGSTALE-03 | AC-5 | unit | `tests/signals/test_freshness.py` | `SIGSTALE-03: a stale optional signal is named but does not make the bundle stale` | required |
| SIGSTALE-04 | AC-4 | integration | `tests/agent/test_stale_abstain.py` | `SIGSTALE-04: a stale run abstains before any model call` | required |
| SIGSTALE-05 | AC-6 | integration | `tests/agent/test_stale_abstain.py` | `SIGSTALE-05: a fresh run proceeds as before` | required |
| SIGSTALE-06 | AC-7 | integration | `tests/web/test_stale_abstention_page.py` | `SIGSTALE-06: the history shows the stale abstention and why` | required |

## NFR verification

| NFR | Budget | Measured how | Where it runs |
| --- | --- | --- | --- |
| NFR-01 | Stale run ends before any model call | SIGSTALE-04 asserts the LLM builder is never reached | `pytest` |

## Not covered by automated tests

| What | Why | How it is checked instead |
| --- | --- | --- |
| A real ESPN outage | Cannot be staged against the live league | The first one shows as an abstention naming projections |
