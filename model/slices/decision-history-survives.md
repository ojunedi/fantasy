---
id: S-001
slice_id: decision-history-survives
status: todo
---

# My season's decision record survives losing the laptop

## Outcome

After every write to the decision store, a copy exists somewhere that is not the same disk. If the laptop dies mid-season, the decision log and the computed scorecards come back.

## Contexts

| id | why |
|----|-----|
| BC-ledger | Owns the decision log and the backtest scorecards — the files at risk |

## Invariants

| id | risk |
|----|------|
| I-10 | A backup must copy the frozen input snapshot verbatim. A backup that re-serialises could alter what the agent is recorded as having seen, which defeats the replay guarantee it exists to protect |

## NFRs

| id | applies |
|----|---------|
| NFR-10 | The decision must still be durable before its run reports complete. The backup is additional, never a substitute for the primary write |

## Contracts

No external contracts. This system publishes no API and no messages — the
`Contracts` table is for endpoints and published events, and there are none to
reference. The domain events this slice introduces are internal and already
mapped in `event-maps/`.

## Open questions

| id | question | owner |
|----|----------|-------|
| — | Where does the copy go? Another directory on the same machine protects against corruption but not against losing the machine. Anything off-machine means a sync target and a decision about whether a personal decision log leaves the laptop | R-01 |
| — | Is loss detected, or only discovered? Nothing currently notices the file missing. A startup check that the expected week count is present would turn a silent loss into a visible one | R-01 |

<!--
Deliberately the narrowest useful version: copy after write, no scheduling, no
retention policy, no restore tooling. A restore is `cp` back, and inventing more
than that before the first real loss would be building for a scenario that has
never happened.
-->
