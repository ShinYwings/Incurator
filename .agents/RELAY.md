# RELAY — HOTFIX DRAFT READY (REV 2, CODE-VERIFIED)

## Goal

[HOTFIX] PDF Cross-Reference Resolution & Ask AI Context Retrieval Fix

## Plan Reference

- Draft: `.agents/drafts/hotfix_pdf_cross_reference_resolution.md` (Revision 2)
- Target Branch: `hotfix/v0.40.3-pdf-crossref-resolution`

## Analysis And Reasoning

- User reported Ask AI failure on selection `"From Result A4.1-(p581)"` (physical
  page 276, printed 258 ⇒ offset +18): injected context was Appendix A1.1 tensor
  notation instead of Result A4.1.
- Revision 1 of the draft (Gemini) was speculative and wrong on layer and
  mechanism (blamed backend RAG / source_spans; resolution is entirely
  plugin-side and deterministic). Claude re-derived the root causes from the
  actual code and regex simulation:
  - **RC1**: theorem/result pattern at `crossReferenceResolver.ts:182` captures
    digits only — `Result A4.1` is never extracted.
  - **RC2**: no `/PageLabels` + `ctx.pageOffset` never populated ⇒
    `explicitPageTarget` identity fallback fetched **physical** 581
    (= printed 563 = Appendix A1) instead of physical 599 (= printed 581), then
    injected it as resolved (confidence 0.65) — poisoned context.
  - **RC3**: `CAPTION_LINE_RE` lacks `results?|corollar…|propositions?|definitions?|claims?|conjectures?`,
    so caption-index can never pin theorem-family definition lines.
- Hotfix scope (patch): fix regexes, add printed→physical offset inference from
  window-page headers, remove identity fallback (fail closed), post-fetch
  verification. Agentic multi-hop tools (Rev 1 Phases 3–4) explicitly deferred
  to a Minor release with its own Arena plan.

## Progress Status

- Draft Revision 2 authored with code-verified root causes, hotfix plan, TDD
  test list, docs list, and deferred follow-up section.
- ROADMAP Active Queue item #0 unchanged (still this hotfix).
- No implementation code written yet; no branch created yet.

## Critical Context / Blockers

- Version bump mandate applies (+0.0.1 → v0.40.3). `CHANGELOG.md` entry is
  `### Fixed` only; no spec-title line change (same minor line).
- All fixes are plugin-side (`crossReferenceResolver.ts`,
  `pdfReferenceContext.ts`); tests via `npx vitest run -c ./plugin/vitest.config.ts`.
- Do NOT re-route this through backend FTS/source_spans — Rev 1's approach,
  invalidated by code trace.

## Immediate Next Action

Executor must use draft Revision 2 as the Arena briefing, create
`hotfix/v0.40.3-pdf-crossref-resolution`, synthesize the `PLAN_TEMPLATE.md`
three-document set in `.agents/plans/`, and await user approval before coding.
