# ADR-001: The agent may refuse to answer

**Status:** accepted in principle, not yet enforceable · **Date:** 2026-10-01

## Context

Every recommendation rests on signals that can be missing, stale, or unresolved. Projections may not have published, the injury report may not have refreshed since Sunday, a key starter's status may genuinely be unknown at the time the agent runs.

The behaviour has existed since the first agent — `abstain` is a terminal tool alongside `propose_lineup` — but it was never written down as a decision. Of 35 logged trade decisions, 22 were abstentions: the majority outcome was undocumented.

## Decision

Abstention is a first-class outcome, not a failure mode. The agent may end a run by declining to recommend, and when it does it must say which signals were missing or stale, by how much, and what would change its answer.

It is modelled as a terminal state on the analysis aggregates and enforced by invariant I-05: an abstention with no evidence is rejected.

## Options rejected

**Always produce a recommendation, with a confidence score.** Rejected because a confidence number is easy to ignore and easy to misread, while a refusal is neither. An agent that always answers is one whose confidence carries no information — and the failure mode is silent: a recommendation built on three-day-old injury data looks exactly like a good one.

**Fail the run on missing signals.** Rejected because it conflates "I cannot help" with "something is broken", and because it leaves the manager with nothing. An abstention still tells them what to go and check.

## Consequences

The manager sometimes gets no recommendation, close to a deadline, and must act unassisted. That is the intended trade: it is better than acting on a confident answer built from nothing.

Abstention needs its own place in the evaluation story. An abstained week is neither a win nor a loss for the agent, and counting it as either would distort the record.

**Unresolved, and the reason the status above is qualified:** the freshness thresholds that trigger abstention do not exist (H-02). The terminal tool is wired and the invariant is written, but nothing computes "too stale", so in practice the agent does not abstain on signal quality today.

This matters beyond the ADR. The resilience model names abstention as the degradation strategy when ESPN reads fail — a mitigation that cannot currently trigger is not a mitigation, and that file now says so. Setting the thresholds is what moves this decision from accepted-in-principle to accepted.
