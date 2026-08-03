# Defense & Revision: Resolver Hotfix (Consensus)

Date: 2026-08-03 | Agent Persona: lead_architect (accepting red_teamer terms)

All seven critique items are accepted; the design is revised as follows and
these terms are **locked** for the Master Plan:

1. **Sync-path equivalence (accepted, documented)**: in the sync path the
   identity fallback never produced a snippet for out-of-window pages, so
   `buildResolvedReferencesBlock`'s `snippet || sectionTitle` filter already
   dropped those references. Removing the fallback changes no sync-path
   output. The async identity probe fully covers the one surface where the
   fallback ever mattered.
2. **Consensus rule (locked)**: modal delta must have ≥ 2 supporting pages AND
   a strict majority over all pages that produced any candidate; any tie for
   the mode → `undefined`. A single-page window can never produce an offset.
3. Ties fail closed — same rule as (2).
4. **Extraction tests (locked)**: "Result And…" must not match (capture
   requires a digit after the optional letter); "results in 2015" year-capture
   parity with the old pattern is asserted (no new false positive class);
   "Result A4.1", "Corollary B2.3", "Definition 3.1" must match.
5. **Alias order test (locked)**: with both "4 Chapter" and "Appendix 4"
   outline entries, a "4" lookup returns the chapter (document order);
   an "A4" lookup returns the appendix.
6. Caption prose false positives accepted as pre-existing class; tests cover
   the definition-line form.
7. **Mismatch filter (locked)**: fires only on a confidently extracted,
   contradicting printed number; absent/ambiguous headers keep the resolution.

No unresolved objections. Proceed to Master Plan synthesis.
