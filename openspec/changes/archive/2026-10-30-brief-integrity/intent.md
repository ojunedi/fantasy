# Intent — brief-integrity

## Outcome

Every number in a lineup brief, a trade rationale or a counterparty pitch
appears in the analysis that run computed; a brief that introduces one is
withheld — the manager sees which numbers it invented instead of the text.

## Who

**Actor:** the manager, and — for a trade pitch — the other team's manager
who would read it.
**What changes for them:** a brief can be read as a restatement of the
analysis, never a source of new figures.

## Why now

Every number in this product is computed deterministically so the model
cannot invent one — and then the briefs are generated prose, the one place
an invented number would look at home. The waiver brief already carries
this check; the lineup and trade briefs do not.

## Acceptance criteria

| # | Criterion | Source |
| --- | --- | --- |
| AC-1 | Every number in a lineup brief (the memo and "what would change this") must appear in that run's analysis: a tool output, a saved projection, the week or the season. A number written at lower precision traces if the computed value rounds to it ("23.1" from 23.09) | invariant I-25; glossary *Brief* |
| AC-2 | Every number is checked, not a headline one: one untraced number among many withholds the brief | invariant I-25 |
| AC-3 | The same holds for each trade's rationale and each counterparty pitch, checked separately: an untraced number withholds that text only | invariant I-27 |
| AC-4 | A withheld text is replaced by a notice naming the untraced numbers; the original is kept on the record for audit and not shown | outcome |
| AC-5 | Withholding a brief never changes the recommendation itself — the starters or the trade packages | outcome |
| AC-6 | The check makes no model call and never triggers a regeneration | NFR-04 |

## Acceptance signal

- Across a season, every brief the manager read is a restatement of numbers
  they could find in the analysis — and any brief that was not shows up as
  withheld rather than slipping through.

## Out of scope

- Templating the prose (H-08's other option).
- Checking claims that are not numbers.
- Changing the waiver brief's check — it already enforces I-26 (tested by WADD-09).

## Carried context

| | |
| --- | --- |
| **Bounded contexts** | Lineup Execution, Trade Execution (their briefs); Waiver Execution (already checked) |
| **Aggregates touched** | LineupAnalysis, TradeAnalysis — brief text only |
| **Invariants at risk** | I-25, I-26, I-27 — a brief may rephrase a number, never introduce one |
| **Contracts** | None external |
| **NFRs that apply** | At most 3 LLM calls per run (NFR-04) |
| **Depends on** | Nothing |

## Interface impact

**Does this slice touch a user interface?** No new screens. A withheld brief
renders through the existing memo, rationale and pitch fields as its notice.

## Open questions

| # | Question | Owner | Blocking? |
| --- | --- | --- | --- |
| H-08 | Template or check? **Resolved: check after generation** — it keeps the prose natural, matches the waiver brief, and costs no model call | — | No |
