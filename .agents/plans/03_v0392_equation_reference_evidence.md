# v0.39.2 Equation-Reference Evidence Ledger

Date: 2026-07-31

## Rollback Anchor

- Base: `bc61fab` (merged v0.39.1 / PR #102)
- Branch: `hotfix/v0.39.2-equation-reference-context`
- No schema or production-data mutation.

## Current Runtime Reality

- Installed and active plugin version: v0.39.1.
- Repository and installed `main.js` SHA-256 values match.
- Installed Antigravity CLI: 1.1.9.
- Live observed launch inserted `$read_file$()` before spawn and ran one `agy`
  process. Antigravity removed the transient rule on exit.
- Observed launch roots contained the vault only:
  `/Users/shin/shinywings/second_brain`.
- Active PDF lived under an external iCloud/Zotero path and was named in the
  prompt, but was not an `--add-dir` root.

## Reported Failure Baseline

- Latest request: `수식 (10)이 본문이랑 완전 다른데?`
- Supplied PDF body ended at equation (9) on page 5.
- Page 6 appeared only as a header-only related hit, not as target body text.
- Provider attempted `read_file` to locate equation (10) and returned the
  headless auto-denial notice.

## Required Post-Fix Evidence

- Failing test demonstrates the same page-5/page-6 gap.
- Target page 6 text containing equation (10) is fetched once and emitted in
  `<resolved_cross_references>`.
- Live replay returns a substantive answer with no `read_file` or `command`
  permission notice.
- Full validation results and commit hashes are appended before release.

## Approval And Handoff

- User approved preparing this hotfix for direct execution and explicitly asked
  to defer implementation until the next session because provider quota is low.
- The next agent should not repeat the live provider reproduction before coding.
  Start with docs-first contract edits and the failing plugin test, using the
  captured live evidence above as the baseline.

## Post-Fix Evidence — 2026-08-01

- The regression now mirrors the real extraction gap: page 5 contains equation
  (9), the loaded page-6 entry is header-only, and the refreshed page-6 body has
  an explicit `Eq. (10)` prose anchor while the equation image is omitted.
- The async resolver recognizes `수식 (10)`, refreshes page 6 exactly once
  through `getPdfContext(pageNum=6, radius=0, maxPages=1)`, and emits page 6 in
  `<resolved_cross_references>` before `<pdf_window>`.
- Focused plugin validation: 71 tests passed; TypeScript passed.
- Full plugin validation: 740 tests passed; production build passed.
- Full backend validation: Ruff passed, MyPy passed, and pytest reported 1373
  passed, 6 skipped, and 4 expected xfails.
- A disposable copy of the active testbed returned exactly the requested page
  for read-only untracked-PDF context with `radius=0`; production `second_brain`
  and the active `testbed/` were not mutated.
- The single isolated live Antigravity replay used the real Zotero attachment
  identity and resolved page-5/page-6 text. It completed successfully in one
  provider turn with a substantive Korean correction and no `read_file`,
  `command`, permission, or filesystem-access denial.
