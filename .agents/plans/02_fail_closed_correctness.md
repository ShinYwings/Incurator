# v0.36.2 Master Implementation Plan

Date: 2026-07-19
Status: DRAFT — Arena debate concluded; awaiting user approval before coding.

## 1. Objective

Make cross-device sync and workspace curation fail closed when their correctness
state is unreadable, invalid, or only partially completed. Done means:

- corrupt existing sync state never creates or persists a replacement device id;
- peer/conflict import and archive failures never produce a successful “merged”
  result;
- a failed tombstone delete rolls back and is never counted/propagated;
- an existing invalid `curate.yml` never becomes the unrestricted default policy;
- valid first-run/missing-workspace defaults and unchanged-sync quiescence remain
  intact.

## 2. Explicit Non-Goals

- No schema-v12 or JSONL format change.
- No global transaction spanning every peer file.
- No content-hash loop guard, raw SQLite synchronization, or auto-quarantine.
- No composite-primary-key tombstone encoding in this patch.
- No change to retrieval ranking, route algorithms, or valid KRS semantics.
- No unrelated broad-exception cleanup.

## 3. Strict Quality Conditions & Release Gates

- Every reproduced failure has a failing test before implementation and a passing
  test after it.
- An existing corrupt sync-state byte sequence remains byte-for-byte untouched.
- First-run state creates exactly one stable device id; repeated reads return it.
- A conflict appears in the successful conflict list only after import and archive.
- Import/archival failure reaches CLI JSON, human CLI, and plugin failed-state UX.
- Tombstone delete exception leaves both target row and incoming tombstone
  uncommitted and increments no deleted count.
- Empty/no-workspace queries still use `default`; invalid-existing-workspace
  queries fail before retrieval, trace, or synthesis.
- Two consecutive unchanged autosync passes apply zero rows and do not export.
- Full backend, plugin, static, build, version-consistency, and testbed gates pass.

## 4. Locked Design Decisions (Arena Consensus)

- Patch version is v0.36.2; schema stays 12.
- Absence is the only state-initialization path. Existing read/decode/root-shape
  failures raise a typed sync-state error.
- Autosync remains per-file transactional and retry-idempotent. Earlier peer files
  may commit before a later failure; overall status is failure and retry is safe.
- JSON CLI callers receive `{ok:false,error}`; human CLI receives a red error and
  non-zero exit.
- `_archive_conflict` raises. Successful conflict names are appended only after
  import and archive both complete.
- Tombstone delete exceptions propagate through `import_knowledge` so SQLite
  rolls back that input file.
- `curate_yml` owns one validated policy resolver. ContextService and
  QueryOrchestrator do not implement private fallback logic.
- Default policy is allowed only for empty workspace context or absent file.
- Existing invalid YAML, source-scope shape, semantic policy, read, or hash
  failures propagate before retrieval.
- Source patterns preserve accepted scalar-string/string-list forms but reject
  mappings, numbers, and nested/non-string list members.

## 5. Scope Exclusions & Stop Conditions

- **Exclusions**: composite-key tombstone transport, retired-device cleanup,
  multi-peer staging transaction, unrelated exception slices.
- **Stop Conditions**:
  - Stop if a schema migration or JSONL compatibility layer is needed.
  - Stop if production/testbed sync state would need deletion or rewriting.
  - Stop if a valid existing `curate.yml` in the active scenario depends on a
    shape the new parser would reject; inspect and bring it back to review.
  - Stop if two-pass autosync is non-quiescent after the fix.

## 6. Evidence Ledger

- Rollback anchor: `06e69058def994d4091a77790b2eeaf162da5393`.
- Branch: `release/v0.36.2` from merged master.
- Current version/schema: v0.36.1 / schema 12.
- Relevant baseline: 95 passed in 425.76s.
- Five failure injections reproduced exactly as recorded in
  `.agents/plans/02_roadmap_evidence.md`.
- No production files changed; temporary directories only.

## 7. Execution Phases (Follow TDD and CI at each phase)

