# v0.32.0+ Stability Regression Audit — Evidence Ledger

Date: 2026-07-30
Status: P5 COMPLETE — v0.39.1 release validation green
Branch: `release/v0.39.1`
Head / rollback anchor for this planning pass: `b567427`
Umbrella plan: `.agents/plans/02_v032_regression_audit.md`

## 1. Repository And Release Reality

- Worktree was clean at `b567427` before planning files and roadmap/relay
  updates.
- PR #101 / v0.39.0 merged as `d8d1e39`; its latest-head CI was green.
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
| F23 | A local mutable-row reinsert clears a future-clock tombstone without advancing its revision, so the next peer replay deletes the reinsert | `db_sync.py` |
| F24 | Malformed/current-schema peer headers are logged and skipped forever instead of failing autosync visibly | `db_sync.py` |

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

## 6. Baseline Test Gaps And Disposition

- P1–P5 closed the source-removal, one-generation reconciliation,
  strict-successor repair/retirement, post-authoritative projection failure,
  future-clock reinsert, and malformed peer-header gaps with red-before-green
  tests.
- Remaining phase-owned gaps:
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

## 11. PR #101 Red/Green Evidence

- P1 contract checks: `test_spec_sync.py` + `test_docs_surface_parity.py`:
  16 passed.
- P2 red run: all seven selected oracles failed for the intended pre-fix state:
  nested labels emitted no relation; double-encoded targets emitted no
  relation; the lone generation stayed authoritative after source deletion;
  repair tied the 2040 clock; omitted audit membership stayed active;
  retirement backdated relation/report clocks; and the winner-dependent report
  retired.
- P3 green run: the same seven selected oracles passed.
- A post-fix quiescence oracle then exposed write amplification for a healthy
  lone generation. It failed before the repair guard and now proves two
  consecutive reconciliation passes leave the row byte/logically unchanged.
- Authored topology suite: 32 passed.
- Related DB sync/schema suites: 40 passed.
- Related graph report/search suites: 27 passed.
- Failure Atlas contract + spec/docs parity: 121 passed.
- Ruff and Mypy pass.
- D2 was not rerun. `_entities.py` changed only outside the frozen Q06 path;
  the evidence narrative and tracked hash were re-armed.

## 12. PR #101 Full Local Release Gate

- Backend: 1,358 passed, 6 skipped, 4 expected xfails; 7 third-party SWIG
  deprecation warnings; 0 failures.
- Plugin: 68 files / 737 tests passed.
- TypeScript: `npx tsc --noEmit -p tsconfig.json` passed from `plugin/`. The
  repository-root `npx tsc` launcher does not resolve the plugin-local
  TypeScript package, so the identical project config was validated from its
  package directory.
- Production plugin build: passed.
- `npm audit --prefix plugin`: 0 vulnerabilities.
- Ruff, Mypy, docs/spec parity, Failure Atlas contract, and `git diff --check`:
  passed.
- Manifests remain synchronized at `0.39.0`; this is an unmerged review
  correction on the existing release branch, not a new version.
- Isolated current-contract G9/Reference Mode smoke:
  - copied only `testbed_template` inputs into a temporary vault;
  - compiled two active authored relations covering a nested label and
    one-pass percent decoding;
  - two consecutive healthy reconciliations were byte/logically quiescent;
  - source removal retired the authored set and removed its search documents;
  - `@zotero_data/storage/TESTKEY1/mock_paper.pdf` resolved outside the vault
    and no PDF was copied into it;
  - temporary vault and its exact repo-cache namespace were deleted.
- Production `last_root` remains `/Users/shin/shinywings/second_brain`; the
  active ResNet testbed and consumed D2 holdout were not mutated.

## 13. PR #101 Delivery Evidence

- Final implementation head before relay closure: `4f3af29`.
- `release/v0.39.0` was pushed and PR #101's Why/What/review-hardening/
  compatibility/validation description was refreshed.
- Latest-head push-event CI:
  - Backend Tests: passed;
  - Plugin Tests: passed;
  - Version Consistency: passed.
- Latest-head pull-request CI:
  - Backend Tests: passed;
  - Plugin Tests: passed;
  - Version Consistency: intentionally skipped by event policy.
- GitHub emitted only the existing Node.js 20 action-runtime deprecation
  annotation; there was no code, test, build, or audit failure.
- PR #101 is ready for human review and merge. P5 remains deliberately blocked
  on the merged `master` anchor so the cross-system patch chain does not branch
  from this release branch.

## 14. P5 Identity/Sync Two-Pass Audit

Rollback anchor: merged v0.39.0 commit `d8d1e39`.

Pass 1 re-read each first-parent merge diff against its historical release
intent and current implementation. Pass 2 independently walked the transition
matrix (create/update/delete/reinsert, local/imported tombstone, future clock,
first peer, replaced peer snapshot, malformed peer, dry-run, shared support,
post-publish projection failure, and deterministic re-emit).

