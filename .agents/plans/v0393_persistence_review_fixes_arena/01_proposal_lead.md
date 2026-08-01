# Lead Architecture Proposal: Commit-Time Merge for Durable State
Date: 2026-08-01 | Agent Persona: Lead Architect

## 1. Core Logic & Implementation

The three findings share one rule: decisions that protect durable state must be
made from the state observed at the commit boundary. The implementation should
therefore keep the current per-path/per-adapter serialization, but move every
merge or permission decision inside the primitive that performs the commit.
No schema, command surface, migration, or version-line change is required.

### A. Merge project config from the locked current mapping

`save_config()` must stop replacing the mapping supplied by
`update_config_file()`. Its callback should begin with the freshly read mapping,
remove all machine-local top-level keys, and recursively merge the requested
vault-only snapshot into what remains. This retains peer-only top-level and
nested keys while preserving the invariant that `llm`, `search`, and `external`
never survive in synced project YAML. Same-key conflicts remain ordinary
last-writer-wins; this patch does not introduce field revisions or tombstones.

```python
def merge_project_config(existing: dict, requested: dict) -> dict:
    merged = copy.deepcopy(existing)
    for key in MACHINE_LOCAL_CONFIG_KEYS:
        merged.pop(key, None)
    vault_only = {
        key: value
        for key, value in requested.items()
        if key not in MACHINE_LOCAL_CONFIG_KEYS
    }
    return _merge_dict(merged, vault_only)

def save_config(paths, config):
    save_global_config(machine_local_subset(config))
    update_config_file(
        paths.config_file,
        lambda existing: merge_project_config(existing, config),
    )
```

The callback runs under the existing `locked_path()` scope, so there is no
second unlocked read and no new locking abstraction.

### B. Merge synced JSON inside Obsidian's atomic process callback

The current plugin queue prevents two calls in this JavaScript process from
overlapping, but `read -> merge -> temp rename` is not a cross-process compare
and swap. Extend `VaultTextAdapter` with the already-available synchronous
`process(path, update)` operation. For an existing valid canonical file,
session and profile persistence must parse, validate, merge, sanitize, and
serialize entirely inside that callback. Obsidian guarantees the file does not
change between the callback's read value and the committed value, so a
Syncthing arrival before commit becomes callback input instead of being
overwritten.

Keep the initial typed read because it drives missing/corrupt/unreadable UI and
migration behavior. Treat it only as classification, never as the merge input.
At commit time, parse the callback's raw value again. If it is corrupt or
structurally invalid, throw the existing blocked-state error from the callback;
`process()` must leave the canonical bytes unchanged. An I/O rejection likewise
marks the store read-only. The local promise queues remain in place to preserve
call ordering and in-memory state assignment.

```typescript
interface VaultTextAdapter {
  // existing methods omitted
  process(path: string, update: (raw: string) => string): Promise<string>;
}

async function commitMergedSession(adapter, path, local) {
  let committed: SessionData | undefined;
  await adapter.process(path, (currentRaw) => {
    const current = parseAndNormalizeSessionOrThrowBlocked(currentRaw);
    committed = sanitizeSessionDataForSync(
      mergeSessionData(local, current)
    );
    return JSON.stringify(committed, null, 2);
  });
  return committed!;
}

async function commitMergedProfiles(adapter, path, local) {
  let committed: ZoteroProfilesFile | undefined;
  await adapter.process(path, (currentRaw) => {
    const current = parseZoteroProfilesFile(currentRaw);
    if (current === null) throw new DurableStoreBlockedError("corrupt");
    committed = mergeZoteroProfilesFiles(current, local);
    return JSON.stringify(committed, null, 2);
  });
  return committed!;
}
```

Extract the profile commit function beside the existing profile merge/parser so
it can be tested without constructing the plugin class; `main.ts` should only
queue it, apply the returned committed mirror, and disable writes on failure.
The session equivalent stays in `sessionStore.ts`.

For a genuinely missing canonical store, retain the existing sanitized sibling
temp creation path used by first-run/legacy migration. Before taking that path,
re-check through `process()` when the adapter now reports the path exists; this
ensures a peer file delivered after classification is merged rather than
replaced. If `process()` rejects and the path now exists or is unreadable, fail
closed instead of falling back to creation. Ordinary saves after creation use
only `process()`. Do not add a retry loop around corruption or arbitrary I/O
failures.

### C. Select replacement mode before creating the temporary file

