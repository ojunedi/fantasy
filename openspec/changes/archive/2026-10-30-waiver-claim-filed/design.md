# Design — waiver-claim-filed

## Context

The waiver scan records a recommendation and the manager's "Intend to claim"
(approved). ESPN's own transaction history for this league shows what a claim
looks like: one `WAIVER` transaction, `executionType: EXECUTE`, with an `ADD`
item (`fromTeamId: 0 → toTeamId: me`) and a `DROP` item (`fromTeamId: me →
toTeamId: 0`); filed claims read back with `status: PENDING`. The trade send
(`execute/trade_api.py`) already posts to the same transactions endpoint and
confirms by reading back — this slice follows it. See `intent.md` for why now.

---

# Build approach

## Where the code goes

| Concern | Location | Pattern it follows |
| --- | --- | --- |
| Claim payload, plan, send, read-back | `src/fantasy_gm/execute/waiver_api.py` | `execute/trade_api.py`: pure payload builder, `plan()` / `execute(live=)` / `_confirm_*`, three-state `confirmed` |
| Fresh league reads | `src/fantasy_gm/adapters/espn.py` | `get_pending_trade_proposals` — raw ESPN shape, cache bypassed |
| Filing route | `src/fantasy_gm/web/routes/waiver.py` — `POST /api/waiver/file` | The lineup write step in `routes/approve.py`: stored record, shared gate, 409 on refusal |
| Filing states on the page | `context.waiver_view` + `partials/waiver_status.html` | Existing waiver states |

## Components

| Component | Action | Notes |
| --- | --- | --- |
| `execute/waiver_api.py` — `build_espn_waiver_claim`, `WaiverClaimPlan`, `WaiverFilingResult`, `ESPNWaiverApiExecutor` (`plan`, `check_still_legal`, `execute`, `_confirm_filed`) | CREATE | `execute` returns `confirmed` True / False / None like the trade send |
| `adapters/espn.py` — `get_pending_waiver_claims(season)`, `get_waiver_rank(team_id, season)` | MODIFY | Both bypass the cache; rank from the `mTeam` view's `waiverRank` |
| `models.py` — `WaiverScanResult.candidate_id`, `displaced_id` | MODIFY | The filing needs player ids; the scan already has them |
| `agent/waiver_agent.py` — carry `player_id` through `gather_scan_inputs` and `score_candidates` | MODIFY | |
| `web/routes/waiver.py` — `file_claim` | MODIFY | Steps below |
| `web/deps.py` — `get_waiver_executor`; `web/app.py` builds `app.state.waiver_executor` | MODIFY | Same as `get_executor`, so tests inject a fake |
| `web/context.py` — `waiver_view` filing states | MODIFY | Reads `record.outcome["filing"]` |
| `partials/waiver_status.html` | MODIFY | Ready to file, dry run, confirmed, not confirmed, not filed, refused |
| `tests/execute/test_waiver_api.py`, `tests/web/test_waiver_filing.py`, `tests/adapters/test_espn_waiver_reads.py` | CREATE | The adapter tests drive the reads with the raw payload captured from this league |

The filing route, in order: load the newest waiver decision for the week
from the store → refuse if any waiver decision this week has a filing that is
sending, confirmed or unconfirmed (`ALREADY_FILED`)
→ `authorise(record, confirm)` → refuse if the decision carries no player ids
(scanned before this slice) → build the plan from the stored ids → Dry run
returns here, recording nothing → `check_still_legal` with fresh reads
(`ROSTER_CHANGED`, with a re-scan exit; `LEAGUE_UNREADABLE` if the read fails)
→ read waiver rank → record the attempt as `sending` → `execute(live=True)` →
record the result over it, keeping every attempt in `outcome["attempts"]` →
`backup_if_dirty` → render.

Only a connection that never opened is `failed`. A send whose connection
opened but whose response was lost may have reached ESPN, so it is decided by
the read-back — confirmed or unconfirmed, never failed.

## Domain

| Aggregate | Invariant it enforces here | Transaction boundary |
| --- | --- | --- |
| `WaiverClaim` (recorded on the waiver `DecisionRecord.outcome["filing"]`) | I-12 fresh legality, I-18 priority captured, I-23 read-back, I-24 per-filing `LIVE` | One `record_outcome` write per live attempt, before the page renders |

## Decisions

