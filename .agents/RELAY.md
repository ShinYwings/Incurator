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
- Arena, domain plans, master plan, and evidence ledger: authored.
- Application code/spec/guide changes: not started.
- Current gate: user approval of the v0.39.0 plan.

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

Await user approval. Then execute P1 docs/spec contract updates, followed by P2
failing tests before application logic.
