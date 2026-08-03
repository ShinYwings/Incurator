# Briefing: PDF Cross-Reference Resolution Injects Wrong-Page Context

Date: 2026-08-03 | Author: Main Agent (Claude) | Source: user report + code-verified draft Rev 2

## Symptom

Selecting `"From Result A4.1-(p581)"` (physical page 276/673 of *Multiple View
Geometry*, printed header 258) and triggering Ask AI injects a
`<resolved_cross_references>` block containing **Appendix A1.1 tensor-notation
text** instead of Result A4.1. The LLM answers with a missing-context
disclaimer instead of explaining the referenced result.

## Verified Failure Trace (all plugin-side)

1. `extractReferences` — theorem/result pattern
   (`plugin/src/context/crossReferenceResolver.ts:182`) captures
   `(\d+(?:\.\d+)*)` (digits only) → `Result A4.1` is **never extracted**
   (regex-simulated: pattern returns `null`; only `p581` matches).
2. Sole reference `p.581` → `explicitPageTarget`
   (`crossReferenceResolver.ts:406-421`): no `/PageLabels` on this PDF
   (`ExternalPdfView.loadPageLabels` → `null`), `ctx.pageOffset` **never
   populated anywhere** → identity fallback: physical `targetPage = 581`,
   confidence 0.65.
3. Async wrapper (`pdfReferenceContext.ts`) fetches physical 581 = printed 563
   = Appendix A1 tensor notation. Correct target (printed 581) is physical 599.
4. `buildResolvedReferencesBlock` injects the wrong page as a resolved-looking
   reference → poisoned context → user-visible failure.
5. `resolveWithNearbyPageHints` — designed for exactly the `"Result X-(pN)"`
   shape — never fires because of (1), and would attach the wrong page because
   of (2).

## Root Causes

- **RC1**: theorem-family number capture rejects letter-prefixed identifiers
  (`A4.1`).
- **RC2**: printed→physical mapping silently degrades to identity when
  pageLabels are absent; no offset inference exists; wrong page passes the
  `usable` filter.
- **RC3**: `CAPTION_LINE_RE` lacks `results?|corollar…|propositions?|definitions?|claims?|conjectures?`
  → caption-index can never pin theorem-family definition lines.
  Secondary: outline titles like `"Appendix 4 …"` normalize to `"4"`, so
  object number `A4.1` (chapter `A4`) can never match its owning outline
  entry, blocking outline-expansion for bare anchors.

## Constraints

- Hotfix scope: **patch** (v0.40.3). Deterministic resolver fixes only.
- Agentic multi-hop retrieval tools (draft Rev 1 Phases 3–4) are **deferred**
  (Minor scope; recorded in draft Rev 2 §6, to be re-queued via USER_REPORT).
- Fail-closed principle: injecting nothing must always be preferred to
  injecting a plausible-but-wrong page.
- No backend changes; plugin `vitest` is the test surface.
