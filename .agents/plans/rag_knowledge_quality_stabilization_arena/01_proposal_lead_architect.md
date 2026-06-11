# Lead Architect Proposal: Quality-Gated Three-Release Stabilization

Date: 2026-06-11 | Agent Persona: lead_architect

> **Superseded sequencing notice:** This proposal remains as the first-pass
> component analysis. Its `retrieval / math / graph+quota` release split was
> rejected after the vault-as-codebase reframing because later compiler changes
> would invalidate earlier retrieval baselines. The active sequence is defined
> in `04_reframing_vault_as_codebase.md` and
> `../03_rag_knowledge_quality_stabilization.md`: Truth Contract & Quality
> Observatory → Evidence Compiler Integrity → Agentic Query Serving &
> Sensemaking. Quota is outside the core stabilization program.

## 1. Core Logic & Implementation

### Release A: Treat retrieval quality as a measured contract

Create a versioned evaluation corpus in `tests/scenarios/` containing:

- exact lexical queries, Korean/CJK queries, paraphrase queries, math queries,
  graph/global queries, and block-reference navigation cases;
- expected source ids/span ids and acceptable top-k sets;
- negative controls that must not rank above the expected evidence;
- deterministic provider-free tests plus optional live Qwen3 embed/rerank runs.

Add an evaluator that reports Recall@k, MRR, nDCG@k, provenance coverage, broken
answer-link count, and degraded-stage warnings from `QTR-*` traces. Retrieval
weight changes are accepted only when they improve the frozen corpus without
regressing any hard case.

Provenance becomes a single contract:

```text
source_span
  -> knowledge_unit.source_span_ids
  -> graph entity/relation/report source_span_ids
  -> synthesis source_span_ids
  -> search_document provenance
  -> search_chunk provenance
  -> EngineHit / QTR / answer evidence
  -> resolvable source locator
```

Add a source locator representation for vault Markdown anchors while keeping
`source_span_ids` authoritative:

```json
{
  "relpath": "03_Notes/example.md",
  "heading": "Optional heading",
  "block_id": "optional-block-id",
  "page_number": null
}
```

The plugin renders/open links from this structured locator instead of guessing a
path from display text.

### Release B: Recover math only where loss is proven

Instrument the PDF parser output to classify formula regions as:

- preserved text/LaTeX;
- fragmented glyph text;
- image-only/undetected;
- uncertain.

Do not replace the parser. Keep `pymupdf4llm`/current text extraction as the fast
base path. Send only uncertain formula crops to a configured vision-capable model,
then store recovered LaTeX with page/bounding-box provenance and confidence.

Strengthen L2/L3 prompt contracts and validators:

- formula-bearing source spans must produce either a preserved formula-bearing
  unit or an explicit `formula_not_promoted` reason;
- extracted formulas must cite allowed source spans;
- no formula may be invented solely from model prior knowledge;
- chunking must not split display-math blocks.

### Release C: Improve graph quality without destructive auto-merges

Entity resolution is two-stage:

1. deterministic canonicalization and alias candidate generation;
2. embedding/LLM-assisted decision producing an auditable merge proposal.

Automatic merge is permitted only above strict thresholds with compatible entity
types and no contradiction. Ambiguous proposals remain reviewable aliases.
Relation insertion applies normalized endpoint ids, exact duplicate collapse,
confidence aggregation, and per-source support counts.

Replace connected-components-only global grouping with hierarchical community
detection behind a deterministic adapter. Leiden is preferred when available;
connected components remains the explicit degraded fallback.

Quota is a policy and observability layer, not deletion:

- default logical vault quota: 200 GB, configurable during `wiki init`;
- count authoritative, derived, cache, asset, and external-reference bytes
  separately;
- warn at thresholds; block only operations that would exceed a hard limit;
- never count external Reference Mode files as managed vault bytes;
- reclaim suggestions target disposable projections/caches first.

## 2. Pros & Cons

### Pros

- Quality changes are measurable before tuning begins.
- Selective VLM use controls cost and avoids replacing a working text parser.
- Provenance and answer-link fixes benefit every later phase.
- Graph merge decisions remain reversible and auditable.
- Quota cannot silently destroy source or durable knowledge.

### Cons

- Release A delays visible ranking tweaks while the evaluation harness is built.
- Formula recovery quality depends on available VLM capability.
- Alias/merge proposal storage likely requires an additive schema migration.
- Leiden introduces an optional dependency or requires a small internal adapter.
