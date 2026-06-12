# Evaluation Baseline & Proposed Gates (Program 1, D1)

Current version: v0.6.0 (D1 diagnostic baseline release)
Contract: `docs/specs/failure_atlas/FAILURE_ATLAS.md`
Data: `fixture_corpus.yml` (frozen synthetic corpus, version 1) and
`qrels.yml` (ground-truth labels, version 1)
Runner: `backend/tests/test_failure_atlas_eval.py`

This document records the query/task families, dataset partitions, labeling
methodology, the measured deterministic baseline at the D1 snapshot, and the
**proposed** (not yet binding) thresholds for later Program 1/2/3 gates.
Thresholds become binding only after user approval per the umbrella plan §6.3 —
"No release threshold is binding until its labeling procedure, baseline,
variance, and user-approved threshold are documented."

## 1. Measurement Snapshot

| Identity | Value |
|---|---|
| Git SHA | `8458f652d5481f377bd957ed1256240aaf470f54` (branch base) |
| Package version | 0.5.6 (D1 measures pre-release behavior) |
| DB schema version | 6 |
| Engine mode | DB-native lexical (FTS5/BM25), `embedder=None`, `reranker=None`, `persist=False` |
| Execution mode | `deterministic` (provider-free; zero run-to-run variance by construction) |
| Corpus | `fixture_corpus.yml` v1 — 10 synthetic knowledge units, 2 topic clusters + 1 homonym pair |
| Measured date | 2026-06-12 |

Latency/token/cost are not part of the deterministic baseline (no providers
involved); they enter with Plan E / D2 provider benchmarks.

## 2. Query/Task Families And Where Each Is Measured

Per FAILURE_ATLAS.md, aggregate-only metrics are prohibited. Family coverage at
D1:

| Family | D1 measurement | Notes |
|---|---|---|
| direct-factual | qrels Q01–Q08 via lexical engine | dev/regression/holdout/adversarial partitions |
| associative | qrels Q09 (lexical reachability) + F11 repro | true multi-hop quality is structurally unmeasurable until explore loops exist (F11) |
| global | F4 reproduction tests | structurally unmeasurable as retrieval quality: selection is query-independent at baseline |
| source-scoped | F10 reproduction tests | evidence capped at 200-char previews at baseline |
| cross-route | F2/F3/F5 reproduction tests | transaction/policy/budget integrity, not ranking |
| compiler | F6/F7/F8/F9 reproductions + experiments module | claim support, mutation, atomicity |
| client-parity | F12 reproduction tests | MCP vs plugin shape divergence |
| evaluation-infra | F13 reproduction + contract tests | scenario staleness, atlas integrity |

The repro/experiment suites are the binding baseline for families whose
retrieval quality cannot honestly be scored yet; replacing those with metric
gates is exactly the D2 specification work.

## 3. Partitions And Labeling Method

Partitions (qrels.yml): `dev` (4 queries), `regression` (2, frozen, binding),
`holdout` (1, frozen, **never measured** during development — the runner
enforces this), `adversarial` (2 hard-negative pairs, binding).

Labeling method: deterministic expected-id labels authored together with the
synthetic corpus — each query's vocabulary was written so that exactly one (or
an enumerated set of) document(s) is correct. Reviewer provenance: authored and
cross-checked against corpus bodies by the D1 agent, 2026-06-12. No model
judges anywhere in the deterministic baseline (model judges may appear in D2
only as supplementary diagnostics).

Claim-to-minimal-support labels: at D1 these exist as fixture-level
constructions inside the reproduction tests (every fixture document/span
declares its provenance; F1/F6 assert support propagation against them). A
corpus-scale claim-support label set is a D2 deliverable, after E informs the
target IR.

## 4. Measured Baseline (2026-06-12, deterministic lexical mode)

Per family and partition; n = query count. Values are exact (zero variance —
deterministic engine, frozen corpus).

| Family | Partition | n | Recall@1 | Recall@3 | Recall@5 | MRR@5 | Hard-neg outranks |
|---|---|---|---|---|---|---|---|
| direct-factual | dev | 3 | 1.00 | 1.00 | 1.00 | 1.00 | — |
| direct-factual | regression | 2 | 1.00 | 1.00 | 1.00 | 1.00 | — |
| direct-factual | adversarial | 2 | — | — | 1.00 | >0 | 0 |
| associative | dev | 1 | — | — | 1.00 | >0 | — |
| direct-factual | holdout | 1 | not measured (frozen) | | | | |

Reading: on a 10-document corpus with well-separated vocabulary, lexical
FTS5/BM25 is already perfect. This is expected and is precisely why this corpus
alone must NOT be used to claim retrieval quality — its role is regression
pinning (any future change that breaks even this trivial baseline is an
unambiguous regression) and hard-negative wiring. Realistic-scale corpora,
distractor density, and provider modes arrive with Plan E benchmarks and the
D2 evaluation specification.

## 5. Proposed Thresholds (NOT binding until user approval)

1. **Regression partition (binding at D1 via CI)**: direct-factual
   Recall@1 = 1.00 on the frozen regression queries; 0 hard-negative outranks
   on the adversarial partition. Already enforced by
   `test_failure_atlas_eval.py`.
2. **Program 1 citation gates (proposed, from umbrella §8)**: citation
   correctness ≥ 95% and completeness ≥ 90% on the initial gold suite — cannot
   be measured until F1 (provenance loss) is repaired in D2; proposed to be
   measured on the D2 observatory and then ratified.
3. **Program 2 compiler gates (proposed, encoded per case)**: see
   `assignment.gate` in cases F6–F10 (0 broad fallbacks, idempotent rebuilds,
   0 homonym false merges, authored topology compiled, full-span evidence).
4. **Program 3 serving gates (proposed)**: see cases F3–F5, F11, F12 (policy
   enforcement, bounded query-relevant routes, explicit omissions, bounded
   iteration, client parity), plus no regression of the §4 table beyond
   approved tolerance on the then-current corpus version.

## 6. Variance And Reproducibility

The D1 baseline is exactly reproducible: deterministic engine, frozen corpus,
no providers, `persist=False`. Re-running
`uv run --directory backend pytest tests/test_failure_atlas_eval.py -q`
on the same snapshot yields identical metrics. LLM-sensitive variance
measurement (temperature, provider drift) is deferred to provider-mode
benchmarks in Plan E / D2 and must be reported separately per
FAILURE_ATLAS.md §5.
