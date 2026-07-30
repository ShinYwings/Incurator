# v0.32.0+ Stability Regression Audit — Evidence Ledger

Date: 2026-07-30
Status: IMPLEMENTATION IN PROGRESS — P1 contract clarification
Branch: `release/v0.39.0`
Head / rollback anchor for this planning pass: `b567427`
Umbrella plan: `.agents/plans/02_v032_regression_audit.md`

## 1. Repository And Release Reality

- Worktree was clean at `b567427` before planning files and roadmap/relay
  updates.
- PR #101 / v0.39.0 is unmerged. Existing latest-head CI is green.
- Build manifests agree on `0.39.0`; DB schema is v13.
- Baseline validation recorded by the prior review:
  - backend: 1,351 passed, 6 skipped, 4 expected xfails;
  - plugin: 737 passed;
  - Ruff, Mypy, production build, and npm audit: green.
- `git diff --check origin/master...HEAD` is clean.
- v0.32.0+ range inventory:
  - 19 merged PRs from #80 through #100;
  - 167 non-merge commits after the v0.32.0 release commit;
  - 216 aggregate changed paths;
  - current PR #101 adds 41 changed files, 3,251 insertions, 293 deletions.

## 2. Historical Contract Sources Read

The following deleted plans were read through `git show` and compared with the
first-parent release history:

| Release | Plan commit | Master plan |
| --- | --- | --- |
| v0.32.0 | `3ce8a11` | `07_path_compat_removal.md` |
| v0.32.1 | `e1b5025` | `07_cross_device_integrity_hotfix.md` |
| v0.34.0 | `0d9c746` | `10_cm1_god_file_decomposition.md` |
| v0.35.0 | `40a217a` | `12_model_catalogue_refresh.md` |
| v0.36.0 | `0095189` | `11_pl1_plugin_decomposition.md` |
| v0.36.1 | `bffddde` | `12_xc1_silent_exception_hardening.md` |
| v0.36.2 | `3a6c3c2` | `02_fail_closed_correctness.md` |
| v0.37.0 | `1ac77a6` | `02_composite_primary_key_tombstones.md` |
| v0.37.1 | `229ddaf` | `02_query_provider_failure_ux.md` |
| v0.38.0 | `2333292` | `02_sidechat_vault_wikilinks.md` |
| v0.39.0 | `13cc0bf` | `02_authored_note_topology.md` |
| v0.39 review | `f6ff089` | `03_authored_topology_review_hardening.md` |

Hotfix implementation ranges v0.32.2, v0.34.1, and v0.36.4–v0.36.8 remain
explicit rows in the audit even when their plan was smaller or folded into
release evidence.

## 3. Authoritative Contracts Read

- `SYSTEM_BEHAVIOR.md §4.2`: source removal deletes generated derived records.
- `SCHEMA.md §11.17`: source tombstone uses the same non-cascading cleanup as
  local removal and applies transactionally.
- `SCHEMA.md §20.3`: no partial authoritative compiler publish is representable;
  generation membership and revisions are authoritative and monotonic.
- `SCHEMA.md §21.6`: authored relations require current exact source structure
  and generation ownership.
- `SEARCH_ENGINE_SCHEMA.md §§2–9`: authoritative corpus only; vector/reranker
  unavailability must be explicit and traced.
- `PLUGIN_SCHEMA.md §§1.4, 2.2, 7, 13.4–13.5`: request-local lifecycle safety,
  mergeable sessions, backend command boundary, and quick-query cancellation.

## 4. Confirmed Finding Register

### P0

| ID | Finding | Reproduction / proof |
| --- | --- | --- |
| F01 | Source deletion leaves authoritative generated data searchable | Temporary DB: after removal `sources=0`, `source_spans=0`, but one generation and KNU remained; materialization recreated the KNU search document. |
| F02 | Single-generation reconciliation skips post-tombstone authored state | Future-clock authored relation plus one authoritative generation survives because the reconciliation loop exits before source/audit validation. |

### P1

| ID | Finding | Primary owner |
| --- | --- | --- |
| F03 | Authored lifecycle does not enforce audit membership | `db/_entities.py` |
| F04 | Repair revision may equal the stale row revision | `db_sync.py` |
| F05 | Relation/report retirement can move LWW clock backward | `db/_entities.py` |
| F06 | Endpoint invalidation can retire an imported winner report | `db/_entities.py` / `db_sync.py` |
| F07 | Post-publish failure leaves partial projection and stale search | `pipeline/compile.py` |
| F08 | Query-embedding failure is silently reported as full-quality/empty vector search | `retrieval/engine.py` |
| F09 | Shared abort controller loses CLI abort state and cannot cancel overlapping requests correctly | `plugin LLMClient.ts` |
| F10 | Non-streaming CLI drops model override and GUI PATH augmentation | `plugin LLMClient.ts` |
| F11 | MCP exposed tool-name sanitization is lossy/colliding | `plugin LLMClient.ts` |
| F12 | MCP shutdown may strand pending Promises forever | `plugin mcpClient.ts` |
| F13 | Plugin backend subprocesses have no timeout or output bound | `plugin/main.ts` |
| F14 | Corrupt `sessions.json` is treated as missing and later overwritten | `plugin/main.ts` |
| F15 | Corrupt secret store becomes empty and next save destroys prior keys | `secret_store.py` |
| F16 | Runtime snapshot can contain legacy plaintext API keys | `runtime_state.py` |

