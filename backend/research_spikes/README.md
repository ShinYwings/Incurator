# Plan E Research Spikes

This directory is the disposable, production-isolated workspace for Program 1E.
It may import read-only utilities from `backend/src/curator/`, but production
modules must never import anything from this directory.

## P0/P1 Scope

- `corpora/graph_stress.yml`: committed synthetic graph-limit corpus.
- `corpora/serving_stress.yml`: committed synthetic serving-policy corpus.
- `dossiers/`: primary-source, mechanism-level candidate records.
- `manifests/p0_baseline_ledger.yml`: frozen repository, corpus, environment,
  and failure-to-candidate identities.
- `evaluation_protocol.yml`: P2 metric, partition, budget, and interpretation
  contract.
- `wave_a.py`: deterministic Wave A retrieval-unit/control runner.
- `reports/wave_a.md`: scoped Wave A result and decision posture.
- `wave_b.py`: deterministic Wave B graph/hierarchy/global/expansion runner.
- `reports/wave_b.md`: scoped Wave B results, decisions, and limitations.
- `wave_c.py`: deterministic Wave C routing/sufficiency/iterative/disclosure
  serving runner (provider-free; reads only the committed corpus).
- `reports/wave_c.md`: scoped Wave C results, decisions, and limitations.
- `wave_d.py`: deterministic Wave D formula-loss/recovery/update runner
  (provider-free; reads only the committed corpus).
- `reports/wave_d.md`: scoped Wave D results, decisions, and limitations.
- `p7_holdout.py`: P7 single-run untouched-holdout runner, red-team audits,
  and decision synthesis (provider-free; consumes RUQ05/GQ07/HQ01/FR05 once).
- `reports/p7.md`: final holdout results, red-team outcomes, and scoped
  decision records mapped to Programs 1/2/3.
- `manifests/p7.yml`: frozen P7 inputs, holdout access record, and decisions.
- `contracts.py`: validation and mutation-guard helpers.
- `prepare_inputs.py`: copies SQLite databases with SQLite's online backup API,
  verifies that sources were unchanged, and writes only under ignored `local/`.

The research corpus tiers are:

1. D1 Failure Atlas frozen corpus and qrels.
2. Synthetic graph stress corpus for noisy bridges, homonyms, giant-component
   pressure, multi-hop paths, and query-relevant global selection.
3. Synthetic serving stress corpus for complexity routing, sufficiency gating,
   bounded iterative retrieval, and progressive context disclosure.
4. Synthetic formula-recovery corpus for parser/distillation loss boundaries,
   uncertain recovery, selective cost, and page-hash invalidation.
5. Read-only copied SQLite snapshots under `local/snapshots/` for scale checks.

`testbed/` currently contains the `complex_math_backprop` scenario. Its plan
documents retired EXH-era behavior, so it is recorded as a stale diagnostic
input and is not a Plan E comparison corpus.

## Safety

Never commit `local/`. It may contain private database copies and raw results.
Create a copied snapshot with:

```bash
uv run --directory backend python research_spikes/prepare_inputs.py \
  --source ../testbed/.curator/state.sqlite \
  --label testbed-complex-math-backprop
```

The command hashes the source before and after SQLite backup, opens the copy in
read-only mode, records table counts and schema identity, and fails if the
source changed during the operation.

Validate P0/P1 contracts with:

```bash
uv run --directory backend pytest -q tests/test_research_spikes_contract.py
```

Spikes must use `dev`, `regression`, or `adversarial` partitions until Plan E
P7. The untouched holdout must not be measured or exposed to tuning.
