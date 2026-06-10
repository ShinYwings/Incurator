# Domain Specialist Validations + Architect Defense

Date: 2026-06-11 | Personas: schema_guardian, source_pair_analyst, lead_architect (defense)

## schema_guardian
- 100% plugin-side (TS): `utils/textUtils.ts` (one new exported helper),
  `ui/quickQueryPopover.ts` (2 capture call sites), `main.ts` (one `keyup`
  listener). No DB, no `state.sqlite`, no DAG, no spec schema, no version-stamped
  spec body changes. ✅ No schema risk, no migration.
- The captured text is ephemeral popover input (`capturedSelection`), not
  persisted to sessions or the vault. ✅

## source_pair_analyst
- No RAG/L1–L4/backprop impact. The captured selection becomes a quick-query LLM
  prompt (`buildQuickQueryMessages`), it does not enter ingestion. Preserving
  LaTeX only improves prompt fidelity. ✅
- The math-gate fast path keeps non-math selections byte-identical, so existing
  quick-query behavior/tests are unaffected. ✅

## lead_architect — Defense / Revisions accepted
- **V1**: keep `keyup`-gated; explicitly NOT `selectionchange`. Guard is cheap
  boolean checks before any DOM read.
- **V2**: rely on `handleSelectionChange`'s existing empty-selection →
  `removeButton()` path; assert it in reasoning + keep mouse path intact.
- **V3 / V6**: export ONLY `selectionToTextWithLatex`; keep `extractTextWithLatex`
  private; preserve the `mjx-container, span.math` gate so non-math = raw
  `toString()`. Unit-test both branches.
- **V4**: whole-formula over-capture on partial drag is INTENDED (documented);
  missing-annotation node already yields "" — no crash.
- **V5**: register `keyup` per popout like `mouseup`; PDF selections hit the fast
  path (no math) → unchanged.
- **V7**: surface the version choice to the user (patch vs minor).

## Consensus
Reuse `extractTextWithLatex` via a single exported `selectionToTextWithLatex`
(math-gated fast path), route both popover captures through it, add a
`keyup`-gated keyboard trigger per document/popout. Defer symptom 3 (partial
editor LaTeX copy) to Icebox. No schema/RAG impact. Proceed to Master Plan.
