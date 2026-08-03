# Critique on [Resolver Hotfix Proposal F1–F3]

Date: 2026-08-03 | Agent Persona: red_teamer

## 1. Vulnerabilities & Flaws

1. **Identity-fallback removal is a silent regression vector.** Today,
   papers/reports with no front matter resolve `p.5` correctly via the 0.65
   fallback. If those PDFs carry no printed headers (common for arXiv text
   layers), inference returns `undefined` and the reference silently vanishes
   from context. The proposal's probe mitigates this ONLY in the async path;
   the sync path (`resolveSelectionReferences`, used for chat pinned refs and
   quick-query fallback) loses the behavior outright.
2. **Offset inference poisoning.** Chapter-opening pages put a bare chapter
   number ("9") at line start; running headers ("9 Epipolar Geometry …") do the
   same; TOC/index pages are full of trailing numbers. A window landing on such
   pages could form a *wrong* consensus (e.g. delta 267). Majority-of-pages is
   not enough if the window is 1–2 pages.
3. **Tie deltas.** Two pages voting 18 and two voting 0 → "modal" is ambiguous.
   Picking arbitrarily injects a 50%-wrong page.
4. **`[A-Z]?` over-capture.** "Result And…" / "results in 2015 the field…" —
   must prove the capture still requires a digit and cannot swallow prose
   words or years any worse than the current pattern.
5. **Appendix alias collision.** `"Appendix 4" → ["4","A4"]` makes a
   `Chapter 4` lookup potentially land on Appendix 4.
6. **Caption RE prose false positives.** "Results 3 and 4 show…" now indexes
   theorem "3"; a bare-anchor lookup for "Result 3" could pin a prose page.
7. **Mismatch filter self-harm.** A fetched target page whose header number is
   OCR-garbled ("58l") or absent must not cause a correct resolution to be
   dropped.

## 2. Suggested Alternatives

1. Accept sync-path loss ONLY because the sync path already could not produce
   a snippet for out-of-window pages (identity page text was never in the
   window map → reference was already omitted by the `snippet||sectionTitle`
   filter). Document this equivalence in the plan; it makes the sync change a
   no-op in practice, not a regression.
2. Require the modal delta to hold a **strict majority of ALL pages that
   yielded any candidate, with ≥2 supporting pages**; on any tie return
   `undefined`. Never infer from a single page.
3. Same as (2) — ties fail closed.
4. Add extraction unit tests for "Result And", "results in 2015" (year is
   captured by the *old* pattern too — assert no worse), "Result A4.1",
   "Corollary B2.3".
5. Keep alias additive and rely on document-order `find` (chapter 4 precedes
   appendix 4 in every real outline); add a regression test asserting a "4"
   lookup with both entries present returns the chapter entry.
6. Pre-existing risk class (identical to "Theorems 2 and 3 imply…" today);
   bounded by nearest-to-current-page selection in `findCaptionEntry`. Ship,
   but assert the definition-line form ("Result A4.1. A general …") indexes
   and the mid-sentence form at line start is tolerated.
7. Mismatch filter must fire **only** when a printed number is confidently
   extractable (both lookaround guards) AND differs from the expected printed
   page; absent/garbled header → keep the resolution (consensus mapping
   already vouches for it).
