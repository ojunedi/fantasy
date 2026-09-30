---
id: SCN-003
scenario_id: lineup-agent-abstains
journey: J-01
kind: alternate
status: agreed
---

# Agent abstains — signal quality too low to recommend

Projections are missing, the injury report has not refreshed since Sunday, or a
key starter's status is genuinely unresolved at the time the agent runs. The
agent declines to produce a lineup rather than producing one built on stale
inputs. It says what was missing and what would change its mind.

Abstention is a first-class outcome. An agent that always answers is an agent
whose confidence carries no information.

## Events

| id | event | scenario | after | actor | context | pivotal | hotspot | notes |
|----|-------|----------|-------|-------|---------|---------|---------|-------|
| E-030 | SignalStalenessDetected | SCN-003 | | R-02 | BC-signal | yes | | Branches at the signal join; one or more inputs fail the freshness threshold |
| E-031 | AbstentionDecided | SCN-003 | E-030 | R-02 | BC-analysis | yes | | The optimizer is not run — there is nothing trustworthy to optimise over |
| E-032 | MissingSignalsReported | SCN-003 | E-031 | R-02 | BC-lineup | | | Names which signals were stale, how stale, and what would resolve it |
| E-033 | AbstentionPresentedToManager | SCN-003 | E-032 | R-01 | BC-lineup | yes | | Manager sees the gap, not an empty screen |
| E-034 | AbstentionLogged | SCN-003 | E-033 | R-02 | BC-ledger | | | Recorded as a decision — an abstention is data about the signal layer |
| E-035 | ManagerSetLineupUnassisted | SCN-003 | E-033 | R-01 | BC-lineup | yes | | Path terminates here — the manager acts without the agent, in the ESPN app |

## Assumptions

| id | assumption | source |
|----|------------|--------|
| ASM-007 | A freshness threshold exists per signal type and is explicit, not implicit | kb |
| ASM-008 | The manager still has time to act unassisted when the abstention arrives | assumed |

## Commands

| id | command | event | actor | aggregate | context |
|----|---------|-------|-------|-----------|---------|
| C-006 | Abstain | E-031 | R-02 | AGG-lineup-rec | BC-analysis |

## Policies

| id | when | then | crosses_context |
|----|------|------|-----------------|
| P-005 | E-030 | Abstain rather than optimise over stale inputs (BC-signal → BC-analysis) | yes |
| P-006 | E-033 | Log the abstention with the staleness evidence (BC-recommendation → BC-audit) | yes |
