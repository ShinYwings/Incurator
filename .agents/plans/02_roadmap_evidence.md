# v0.36.2 Evidence Ledger

Date: 2026-07-19
Status: PRE-IMPLEMENTATION BASELINE

## 1. Rollback And Repository Reality

- PR #89 merged as `06e69058def994d4091a77790b2eeaf162da5393`.
- Branch `release/v0.36.2` was created directly from that merged `master`.
- Worktree was clean before plan artifacts were created.
- Build manifests are v0.36.1; SQLite `SCHEMA_VERSION` is 12.
- No production vault or DB was modified during failure injection.
- Active testbed is the existing `gaussian_splatting` scenario recorded by the
  prior relay; `testbed/` exists.

## 2. Current Code Reality

| Failure | Current owner | Current behavior |
| --- | --- | --- |
| Corrupt sync state | `db_sync.read_sync_state` | Broad catch returns `{}`; new device id overwrites corruption |
| Peer/conflict failure | `db_sync.import_all_peers`, `_archive_conflict`, `autosync` | Logs/swallows; conflict UI can say merged while file remains |
| Tombstone delete failure | `db_sync._apply_tombstone` | Swallows delete error, records tombstone, returns applied |
| Malformed workspace policy | `context_service._resolve_policy`, `retrieval.orchestrator._resolve_policy` | Both swallow and return unrestricted default |
| Wrong-shaped source scope | `curate_yml.load_curate_spec` | Non-mapping/invalid values normalize to empty include/exclude |
| Invalid curation planning | MCP `curator_plan_workspace`, hidden plugin planner | Invalid semantic policy is normalized and persisted before/while reporting failure |

## 3. Reproduction Evidence

One-shot failure injection on the rollback anchor produced:

```json
{"case":"corrupt_sync_state","read_value":{},"generated_id":"<new>","corruption_overwritten":true}
{"case":"conflict_archive_failure","counted_imported":["peer.sync-conflict-copy.jsonl"],"conflict_file_remains":true}
{"case":"tombstone_delete_failure","reported_applied":true,"row_exists":true,"tombstone_propagated":true}
{"case":"malformed_curate_policy","context_default_project":"default","context_hash":"","query_default_project":"default","query_hash":""}
```

A valid YAML document with `sources:` as a sequence produced
`parsed_include=[]`, `policy_include=()`, and `scope_became_unrestricted=true`.

An invalid semantic route produced:

```text
MCP:    ok=true, route=auto, persisted_plan_count=1
Plugin: ok=false, exit_code=0, persisted_plan_count=1
```

Repository/testbed compatibility preflight found four current `curate.yml`
files (active Gaussian Splatting testbed plus three scenario fixtures). Every
`sources` block is a mapping and every include/exclude is a list of strings, so
the proposed strict source-pattern parser does not reject current valid assets.

## 4. Pre-Change Test Baseline

```text
scripts/backend-check pytest \
  backend/tests/test_db_sync.py \
  backend/tests/test_cli_db_autosync.py \
  backend/tests/test_plan_f_context_service_contract.py \
  backend/tests/test_query_orchestrator.py -q

95 passed in 425.76s
```

The green baseline does not cover any of the six reproduced false-success or
scope-bypass paths.

## 5. Contract Evidence

- SYSTEM_BEHAVIOR §13.1: conflict import + archive and stable one-writer identity.
- SYSTEM_BEHAVIOR §13.3: sync state is device-local bookkeeping.
- SCHEMA §11.17: tombstones delete matching canonical rows before upsert.
- SYSTEM_BEHAVIOR §9/§16: default is legitimate outside a workspace; existing
  workspace KRS compiles into the retrieval policy and invalid specs surface.
- USER/PLUGIN guides currently promise that conflict files are merged then
  archived, which the current implementation cannot guarantee.

## 6. Rollback Requirements

- Application rollback is `git revert` of v0.36.2 commits; no data migration is
  planned.
- Never overwrite, delete, or quarantine a corrupt sync-state file automatically.
- Tests use temporary cache/vault roots. Testbed validation must leave production
  `VAULT_ROOT` unchanged.
- Stop if implementation requires changing schema v12, JSONL row/header format,
  or synchronized tombstone encoding.

## 7. Post-Change Evidence Slots

- [ ] Failing TDD tests captured before logic changes.
- [ ] Sync fail-closed focused tests pass.
- [ ] Policy fail-closed focused tests pass.
- [ ] Backend pytest/Ruff/Mypy pass.
- [ ] Plugin Vitest/TypeScript/build pass.
- [ ] `gaussian_splatting` testbed smoke passes.
- [ ] Consecutive real autosync + dry-run is quiescent.
- [ ] Version/spec consistency passes for v0.36.2.
