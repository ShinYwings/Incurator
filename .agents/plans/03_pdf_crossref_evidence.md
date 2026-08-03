# v0.40.3 Evidence Ledger — PDF Cross-Reference Resolution Hotfix

Date: 2026-08-03

## Rollback Anchor

- Branch: `hotfix/v0.40.3-pdf-crossref-resolution` (from `master`)
- Anchor commit: `365934c9e18efd5ac9bf219c8cbacfcda9f7dc91`
  (`chore(agents): reset master state to IDLE after v0.40.2`)
- Rollback: `git checkout master` + delete branch; no DB/schema surface touched.

## Current Dirty Worktree (pre-plan)

- `.agents/RELAY.md` (modified — Rev 2 relay state)
- `.agents/ROADMAP.md` (modified — Active Queue item #0, pre-existing)
- `.agents/drafts/hotfix_pdf_cross_reference_resolution.md` (untracked —
  Rev 2 briefing; replaced by this plan set per draft→plan pipeline)
- No production code modified before P3.

## Current Repository Reality (fact-checked 2026-08-03)

- Versions agree at `0.40.2` (`backend/pyproject.toml:3`,
  `plugin/package.json:3`, `plugin/manifest.json:4`).
- Theorem pattern digit-only capture: `plugin/src/context/crossReferenceResolver.ts:182`.
- Identity fallback: `crossReferenceResolver.ts:417-419`; `ctx.pageOffset` has
  zero producers (grep: only the type definition and its doc comment).
- `CAPTION_LINE_RE` keyword list: `crossReferenceResolver.ts:222-223`.
- Entry points: `quickQueryPopover.ts:472-496` (async),
  `quickQueryContext.ts:127-129` (sync fallback),
  `ChatSidebarView.ts:1496` (sync pinned refs) / `:1773` (async).
- `loadPageLabels` returns `null` without `/PageLabels`:
  `ExternalPdfView.ts:1459-1467`.
- Regex simulation on `"From Result A4.1-(p581)"`: current theorem pattern →
  `null`; `[A-Z]?` variant → `["Result A4.1"]`; page pattern → `["p581"]`;
  current `CAPTION_LINE_RE` on `"Result A4.1. A general …"` → `false`.

## Pre-Validation (P0 baseline)

- To record before P3: `npx vitest run -c ./plugin/vitest.config.ts` on
  `crossReferenceResolver.test.ts` + `pdfReferenceContext.test.ts` (expected
  green at anchor).

## Post-Validation (P5 gate)

- Full plugin vitest green; `scripts/backend-check pytest|ruff|mypy` green;
  three manifests at `0.40.3`; CHANGELOG `### Fixed` entry present.
