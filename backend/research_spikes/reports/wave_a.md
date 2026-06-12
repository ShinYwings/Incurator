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
  remain unmeasured.
- The deterministic token-hash vector control is only a control. It is not
  evidence about the configured production embedder.

## Scoped Decision Posture

### Context-Enriched Chunks

`benchmark-later`.

Wave A supports a downstream contract candidate: generated retrieval context
must remain visibly non-authoritative, preserve exact raw-span linkage, beat a
deterministic heading control, and pass direct-factual non-regression. It does
not support production implementation or framework adoption because the corpus
is small, synthetic, provider-free, and the holdout remains untouched.

### Fine-Grained RAG Diagnostics

`adopt-contract` candidate, pending final P7 holdout/provenance audit.

Per-family retrieval, top-ranked citation correctness/completeness, provenance
resolution, hard-negative outranks, and cost must remain separate. Aggregate
Recall@5 and model-judge-only gates are rejected defaults.

## Rejected Defaults

- Generated context treated as source evidence.
- Contextualization accepted without beating deterministic heading context.
- Aggregate-only retrieval reporting.
- Model-judge-only release gates.
- Vector-control results generalized to the production embedder.

## Revisit Triggers

- Run the same contract against realistic source-scoped fixtures and a guarded
  production-scale copy.
- Measure source-edit invalidation and contextualization cache cost.
- Run the untouched holdout once at P7 under frozen configurations.
