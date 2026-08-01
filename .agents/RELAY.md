# RELAY — ACTIVE

## Goal

Ship v0.40.2 Stability Regression Audit P8: explicit retrieval degradation,
exact finite provider output validation, successful-provider prompt trace
attribution, and numeric prompt-version ordering.

## Plan Reference

- `.agents/plans/02_v032_regression_audit.md` — approved P8 phase.
- `.agents/plans/C_retrieval_provider_analysis.md` — locked design boundary.
- `.agents/plans/02_v032_regression_evidence.md` — active evidence ledger.

## Analysis And Reasoning

- Branch `release/v0.40.2` starts from clean relay-reset head `710817c`.
- This is a patch: no schema, command, setting, or ranking-policy change.
- The consumed D2 holdout is lexical-only with providers/reranking disabled;
  P8 changes provider-present branches and will re-arm only the affected hashes.
- The unrelated existing testbed and production vault must not be mutated;
  deterministic temporary DB/provider tests are the authoritative P8 proof.

## Progress Status

- Docs/specs, failing tests, implementation, and v0.40.2 release metadata are
  complete.
- Local gates are green: backend 1,401 passed / 6 skipped / 4 xfailed; plugin
  778 passed; Ruff, mypy, TypeScript, production build, docs/version consistency,
  and frozen-holdout fingerprints passed.
- Implementation commit: `a9792e3`.

## Critical Context / Blockers

- `D2_HOLDOUT_RESULT.yml` has already consumed all three permitted runs; never
  rerun the holdout.
- `backend/src/curator/retrieval/engine.py` and `embedding.py` are fingerprinted
  and require an explicit non-impact re-arm after their final edits.

## Immediate Next Action

Create `chore(release): v0.40.2`, push `release/v0.40.2`, open the draft PR, and
verify latest-head GitHub CI.