### P0 — Research & Measured Baseline (complete)

- Reproduce all five failures on merged master.
- Read current sync, curation, CLI, plugin, specs, paired guides, and historical
  sync plans.
- Freeze rollback anchor and 95-test baseline.

### P1 — Contract Specification

Update English source text first, then Korean pairs:

- `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md`: state corruption, partial
  autosync, conflict success, and invalid-existing-policy behavior.
- `docs/specs/curator_schema/SCHEMA.md`: tombstone delete/record transaction
  atomicity without schema change.
- `docs/guides/USER_GUIDE.md` then `_KR.md`: actionable autosync failures and
  idempotent retry.
- `docs/guides/PLUGIN_GUIDE.md` then `_KR.md`: failed status/notice and no false
  conflict toast.
- `docs/guides/MCP_USER_GUIDE.md` then `_KR.md`: missing workspace default versus
  invalid `curate.yml` failure.

Verify docs/spec synchronization tests before P2.

### P2 — Failing TDD Oracles

Add focused backend tests for:

- malformed JSON, invalid UTF-8, I/O failure, and non-object sync state;
- absent-state first run and stable repeated id;
- corrupt state bytes are not overwritten;
- peer import failure and conflict import/archive failure surface;
- conflict success list only after completed archive;
- tombstone delete exception rolls back row/tombstone/count;
- JSON/human CLI failure envelopes;
- missing `curate.yml` default remains valid;
- malformed YAML, wrong-shaped source patterns, semantic validation errors, and
  hash/read races fail in both public query paths before retrieval.

Add/adjust the plugin client test proving `{error}` maps to `ok:false` and never
produces a merged-conflict result.

Verify tests fail for the expected assertions, not fixture/setup mistakes.

### P3 — Sync Correctness Implementation

- Add minimal typed sync error(s).
- Harden read-state shape/field validation without repair.
- Propagate contextual peer import and conflict archive errors.
- Populate successful conflicts only after completion.
- Remove tombstone delete suppression.
- Map known errors at `wiki db autosync` boundaries.

Verify focused sync + CLI tests and Ruff before P4.

### P4 — Curation Policy Integrity Implementation

- Add strict source-scope parsing for security-relevant fields.
- Add shared validated policy resolver in `curate_yml`.
- Replace duplicate ContextService/QueryOrchestrator fallback functions.
- Ensure policy failures predate retrieval, trace, and synthesis writes.

Verify focused curation/query tests and Ruff before P5.

### P5 — Integration And Testbed

- Run `scripts/backend-check pytest`, Ruff, and Mypy.
- Run plugin Vitest, TypeScript, and production build.
- Run `gaussian_splatting` testbed status/sync/lint and relevant query checks when
  the configured LLM is available.
- Run real `VAULT_ROOT=testbed wiki db autosync`, then dry-run twice; require zero
  imports and `would_export=false` after convergence.
- Verify reference-mode Zotero resources remain external and untouched.

### P6 — Release Closure

- Update backend/plugin manifests to 0.36.2 and `CHANGELOG.md`.
- Keep static spec title at v0.36 because this is a patch.
- Remove completed v0.36.2 active plan/Arena/evidence files after validation.
- Clean ROADMAP item, update RELAY, commit `chore(release): v0.36.2`, push, and
  open a PR with Why/What/How and validation evidence.

## 8. Multi-Agent Role Reviews

- **lead_architect**: shared authoritative boundaries, minimal code surface.
- **red_teamer**: attacked absence/corruption confusion, partial commits,
  premature conflict success, weak helper-only tests, and retry loops.
- **schema_guardian**: confirmed no schema bump and transaction rollback semantics;
  prohibited guessed composite-key encoding.
- **source_pair_analyst**: confirmed policy failure precedes evidence selection and
  valid source include/exclude remains unchanged.
- **system_synthesizer**: accepted per-file partial progress with visible overall
  failure because imports are idempotent; locked structured JSON failure output.

