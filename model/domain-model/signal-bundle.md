---
product: Fantasy GM
stage: domain-design
aggregate: AGG-signal-bundle
---

# AGG-signal-bundle

## Invariants

| id | aggregate | rule | enforced_in |
|----|-----------|------|-------------|
| I-01 | AGG-signal-bundle | Every signal in the bundle carries a source and an as-of timestamp; a signal without provenance cannot enter it | SignalBundle.add |
| I-02 | AGG-signal-bundle | The bundle reports complete only if every member is within its own type's freshness threshold; otherwise it reports stale and names which members failed | SignalBundle.assessFreshness |

## Transitions

| aggregate | from | to | event |
|-----------|------|----|-------|
| AGG-signal-bundle | new | gathering | E-002 |
| AGG-signal-bundle | gathering | complete | E-007 |
| AGG-signal-bundle | gathering | stale | E-030 |

## Members

| id | name | aggregate | kind | notes |
|----|------|-----------|------|-------|
| ENT-player | Player | AGG-signal-bundle | entity | Identity persists across weeks and seasons; status and team change under it |
| ENT-projection | PlayerProjection | AGG-signal-bundle | value-object | A number as of a timestamp. Replaced wholesale on refresh, never edited — editing one would destroy the as-of guarantee I-14 depends on |
| ENT-provenance | Signal provenance | AGG-signal-bundle | value-object | The source and as-of pair. Inseparable from the value it describes (I-01) |

