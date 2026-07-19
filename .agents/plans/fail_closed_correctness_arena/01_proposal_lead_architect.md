# Sync And Policy Proposal: Explicit Correctness Boundaries
Date: 2026-07-19 | Agent Persona: lead_architect

## 1. Core Logic & Implementation

### Sync-state boundary

Make `read_sync_state()` distinguish absence from corruption:

```python
if not path.exists():
    return {}
try:
    decoded = json.loads(path.read_text(encoding="utf-8"))
except (OSError, UnicodeError, json.JSONDecodeError) as exc:
    raise SyncStateError(path, exc) from exc
if not isinstance(decoded, dict):
    raise SyncStateError(path, "root must be an object")
validate device_id / peers / timestamp field shapes
return decoded
```

Only the absent-file result may reach `get_device_id()` without an id. Never
auto-repair or overwrite a malformed file.

### Peer/conflict boundary

- `import_all_peers()` must raise a contextual sync error when a peer snapshot
  cannot be imported; logging and continuing is false overall success.
- `_archive_conflict()` must allow filesystem errors to propagate.
- `autosync()` imports a conflict, then archives it. If archive fails after DB
  commit, the command fails visibly and the file remains for an idempotent retry.
- `db_autosync` converts known sync errors into `{ok:false,error:...}` for JSON
  callers and a red non-zero CLI failure for humans.
- Successful summaries may call a conflict “merged” only after archive succeeds.

### Tombstone boundary

Remove the broad catch around the primary-key delete. A failed `DELETE` aborts
the file transaction, so neither the applied counter nor propagated tombstone
commits. Dry-run remains read-only.

### Curation-policy boundary

Add one validated-spec loader and move duplicated policy resolution into a
`curate_yml` helper used by ContextService and QueryOrchestrator:

```python
def resolve_curation_policy(workspace_path):
    if not workspace_path: return default_policy, ""
    spec = load_curate_spec(workspace_path)
    if spec is None: return default_policy, ""
    errors = validate_curate_spec(spec)
    if errors: raise ValueError(...)
    return compile_curate_policy(spec, workspace_path), curate_spec_hash(workspace_path)
```

`load_curate_spec()` must reject a non-mapping `sources` block and wrong-shaped
`include`/`exclude` values instead of normalizing them to an unrestricted scope.
Preserve the currently accepted single string and list-of-strings forms.

Both curation-plan surfaces must call the same validated-spec loader before
`record_curation_plan()`. Validation errors return a failure and perform no DB
write. The validation-only MCP tool may still return an error list and compiled
preview because it has no persistence side effect.

## 2. Pros & Cons

### Pros

- Fixes root causes at the authoritative boundaries.
- Keeps retries safe through existing row-level idempotency.
- Removes duplicate policy behavior that can drift again.
- Avoids schema changes and compatibility layers.

### Cons

- One corrupt peer file can make explicit autosync fail until corrected.
- A conflict import may have committed before archive failure; the user sees a
  failed pass even though some rows changed. Retrying is required and safe.
- Stricter source-policy parsing may expose previously ignored malformed files.
