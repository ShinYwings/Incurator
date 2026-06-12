# Plan E Wave A Report

Date: 2026-06-12
Status: Completed; awaiting PM review before Wave B

## Scope

Wave A compared raw chunks, deterministic heading context, and explicitly
labeled generated context on a frozen synthetic source-scoped/direct-factual
corpus. Each variant ran through lexical-only, deterministic vector-only, and
hybrid controls. No provider, model judge, production state, or holdout was
used.

## Results

| Variant | Mode | Source-scoped Recall@1 | Direct-factual Recall@1 | Mean top-1 citation correctness | Hard-negative outranks | Indexed chars |
|---|---:|---:|---:|---:|---:|---:|
| raw | lexical | 0.00 | 1.00 | 0.50 | 0 | 334 |
| raw | vector | 0.50 | 1.00 | 0.75 | 1 | 334 |
| raw | hybrid | 0.50 | 1.00 | 0.75 | 1 | 334 |
| heading | lexical | 0.00 | 1.00 | 0.50 | 0 | 436 |
| heading | vector | 0.50 | 1.00 | 0.75 | 1 | 436 |
| heading | hybrid | 0.50 | 1.00 | 0.75 | 1 | 436 |
| generated context | lexical | 1.00 | 1.00 | 1.00 | 0 | 753 |
| generated context | vector | 1.00 | 1.00 | 1.00 | 0 | 753 |
| generated context | hybrid | 1.00 | 1.00 | 1.00 | 0 | 753 |

All returned hits in all variants/modes retained resolvable source-span ids.
The untouched holdout was not measured.

## Interpretation

- The contextual prefix isolated the source identity that raw chunks and generic
  headings lacked. It beat the simplest plausible heading control in every
  retrieval mode without direct-factual regression.
- Fine-grained citation correctness exposed the wrong top-ranked source in raw
  and heading modes even when Recall@5 would look successful.
- Context increased indexed characters by 125% versus raw chunks. Update cost,
  generated-context quality, provider variance, and realistic-scale behavior
  remain unmeasured. The benchmark-later posture therefore records the
  cache/invalidation assumptions the later benchmark must validate:
  - Cache granularity: one generated-context entry per source chunk, keyed by
    the chunk's source-span content hash plus the contextualization
    prompt/model version. No coarser (whole-document) cache key is assumed.
  - Source-edit trigger: any edit that changes a chunk's content hash
    invalidates that chunk's cached context; sibling chunks of the same source
    are re-queued for re-contextualization because document-level context may
    have shifted, even if their own hashes are unchanged.
  - Deletion trigger: deleting or archiving a source invalidates every cached
    context derived from it; generated context must never outlive the raw span
    it annotates.
  - Configuration trigger: changing the contextualization prompt or model
    version invalidates the entire cache (full re-contextualization). This
    full-rebuild path is the dominant cost the later benchmark must measure.
- The deterministic token-hash vector control is only a control. It is not
  evidence about the configured production embedder.

## Scoped Decision Posture

### Context-Enriched Chunks

`benchmark-later`.

- Downstream contract/spec owner: Program 2/3 (per the Plan E candidate
  matrix; recorded in the dossier as `downstream_owner: program-2`). Any
  future contract derived from this candidate lands in Program 2/3 specs, not
  in this research branch.
- Revisit trigger: rerun the identical frozen contract against realistic
  source-scoped fixtures and a guarded production-scale read-only copy, and
  measure source-edit invalidation plus contextualization cache cost under the
  assumptions recorded in the Interpretation section above. The candidate is
  re-evaluated only when both measurements exist.

Wave A supports a downstream contract candidate: generated retrieval context
must remain visibly non-authoritative, preserve exact raw-span linkage, beat a
deterministic heading control, and pass direct-factual non-regression. It does
not support production implementation or framework adoption because the corpus
is small, synthetic, provider-free, and the holdout remains untouched.

### Fine-Grained RAG Diagnostics

`adopt-contract` candidate, pending final P7 holdout/provenance audit.

- Downstream contract/spec owner: Program 1 (diagnostics/observatory release
  gates, per the Plan E candidate matrix; recorded in the dossier as
  `downstream_owner: plan-d2`).
- Revisit trigger: run the untouched holdout once at P7 under frozen
  configurations with a provenance audit. The contract is confirmed or
  withdrawn based on that single holdout measurement; no interim re-tuning is
  permitted.

Per-family retrieval, top-ranked citation correctness/completeness, provenance
resolution, hard-negative outranks, and cost must remain separate. Aggregate
Recall@5 and model-judge-only gates are rejected defaults.

## Rejected Defaults

- Generated context treated as source evidence.
- Contextualization accepted without beating deterministic heading context.
- Aggregate-only retrieval reporting.
- Model-judge-only release gates.
- Vector-control results generalized to the production embedder.

## Revisit Triggers (Consolidated Register)

Each trigger is owned inline by its candidate block above; this register is a
consolidated view, not the authoritative linkage.

- Context-Enriched Chunks: run the same contract against realistic
  source-scoped fixtures and a guarded production-scale copy.
- Context-Enriched Chunks: measure source-edit invalidation and
  contextualization cache cost.
- Fine-Grained RAG Diagnostics: run the untouched holdout once at P7 under
  frozen configurations.
