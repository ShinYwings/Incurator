# Durable Persistence Proposal: Atomic Merge Contracts Without State Regression
Date: 2026-08-01 | Agent Persona: Schema Guardian / Domain Validator

## 1. Core Logic & Implementation

### Repository reality and contract boundary

This follow-up changes no persisted schema and needs no migration. The existing
schemas and merge functions remain authoritative:

- `SessionData.deletedSessionIds` is a grow-only set of session-id tombstones.
  `mergeSessionData(local, current)` unions both tombstone sets before merging
  live sessions, so a stale peer copy cannot resurrect a deleted session.
- `ZoteroProfilesFile.deletedProfiles` is a name-keyed timestamp map.
  `mergeZoteroProfilesFiles(current, local)` keeps the maximum tombstone,
  removes profiles whose `lastUsedAt` is not newer than that tombstone, and
  permits an explicit recreation only when its timestamp is newer.
- `MACHINE_LOCAL_CONFIG_KEYS = {llm, search, external}` is a routing boundary,
  not ordinary synced data. These blocks must be absent from
  `.curator/settings.yml` even if an older or peer-written file still contains
  them.
- Existing corrupt or unreadable canonical JSON/YAML is recoverable evidence.
  No retry, merge, migration, or default initialization may overwrite it.

The defect is therefore not in the merge algorithms. It is that the merge sees
a pre-commit snapshot instead of the canonical bytes at the commit boundary.

### Obsidian session and profile commit boundary

Extend the internal `VaultTextAdapter` contract with the existing Obsidian
`DataAdapter.process(path, synchronousCallback): Promise<string>` operation.
The bundled Obsidian declaration describes this operation as atomically reading,
modifying, and saving a plaintext file. Official Obsidian Vault guidance also
states that `process()` guarantees the file does not change between the read and
write; it explicitly requires a synchronous modification callback. This is the
portable boundary for files in hidden `.curator/` storage and must be preferred
over desktop-only `FileSystemAdapter`, Node `fs`, advisory locks, or a
read/check/rename loop.

For an existing canonical session file, run validation, merge, sanitization,
and serialization inside the `process()` callback:

```typescript
adapter.process(path, (currentRaw) => {
  const current = parseAndValidateSession(currentRaw);
  if (!current.valid) throw new SessionStoreBlockedError("corrupt");
  result = sanitizeSessionDataForSync(mergeSessionData(local, current.value));
  return JSON.stringify(result, null, 2);
});
```

The callback must contain no `await`, Promise, notice, adapter call, or mutable
load operation. `normalizeSessionData()` alone is too permissive for this
boundary; malformed required session structure must continue to be classified
as corrupt before normalization. If the callback throws, `process()` must not
commit replacement bytes. An adapter read/process I/O rejection propagates
without converting the canonical file to `missing` or initializing defaults.
Only the known corrupt-state error disables further ordinary session writes for
the run; a generic write failure must not be mislabeled as canonical corruption.

Keep the existing adapter/path queue. It orders local saves and gives the next
queued save the prior committed in-memory result, while `process()` closes the
separate peer/external-writer race. Return and install the merged result only
after `process()` resolves successfully.

Apply the same boundary to Zotero profiles. The synchronous callback must call
`parseZoteroProfilesFile(currentRaw)` and refuse invalid shape/JSON, then call
`mergeZoteroProfilesFiles(current, local)`. Update `settings.zoteroProfiles`,
the recent-item LRU, and `deletedZoteroProfiles` only after a successful commit.
This preserves the existing maximum-timestamp tombstone and newer-recreation
rules exactly; do not replace them with array union, local replacement, or
last-callback-wins logic.

```typescript
adapter.process(ZOTERO_PROFILES_PATH, (currentRaw) => {
  const current = parseZoteroProfilesFile(currentRaw);
  if (current === null) throw new ProfileStoreBlockedError("corrupt");
  result = mergeZoteroProfilesFiles(current, local);
  return JSON.stringify(result, null, 2);
});
```

The pre-read may still distinguish genuinely missing state from present state,
but it is not data that an existing-file commit may merge against. A present
file must always be reparsed from the `process()` callback's `currentRaw`.
First creation and legacy migration have no existing value to merge and may
continue through the sibling-temp atomic creation path, followed by normal
`process()` commits. `DataAdapter` exposes no portable create-if-absent/CAS
primitive, so the implementation must not claim stronger simultaneous
first-creation exclusion or add desktop-only filesystem code. The regression
proof concerns an existing synced canonical file changed between an earlier
read and commit.

Update `PLUGIN_SCHEMA.md` and the paired session/profile guide text to replace
the overly specific claim that every valid existing write is a temp rename.
The locked behavior is: existing canonical files use adapter-atomic
read/merge/write; first creation may use sibling-temp replacement; corruption
always preserves canonical bytes; interrupted writes never publish partial
JSON. This is a persistence-mechanism clarification, not a `SessionData` or
`ZoteroProfilesFile` schema change.

### Project configuration merge under the lock

`save_config(paths, config)` receives a full, potentially stale effective
snapshot. Its updater must use the mapping freshly read by
`update_config_file()` while the per-target lock is held:

```python
def merge_project_config(existing: dict) -> dict:
    synced_current = {
        key: copy.deepcopy(value)
        for key, value in existing.items()
        if key not in MACHINE_LOCAL_CONFIG_KEYS
    }
    return _merge_dict(synced_current, vault_only)
```