### P2

| ID | Finding | Primary owner |
| --- | --- | --- |
| F17 | Nested Markdown labels are rejected | `authored_topology.py` |
| F18 | Markdown targets are percent-decoded/unescaped twice | `authored_topology.py` |
| F19 | Short reranker output silently drops fused candidates | `retrieval/engine.py` |
| F20 | Short embedding output silently skips chunks as success | `retrieval/embedding.py` |
| F21 | Prompt trace records failed primary after successful failover | `prompting/runner.py` |
| F22 | Latest prompt version uses lexicographic sorting | `prompting/registry.py` |

## 5. Direct Diagnostic Evidence

- Source deletion was reproduced only in `TemporaryDirectory`; no repository,
  production vault, or active testbed DB was changed.
- Secret corruption was reproduced by redirecting `_secret_dir` to a temporary
  directory. After corrupting the two-key store and setting a third key, only
  `third` remained and `secret:first` resolved to empty.
- Prompt ordering proof: string sorting returns `v9` as newer than `v10`.
- Previous focused diagnostics reproduced:
  - report `updated_at=2040` retired with caller `now=2030` becomes 2030;
  - `A%2520B.md` resolves as `A B.md`;
  - `[see [nested]](Target.md)` produces no link.
- Review correction: successful query result `source_span_ids` intentionally
  represent answer-cited spans under `SYSTEM_BEHAVIOR.md`; the earlier candidate
  concern about empty successful citations was rejected and is not queued.

## 6. Current Test Gaps

- No source-removal test asserts zero serving generations/KUs/extracted graph/
  reports/synthesis/search across local removal and imported tombstone paths.
- No one-generation/no-source replica reconciliation test.
- No strict-successor LWW test for repair and retirement.
- No post-authoritative-commit projection failure injection.
- No query-embedding exception trace test when corpus vectors already exist.
- Plugin abort tests prove an older request cannot clear a newer controller, but
  do not prove both overlapping requests can be canceled or CLI abort is
  classified correctly.
- CLI model-override tests cover Ollama only.
- No MCP shutdown pending-settlement or sanitized-name collision tests.
- Session tests sanitize writes but do not preserve malformed canonical input.
- No secret-store corruption/concurrent-write/atomic-replace tests.

## 7. Testbed And External-State Boundary

- The current `testbed/` is marked `testbed: true` and resembles the
  `complex_math_backprop` scenario. That scenario contains historical EXH-era
  assertions and cannot be treated wholesale as a current contract.
- Do not reinitialize or mutate it.
- Use:
  - temporary DBs for sync/source/clock fault injection;
  - a disposable copy of current scenario source material when LLM coverage is
    needed;
  - the current `testbed_template` G9 source-edit/delete/rename and Reference
    Mode contracts for deterministic smoke.
- External Zotero roots remain references; no PDF is copied into a durable
  vault during validation.

## 8. D2 Holdout Boundary

- The holdout is consumed and must not be rerun.
- Before changing a tracked file, inspect
  `docs/specs/failure_atlas/D2_HOLDOUT_RESULT.yml`.
- If a tracked hash changes, update permitted drift evidence/hashes in the same
  patch without claiming a new holdout result.

## 9. Pre-Implementation Worktree

Expected planning-only paths:

- `.agents/USER_REPORT.md`
- `.agents/ROADMAP.md`
- `.agents/RELAY.md`
- `.agents/plans/01_system_stability_overhaul.md`
- `.agents/plans/01_roadmap_evidence.md`
- `.agents/plans/02_v032_regression_audit.md`
- `.agents/plans/02_v032_regression_evidence.md`
- `.agents/plans/A_v032_release_history_analysis.md`
- `.agents/plans/B_integrity_lifecycle_analysis.md`
- `.agents/plans/C_retrieval_provider_analysis.md`
- `.agents/plans/D_plugin_persistence_analysis.md`
- `.agents/plans/v032_regression_audit_arena/`

No application, test, spec, guide, manifest, or production data path may change
before approval.

## 10. Implementation Approval

- User approval received on 2026-07-30.
- PR #101 has no GitHub-hosted review threads; the seven in-session diff
  findings F02–F06 and F17–F18 are the complete current-branch correction
  scope.
- Existing latest-head PR checks were green before this implementation pass.
- The consumed D2 holdout will not be rerun. Any changed tracked fingerprint
  will be re-armed only after proving the edited path is outside the frozen Q06
  lexical ranking/citation execution path.
