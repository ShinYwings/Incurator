# Planning Evidence Ledger: Graph Resolution And Hierarchy

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

## Verified Graph Reality

- Entity deduplication is exact `(canonical_name, entity_type)`.
- Entity upsert unions source spans/knowledge units but has no alias/proposal/
  redirect/reversal lifecycle.
- Relation upsert deduplicates endpoint/type triples but overwrites support
  fields rather than preserving independent support records.
- Graph extraction is batch-local and validates endpoint declaration plus allowed
  span ids, but not support correctness or cross-batch resolution.
- Community detection is connected components over all relations.
- Current community plans are level 0 only; the schema already has a level field.
- Community reports use entity/relation content dependency hashes but can use a
  broad community span fallback.
- Existing tests prove connected-component grouping and dependency-hash change,
  not homonym safety, support aggregation, hierarchy quality, or reconciliation.

## Authoritative Inputs

- `.agents/plans/03_rag_knowledge_quality_stabilization.md`
- Umbrella graph/schema/source-pair/red-team/consensus/failure-atlas inputs.
- `docs/specs/curator_schema/SCHEMA.md`
- `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md`
- `docs/specs/search_engine/SEARCH_ENGINE_SCHEMA.md`
- Current graph/community/report/synthesis/compiler modules.

## Rollback Anchor Requirements

Immediately before implementation:

1. Start from merged Plan B `master` on a fresh Program-2 branch.
2. Record exact git SHA, claim-generation contract, schema version, active
   scenario, algorithm dependency versions, seed/config, and baseline graph
   metrics.
3. Back up `state.sqlite` and verify restore.
4. Rehearse additive migration and clean graph/report rebuild on disposable DBs.
5. Preserve old entity/relation/report rows until the new graph audit passes.
6. Keep accepted merge/rewrite lineage sufficient for reversal.
7. Retain filtered connected components as an explicit runtime fallback.

## Evidence Gaps Program 1/B Must Close

- Gold synonym/homonym/abbreviation/multilingual resolution set.
- Current duplicate entity, false-merge, unsupported relation, and giant
  component rates.
- Independent-source lineage definition for repeated/copying notes.
- Frozen hierarchy benchmark and approved multi-metric thresholds.
- Published claim-generation identity and claim-support eligibility rules.
