# Design — unread-recommendation-surfaced

## Context

A lineup `DecisionRecord` saves, at decision time, `inputs_snapshot["projections"]`
(player id → projected points) and `recommendation["starter_player_ids"]`.
Those projections predate kickoff by construction, which is what I-14 needs.
The lineup that actually played is the week's roster read from ESPN (each
scoring period keeps its own lineup). See `intent.md` for why now.

---

# Build approach

## Where the code goes

| Concern | Location | Pattern it follows |
| --- | --- | --- |
| Finding and costing missed weeks | `src/fantasy_gm/nudge/missed.py` — `record_missed_lineups(store, adapter, team_id, season, now)` | `nudge/check.py`: store and clock injected, pure decisions, kickoff from `next_sunday_kickoff_utc` |
| Running it | `/history` page load (`web/routes/pages.py`) and `python -m fantasy_gm.nudge.missed` | The nudge CLI |
| Showing it | `context.decision_summary` + `partials/history.html` | Existing history row |

## Components

| Component | Action | Notes |
| --- | --- | --- |
| `nudge/missed.py` — `week_kickoff`, `week_settled`, `missed_cost`, `record_missed_lineups`, `main()` | CREATE | |
| `db/store.py` — `responded_at` column (migration), set by `record_human_response`; `models.DecisionRecord.responded_at` | MODIFY | Lets "responded before kickoff" be decided from the log |
| `web/routes/pages.py` — `history` | MODIFY | Records missed weeks before listing; a failure to read ESPN never blocks the page |
| `web/context.py` — `decision_summary` | MODIFY | Adds `missed` (cost) |
| `partials/history.html` | MODIFY | `missed` tag and cost in the Your call cell |
| `tests/nudge/test_missed.py`, `tests/web/test_history_missed.py` | CREATE | |

## Domain

| Aggregate | Invariant it enforces here | Transaction boundary |
| --- | --- | --- |
| `Decision` | I-09 — only `outcome["missed"]` is written; `human_response` and `override_reason` untouched. I-14 — the cost reads only `inputs_snapshot["projections"]` | One `record_outcome` per missed week |

Kickoff for a week comes from the week number, never from when a run was
made: week 1's Sunday is the Sunday after Labor Day, each later week seven
days on, 1 PM ET (`week_kickoff`). A week is recorded once settled — Tuesday
6 AM ET (`week_settled`) — with the lineup read fresh, so neither the cost nor
the hindsight depends on when the check happened to run. A week is missed when
no lineup decision for it got a response before kickoff; responses carry a
time (`decisions.responded_at`, added by migration — older responses have
none and count as in time). The miss is written on the newest run made before
kickoff that recommended starters; a later run is never charged (I-14).

Recorded shape: `{"missed": {"cost": float, "recommended_ids": [...],
"standing_ids": [...], "recommended_projected": float,
"standing_projected": float, "unprojected": [...], "kickoff": iso,
"hindsight": {"recommended_actual": float, "standing_actual": float} | null}}`.

## Decisions

| Decision | Chosen | Rejected, and why |
| --- | --- | --- |
| Cost basis | Saved pre-kickoff projections | Actual points: hindsight, forbidden by I-14; kept as labelled context |
| Where the miss lives | `outcome["missed"]` | A `HumanResponse.UNACTIONED`: a human response is a human choice, and silence must not look like one (I-09) |
| When it runs | On `/history` load and by hand | A new background job: installing one changes the machine's configuration |
| Several runs in one week | One miss, on the newest unactioned run | One per run: would multiply the cost |

## Risks

| Risk | Mitigation |
| --- | --- |
| ESPN unreachable when the history loads | Errors are caught per week; the page renders, the week is tried next load |
| A week's roster read returns the current lineup, not that week's | `get_roster(team, week, season)` is scoped to the scoring period |

---

# Test approach

## Scenario coverage

| Scenario | AC | Level | Test file | Test name | Status |
| --- | --- | --- | --- | --- | --- |
| LMISS-01 | AC-1, AC-3 | unit | `tests/nudge/test_missed.py` | `LMISS-01: an unactioned week after kickoff is recorded as missed` | required |
| LMISS-02 | AC-2 | unit | `tests/nudge/test_missed.py` | `LMISS-02: a week with an actioned decision is not missed` | required |
| LMISS-03 | AC-8 | unit | `tests/nudge/test_missed.py` | `LMISS-03: nothing is recorded before kickoff` | required |
| LMISS-04 | AC-7 | unit | `tests/nudge/test_missed.py` | `LMISS-04: a recorded miss is not recomputed` | required |
| LMISS-05 | AC-4 | unit | `tests/nudge/test_missed.py` | `LMISS-05: the cost is the difference in saved projections` | required |
| LMISS-06 | AC-5 | unit | `tests/nudge/test_missed.py` | `LMISS-06: a standing starter with no saved projection counts as zero and is named` | required |
| LMISS-07 | AC-6 | unit | `tests/nudge/test_missed.py` | `LMISS-07: actual points are recorded as hindsight, never as the cost` | required |
| LMISS-09 | AC-1 | unit | `tests/nudge/test_missed.py` | `LMISS-09: a run made after kickoff is never charged` | required |
| LMISS-10 | AC-2 | unit | `tests/nudge/test_missed.py` | `LMISS-10: a response after kickoff does not erase the miss` | required |
| LMISS-11 | AC-1, AC-9 | integration | `tests/web/test_history_missed.py` | `LMISS-11: opening the history records a settled missed week` | required |
| LMISS-08 | AC-9 | integration | `tests/web/test_history_missed.py` | `LMISS-08: history shows missed with the projected cost` | required |

## Fixtures and test data

| Fixture | Why it must be realistic |
| --- | --- |
| Lineup records shaped like the real ones in `data/decisions.db` (`inputs_snapshot.projections`, `starter_player_ids`) | The cost reads exactly those keys |

## NFR verification

| NFR | Budget | Measured how | Where it runs |
| --- | --- | --- | --- |
| NFR-06 kickoff trigger | Nothing before Sunday 1 PM ET | LMISS-03 with an injected clock | `pytest` |

## Not covered by automated tests

| What | Why | How it is checked instead |
| --- | --- | --- |
| Real past weeks in this season's log | Reads the live league | Run `python -m fantasy_gm.nudge.missed` once and read the history page |
