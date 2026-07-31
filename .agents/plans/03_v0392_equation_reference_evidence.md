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
