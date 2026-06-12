# Plan E Wave B Report

Date: 2026-06-12
Status: Completed; awaiting PM review before Wave C

## Scope

Wave B compared current graph/explore/global controls with disposable,
deterministic graph mechanisms:

- current depth-2 memory-path scoring versus weighted Personalized PageRank;
- raw connected components versus confidence-denoised connected components;
- current all-report global loading versus query-relevant top-1 community
  selection;
- seed retrieval versus confidence-filtered bounded graph expansion.

The frozen graph stress corpus measured correctness and update/delete behavior.
An ignored, read-only production `state.sqlite` copy measured scale and current
graph-confidence reality. No provider, model judge, production mutation, or
holdout was used.

## Results

### Associative And Multi-Hop

| Case | Current memory-path recall | PPR recall | PPR forbidden rate | Filtered expansion recall | Expansion forbidden rate | PPR edge updates | Expansion traversed edges |
|---|---:|---:|---:|---:|---:|---:|---:|
| GQ01 residual → continuous depth | 1.00 | 1.00 | 0.00 | 1.00 | 0.00 | 660 | 4 |
| GQ03 bleaching → symbiotic algae | 1.00 | 1.00 | 0.25 | 1.00 | 0.00 | 660 | 4 |

Unfiltered weighted PPR did not improve recall over current memory paths and
ranked a noisy-bridge node in one of two cases. Confidence-filtered expansion
matched recall, exposed every seed/path/edge/provenance locator, and did not add
forbidden evidence.

### Direct-Factual Non-Regression

| Case | Lexical entity Recall@2 | Graph-expanded Recall@2 | Hard-negative outranks |
|---|---:|---:|---:|
| GQ05 Jaguar animal | 1.00 | 1.00 | 0 |
| GQ06 Jaguar car | 0.50 | 1.00 | 0 |

The graph relation from `Straight-six engine` repaired the exact-name Jaguar
homonym miss under a two-edge expansion budget without promoting the animal
hard negative.

### Hierarchy And Update/Delete Behavior

| Measurement | Raw connected components | Confidence-denoised components |
|---|---:|---:|
| Synthetic giant-component ratio | 0.714 | 0.300 |
| Production-copy giant-component ratio | 0.740 | 0.740 |
| Production-copy component count | 70 | 70 |

The synthetic candidate was deterministic. Deleting low-confidence edges caused
`0.000` partition churn because those edges were already excluded; deleting one
high-confidence structural edge caused `0.300` churn. Isolated entities are
excluded in both controls, matching the current production community detector.

The guarded production copy contains `953` graph entities and `1,180`
relations. Every relation confidence is at least `0.9` (`mean=0.966`), so a
`0.5` confidence threshold removes no edge and cannot reduce the giant
component. The scale run completed in under `100 ms`, but this is only
an algorithmic read-only measurement on a schema-v6 copy.

### Query-Relevant Global Selection

| Case | All-report precision | Query-relevant precision | All reports | Selected reports |
|---|---:|---:|---:|---:|
| GQ02 reef mechanism | 0.333 | 1.000 | 3 | 1 |
| GQ04 continuous-depth concepts | 0.333 | 1.000 | 3 | 1 |

Query-relevant top-1 selection removed unrelated components while preserving
all selected components' source-span locators. It proves the bounded-selection
invariant on the synthetic corpus, not the quality of generated community
summaries.

## Scoped Decision Posture

### Passage/Entity PPR

`reject-default` for unfiltered PPR on the current measured graph scope;
`benchmark-later` only after Program 2 supplies a trusted graph/noise policy.

- Evidence: no recall gain over current memory paths, one noisy-bridge
  regression, and `660` edge updates versus `4` traversed expansion edges.
- Downstream owner: Program 3, gated on Program 2 graph quality.
- Revisit trigger: rerun filtered/budgeted PPR after graph identity, relation
  confidence, and authored-topology contracts pass Program 2 gates.

### Denoised Hierarchy / Leiden Candidate

`benchmark-later`.

- Evidence: confidence denoising reduced the synthetic giant component but had
  zero effect on the production-scale copy because current confidence values do
  not separate weak edges. Leiden itself was not adopted or imported; changing
  the partition algorithm cannot repair untrustworthy edge scores.
- Downstream owner: Program 2.
- Revisit trigger: compare connected components, confidence denoising, authored
  topology, and fixed-seed Leiden only after relation-quality labels exist.

### Query-Relevant Global Selection

`adopt-contract` candidate, pending P7 holdout/provenance audit.

- Contract candidate: global retrieval must rank/select query-relevant
  communities under an explicit evidence budget; loading every report is a
  rejected default.
- Evidence: precision improved from `0.333` to `1.000` while selected report
  count fell from `3` to `1` on both measured global cases.
- Downstream owner: Program 3.
- Revisit trigger: validate against source-linked, freshness-checked community
  reports after Program 2 graph/report invalidation contracts exist.

### KG-Guided Expansion And Organization

`benchmark-later`; adopt only the explainability/budget invariant as a
downstream contract candidate.

- Contract candidate: every graph-added item must expose its seed, traversed
  path/edge types, source locator, and bounded expansion cost.
- Evidence: filtered expansion matched associative recall, avoided forbidden
  evidence, and repaired the measured homonym case.
- Downstream owner: Program 3, gated on Program 2 relation quality.
- Revisit trigger: run on a trusted Program 2 graph with source edits/deletes
  and relation hard negatives.

## Rejected Defaults

- Unfiltered graph-only PPR over the current graph.
- Treating uniformly high relation confidence as a denoising signal.
- Replacing connected components with Leiden before edge quality is measured.
- Loading every community report for every global query.
- Graph additions without explicit seed/path/provenance/budget explanations.
- Interpreting synthetic or schema-v6 scale results as production approval.

## Limitations

- The stress corpus is synthetic and small; the untouched holdout remains
  inaccessible until P7.
- The production copy is schema version 6 while current code is schema version
  7. It is valid only for read-only scale/current-data diagnosis.
- Production-scale PPR and query selection were not run because the copy lacks
  trusted query/task labels and current relation confidence is not
  discriminative.
- Community-summary freshness and source-edit invalidation remain unmeasured;
  this blocks mechanism adoption.
