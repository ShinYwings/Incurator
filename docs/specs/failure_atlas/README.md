# Failure Atlas Directory Index

This directory contains the Failure Atlas contract plus frozen evaluation
oracles used by backend tests. Files here are not interchangeable: some are
human-readable specs, and some are machine-readable test fixtures whose content
is intentionally pinned.

## Live Contract Docs

- `FAILURE_ATLAS.md` is the authoritative diagnostic contract for Failure Atlas
  case records, status lifecycle, evidence bundles, and downstream oracle use.
- `EVALUATION_BASELINE.md` records deterministic baseline measurements, release
  gates, corpus partitions, and holdout rules.
- `PROGRAM_HANDOFFS.md` is the final Program 1 handoff for downstream Programs 2
  and 3. Treat it as a frozen handoff contract unless a new atlas-version
  decision explicitly supersedes it.

## Frozen Test Oracles

These files are read directly by backend tests. Changing them is a test-oracle
change, not a normal documentation edit; update the relevant tests and hashes in
the same change.

- `cases/F*.yml` are the machine-readable case records for F1 through F13.
- `fixture_corpus.yml` is the synthetic corpus used by deterministic Failure
  Atlas evaluation.
- `qrels.yml` is the ground-truth query relevance set, including the holdout
  partition that must not be tuned against.
- `support_labels.yml` maps query-level expected answers to minimal source
  support labels.
- `plan_b_compiler_gold.yml` is the compiler-integrity gold fixture for Plan B
  support and staging tests.
- `D2_HOLDOUT_RESULT.yml` records the one accepted D2 holdout run and the hashes
  of its frozen inputs.

## Maintenance Rules

- Do not delete or move the YAML oracles as a cleanup task; tests depend on their
  current paths.
- If a case, qrels entry, support label, or gold fixture changes, treat it as an
  atlas-version decision and update the corresponding backend tests.
- Keep aggregate-only metrics out of release gates. Failure Atlas evidence must
  remain per-family and tied to concrete case ids or query ids.
- Historical context belongs in Git history unless a file is still cited by the
  active contract. `PROGRAM_HANDOFFS.md` remains here because downstream program
  obligations still cite it.
