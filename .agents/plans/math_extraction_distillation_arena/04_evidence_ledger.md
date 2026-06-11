# Planning Evidence Ledger: Math Extraction And Distillation

Date: 2026-06-11
Status: PLANNING SNAPSHOT — refresh immediately before implementation

## Repository And Worktree Reality

- Inspected SHA: `12cc63ec3c43cfdf2049215f314876842b079f2d`
- Inspected branch: `feature/editor-latex-copy`
- Version files currently agree on `0.5.4`.
- The worktree contains pre-existing shared/unrelated changes. This planning
  task modifies only its owned plan paths.
- No implementation branch, schema, tests, specs, guides, ROADMAP, RELAY, or
  umbrella plan was changed.

## Verified Compiler Reality

- `source_spans` deduplicates by `(source_id, content_hash)` and stores a
  200-character preview plus optional metadata.
- L1 preserves explicit `$$...$$` blocks when they exist in parsed text.
- L2 validates that cited span ids are real/allowed, but not that they minimally
  support the claim.
- L2 creates new `KNU-` ids by default and lacks source-level stale-unit
  reconciliation.
- `compile_source_l2()` performs multiple persistent writes before all stages
  succeed.
- Graph extraction can truncate oversized statements.
- Report and synthesis generation can substitute broad upstream span sets when
  item-level citations are absent.
- Existing deterministic tests cover valid ids, no partial unit write for one
  failed prompt, math-block chunk boundaries, and connected-component reports;
  they do not cover claim entailment, source-level atomicity, or reconciliation.

## Authoritative Inputs

- `.agents/plans/03_rag_knowledge_quality_stabilization.md`
- Umbrella math/source-pair/schema/red-team/consensus/failure-atlas inputs.
- `docs/specs/curator_schema/SCHEMA.md`
- `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md`
- `docs/specs/search_engine/SEARCH_ENGINE_SCHEMA.md`
- Current compiler modules and `tests/scenarios/complex_math_backprop`.

## Rollback Anchor Requirements

Immediately before implementation:

1. Start from merged Program 1 `master` on a fresh Program-2 branch.
2. Record exact git SHA, schema version, provider/model identities, active
   scenario, and baseline audit metrics.
3. Back up `state.sqlite` and verify restore.
4. Rehearse additive migration on a disposable copy.
5. Preserve a clean-rebuild path from source truth.
6. Stage compiler generations so a failed publish can discard the new
   generation without mutating the prior authoritative generation.

## Evidence Gaps Program 1 Must Close

- Exact formula-loss distribution across representative Markdown/PDF/Reference
  Mode sources.
- Human-labeled minimal support and formula-centrality gold set.
- Current duplicate/stale rate after unchanged rebuild and edit/delete/split.
- Exact downstream dependency closure and current orphan rate.
- Whether recovery candidates require a normalized table rather than metadata.
