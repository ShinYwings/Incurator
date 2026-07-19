# v0.36.2 Fail-Closed Correctness Briefing

Date: 2026-07-19
Status: Arena briefing
Rollback anchor: `06e69058def994d4091a77790b2eeaf162da5393`

## 1. User Objective

The stability milestone is not complete when code is merely decomposed or when
tests are green. It must find and fix real behavior bugs, especially places
where the implementation and documentation disagree or an operation reports
success after its correctness precondition failed.

## 2. Reproduced Failures

Failure injection on the merged v0.36.1 baseline proves five paths:

1. An existing malformed device-local sync-state file is read as `{}`.
   `get_device_id()` then generates a new id and overwrites the corrupt state,
   silently changing snapshot ownership and discarding peer high-water marks.
2. A Syncthing conflict file can import successfully, fail to archive, remain in
   the synced directory, and still be counted/displayed as merged.
3. A tombstone `DELETE` exception is swallowed. The importer returns
   `applied=True`, leaves the target row alive, and records the tombstone for
   propagation.
4. A syntactically malformed workspace `curate.yml` is swallowed by both
   ContextService and QueryOrchestrator and becomes the unrestricted default
   policy with an empty policy hash.
5. A syntactically valid but wrong-shaped `sources:` block is normalized to an
   empty include/exclude policy, silently removing workspace source scope.

Current failure-injection observations:

```text
corrupt_sync_state: read_value={}, generated new device_id, corruption overwritten
conflict_archive_failure: counted imported, file remains
tombstone_delete_failure: reported_applied=true, row_exists=true, tombstone exists
malformed_curate_policy: both resolvers returned project=default, hash=""
wrong-shaped sources: parsed_include=[], policy_include=(), unrestricted=true
```

## 3. Contract Conflicts

- SYSTEM_BEHAVIOR §13.1 says conflict files are imported, archived, and surfaced;
  the implementation can surface “merged” without archive completion.
- SCHEMA §11.17 says a tombstone deletes the matching row; the implementation
  can propagate it without deleting locally.
- `load_curate_spec()` says an existing invalid file raises `ValueError`, while
  retrieval resolvers suppress that error and use defaults.
- SYSTEM_BEHAVIOR §16 says `curate.yml` compiles into the retrieval policy and
  invalid specs surface errors; the current path can erase source scope.
- Device identity is documented as generated once, but corrupt bookkeeping can
  silently generate it again.

## 4. Constraints

- Keep v0.36.2 a patch: no SQLite schema or JSONL schema change.
- A genuinely absent sync-state file remains the first-run case and may create
  a device id. An existing unreadable/malformed file must fail closed.
- Empty workspace context or a workspace with no `curate.yml` may use the
  documented default policy. An existing invalid file must never do so.
- Preserve per-file SQLite transactions. A multi-peer pass may be partially
  applied before a later file fails; retries are content-idempotent. It must not
  report overall success.
- Do not reintroduce snapshot content hashes or whole-file SQLite sync.
- Do not silently quarantine, rewrite, or delete corrupt user state.
- Do not change `03_Notes/`, `04_Resources/`, or production vault data during
  validation.

## 5. Required Evidence

- Failing tests must reproduce every failure above before application changes.
- Error responses must reach both human CLI and Obsidian plugin boundaries.
- A successful unchanged autosync must remain quiescent on two consecutive
  passes.
- Missing `curate.yml` default behavior must remain covered separately from
  invalid-existing-file failure.

