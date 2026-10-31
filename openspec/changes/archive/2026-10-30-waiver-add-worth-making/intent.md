# Intent — waiver-add-worth-making

## Outcome

The manager receives a scored recommendation of which player to add from the waiver wire this week — with the reasoning and the player they would drop — before the Tuesday filing deadline.

## Who

**Actor:** The manager (R-01)
**What changes for them:** Each waiver window the manager can see a brief explaining whether a candidate clears both scoring bars and which player would be displaced, instead of deciding by platform ranking alone.

## Why now

First half of the waiver walking skeleton. It proves signal gathering, two-bar scoring, and brief generation for a new decision type. Without it, every waiver decision is unassisted and the objective of covering every waiver window cannot be met (O-02). The claim filing slice depends on this one — the recommendation must exist before it can be acted on.

## Acceptance criteria

| # | Criterion | Source |
|---|---|---|
| AC-1 | When the waiver scan runs and at least one candidate clears all three conditions, the output names the top candidate, the player it would displace, and the value margin | outcome |
| AC-2 | A candidate clears the relative bar only if its rest-of-season projected value exceeds the worst rostered player it would displace at its position | invariant I-06 (WaiverAnalysis) |
| AC-3 | A candidate clears the absolute bar only if it ranks inside the league-wide startable tier — team count × starting slots at that position — derived from league settings, not hardcoded | invariant I-28 (WaiverAnalysis) |
| AC-4 | A candidate must project as startable within the next 3 weeks against a fully-available roster; a bye-week or short-term injury opening does not count as a path to starting | invariant I-30 (WaiverAnalysis) |
| AC-5 | A candidate appears as recommended only if it clears all three conditions; a candidate who clears one or two is not a weaker recommendation — it is not a recommendation | invariant I-29 (WaiverAnalysis) |
| AC-6 | When no candidate clears all conditions, the output names the closest candidate, which condition it failed, and by how much | invariant I-17 (WaiverAnalysis) |
| AC-7 | Every number in the brief appears verbatim in the analysis output that produced it; the brief may restate a number but may not introduce one | invariant I-26 (WaiverClaim) |
| AC-8 | Each signal in the bundle carries a source identifier and an as-of timestamp; a signal without provenance is rejected before the analysis runs | invariant I-01 (SignalBundle) |
| AC-9 | If any signal source exceeds its freshness threshold, the run reports stale, names the failing source(s), and does not produce a recommendation | invariant I-02 (SignalBundle) |
| AC-10 | The waiver decision record — recommendation or no-add — is written to SQLite before the run reports completion | NFR-10 (SVC-gm) |
| AC-11 | A no-add outcome (no candidate clears all conditions) is recorded in the decision log with the same weight as a positive recommendation | invariant I-19 (WaiverClaim) |
| AC-12 | The waiver scan uses at most 3 LLM calls | NFR-04 (SVC-gm) |

## Acceptance signal

The manager acts on a waiver recommendation each Tuesday window for the rest of the 2026 season rather than scanning the platform by hand; every waiver window has a logged decision in the ledger.

## Out of scope

- Filing the waiver claim — that is the next slice
- Modeling priority order or contested-claim outcomes — the brief names the target; priority logistics belong to the filing slice (H-03)
- Automatic claim submission without manager approval — the human gate is not negotiable
- Bid amounts — this league uses snake priority, not FAAB

## Carried context

| | |
|---|---|
| **Bounded contexts** | Signal Kernel (BC-signal), Decision Analysis (BC-analysis), Waiver Execution (BC-waiver), Decision Ledger (BC-ledger) |
| **Aggregates touched** | SignalBundle, WaiverAnalysis, WaiverClaim (decision record only — no claim filed this slice) |
| **Invariants at risk** | I-01, I-02 (SignalBundle); I-06, I-17, I-28, I-29, I-30 (WaiverAnalysis); I-19, I-26 (WaiverClaim) |
| **Contracts** | None external |
| **NFRs that apply** | NFR-04 (≤3 LLM calls), NFR-07 (before Tuesday deadline), NFR-08 (no uptime requirement), NFR-10 (written to SQLite before completion) |
| **Depends on** | None |

## Interface impact

**Does this slice touch a user interface?** Yes

The waiver brief and recommendation surface in the web UI. The manager reads the recommendation, approves (intends to claim) or declines, and sees the outcome in the decision history.

## Open questions

| # | Question | Owner | Blocking? |
|---|---|---|---|
| Q-1 | Does the waiver scan run on demand (manager triggers it) or on a schedule (every Wednesday), or both? | R-01 | Yes — shapes the trigger mechanism and whether a launchd plist is needed |
| Q-2 | Is the replacement baseline computed over the whole roster or only startable slots? A receiver buried on the bench is cheap to displace but not a meaningful opening (H-05) | R-01 | Yes — I-06 says "worst rostered player" but H-05 marks this unsettled; ACs above assume whole-roster until resolved |
| Q-3 | Should the recommendation include a suggested drop player here, or only in the filing slice? Earlier is cleaner but the filing slice can prompt for it | R-01 | No |
