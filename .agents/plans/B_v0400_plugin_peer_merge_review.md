# Plugin Peer-Merge Review Domain Analysis

## Design constraints from repository reality

- The current per-adapter/per-path promise queue orders local calls only.
  Syncthing or another peer can replace the canonical file between the queue's
  `read()` and sibling-temp `rename()`.
- `SessionData` uses grow-only `deletedSessionIds`; `ZoteroProfilesFile` uses
  timestamped `deletedProfiles`. Existing merge and normalization rules remain
  authoritative.
- Corrupt and unreadable canonical bytes are recoverable user data and must not
  be normalized into an empty store or overwritten.
- Obsidian `DataAdapter.process()` requires a synchronous callback and is the
  official atomic read/modify/save boundary for an existing plaintext file.

## API compatibility evidence

Official `obsidian-api` history adds `DataAdapter.process()` in the v1.1.0 API
update. The plugin declares `minAppVersion: 1.0.0`. Feature-detecting and using
the old racy path would retain the defect, so v0.40.0 raises the minimum to
1.1.0 and records v0.39.2/1.0.0 plus v0.40.0/1.1.0 in `versions.json`.

## Alternatives and trade-offs

- A preflight read followed by `process(() => precomputed)` is rejected because
  the callback still commits stale data.
- Node `fs`, advisory lock files, and desktop-specific paths are rejected: sync
  peers do not honor local advisory locks and the adapter is the supported
  abstraction.
- Retry-after-rename and exists/recheck loops are rejected as false CAS. The
  portable API cannot fully exclude simultaneous first creation; that limit is
  documented rather than hidden.
- Generic process failures do not prove corruption. Only strict typed parsing
  failures block the store for the run.

## Final decision and pseudocode

```typescript
async function processMergedStore(adapter, path, localSnapshot, parse, merge) {
  const committedRaw = await adapter.process(path, (currentRaw) => {
    const current = parse(currentRaw); // throws typed blocked error
    return JSON.stringify(merge(current, localSnapshot), null, 2);
  });
  return parse(committedRaw); // install only committed source of truth
}
```

Sessions sanitize after tombstone-aware merge. Profiles preserve maximum
deletion timestamps and the `lastUsedAt > deletedAt` recreation rule. Each
caller snapshots its local operand when enqueueing and installs the parsed
committed result only after success. Initial missing-store creation keeps the
temp replacement helper; cleanup covers both partial temp write and rename
failure. Existing stores never fall back from `process()` to racy replacement.
