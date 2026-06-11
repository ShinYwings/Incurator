# Arena Briefing: Entity/Relation Resolution And Hierarchical Community Quality

Date: 2026-06-11
Program: Program 2 — Evidence Compiler Integrity
Status: PLANNING ONLY — no implementation authorized

## Problem Statement

Incurator's L3 graph must compile trusted L2 claims into a faithful,
incrementally maintainable semantic topology. The current graph is batch-local,
deduplicates entities only by exact `(canonical_name, entity_type)`, overwrites
duplicate relations rather than preserving independent support, and detects
communities as connected components. Synonyms fragment the graph, homonyms risk
false consolidation, noisy bridge relations create giant components, and report
quality can hide unsupported or stale graph inputs.

Graph algorithms cannot repair weak source claims. Plan C must consume the
minimal claim-support contract delivered by Plan B and preserve the authored vs
extracted topology distinction established by the umbrella program.

## Verified Current Reality

- `graph_index.py` extracts entities and relations per batch from knowledge units.
- Its in-memory endpoint map is keyed by canonical name within each batch.
- `upsert_graph_entity()` merges exact `(canonical_name, entity_type)` and unions
  spans/knowledge-unit ids.
- `upsert_graph_relation()` deduplicates exact endpoint/type triples but replaces
  description, assertion source, spans, and confidence instead of aggregating
  independent support.
- Relations validate endpoint existence and confidence range, but not independent
  support, self-loop policy, noisy bridge risk, or quarantine status.
- `detect_communities()` uses deterministic connected components over every
  relation; one weak bridge can create a giant component.
- `community_key` hashes leaf entity ids; reports have a `level` column but the
  current detector emits only level 0.
- Community report dependency hashes cover entity/relation content, but report
  fallback may use the whole community span pool.
- The current schema already distinguishes `source_states`, `system_infers`, and
  `workspace_derives`, and `curate.yml` contains `avoid_merges` safeguards.

## Required Outcomes

1. Entity resolution is reversible, auditable, homonym-safe, and defaults to
   alias/proposal rather than destructive merge.
2. Graph entities preserve all supporting claims/spans and retain stable identity
   through accepted aliases and source updates.
3. Relations aggregate independent claim-level support; unsupported/noisy edges
   are provisional or quarantined rather than treated as trusted topology.
4. Authored topology and extracted topology remain distinguishable and weighted
   by contract.
5. Community construction is deterministic, hierarchical where measured useful,
   seed-stable, provenance-complete, and resistant to unexplained giant
   components.
6. Community reports cite claim-level evidence and regenerate only when their
   exact graph/support dependencies change.
7. Graph rebuild/edit/delete reconciliation produces no orphan endpoints, stale
   aliases, stale relation support, stale reports, or duplicate amplification.

## Scope

### In Scope

- Entity normalization for candidate generation only.
- Alias records, merge proposals, strict accepted-merge lifecycle, and redirects.
- Homonym/contradiction/`avoid_merges` protection.
- Relation support aggregation, confidence policy, self-loop/duplicate/noisy-edge
  handling, and quarantine.
- Authored vs extracted topology contracts.
- Deterministic weighted hierarchical community benchmarking/implementation.
- Community report claim-level support and precise dependency invalidation.
- Graph audit, migration, reconciliation, and current testbed fixtures.

### Explicitly Excluded / Deferred

- Vault quota, storage meter UI, hard limits, admission control, or deletion.
- Retrieval routing, PPR, DRIFT, global query serving, or context packing.
- Math/source-pair/claim-support implementation owned by Plan B.
- Automatic similarity-only entity merge.
- Automatic edits to human source/reference spaces.

## Dependencies And Ordering

- Hard dependency: merged Program 1 truth/evaluation/observability contracts.
- Hard implementation dependency: merged Plan B claim-level support and
  reconciliation contracts.
- Plan C remains an independent Arena and release plan, but it cannot implement
  against broad or unchecked claim support.
- Program 3 starts only after C is merged.

## Debate Questions

1. Which alias/merge decisions are safe to automate, and which require proposals?
2. How should independent relation support affect confidence and topology weight?
3. How can authored links participate without becoming equivalent to inferred
   semantic relations?
4. Which hierarchy method wins against connected components on frozen graph
   fixtures, and what is the degraded fallback?
5. How are community/report identities kept stable enough for incremental
   invalidation without preserving obsolete topology?

## Success Definition

The Arena succeeds when it produces a migration-safe, TDD-ready plan that
prevents homonym false merges, preserves synonym discoverability, quarantines
unsupported/noisy edges, produces measured deterministic hierarchy, and proves
precise graph/report reconciliation. Quota must not appear in its implementation
phases or release gates.
