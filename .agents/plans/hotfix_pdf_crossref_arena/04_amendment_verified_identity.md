# Amendment: Verified Identity Replaces Identity-Fallback Deletion

Date: 2026-08-03 | Agent Persona: system_synthesizer | Trigger: P3 evidence

## Evidence that invalidates the original locked decision

Two **existing contract tests** depend on the identity fallback and would be
weakened by outright deletion (a Stop Condition):

- `crossReferenceResolver.test.ts` "uses a nearby explicit page locator as the
  target for an otherwise unresolved section" — sync path, no labels/offset,
  `getPageText(281)` available, hint transfer to the section ref.
- `pdfReferenceContext.test.ts` "fetches a distant explicit page locator for an
  unresolved section pointer" — async path, `fetch(281)` expected, block must
  contain `target_page="281"`.

The defense §1 claim ("sync path never produced a snippet from the identity
page") was factually wrong: prior releases shipped this behavior deliberately
for header-less documents where printed = physical.

## Revised locked decision (F2, supersedes "delete identity fallback")

`explicitPageTarget` precedence becomes:

1. `printedToPdf` (pageLabels) — confidence 0.9 (unchanged)
2. `pageOffset` (new consensus inference) — 0.75 (unchanged)
3. **`printedHeaderToPdf` (new)** — scan already-known page texts for a page
   whose extracted printed header equals the requested printed number — 0.8
4. **Verified identity (revised)** — physical = printed, bounded by
   `pageCount`, **kept only while not contradicted**: if the identity page's
   text is available and its extracted printed-header candidates exist but do
   not include the requested number, the reference resolves as `unresolved`
   instead — 0.65 when kept
5. otherwise unresolved

Async additions:

- The single direct-fetch pass becomes a bounded **round loop (≤3 fetch
  rounds)**: fetch missing resolved targets → re-resolve → repeat.
- **Repair candidates**: when a fetched identity page contradicts (header `H`
  on physical `P`), the next round probes `P + (P − H)` once; the result is
  accepted only via rule 3 (header verification), never blindly.
- Round-loop consequence for the user's case: window headers give offset 18 →
  physical 599 fetched directly; physical 581 is **never** fetched.
- Header-less-window consequence: identity probe fetch(581) → contradiction
  (header 563) → repair fetch(599) → header-scan verifies → correct content.
- No-header documents (both existing contract tests): identity fetch returns
  text without extractable header → no contradiction → behavior unchanged.

Consensus rule for `inferPrintedPageOffset` is unchanged (≥2 supporting pages,
strict majority, ties fail closed); the repair path never feeds it more than
real page text.

All other locked decisions stand. Both pre-existing contract tests must remain
green **unmodified**.
