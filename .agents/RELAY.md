# RELAY — ACTIVE

## Goal

Ship v0.39.0 by closing canonical Failure Atlas F9: compile exact authored
Markdown wikilinks, embeds, tags, and frontmatter references into deterministic
graph topology without treating them as LLM-extracted factual support.

## Plan Reference

- Master: `.agents/plans/02_authored_note_topology.md`
- Evidence: `.agents/plans/02_authored_note_topology_evidence.md`
- Arena: `.agents/plans/authored_note_topology_arena/`
- Domains: `.agents/plans/A_authored_reference_extraction.md`,
  `.agents/plans/B_authored_graph_lifecycle.md`

## Analysis & Reasoning

- Branch `release/v0.39.0` starts from clean `master` rollback anchor
  `f7f0b08`; v0.38.0 shipped in PR #100.
- Schema v13 already contains the required authored/extracted, lifecycle,
  topology-weight, generation, and source-span fields; no migration is planned.
- The canonical F9 strict xfail does not invoke the real compiler. Tests must be
  re-pinned before implementation.
- Authored structure may shape graph topology, but factual report relation ids,
  citations, and independent-lineage support remain extracted-only.
- F9-created note/asset/tag entities and authored relations require stable
  portable ids so independent replicas converge under existing DB sync.
- Authored extraction is staged in memory and reconciled inside the successful
  compiler publish transaction. Failed compilation preserves prior topology.
- Ordinary explore traversal must become active-only; diagnostic materialization
  may retain labeled non-active rows.

## Progress Status

- P0 repository/schema/compiler/consumer/sync audit: complete.
- Official Obsidian syntax and read-only user-vault pattern measurement:
  complete.
- Arena, domain plans, master plan, and evidence ledger: approved.
- P1 docs/spec contract, v0.39 spec-line/manifests, and F9 identifier cleanup:
  complete. Spec/docs/atlas contract tests: 121 passed; Ruff: green.
- P2 production-boundary/parser/lifecycle/reconciliation/replica/consumer tests:
  authored. Red baseline is intentional: 6 failed, 2 passed, 1 xfailed before
  the non-vacuous replica assertion was added; failures are the missing
  `authored_topology` module and absent compiled rows. Ruff: green.
- Application logic: not started.
- Current phase: P3 deterministic extraction, identity, and persistence.

## Critical Context / Blockers

- If implementation demonstrates a schema migration is required, stop and
  revise the contract before coding the migration.
- Do not mutate the production vault or overwrite the active ResNet Dynamics
  testbed. Use an isolated temporary copy for F9 smoke validation.
- Do not broaden F9 into fuzzy resolution, general alias merging, plugin-specific
  citation grammar, or L1 span redesign.
- Later Plan C comments reuse “F9” for unrelated fallback/hierarchy behavior;
  relabel them during the docs-first phase.

## Immediate Next Action

Implement the focused authored-topology module and explicit-id graph upserts,
then integrate atomic production publication until the P2 contracts pass.
