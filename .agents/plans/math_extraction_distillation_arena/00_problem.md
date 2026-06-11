# Arena Briefing: Source-Pair, Math Extraction, And Claim-Level Distillation Integrity

Date: 2026-06-11
Program: Program 2 — Evidence Compiler Integrity
Status: PLANNING ONLY — no implementation authorized

## Problem Statement

Incurator must compile Markdown/PDF source truth into reusable L2 claims without
losing the exact source/claim pair. A real `source_span_id` proves that a span
exists; it does not prove that the generated claim is entailed by that span.
Today the compiler validates allowed span ids, but does not validate minimal
claim support, stable claim identity, formula centrality, or stale-record
reconciliation.

Math creates an additional failure surface. Formula loss may happen in the
parser, L1 span extraction, L2 distillation, graph prompt truncation, report
generation, synthesis, or search materialization. The architecture must locate
the actual loss boundary before adding expensive recovery. A recovered formula
must remain an evidence candidate with page/crop/model/confidence lineage; it
must never silently replace raw parser evidence.

## Verified Current Reality

- `pipeline/source_spans.py` preserves fenced code and `$$...$$` blocks, but
  parser output can already have lost or fragmented a PDF formula.
- `source_spans` stores only a 200-character preview in SQLite; full text is
  passed in-memory to L2 extraction.
- `pipeline/knowledge_units.py` subdivides oversized spans through
  `_chunk_text`, batches prompts, and accepts any real allowed span id.
- `upsert_knowledge_unit()` creates a new `KNU-` unless an explicit id is
  supplied. Rebuild identity and stale-unit reconciliation are not defined.
- `compile_source_l2()` persists spans, units, projections, dependencies, and
  graph output incrementally rather than as one source-level transaction.
- `graph_index.py` truncates oversized statements, which can remove a
  formula-bearing tail.
- Community reports and synthesis may fall back from item-level support to broad
  upstream span sets.
- `complex_math_backprop` contains useful math fixtures but stale EXH/qmd
  assumptions and is not a sufficient current compiler-integrity oracle.

## Required Outcomes

1. Every source-supported generated claim cites the smallest sufficient source
   evidence set and passes an entailment-oriented support validator.
2. Every formula-bearing claim records whether the formula was preserved,
   intentionally omitted as incidental, uncertain/recovered, or missing.
3. L1 raw evidence remains immutable; recovered formula candidates are additive.
4. Unchanged compilation is authoritative-record-idempotent.
5. Source edit/delete/split reconciles stale spans, units, projections,
   dependencies, graph inputs, reports, synthesis, and search-derived rows
   through the expected dependency closure.
6. A failed source compile leaves no partial authoritative compiler state.
7. The compiler audit can trace each L2-L4 claim to minimal support and report
   unsupported, broad-fallback, stale, or uncertain evidence.

## Scope

### In Scope

- Markdown/PDF source-pair diagnosis and exact loss-boundary classification.
- Source span evidence metadata needed for formula candidates and locators.
- Claim-level support contracts and validators.
- Stable semantic identity and reconciliation for L2 knowledge units.
- Selective formula recovery after measured parser loss.
- Centrality-aware formula retention through L2 and downstream compiler inputs.
- Removal of broad all-upstream-span grounding fallback from Plan-B-owned
  source-pair/L2 and non-graph generated claims; graph/report fallback is an
  explicit Plan-C handoff.
- Atomic source compile behavior and compiler audit coverage.

### Out Of Scope

- Entity alias/merge resolution, relation denoising, and hierarchical
  communities; those belong to Plan C.
- Query routing, retrieval tuning, context packing, or agent-serving changes;
  those belong to Program 3.
- Vault quota, storage bars, or admission control.
- Automatic edits to `03_Notes/`, `04_Resources/`, or `06_Archives/`.
- Running every PDF page through a VLM.

## Dependencies And Ordering

- Hard dependency: merged and approved Program 1 truth contract, evaluation
  specification, exact locator contract, and quality observatory.
- Plan B is the first Program-2 compiler-integrity release.
- Plan C may be planned independently but implementation starts only after B is
  merged because graph extraction consumes B's claim/support contracts.
- Program 3 starts only after B and C are merged.

## Debate Questions

1. What is the minimum schema needed to represent exact raw support, recovered
   formula candidates, support verdicts, and stable claim identity?
2. How can support validation catch wrong-but-real span citations without making
   a model judge the sole release gate?
3. Which compile operations must be transactionally staged together?
4. How should formula centrality be defined and tested without copying every
   equation into every claim?
5. Which existing records can be migrated in place, and which must be rebuilt?

## Success Definition

The Arena succeeds when it produces a locked, migration-safe, TDD-ready plan
whose tests can distinguish preserved evidence, unsupported claims, deliberate
omissions, parser loss, recovery uncertainty, stale records, duplicate records,
and partial compile failure.