This locks the following semantics:

1. Unknown peer-only top-level and nested keys absent from the stale snapshot
   survive.
2. Values explicitly present in `vault_only` remain local-wins, recursively;
   the current API has no base revision and therefore cannot resolve a
   concurrent same-key edit without a schema/provenance change.
3. Omission from the supplied full snapshot is not a deletion instruction.
   Explicit deletion must use an explicit updater in a future command, not
   infer deletion from stale absence.
4. Every machine-local top-level block found in current project YAML is removed
   before merging, and none can re-enter because `vault_only` excludes them.
   Their supplied values continue to route through `save_global_config()`.
5. Corrupt/non-mapping project YAML still raises `DurableStateError` before the
   updater runs and remains byte-identical.

The required test must load a stale snapshot, update project YAML with both a
peer-only top-level key and a peer-only nested key, then call `save_config()`.
Both peer keys must survive, the intended local update must commit, and seeded
`llm`, `search`, and `external` blocks must all be absent afterward.

### Atomic replacement and permission contract

`mkstemp()` always creates mode `0600`, so it cannot implement the required
default creation semantics by itself. Create the unique sibling temp with
`os.open(..., O_WRONLY | O_CREAT | O_EXCL, requested_mode)` and collision-safe
random naming. Keep it in the target directory so `os.replace()` stays on one
filesystem.

Select permissions before replacement as follows:

```text
explicit mode supplied:
    create temp, then set the exact explicit mode (secret/key stores: 0600)
existing target and no explicit mode:
    capture stat.S_IMODE(target.stat().st_mode)
    create temp, then set that exact captured mode
missing target and no explicit mode:
    create temp with requested 0666 and do not chmod it
    (the operating system applies the process umask normally)
write + flush + fsync temp; os.replace(temp, target); always clean temp on error
```

Mode capture and replacement should occur inside the caller's existing path
lock. Preserve permission bits only (`stat.S_IMODE`), not file type bits. Do not
copy ownership, ACL, xattrs, or platform-specific metadata in this patch; those
are different contracts and attempting partial emulation would expand scope.
On a failed `os.replace`, the original target bytes and original mode remain
unchanged, and the sibling temp is removed. Secret store and secret-key callers
must continue passing explicit `0o600`, so a permissive umask cannot weaken
credential storage.

POSIX permission proofs should be gated off on Windows because Windows ACL and
read-only semantics are not Unix mode semantics. Do not add an unconditional
POSIX-only import for the permission implementation, call `os.umask`, or assume
desktop filesystem paths in portable plugin code. For the new-file test, create a normal sibling control file through
Python's regular text-open path and compare its permission bits to the new
config; this verifies normal umask-derived behavior without temporarily
changing the process-global umask in a test runner. On POSIX, prove:

- an existing `0664` config remains `0664` after success;
- a new config has the same mode as a normally created control file;
- an explicit secret file is `0600`;
- an injected replacement failure preserves both existing bytes and `0664`
  mode and leaves no temp sibling.

### Adversarial plugin proofs

The mock adapter must implement `process()` with the same synchronous contract.
Before invoking its callback, it injects a peer update into the canonical raw
text; while the callback runs it must not permit a second change. Tests must
prove:

- sessions finish with the original, local, and injected peer session ids;
- a local session tombstone still suppresses an injected stale peer session;
- profiles finish with local and injected peer-only profiles/recent keys;
- an injected peer deletion tombstone prevents stale local profile
  resurrection, and a genuinely newer recreation still clears the tombstone;
- malformed callback input throws and leaves the exact canonical raw text
  unchanged;
- adapter process rejection leaves the previous canonical text unchanged;
- existing in-process queue tests still retain two overlapping local saves.

Tests should target the utility boundary directly rather than assert source-code
strings in `main.ts`. Source assertions may remain as smoke guards, but they are
not evidence of atomic semantics.

## 2. Pros & Cons

### Pros

- Uses Obsidian's documented portable atomic mutation primitive, so Syncthing or
  another writer cannot slip a valid update between the merge read and commit
  for an existing canonical file.
- Preserves all current session/profile schemas, sanitizer behavior, conflict
  precedence, and deletion tombstones.
- Fixes project lost updates without weakening the machine-local routing
  boundary or requiring a config schema revision.
- Preserves existing POSIX permissions, restores conventional umask behavior
  for new configs, and keeps secrets explicitly private.
- Keeps failure behavior fail-closed and testable with isolated adapters and
  temporary paths; no production vault or active testbed access is needed.

### Cons and explicit limitations

- `DataAdapter.process()` supports synchronous transforms only. Any future
  asynchronous merge input must be computed before the call and revalidated
  against the callback's current data; it cannot be awaited inside the
  callback.
- Obsidian exposes no portable create-if-absent/CAS primitive for hidden adapter
  paths. This patch closes the reproduced race for existing synced files but
  cannot promise exclusive simultaneous first creation without desktop-only
  filesystem behavior or a new storage design.
- `save_config()` still resolves concurrent writes to the same supplied key as
  local-wins. True three-way same-key conflict detection would require a base
  revision, patch API, or persisted version contract and is outside this patch.
- Replacing a POSIX file does not preserve ownership, ACLs, xattrs, or hard-link
  identity. Only permission bits are in the approved review scope.
- Windows permission assertions cannot establish `0664`/`0600` POSIX semantics;
  portable functional tests must run there while Unix mode tests remain POSIX-
  conditional.
