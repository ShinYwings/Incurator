# Plan D2 Evidence Ledger

Date: 2026-06-12
Branch: `feature/plan-d2-failure-atlas`
Rollback anchor: `ea3e435838375f4208822835d519d8725d2cbc02`

## Current Repository And Schema Reality

- Plan D1 (`v0.6.0`), Plan E, and the SQLite leak hotfix (`v0.6.1`) are
  merged into the local `master` used for this branch.
- `state.sqlite` schema version is `7`; D2 requires no schema migration.
- F1 is reproduced at `search.SearchHit -> retrieval.evidence.EvidenceItem`:
  hydrated `EngineHit.source_span_ids` are dropped.
- F2 is reproduced because orchestrated evidence search persists an engine
  `QTR-` and the orchestrator persists a second disconnected `QTR-`.
- F13 is reproduced against the historical local `complex_math_backprop`
  scenario. The tracked `testbed_template` already targets CTX/ATM/CON/SYN and
  DB-native search, but lacks explicit agent-reuse and incremental-correctness
  gates.
- Plan E P7 adopted fine-grained RAG diagnostics and reserved Failure Atlas
  holdout `Q06` for one D2-approved run.

## Baseline And Rollback Evidence

- Active testbed scenario: `gaussian_splatting` (inferred from the initialized
  `testbed/` workspace and matching scenario assets).
- Testbed DB SHA-256 before D2:
  `4bb46326faf8512f88b51c7a35bbe3d31ac36fafbf1cf887759db1784a6109cc`.
- Testbed DB backup:
  `.agents/backups/d2-pre-observatory-state.sqlite` (gitignored), SHA-256
  `4bb46326faf8512f88b51c7a35bbe3d31ac36fafbf1cf887759db1784a6109cc`.
- Testbed `curate.yml` SHA-256:
  `a45b5ef13bff1d335ff1d95a95e1df9d6e34d338bd7aef6644e6e17633ed672f`.
- Failure Atlas fixture SHA-256:
  `35301871bdd1e8e676d63c032e7c566d863a9760f94d1c00e5de8217e364603b`.
- Failure Atlas qrels SHA-256:
  `e3b254054779595aa4157df82db1c885356e3763f35430be0b23bb187c35c6a0`.
- DB schema fingerprint:
  `6978ec480800bc419835ce9c83e96b1af3963c9c9c52f91e02d94e7b5da786f4`.

## Current Dirty Worktree

Pre-existing changes outside D2 ownership are preserved:

- deleted `.agents/drafts/bug_sqlite_leak.md`;
- modified generated `backend/src/curator/data/build_manifest.json`.

## D2 Approved Minimum Substrate

1. Preserve search-hit source-span provenance through the public search adapter
   and evidence pack.
2. Persist one authoritative orchestrator `QTR-` while embedding the engine
   retrieval trace into it.
3. Add a reusable provider-free fine-grained evaluation runner and produce one
   valid `Q06` result under frozen inputs.
4. Make the tracked testbed template the current-architecture F13 oracle,
   including truth, retrieval, agent-reuse, and incremental-correctness gates.

No ranking weights, routes, answer synthesis, compiler behavior, or schema are
changed by D2.

## Holdout Audit Correction

- The first Q06 run was invalidated because provenance resolution compared
  against fixture declarations rather than authoritative `source_spans`.
- The second run was invalidated because review required complete ranking-stack
  identity, all-gate preflight, and authoritative record/span citation pairing.
- No ranking configuration, query, corpus, qrels, or threshold changed.
- The final valid run used query-level `support_labels.yml`, authoritative
  temporary source-span rows, and the same lexical limit/rerank settings.
- `D2_HOLDOUT_RESULT.yml` records both invalidated runs and the one valid
  result, plus exact evaluated-code and ranking-stack file hashes.

## Testbed Validation

- `testbed_template` initialized and completed provider-backed `wiki update`
  through current CTX/ATM/CON/SYN generation plus structural/logical sync.
- An initial provider-backed `wiki query "sample"` gate hung in the local
  reranker/model runtime and was interrupted.
- The final scenario uses the production orchestrator's provider-free
  `fetch_context` surface instead. It passed one-QTR/retrieval-trace/provenance
  checks and the mutation regression probes.
- The original `gaussian_splatting` scenario was restored, and its pre-D2
  `state.sqlite` SHA-256 was restored exactly:
  `4bb46326faf8512f88b51c7a35bbe3d31ac36fafbf1cf887759db1784a6109cc`.
