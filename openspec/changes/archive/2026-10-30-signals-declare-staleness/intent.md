# Intent — signals-declare-staleness

## Outcome

When a lineup run's projections or injury status are older than their
threshold — or missing — the agent abstains before any model call, and the
manager sees which inputs were stale, how old, and the threshold each broke.

## Who

**Actor:** the manager
**What changes for them:** a run that today would optimise on missing
projections (an ESPN read that failed) now says so and recommends nothing.

## Why now

The abstain tool is wired, the invariant is written, and two documents name
abstention as the degradation strategy for ESPN read failures — but nothing
computes "too stale", so it cannot fire. Sequenced after the waiver work so
thresholds could be chosen against three decision types.

## Acceptance criteria

| # | Criterion | Source |
| --- | --- | --- |
| AC-1 | Each signal type has its own threshold: projections 6 h, injuries 1 h (required for a lineup decision); usage trends 7 days, Vegas lines 24 h, weather 12 h (optional) | hotspot H-02; invariant I-02 |
| AC-2 | The bundle reports fresh only if every required signal is available, carries an as-of time, and is within its threshold; otherwise it reports stale and names each failing signal | invariant I-02 |
| AC-3 | A signal that is unavailable, or has no as-of time, counts as stale — never as fresh | invariant I-01 |
| AC-4 | When the bundle is stale, the lineup run abstains without calling the model, and the abstention records, per failing signal: its name, its age (or that it is missing), and its threshold | invariant I-05; NFR-01 — abstaining ends the run early |
| AC-5 | A stale optional signal never causes an abstention; it is named in the bundle report and the run continues | outcome; H-02 — only inputs the decision depends on can stop it |
| AC-6 | A fresh bundle changes nothing about how the run proceeds | outcome |
| AC-7 | The decision history shows the stale abstention as abstained, and its memo names the stale signals | outcome |

## Acceptance signal

- A Sunday morning with ESPN's projections endpoint down produces an
  abstention naming projections as missing, instead of a lineup optimised on
  nothing.

## Out of scope

- The trade agent (its own slice if wanted).
- Abstaining only when a starter's status is unresolved — the narrower H-02
  option; age-based thresholds first.
- The waiver scan, which already has its own freshness check.

## Carried context

| | |
| --- | --- |
| **Bounded contexts** | Signal (freshness and thresholds); Analysis (the abstention) |
| **Aggregates touched** | SignalBundle; LineupAnalysis (abstained) |
| **Invariants at risk** | Provenance (I-01); bundle completeness names failures (I-02); abstention carries evidence (I-05) |
| **Contracts** | None external |
| **NFRs that apply** | Run time (NFR-01) |
| **Depends on** | Nothing |

## Interface impact

**Does this slice touch a user interface?** No new screens. The abstention
renders through the existing abstained state in the decision history and
detail page.

## Open questions

| # | Question | Owner | Blocking? |
| --- | --- | --- | --- |
| H-02 | Thresholds. **Resolved:** per signal, required vs optional, values in AC-1. What can trip in practice: projections trip as *missing* when ESPN fails (its cache refetches after 1 h, and a failed refetch raises), so the 6 h age is a backstop; injury status is read live each run; usage trends and Vegas lines carry their nflverse file's real age, since a failed reload serves the old copy, and do trip; weather is fetched live | — | No |