| Release / PR | Pass 1 — merge-diff result | Pass 2 — current transition proof |
| --- | --- | --- |
| v0.32.0 / #80 | Current-only portable path removal remains deliberate; no compatibility shim or destructive migration was reintroduced. | Portable-path, machine-config, runtime-state, and schema tests pass. No new P0/P1. |
| cleanup / #81 | Roadmap/relay-only merge; no behavior-bearing path. | No runtime transition to retest. |
| v0.32.1 / #82 | Device identity/source remap introduced the incomplete source-delete closure (F01); durable-state findings F14–F16 remain assigned to P6. | Local/imported deletion, stale replay, live-source serving, shared-support, and immediate search eviction now pass. |
| v0.32.2 / #83 | Legacy-peer tolerance also classified malformed current peer headers as skippable (new F24). | Malformed/current-schema headers now fail visibly without checkpointing; valid incompatible-schema peers remain the only skip case. |
| v0.33.0 / #84 | DB-native materialization/re-emit exposed F07; query degradation F08 remains assigned to P8. | Post-commit file failure recovers without LLM/new generation; standalone re-emit persists one stable Atom id. |
| v0.34.0 / #85 | CLI/MCP/plugin facade moves retain the characterized command boundary; no additional P0/P1 identity defect found. | Command-surface and PR-85 characterization suites pass. |
| v0.34.1 / #86 | Export-id/high-water loop prevention remains correct. | First identity, unchanged/replaced snapshot, dry-run high-water, and no-self-import tests pass. |
| v0.37.0 / #98 | Composite tombstones are portable, but explicit local reinsert could backdate a future delete (new F23). | Local reinsertion advances strictly past the tombstone; older tombstone rewrites cannot backdate a newer delete. |

Red-before-green evidence:

- Five F01/F07 source/projection oracles failed on the merged baseline, then
  passed after the lifecycle and recovery implementation.
- F23 failed with a 2040 tombstone and a 2026 reinsert revision; the shared
  clear boundary now advances the row strictly past 2040 before clearing.
- Both F24 corrupt-header variants were silently skipped before the repair and
  now raise `AutosyncError` with the peer filename and no checkpoint.
- A forced process interruption immediately after authoritative publish
  previously left `l2_status=running` and invoked the LLM again on retry. The
  transaction now commits a projection-pending marker and retry re-emits from
  the same generation without an LLM call.
- Full re-emit previously left generated page hashes stale; a naive all-layer
  refresh then proved unsafe because it would bless preserved CTX edits. The
  final path refreshes only regenerated ATM/CON/SYN hashes, deletes orphan CTX
  hashes, and leaves live CTX baselines unchanged.
- The second-pass identity/sync matrix is green: 198 tests across config,
  portable paths, schema, DB sync/autosync, CLI autosync, facade
  characterization, composite tombstones, source lifecycle, staged compile,
  projection re-emit, and search materialization.

## 15. P5 Full Local Release Gate

- Backend: 1,373 passed, 6 skipped, 4 expected xfails; 7 third-party SWIG
  deprecation warnings; 0 failures.
- Plugin: 68 files / 737 tests passed.
- Ruff: passed.
- Mypy: 126 source files checked with no issues.
- TypeScript: `npx tsc --noEmit -p plugin/tsconfig.json` passed.
- Production plugin build: passed.
- `npm audit --prefix plugin`: 0 vulnerabilities.
- Docs/spec parity and Failure Atlas contract: 121 passed.
- `git diff --check`: passed.
- Build manifests and lockfile root metadata agree on `0.39.1`.
- D2 was not rerun. The edited `_entities.py` and `sources.py` paths do not run
  in frozen Q06; their exact hashes and bounded drift rationale were re-armed
  in `D2_HOLDOUT_RESULT.yml`.

## 16. P5 Isolated Testbed And External Boundary

- Initialized only `testbed_template/stage` in a disposable `/tmp` vault; the
  active repository testbed and production DB were not touched.
- `wiki add --no-sync` registered both fixture sources. Removing the valid
  source without `--delete-file` preserved its SHA-256 exactly while source,
  span, active-unit, and search-document counts all became zero.
- The removed source's L1 projection disappeared immediately. `wiki lint`
  returned 100/100 and `wiki sync --no-deep --no-interactive` reported no
  logical or structural gaps.
- A disposable Zotero SQLite index resolved `TESTKEY1` to the scenario's mock
  PDF outside the vault. No PDF appeared inside the vault.
- The temporary vault, external fixture copy, and exact repository cache
  namespace were moved to Trash after validation.
- Repository `last_root`, Gemini MCP `VAULT_ROOT`, and production Claude MCP
  `VAULT_ROOT` all resolve to `/Users/shin/shinywings/second_brain` after
  cleanup.

## 17. P5 Delivery Evidence

- Commits:
  - `da57809` — source lifecycle/projection implementation, tests, and
    contracts;
  - `17c96fc` — audit plan and evidence;
  - `c3f20c8` — `chore(release): v0.39.1`.
- `release/v0.39.1` was pushed and draft PR #102 opened against `master`.
- Latest-head push-event CI:
  - Backend Tests: passed;
  - Plugin Tests: passed;
  - Version Consistency: passed.
- Latest-head pull-request CI:
  - Backend Tests: passed;
  - Plugin Tests: passed;
  - Version Consistency: intentionally skipped by event policy.
- PR #102 is ready for human review and merge. P6 remains gated on the merged
  `master` anchor.
