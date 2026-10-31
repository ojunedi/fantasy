---
product: Fantasy GM
stage: feature-slices
---

# Feature Slices

Thirteen slices. Three touch the interface.

**The walking skeleton spans two slices, and that is a compromise worth naming.** A skeleton should walk through every layer, and the waiver capability's layers end at a write to ESPN. Splitting scoring from filing means neither slice alone proves the whole path. The October window forced it: the scoring half is what can realistically ship inside the waiver season, and the filing half is where the write risk lives. They should be built back to back.

## Slices

| id | slice_id | name | interface | depends_on | status | openspec_change |
|----|----------|------|-----------|------------|--------|-----------------|
| S-001 | decision-history-survives | My season's decision record survives losing the laptop | | | complete | decision-history-survives |
| S-002 | pre-kickoff-nudge | I am nudged before kickoff when a recommendation is sitting unread | yes | | complete | pre-kickoff-nudge |
| S-003 | waiver-add-worth-making | The agent tells me whether there is a waiver add worth making, and if so which | yes | | complete | waiver-add-worth-making |
| S-004 | one-approval-gate | There is one approval gate, not two that can silently disagree | | | complete | one-approval-gate |
| S-005 | waiver-claim-filed | An approved claim is filed through the API and confirmed, not typed by hand | | S-003,S-004 | todo | |
| S-006 | claim-outcome-recorded | I find out whether my claim cleared or lost to priority | | S-005 | todo | |
| S-007 | unread-recommendation-surfaced | A missed recommendation is recorded with what it cost | | | todo | |
| S-008 | write-failure-reaches-me | I find out when both write paths failed, while there is still time to act | yes | | todo | |
| S-009 | refuse-unsafe-start | The app refuses to start in a way that exposes my ESPN cookies | | | todo | |
| S-010 | signals-declare-staleness | The agent declines to answer when its signals are too stale to trust | | | todo | |
| S-011 | brief-integrity | A brief cannot contain a number the analysis never computed | | | todo | |
| S-012 | claim-would-clear | Waiver recommendations account for whether the claim would actually clear | | S-006 | todo | |
| S-013 | fantasypros-projections | Projections come from FantasyPros rather than ESPN | | | todo | |

## Sequence

| order | slice | rationale |
|-------|-------|-----------|
| 1 | S-001 | Retires the only unrecoverable failure in the system, and the exposure grows every week the season continues. Not the skeleton and retires no design uncertainty — first because what it protects is irreplaceable and the fix is an afternoon |
| 2 | S-002 | **The measured gap is adherence, not analysis.** In weeks 1–2 the optimizer matched what was actually started; in week 3 it was right by 8.9 points and was not followed. Meanwhile the naive baseline is ahead of actual decisions by roughly 3 points a week. No amount of new capability fixes a recommendation nobody reads, which makes this the highest-value slice in the list |
| 3 | S-003 | First half of the walking skeleton, and time-boxed — it is already October. Proves signal gathering, the two-bar scoring, the brief and the log connect for a third decision type. Stops before the gate and the write, deliberately |
| 4 | S-004 | **Moved ahead of the waiver filing on purpose.** The filing slice needs a `LIVE` gate, and there are already two copies of that rule. Building the waiver gate before consolidating would create a third and then pay to remove it — so consolidation comes first and the waiver filing becomes the new gate's first caller |
| 5 | S-005 | Second half of the skeleton. Completes the layer the first half stopped short of, which is also the layer where the trade write was found returning success without acting. Filing through the API rather than by hand is also what lets the system know a claim was filed at all |
| 6 | S-006 | Makes the scorer improvable. Without the claim outcome there is no way to learn it keeps naming players we were never going to get, and that is the failure a waiver scorer is most likely to have |
| 7 | S-007 | The after-the-fact record of a missed recommendation. Lower than the nudge because the nudge may prevent the miss, but still wanted: reminders get ignored, and the cost of a miss is worth knowing either way |
| 8 | S-008 | The twin of the miss: everything upstream worked and the lineup still did not change, this time because the write failed silently rather than because nobody looked. Same shape, same consequence, and it had no slice until the slicing was challenged |
| 9 | S-009 | Real but lower likelihood than everything above on a personal machine. Here because it is small, and because relying on a default for a whole season is different from deciding to |
| 10 | S-010 | Unblocks abstention, which two documents already name as a mitigation and which cannot currently fire. After the waiver work on purpose — thresholds are easier to choose against three decision types than two |
| 11 | S-011 | Enforces the guarantee the whole design exists for. Last of the risk-retiring slices because the failure is a wrong number in prose the manager reads before acting, rather than a wrong action |
| 12 | S-012 | **Conditional, not merely late.** S-006 produces the evidence for whether lost claims are frequent enough to justify modelling priority at all. Building it first would be solving a problem by assumption |
| 13 | S-013 | **Sequenced by convenience, not risk.** An accuracy upgrade with no deadline and a working fallback. The architecture requirement — that the projection source stays pluggable — is already met, so this is the swap itself whenever it is wanted |

<!--
Two positions declare themselves as sequenced by something other than risk, and
one of those (S-012) is conditional rather than merely late.

One gap is retired by nothing here, deliberately: the decision store keeps three
aggregates in one table with their states in a JSON column, which
`architecture/data-model.md` calls its own biggest gap. The backup slice copies
that gap rather than closing it. Accepted until a question needs answering
across weeks without a table scan — the migration is written down, and nobody
has needed it yet.

Two live hotspots also have no slice: who initiates a trade (H-04), and whether
a refused offer can be distinguished from an unanswered one (H-07). The second
quietly caps how much the ledger can say about which pitches work.
-->