| Decision | Chosen | Rejected, and why |
| --- | --- | --- |
| One request or two | One `WAIVER` transaction with ADD + DROP — what ESPN's own app files | Two requests: a window where the drop lands and the add does not |
| Where the filing is recorded | `outcome["filing"]` on the waiver decision | A new table: the decision already owns the claim, and the next slice adds the cleared/lost result beside it |
| Record dry runs? | No — only live attempts | Recording dry runs: they are not filings, and would read as claims in the log |
| Legality check | Fresh roster + free-agent reads right before the send | Trust the scan: a roster can change between Monday's scan and Tuesday's filing |
| Retry after unconfirmed | Never offered | Offering it: a duplicate claim is worse than an unverified one |

## Risks

| Risk | Mitigation |
| --- | --- |
| The payload has never been sent by this system | Copied field-for-field from ESPN's own claims in this league; the Dry run shows it first; the first `LIVE` is the manager's |
| ESPN accepts without acting (seen on the trade write) | Confirmed only by finding the pending claim on a cache-bypassed read |
| A stale pending claim from earlier weeks matches | Read-back matches on team, week, add and drop together, and on status `PENDING` |
| A response lost after ESPN received the claim | Treated as possibly filed: read back, never re-offered (WADD-20) |
| A re-run scan or a second tab files twice | Week-wide guard; `sending` recorded before the POST (WADD-21) |

---

# Test approach

## Scenario coverage

| Scenario | AC | Level | Test file | Test name | Status |
| --- | --- | --- | --- | --- | --- |
| WADD-11 | AC-1 | unit | `tests/execute/test_waiver_api.py` | `WADD-11: filing builds one transaction with the add and the drop` | required |
| WADD-12 | AC-2 | integration | `tests/web/test_waiver_filing.py` | `WADD-12: anything but LIVE is a dry run` | required |
| WADD-13 | AC-2 | integration | `tests/web/test_waiver_filing.py` | `WADD-13: a decision that is not approved is refused` | required |
| WADD-14 | AC-3 | integration | `tests/web/test_waiver_filing.py` | `WADD-14: a roster that changed since the scan refuses the filing` | required |
| WADD-15 | AC-4, AC-7 | integration | `tests/web/test_waiver_filing.py` | `WADD-15: a claim found pending on read-back is confirmed` | required |
| WADD-16 | AC-5, AC-7 | integration | `tests/web/test_waiver_filing.py` | `WADD-16: an accepted send the read-back cannot find is not confirmed` | required |
| WADD-17 | AC-6, AC-7 | integration | `tests/web/test_waiver_filing.py` | `WADD-17: a send ESPN rejects is reported as not filed` | required |
| WADD-20 | AC-5, AC-8 | integration | `tests/web/test_waiver_filing.py` | `WADD-20: a send that may have reached ESPN is never reported not filed` | required |
| WADD-21 | AC-8 | integration | `tests/web/test_waiver_filing.py` | `WADD-21: a rescan after filing does not reopen the claim` | required |
| WADD-18 | AC-8 | integration | `tests/web/test_waiver_filing.py` | `WADD-18: a decision already filed live cannot be filed again` | required |
| WADD-19 | AC-9 | integration | `tests/web/test_waiver_filing.py` | `WADD-19: the players come from the decision log, not the request` | required |

The web tests run the real `ESPNWaiverApiExecutor` against a fake adapter,
with `httpx.post` patched — so the payload, the legality check, the
read-back match and the three states are the production code, and only the
network is faked.

## Fixtures and test data

| Fixture | Why it must be realistic |
| --- | --- |
| Pending-claim read-back built from the ESPN shape captured in this league (week 1, team 8) | The match must work on ESPN's real field names, not on ones we invented |
| A stale `PENDING` claim for the same team with different players | Proves the match keys on the players, not just the team |

## NFR verification

| NFR | Budget | Measured how | Where it runs |
| --- | --- | --- | --- |
| NFR-09 read-back | Confirmed only on a found pending claim | WADD-15 / WADD-16 | `pytest` |
| NFR-10 logged before reported | Record written before render | WADD-15–17 read the store after the response | `pytest` |
| NFR-11 untrusted web caller | Request fields cannot pick players or approve | WADD-13, WADD-19 | `pytest` |
| NFR-07 before Tuesday deadline | Filing is on demand | Not enforced in code; the manager files it | — |

## Not covered by automated tests

| What | Why | How it is checked instead |
| --- | --- | --- |
| A real `LIVE` claim against ESPN | Tests never write to the live league | The manager's first `LIVE` filing, checked in the ESPN app |
| Browser rendering of the filing states | No browser test harness | Manual walk-through |
