# Critique on lead_architect's proposal

Date: 2026-06-11 | Agent Persona: red_teamer (The Adversary)

## 1. Vulnerabilities & Flaws

**V1 — `keyup` on every keystroke is a hot path.** Registering `keyup` on the
document fires for ALL typing, including while the user composes a chat message
or edits a note. Even with the early `shiftKey`/Arrow guard, the handler runs on
every keyup. → Mitigation: the guard returns before any DOM work for non-matching
keys (cheap boolean checks), and `handleSelectionChange` only does work when a
non-empty selection exists. Acceptable, but ALSO: do not attach inside text
inputs needlessly — the guard already filters; keep it. Confirm the `setTimeout(0)`
doesn't pile up: each call schedules one microtask that no-ops on empty selection.
Fine. **Do NOT use `selectionchange`** (the proposal's rejected alternative) — it
fires on every caret move and would be far worse; keyup-gated is the right call.

**V2 — Shift+Arrow that SHRINKS a selection to empty must remove the button.**
If the user Shift+Arrows back to a caret, `handleSelectionChange` must hide the
button. It already calls `removeButton()` on empty text — verify that path is hit
(it is, lines 142-145). OK, but add a test/asserted reasoning so a refactor can't
regress it.

**V3 — Capture extractor must not change NON-math behavior.** `extractTextWithLatex`
inserts `\n` around block tags (p/div/li/...). For a plain multi-line selection
the OLD `toString()` and the NEW path could differ in whitespace, subtly changing
what gets sent to the LLM. → Mitigation: the helper already gates on
`frag.querySelector("mjx-container, span.math")` and returns raw `toString()` when
no math is present, so non-math selections are byte-identical to today. Keep that
gate exactly. Unit-test it.

**V4 — `cloneContents()` on a partial selection inside a single `mjx-container`.**
If the user drags from the middle of a formula, the cloned fragment may contain a
partial `mjx-container` without its `annotation` child, or an `annotation` with
the FULL formula (over-capturing). getLatexFromMathEl returns the full annotation
→ the captured text includes the whole formula even if only half was visually
selected. → Judgment: over-capturing the whole formula is the DESIRED behavior
here (a half-formula is useless to the LLM); document it as intended, not a bug.
But guard against a cloned `mjx-container` whose `annotation` is absent → it
should fall back to empty for that node (extractTextWithLatex already returns ""
for mjx-container with no annotation), not crash. Verify.

**V5 — Popout windows / PDF.** `selectionToTextWithLatex` uses
`selection.getRangeAt(0)` from whatever `doc` is passed; the keyup listener must
be registered per popout like `mouseup` is. The proposal does this. But PDF
selections (`pdfCapture.ts` / `externalPdfView.ts`) — does the popover capture run
there too? If PDF text layers have no `mjx-container`, the fast path returns
`toString()` (unchanged). No regression. Confirm PDF still uses its own capture
where applicable and the math gate simply never trips.

**V6 — `extractTextWithLatex` is currently NOT exported** (module-private,
used only by `attachLatexCopyHandler`). The new helper is in the same file so it
can call it directly without exporting it — keep `extractTextWithLatex` private,
export only `selectionToTextWithLatex`. Smaller API surface.

**V7 — Version classification.** This bundles a bug fix (symptom 1, hotfix-class)
with a new user-facing behavior (symptom 2, keyboard trigger). That tilts toward
a **minor** bump, but it is small. Flag for the user: patch `v0.5.1` (treat as a
fix bundle) vs minor `v0.6.0` (new keyboard-trigger behavior).

## 2. Suggested Alternatives (net)
- Keep `keyup`-gated trigger (reject `selectionchange`).
- Keep the math-gate fast path so non-math selections are byte-identical.
- Export only `selectionToTextWithLatex`; keep `extractTextWithLatex` private.
- Treat whole-formula over-capture as intended; guard missing-annotation nodes.
- Defer symptom 3 to Icebox. Ask the user the version question.
