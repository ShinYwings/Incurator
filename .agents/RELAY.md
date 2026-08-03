# RELAY — v0.40.3 HOTFIX IMPLEMENTED, PR PENDING MERGE

## Goal

[HOTFIX] PDF Cross-Reference Resolution & Ask AI Context Retrieval Fix (v0.40.3)

## Plan Reference

- Plan set was implemented and deleted per workflow Step 11; recover via
  `git show` on `.agents/plans/03_pdf_crossref_hotfix.md`,
  `03_pdf_crossref_evidence.md`, and `hotfix_pdf_crossref_arena/` in this
  branch's history.
- Branch: `hotfix/v0.40.3-pdf-crossref-resolution`

## Analysis And Reasoning

- Root causes (code-verified): RC1 theorem-family regex rejected
  letter-prefixed numbers (`Result A4.1`); RC2 printed→physical page mapping
  silently degraded to identity (no pageLabels, `ctx.pageOffset` never
  populated) and injected the wrong physical page as resolved; RC3 caption
  index lacked theorem-family keywords and appendix outline aliasing.
- Arena amendment 04: identity fallback NOT deleted (two pre-existing contract
  tests depend on it) — replaced with *verified identity* + printed-header
  scan + bounded ≤3-round repair fetching. All fail closed on contradiction.

## Progress Status

- Implemented in `plugin/src/context/crossReferenceResolver.ts` and
  `pdfReferenceContext.ts`; 17 new vitest specs incl. exact user repro
  (physical 276 / printed 258 / p581 → physical 599, never 581).
- Full plugin suite green (73 files / 797 tests). Backend ruff + mypy green.
- Docs updated: `PLUGIN_SCHEMA.md`, `PLUGIN_GUIDE.md`, `PLUGIN_GUIDE_KR.md`.
- Version 0.40.3 across all three manifests + CHANGELOG `### Fixed` entry.
- Deferred agentic PDF retrieval tools recorded as ROADMAP item 7.

## Critical Context / Blockers

- None. Patch keeps the 0.40 minor line, so spec titles are untouched
  (spec-sync test reads manifests directly).

## Immediate Next Action

Human: review and merge the GitHub PR for
`hotfix/v0.40.3-pdf-crossref-resolution`. After merge, the next agent session
performs the IDLE relay cleanup on `master` per the Feed-Forward Exception.
