# Design — claim-outcome-recorded

## Context

A filed claim sits on the waiver decision's `outcome["filing"]` (state,
transaction, waiver rank). ESPN's `mTransactions2` view reports every waiver
claim with a terminal status: `EXECUTED`, `FAILED_INVALIDPLAYERSOURCE` (the
player left the pool — a loss to priority when another team's claim for him
executed), other `FAILED_*` reasons, `CANCELED`, or `PENDING`. See
`intent.md` for why now.

---

# Build approach

## Where the code goes

| Concern | Location | Pattern it follows |
| --- | --- | --- |
| Reading a week's waiver transactions | `adapters/espn.py` — `get_waiver_transactions(season, week)` | `get_pending_waiver_claims`: raw ESPN shape, cache bypassed. Scoped to the claim's week — unscoped, ESPN returns only the current week's |
| Resolving a claim | `execute/waiver_api.py` — `resolve_claim(transactions, filing, team_id, week)` | Pure function beside the filing it reads; same team + week + add + drop match as `_confirm_filed` |
| Check route | `web/routes/waiver.py` — `POST /api/waiver/result` | The filing route: stored record, refuse with 409, render the status partial |
| Result states | `context.waiver_view` + `partials/waiver_status.html` | Existing filed states |

## Components

| Component | Action | Notes |
| --- | --- | --- |
| `adapters/espn.py` — `get_waiver_transactions`; `get_pending_waiver_claims` gains `week` | MODIFY | `WAIVER` transactions for the claim's week, every status; the filing read-back is scoped the same way |
| `execute/waiver_api.py` — `resolve_claim`, `ClaimResult` | MODIFY | Returns cleared / lost / failed / cancelled, or None while unresolved |
| `web/routes/waiver.py` — `check_result`, `_resolve`, `_earlier_unresolved` | MODIFY | Records `outcome["result"]` then renders; `backup_if_dirty`. The page lists earlier weeks' unresolved claims; the scan route refuses once this week's claim is filed |
| `web/context.py` — `waiver_view`, `claim_check_view`, `claim_failure_words` | MODIFY | Passes `result`; an earlier week's claim gets its own panel; ESPN failure statuses in words |
| `partials/claim_result_text.html`, `partials/claim_check.html`; `waiver.html` | CREATE / MODIFY | One result sentence shared by the current-week state and the earlier-week panels |
| `partials/waiver_status.html` | MODIFY | Check result button and the result states |
| `tests/execute/test_claim_result.py`, `tests/web/test_claim_result_page.py` | CREATE | |

## Domain

| Aggregate | Invariant it enforces here | Transaction boundary |
| --- | --- | --- |
| `WaiverClaim` (on the waiver decision's `outcome`) | I-18 — the result copies the filing's rank; I-23 — only a found terminal transaction resolves it | One `record_outcome` write, before render |

Matching: this team's `WAIVER` transaction whose `scoringPeriodId` is exactly
the filing's week and whose items are exactly {ADD add, DROP drop}. If several
match (an app-filed duplicate): `EXECUTED` wins; otherwise any `PENDING` copy
leaves the claim unresolved, so a cancelled or failed duplicate cannot settle
a claim that may still clear.

The claim is read for the week it was filed in, not the league's current
week: waivers often run after the week rolls over. Earlier weeks' unresolved
claims are listed on the waiver page, each with its own **Check result**. Lost to priority additionally needs another
team's `EXECUTED` waiver claim adding the same player in the same week; its
team is the winner, named from the standings read.

## Decisions

| Decision | Chosen | Rejected, and why |
| --- | --- | --- |
| When to resolve | On the manager's **Check result** | A schedule: out of scope; the check is cheap and explicit |
| `FAILED_INVALIDPLAYERSOURCE` with no winner found | failed, not lost | Calling it lost: a loss to priority needs the winning claim as evidence |
| Where the result lives | `outcome["result"]` beside `outcome["filing"]` | A new table: the decision owns the claim |

## Risks

| Risk | Mitigation |
| --- | --- |
| ESPN status names change | Unknown `FAILED_*` statuses fall to failed with the raw status as the reason — never lost |
| Overwriting a result with a later read | A recorded result short-circuits the route before any read (WADD-28) |

---

# Test approach

## Scenario coverage

| Scenario | AC | Level | Test file | Test name | Status |
| --- | --- | --- | --- | --- | --- |
| WADD-22 | AC-1, AC-2 | integration | `tests/web/test_claim_result_page.py` | `WADD-22: an executed claim is recorded as cleared` | required |
| WADD-23 | AC-3 | integration | `tests/web/test_claim_result_page.py` | `WADD-23: a claim beaten by another team is recorded as lost to priority` | required |
| WADD-24 | AC-4 | unit | `tests/execute/test_claim_result.py` | `WADD-24: any other failure is not a priority loss` | required |
| WADD-25 | AC-5 | integration | `tests/web/test_claim_result_page.py` | `WADD-25: a pending or missing claim stays unresolved` | required |
| WADD-26 | AC-5 | unit | `tests/execute/test_claim_result.py` | `WADD-26: a cancelled claim is recorded as cancelled` | required |
| WADD-27 | AC-6 | integration | `tests/web/test_claim_result_page.py` | `WADD-27: the result records the filing's priority position before the page shows it` | required |
| WADD-28 | AC-7, AC-8 | integration | `tests/web/test_claim_result_page.py` | `WADD-28: a recorded result is not read again` | required |

## Fixtures and test data

| Fixture | Why it must be realistic |
| --- | --- |
| Transactions built from the week-4 contested claim in this league (winner `EXECUTED`, losers `FAILED_INVALIDPLAYERSOURCE`, 1 ms apart) | The rule is written against ESPN's real status names |

## NFR verification

| NFR | Budget | Measured how | Where it runs |
| --- | --- | --- | --- |
| NFR-09 read-back | A result only from a found transaction | WADD-25 | `pytest` |
| NFR-10 logged before shown | Result in the log at render | WADD-27 | `pytest` |

## Not covered by automated tests

| What | Why | How it is checked instead |
| --- | --- | --- |
| The live league after a real window | Needs a real filed claim | The manager's first Check result after their first filing |
