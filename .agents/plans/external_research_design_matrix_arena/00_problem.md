# Problem Definition: External Research Design Matrix

Date: 2026-06-11
Status: DRAFT — planning and comparative research only; no production implementation

## 1. Program Position

This Arena defines the Program-1 external primary-source research and comparative
spike process required by
`.agents/plans/03_rag_knowledge_quality_stabilization.md`.

It is not a product implementation plan. Its output is a defensible decision
package that tells later Program-1 specification work which techniques to adopt
as contracts, which to benchmark further, and which to reject.

## 2. Objective

Determine which external RAG, graph-memory, retrieval-evaluation, and
context-management techniques can address reproduced Incurator failures without
weakening source provenance, deterministic rebuilds, factual retrieval, bounded
cost, or update behavior.

Every decision must connect:

```text
reproduced Incurator failure
  -> falsifiable hypothesis
  -> primary-source claim
  -> disposable comparative spike
  -> frozen measurement
  -> adopt | benchmark | reject decision
  -> downstream specification requirement
```

## 3. Current Repository Reality To Preserve

- `state.sqlite` is authoritative; `.curator/Collections/` is derived.
- Search is DB-native FTS5/BM25 + chunk vectors + RRF + optional reranking.
- L1-L4 source and generated records already exist and carry provenance fields.
- The current system has verified failures around dropped search provenance,
  disconnected query traces, unbounded routes, fixed character budgets, broad
  support fallback, compiler idempotency, graph quality, and cross-client parity.
- Program 2 owns compiler changes. Program 3 owns ContextService and retrieval
  serving implementation. This research program may measure and specify them but
  may not implement them.

## 4. Questions The Research Must Answer

1. Which techniques improve the exact failing query/task families rather than
   only aggregate benchmark scores?
2. Which gains survive source edits, deletes, incremental rebuilds, and a
   personal-vault scale/cost envelope?
3. Which techniques preserve exact claim-to-source evidence and auditable route
   decisions?
4. Which techniques complement the current hybrid baseline, and which require a
   replacement architecture that should be rejected?
5. Which techniques are mature enough to adopt as a contract now, require a
   later benchmark behind an experiment flag, or should be rejected as defaults?

## 5. Required Candidate Families

- Context-enriched chunks.
- Passage/entity graph retrieval and Personalized PageRank.
- Hierarchical community construction and query-relevant community selection.
- Graph-guided chunk expansion and organization.
- Retrieval sufficiency/corrective gates.
- Complexity-aware routing.
- Bounded iterative retrieval.
- Progressive context disclosure and virtual-context management.
- Retrieval, citation, and claim-support evaluation methods.
- Selective formula recovery only where parser loss is measured.

Additional candidates may enter only when tied to a reproduced failure and a
primary source.

## 6. Non-Goals

- No production code, schema migration, dependency addition, or provider change.
- No wholesale framework adoption.
- No benchmark built only from public datasets or model-judge scores.
- No tuning of production RRF/reranker weights.
- No web fallback presented as vault evidence.
- No adoption based on popularity, paper headline results, or architectural
  similarity alone.

## 7. Completion Criteria

The work is complete only when:

- every candidate has a primary-source dossier and verified claim boundary;
- every comparative spike has a frozen fixture, baseline, metrics, cost/latency
  record, and reproducible command;
- every decision is `adopt`, `benchmark`, or `reject`, with explicit rationale;
- every adopted or benchmarked technique maps to a downstream Program-1, 2, or 3
  specification requirement;
- no production behavior has changed;
- the decision package passes red-team review for provenance, benchmark leakage,
  cost blindness, and framework bias.
