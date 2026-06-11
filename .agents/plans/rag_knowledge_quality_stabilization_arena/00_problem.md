# Problem Definition: RAG & Knowledge Quality Stabilization

Date: 2026-06-11
Status: DRAFT — planning only; no implementation until user approval

## Planning Output Contract

This top-level Arena decides the shared product thesis, cross-component
dependencies, and three-batch sequence. Its synthesis is
`../03_rag_knowledge_quality_stabilization.md`.

Detailed implementation planning is delegated to six independent component
Arenas and Master Plans (`A-F`). This prevents one oversized debate from hiding
domain-specific trade-offs while keeping all six plans under one ordered
stabilization program.

## 1. Objective

Make Incurator's DB-native RAG and L1-L4 knowledge pipeline measurably reliable
for a real research vault. The system must preserve source evidence, retrieve the
right evidence, retain important mathematics, avoid graph fragmentation/noise,
and expose quality degradation before it becomes destructive.

## 2. Current Repository Reality

- `state.sqlite` is authoritative. `.curator/Collections/` is derived.
- Search is already DB-native: FTS5/BM25 + chunk vectors + RRF + configured
  reranking. `qmd` is retired and must not return.
- L1-L4 means source spans/Contexts → knowledge units/Atoms → graph
  entities/relations/community reports/Concepts → shared Synthesis.
- Static `EXH-*` artifacts and EXH reverse-parse backprop are retired.
- Existing provenance is centered on `source_span_ids`, but L2/L3 batching,
  projection, retrieval hydration, and answers need an end-to-end invariant test.
- Entity dedup currently matches exact `(canonical_name, entity_type)` only.
- Community detection currently uses connected components; a single noisy edge
  can collapse unrelated topics into one community.
- The existing `complex_math_backprop` scenario contains stale EXH-era assertions
  and cannot serve as the stabilization oracle without being rewritten.

## 3. User-Visible Failures To Eliminate

1. Relevant evidence is missed or ranked below generic/weakly related evidence.
2. Formula-bearing sources lose mathematical meaning during PDF extraction or
   L2/L3 distillation.
3. Generated knowledge cannot reliably trace back to the exact source span/page.
4. Synonyms and near-duplicates fragment entities; noisy edges distort global
   communities and synthesis.
5. Answer links are emitted but do not reliably open the source note, heading, or
   Obsidian block reference such as `[[Note#^block-id]]`.
6. External and Obsidian agents do not consume one bounded, verifiable prior-
   knowledge contract.

## 4. Non-Goals

- Do not reintroduce qmd.
- Do not restore static Exhibitions or mutate source truth.
- Do not apply LLM/embedding similarity merges without an auditable merge plan.
- Do not send every PDF page through a VLM.
- Do not silently delete knowledge to satisfy quota.
- Do not tune retrieval weights without a frozen evaluation corpus and metrics.

## 5. Required Three-Program Split

- **Program 1 — Truth Contract & Quality Observatory:** deeply diagnose the full
  RAG+DAG system, research external designs, freeze evaluation and truth
  contracts, write the target implementation specification, then implement the
  diagnostic/lineage substrate required to measure future changes.
- **Program 2 — Evidence Compiler Integrity:** make note/PDF → L1-L4 knowledge
  compilation faithful, deterministic, incremental, and claim-level grounded.
- **Program 3 — Agentic Query Serving & Sensemaking:** expose the trusted compiled
  prior knowledge through one bounded, progressive, freshness-aware context
  runtime for external and Obsidian agents.

Each program repeats focused research → approved implementation spec → TDD →
implementation → evaluation. Each is independently releasable and must pass full
local CI and its quality gates before the next program starts.
