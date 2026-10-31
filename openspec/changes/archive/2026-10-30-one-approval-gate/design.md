# Design — one-approval-gate

## Context

Three places decide whether an execution writes for real, each with its own
`== "LIVE"`: the command line's lineup write (`memo/cli.py`, after `.strip()`),
its trade send (`memo/cli.py`, after `.strip()`), and the web write step
(`web/routes/approve.py`, exact). The web step never reads the decision's
approval state. See `intent.md` for why this is merged now.

---

# Build approach

## Where the code goes

| Concern | Location | Pattern it follows |
| --- | --- | --- |
| The gate | `src/fantasy_gm/execute/gate.py` | Sits beside the executors it guards; a pure function over a `DecisionRecord`, like `execute/lineup_plan.py` |
| Command-line callers | `src/fantasy_gm/memo/cli.py` | Existing prompt flow; the raw `input()` text goes to the gate untrimmed |
| Web caller | `src/fantasy_gm/web/routes/approve.py` — `execute()` | Existing route; record loaded from the store with `load_decision`, as today |
| Refusal display | `partials/execution_result.html` | Adds a refused branch above the existing success / failure branches |

## Components

| Component | Action | Notes |
| --- | --- | --- |
| `execute/gate.py` — `authorise()`, `Authorisation`, `Verdict` | CREATE | The only `LIVE` comparison in the source |
| `memo/cli.py` — `_execute_approved_lineup`, `_send_approved_trade` | MODIFY | Ask the gate; print the refusal and stop when refused |
| `web/routes/approve.py` — `execute` | MODIFY | Ask the gate with the stored record; also refuse a decision that is not a lineup with starters (an empty starter list would bench everyone); 409 and no executor call when refused |
| `templates/base.html` | MODIFY | htmx config: swap 409 and 422 responses instead of dropping them, so a refusal is shown |
| `partials/execution_result.html` | MODIFY | Refused branch: "Nothing was sent" and the refusal message |
| `tests/execute/test_gate.py` | CREATE | Gate rules and the cross-surface matrix |
| `tests/web/test_execute.py` | MODIFY | Web refusal cases |
| `tests/web/test_gate_parity.py` | CREATE | Both surfaces across the full state × confirmation matrix; under `tests/web` to share its fixtures |

## Domain

| Aggregate | Invariant it enforces here | Transaction boundary |
| --- | --- | --- |
| `Decision` | I-11 (approved or overridden only), I-09 (override carries a reason), I-24 (per execution, never persisted) | Read only — the gate writes nothing |

`authorise(record, confirmation)` returns one of three verdicts:

| Decision state (`human_response`) | Confirmation exactly `LIVE` | Anything else |
| --- | --- | --- |
| `approved` | live | Dry run |
| `modified` (overridden) with a non-blank `override_reason` | live | Dry run |
| `modified` with a blank or missing reason | refused `OVERRIDE_REASON_MISSING` | refused |
| none (pending), `rejected`, `declined` | refused `NOT_APPROVED` | refused |

State is checked before confirmation, so a refusal never depends on what was typed.

## Contracts

None external.

## Data and migrations

None. The gate stores nothing (I-24).

## Decisions

| Decision | Chosen | Rejected, and why |
| --- | --- | --- |
| Merge or test for equivalence | Merge into one function (the manager's call) | Equivalence test only: keeps three copies, and waiver filing would add a fourth |
| Confirmation trimming | Exact match, no trimming, on both surfaces | Trim on both: relaxes the stricter web rule, which the slice forbids |
| Unapproved decision | Refuse, and do not even dry-run | Dry-run it: a dry run of an unapproved decision invites the next step to be `LIVE`; refusing says what is wrong |
| Gate's input | The `DecisionRecord` itself | Separate flags (`approved: bool`): a caller can pass the wrong one; the record is the only source of truth |
| Executor signature | Unchanged — callers pass `live=verdict.live` | Executors take an `Authorisation`: four executors and their tests change for no behaviour gain this slice |

## Risks

| Risk | Mitigation |
| --- | --- |
| A future caller compares against `LIVE` itself | APPGATE-09 searches the source and fails on any second comparison |
| The command line's prompt flow regresses mid-season | `tests/web/test_gate_parity.py` drives the lineup prompt with patched `input` |
| A shared helper caches the verdict | `authorise` is a pure function with no module state; APPGATE-06 executes twice |

---

# Test approach

## Scenario coverage

| Scenario | AC | Level | Test file | Test name | Status |
| --- | --- | --- | --- | --- | --- |
| APPGATE-01 | AC-1 | unit | `tests/execute/test_gate.py` | `APPGATE-01: approved decision confirmed with LIVE writes` | required |
| APPGATE-02 | AC-1 | unit | `tests/execute/test_gate.py` | `APPGATE-02: overridden decision with a reason confirmed with LIVE writes` | required |
| APPGATE-03 | AC-3 | unit | `tests/execute/test_gate.py` | `APPGATE-03: anything but exactly LIVE is a dry run` | required |
| APPGATE-04 | AC-2 | unit | `tests/execute/test_gate.py` | `APPGATE-04: pending, rejected or declined decision is refused` | required |
| APPGATE-05 | AC-4 | unit | `tests/execute/test_gate.py` | `APPGATE-05: override without a written reason is refused` | required |
| APPGATE-06 | AC-5 | integration | `tests/web/test_execute.py` | `APPGATE-06: a live execution does not authorise the next one` | required |
| APPGATE-07 | AC-2, AC-7 | integration | `tests/web/test_execute.py` | `APPGATE-07: web write step refuses an unapproved decision` | required |
| APPGATE-08 | AC-6, AC-8 | integration | `tests/web/test_gate_parity.py` | `APPGATE-08: both surfaces give the same verdict` | required |
| APPGATE-10 | AC-7 | integration | `tests/web/test_execute.py` | `APPGATE-10: web write step refuses an approved decision that is not a lineup` | required |
| APPGATE-09 | AC-6 | unit | `tests/execute/test_gate.py` | `APPGATE-09: no code outside the gate compares against LIVE` | required |

APPGATE-08 drives the real surfaces, not the gate: the command line's lineup
write and trade send through their prompt functions with `input` patched, the web through the test client,
both against a recording executor, across the full state × confirmation matrix.

## Fixtures and test data

| Fixture | Why it must be realistic |
| --- | --- |
| Decision records saved to a temporary decision log, then given a response with `record_human_response` | The gate must read the state the store actually holds, not a hand-set attribute |
| A recording executor (`FakeExecutor` in `tests/web/test_execute.py`) | Proves the executor is not called on a refusal, and with which `live` value otherwise |

## NFR verification

| NFR | Budget | Measured how | Where it runs |
| --- | --- | --- | --- |
| NFR-11 (web is the less-protected caller) | No request field can change the verdict | APPGATE-07 posts forged approval fields | `pytest`, every run |

## Not covered by automated tests

| What | Why | How it is checked instead |
| --- | --- | --- |
| A real ESPN write | Live writes are never made from tests | The season-end match of ESPN transactions against the decision log (intent's acceptance signal) |
