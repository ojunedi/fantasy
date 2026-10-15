# Intent — decision-history-survives

## Outcome

After every write to the decision store, a committed copy of it exists in a private repository off this machine, so losing the laptop costs an afternoon of setup rather than the season's decision record.

## Who

**Actor:** the manager — the single human who approves every decision and reads the end-of-season review.

**What changes for them:** nothing in how they work. What changes is that the question *"what did the agent recommend in week 3, and why did I overrule it"* stays answerable after a disk failure, a theft, or a mistaken delete.

## Why now

It retires the only unrecoverable failure in the system. Every other failure recorded in the architecture is either costless or recoverable; this one ends the season's evidence. The decision log is also the product's primary artifact by design — the override log is what the whole evaluation story rests on — and it is currently one unreplicated file with nothing noticing if it disappears.

Not the walking skeleton. It walks through no layers and retires no design uncertainty. It is first because what it protects is irreplaceable, the exposure grows every week the season continues, and the fix is small.

## Acceptance criteria

| # | Criterion | Source |
| --- | --- | --- |
| AC-1 | After any write to the decisions table, a SQL dump of that table exists in the separate private backup repository, committed, with a message naming the week and season just written | outcome |
| AC-2 | Restoring the dump into an empty database reproduces every stored input snapshot byte-identically — no re-serialisation, no timestamp normalisation, no key reordering | invariant I-10 (`LineupDecision`) |
| AC-3 | A backup that cannot reach its remote leaves the decision already written and durable locally, names the failure, and does not abort the run that produced it | NFR-10 (SVC-gm) |
| AC-4 | The dump contains no ESPN session cookie, no API key, and no value read from the environment | security — the decision log now leaves the machine, which the architecture currently states it never does. That statement needs correcting when this ships |
| AC-5 | When the backup repository holds decisions for weeks the local store does not, starting the tool names the missing weeks | hotspot — nothing currently detects the loss this slice exists to survive |
| AC-6 | A restore from any commit yields a database the backtest runs against without error, rebuilding the scorecards from the restored decisions | outcome |

## Acceptance signal

- Replacing the laptop mid-season costs setup time, not decision history.
- At the end of the season, the override log is complete for every week played — not every week since the last time someone remembered to copy a file.

## Out of scope

Binding.

- **Automated restore tooling.** A restore is a clone and a SQLite import. Building tooling for it before a real loss is building for a scenario that has never happened.
- **Retention or pruning.** The dump is small and the repository is versioned. Pruning is premature.
- **Backing up the LangGraph checkpoints.** They are resumable-run state; a lost checkpoint costs a re-run. See the open question — this may be wrong.
- **Backing up the parquet and ESPN caches.** They re-fetch.
- **Backing up the scorecards.** They are computed entirely from the decision log plus historical projections, so a restore rebuilds them with one backtest run. Protecting a reconstructible table alongside an irreplaceable one would also have forced a commit-per-run cadence, because a full-season backtest writes seventeen scorecards in seconds.
- **Protecting against loss of the backup repository itself.** One off-machine copy is the whole scope.

## Carried context

| | |
| --- | --- |
| **Bounded contexts** | Decision Ledger — owns the log and the computed scorecards |
| **Aggregates touched** | All three decision aggregates and the backtest report are *read*. None is modified |
| **Invariants at risk** | The frozen input snapshot (I-10) |
| **Contracts** | None. Nothing external is involved |
| **NFRs that apply** | Durability before a run reports complete (NFR-10) |
| **Depends on** | Nothing |

## Interface impact

**Does this slice touch a user interface?** No.

The manager interacts with it through the CLI only, and only when something is wrong: a backup failure message, and the startup warning when the local store is behind the backup. The `ux` artifact is therefore skipped.

## Open questions

None open.

The backup repository is created by the manager, once, with its remote already
configured; the slice is pointed at it by environment variable and names what is
missing if it is not there. This matches how every other external dependency in
the system is configured, and keeps the choice of remote — and whether it is
private — out of the code.

A restored decision is *readable*, not *replayable*. The frozen input snapshot
and the backtest rebuild are the whole of what survives; re-running a restored
decision through the agent is not in scope, and the agent's graph state is not
backed up.

## Quick challenge

**Resolved during this document.** The challenge was whether committing on every write is the right cadence: right for live decisions at three or four a week, wrong for a backtest writing seventeen scorecards in seconds. The question underneath it was whether the scorecards belong in the backup at all, given they are fully recomputable from the decisions.

They do not. The scope is now the decisions table alone, which makes commit-per-write correct again — every commit is a real decision — and leaves the restore path as clone, import, and one backtest run.

**Settled since:** a restored decision is readable, not replayable. The input snapshot survives by AC-2 and the backtest rebuilds the scorecards from it, but re-running a restored decision through the agent is not in scope and the graph state is not backed up.
