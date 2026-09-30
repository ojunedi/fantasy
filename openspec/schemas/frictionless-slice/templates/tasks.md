# Tasks — <slice-id>

<!--
Checkbox format is parsed. `- [ ] N.M description` or it is not tracked.
Write the test task before the implementation task it covers.
Every scenario in specs/**/*.md appears by its id in at least one task.
Derive component tasks from the Components table in design.md — one task per
CREATE, one per non-trivial MODIFY, one per REMOVE.

TESTS ARE NAMED AFTER THE SCENARIO, AND ANNOTATED CLAUSE BY CLAUSE:

  it('INVSUB-02: submitting an empty invoice is rejected', async () => {
    const result = await submit(emptyDraft);

    // INVSUB-02 THEN the request is rejected with INVOICE_EMPTY
    expect(result.status).toBe(422);
    expect(result.body.code).toBe('INVOICE_EMPTY');

    // INVSUB-02 AND the Invoice remains in Draft
    expect(await invoices.get(emptyDraft.id)).toHaveProperty('state', 'Draft');

    // INVSUB-02 AND no event is published
    expect(await published(emptyDraft.id)).toHaveLength(0);
  });

One comment per THEN/AND clause of the scenario, sitting directly above the
assertion that proves it. Write them as you write the test, not afterwards —
the point is to notice the clause you have no assertion for while you can still
add one cheaply.

A comment is a CLAIM, not evidence. Never write one above an assertion that
does not actually prove that clause; a false claim here is worse than no
comment, because it survives review looking like coverage.

If a clause genuinely cannot be asserted, it does not get a comment. Say so in
the waiver instead — an unclaimed clause is a finding, and it is meant to be.
-->

## 1. Contracts and scaffolding

- [ ] 1.1 Update `contracts/billing/openapi.yaml` with the submit endpoint (BREAKING: no)
- [ ] 1.2 Add the `InvoiceSubmitted` event schema

## 2. Components

<!--
One task per CREATE component in design.md. Add MODIFY tasks for non-trivial
changes. A component in the diff that has no task here is a finding in the
code review.
-->

- [ ] 2.1 Create `InvoiceSubmitHandler` (API handler — new)
- [ ] 2.2 Modify `InvoiceDraftForm` — add submit action and error state

## 3. Domain

- [ ] 3.1 Write `INVSUB-02: submitting an empty invoice is rejected` (unit), one clause comment per THEN/AND — confirm it fails before implementation
- [ ] 3.2 Write `INVSUB-01: submitting a valid draft publishes InvoiceSubmitted` (integration), one clause comment per THEN/AND — confirm it fails before implementation
- [ ] 3.3 Implement `Invoice.submit()` enforcing invariants I-1 and I-3
- [ ] 3.4 Emit `InvoiceSubmitted` on the transaction boundary

## 4. API

- [ ] 4.1 Write `INVSUB-03: resubmitting is idempotent` (integration), one clause comment per THEN/AND — confirm it fails before implementation
- [ ] 4.2 Add `POST /invoices/{id}/submit`
- [ ] 4.3 Map domain errors to the error codes in the spec

## 5. E2E

<!--
One e2e test covering the acceptance signal from intent.md — not every
permutation, just the end-to-end proof that the slice works in a running
environment. Run against a deployed or locally started environment.

A `type: journey-e2e` slice whose journey the prototype covers adds one task
per registered flow — asserting the shipped screens and transitions match the
flow a human approved — plus a task running `prototype.mjs check`:

  - [ ] 5.2 Assert flow `submit-for-approval`: drafts list → draft → queued, with the
        validation-error exit (e2e, against the registered prototype flow)
  - [ ] 5.3 Run `prototype.mjs check` and resolve every CRITICAL
-->

- [ ] 5.1 Write `AC-SIGNAL: <acceptance signal from intent.md>` (e2e)
- [ ] 5.2 Run e2e suite against a running environment and record real output

## 6. Verification

- [ ] 6.1 Write `INVSUB-04: submit p99 under 300ms at 200 rps` (k6)
- [ ] 6.2 Run the full test suite and record real output — no "should work"
- [ ] 6.3 Run `node "${CLAUDE_PLUGIN_ROOT}/scripts/trace.mjs" check --phase delivery` and resolve every CRITICAL
- [ ] 6.4 Confirm each test would fail if its scenario were violated — not just that it passes

<!--
6.3 replaces a checkbox that used to be self-attested. "Every criterion maps to
a passing test" was tickable while a scenario had no test at all, because the
criterion had a row and the scenario was never counted. The script counts
scenarios, so the claim is now checked rather than asserted.

6.4 is the half no script can do. The script proves a test EXISTS for each
clause; only a human can say whether the assertion under a clause comment would
actually fail if that clause were violated.
-->

## 7. Code review

- [ ] 7.1 Run `/frictionless:slice-review` and resolve all CRITICAL findings before continuing
- [ ] 7.2 Accept or document any HIGH findings with a reason

<!--
7.1 checks: AC coverage, spec match, architecture alignment, contract fidelity,
scope. A CRITICAL finding blocks archiving. When 7.1 is clean, run
`/frictionless:build:ship` to archive, commit, and mark shipped.

For interface slices, add a UI group covering each state named in ux.md, and
a task for every element flagged NEW COMPONENT — it must also appear in the
Components table in design.md.

Every UI task names the library component and import path from design.md's UI
approach, and the prototype screen behind it where one exists:

  - [ ] N.1 Build the line item table with `DataTable` from `@acme/ui` (density="compact") — prototype `invoice-draft`
  - [ ] N.2 Render the permission-denied state — Submit hidden, not disabled — prototype `invoice-draft`

A UI task that does not name its component gets implemented from scratch, and
the registered design system is bypassed without anyone deciding to. One that
does not name its screen gets redesigned during implementation by whoever picks
it up.
-->