`mkstemp()` hard-codes a private initial mode, so it cannot represent normal
new-config permissions. Replace only the temp-file creation portion of
`atomic_write_text()` with a secure `os.open(..., O_CREAT | O_EXCL, 0o666)` on a
random same-directory sibling. `O_EXCL` preserves race safety and the kernel
applies the current process umask without reading or mutating the process-global
umask.

Under the caller's existing path lock, choose the final mode before writing:

1. Explicit `mode` wins (`secret_store` continues to pass `0o600`).
2. Otherwise, if the target exists, preserve `stat.S_IMODE(target.stat().st_mode)`.
3. Otherwise, leave the `os.open(..., 0o666)` result unchanged so normal umask
   semantics apply.

After writing and `fsync`, call `fchmod` on the open descriptor when a final
mode was selected, then close and `os.replace`. Keep unconditional sibling
cleanup. If stat, write, chmod, fsync, or replace fails, the prior target bytes
and mode remain untouched.

```python
existing_mode = (
    mode
    if mode is not None
    else stat.S_IMODE(path.stat().st_mode) if path.exists() else None
)
fd, temp_path = exclusive_same_dir_open(path, requested_mode=0o666)
try:
    write_flush_fsync(fd, text)
    if existing_mode is not None:
        os.fchmod(fd, existing_mode)
    close(fd)
    os.replace(temp_path, path)
finally:
    close_if_open(fd)
    temp_path.unlink(missing_ok=True)
```

### D. TDD and validation strategy

Add failing regression tests before implementation:

- Backend config: capture a stale full config snapshot, insert a peer-only
  top-level and nested key through `update_config_file()`, then call
  `save_config(stale_snapshot)`. Assert both peer keys survive, the requested
  local change is present, and seeded `llm`/`search`/`external` keys are absent
  from project YAML.
- Backend modes: verify an existing `0664` config remains `0664`; a new config
  gets `0o666 & ~current_umask`; an explicit secret file remains `0600`; and an
  injected `os.replace` failure preserves both original bytes and original
  mode while removing the temp sibling.
- Sessions: enhance the memory adapter with `process()`. Have it inject a valid
  peer session immediately before invoking the process callback. Assert the
  committed file contains initial, peer, and local sessions. Repeat with
  corruption injected at that boundary and assert rejection plus byte equality.
- Profiles: run the extracted profile commit helper against the same adversarial
  adapter, injecting a peer-only profile/recent item/tombstone immediately before
  the callback. Assert peer and local data survive and tombstone semantics are
  unchanged. Repeat with invalid callback input and assert fail-closed behavior.
- Interruption: make `process()` reject before committing and prove the original
  existing session/profile bytes remain. Retain the existing temp-rename cleanup
  test for missing-store creation.

Run focused backend durability/config tests plus focused plugin session/profile
tests first, then the repository's complete pytest, Ruff, mypy, plugin build,
and Vitest gates. No production vault or active testbed is needed or permitted.

## 2. Pros & Cons

**Pros**

- Fixes the root cause of both stale-merge findings: merging happens from the
  value protected by the actual commit primitive.
- Reuses existing backend locks, plugin queues, parsers, merge rules, and
  fail-closed errors; the change remains patch-sized.
- Preserves machine-local config separation, session/profile tombstones,
  corrupt-byte recovery, and explicit secret permissions.
- Uses the operating system's umask naturally instead of temporarily mutating
  the process-global umask, which would be unsafe during concurrent writes.
- Extracted profile persistence gives deterministic race tests without brittle
  `main.ts` integration scaffolding.

**Cons / Limits**

- `DataAdapter.process()` requires a synchronous callback, so parsing and merge
  logic inside it must remain pure and must not perform notices or other async
  work; callers handle UI state after rejection.
- A full project-config save can preserve unrelated keys, but without per-key
  revisions it cannot distinguish two concurrent edits to the same key;
  same-key conflict behavior remains last-writer-wins.
- First creation of a genuinely absent hidden file cannot use an existing-file
  read/modify primitive. The implementation must re-check before creation and
  fail closed if a peer appears; subsequent ordinary writes are protected by
  `process()`.
- Moving existing-file commits from explicit temp rename to Obsidian's atomic
  process primitive changes an internal persistence mechanism. Specs and paired
  guides should describe atomic commit-time merge without promising a specific
  temp filename for this path, while retaining the temp-cleanup guarantee for
  creation fallback.
