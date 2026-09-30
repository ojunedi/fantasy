# Working agreement

How to work with me on this project. The protocol below arrived with the
frictionless SDLC; everything under it is ours to write.

<!-- >>> frictionless working protocol (managed) -->
<!-- Managed by the frictionless plugin; restore with `/frictionless:doctor fix`.
     Add your own notes OUTSIDE this block — those are never touched. -->

## Working protocol

**Say the thing, not its id.** The model behind this project is full of stable
ids — `CON-11`, `S-123`, `AGG-quote`, `NFR-03`. They are addresses, not names,
and nobody holds them in their head. A sentence like "CON-11 conflicts with
S-123, so S-004 is invalid" asks me to open three files before I can tell
whether I disagree. In conversation I will not do that. I will nod, and a nod
is not agreement.

Say what the thing actually is. Put the id in parentheses, once, at the end, so
it can be looked up.

| Instead of | Say |
| --- | --- |
| "CON-11 conflicts with S-123" | "The seven-year audit retention rule collides with the first slice, which deletes its records after 30 days *(CON-11, S-123)*" |
| "AC-4 has no coverage row" | "Nothing tests what happens when a rejected quote is resubmitted *(AC-4)*" |

**The test:** read the sentence aloud with every id removed. If it still makes
sense, it is fine. If it leaves a hole, the id was carrying meaning it should
not have been.

**Don't narrate the plumbing either.** Script names, column names, internal
step names, file paths, rule numbers — these leak the same way and read worse,
because a script name dropped into a sentence implies the answer is in a file I
have not got. "Three things in the model don't line up" beats "`model.mjs
validate` reports 3 errors". Say what you found, and say you checked.

**Except when I am the one who has to act on it.** A command to type, a file to
open, a path a tool printed at me — name those exactly, in a code block. The
rule is about narrating your own plumbing, never about withholding something I
need.

**Ids and numbers stay in the model itself.** Tables, specs, contracts, and
generated documents keep every one of them — there the id *is* the reference,
and traceability is the point. This is about how prose reads, never about
dropping data.

**Edit the file; git is the history.** No "Correction:" blocks, no dated
"Update:" sections, no superseded row left in place with a note underneath.
When a decision changes, edit the decision. Someone who reads the top of an
amended file and stops has read a lie.
<!-- <<< frictionless working protocol (8c7fb263d46b) -->

## Project notes

<!-- Conventions, gotchas, commands worth knowing, decisions that keep coming
     back up. Add them here as they come up — this section is meant to grow. -->
