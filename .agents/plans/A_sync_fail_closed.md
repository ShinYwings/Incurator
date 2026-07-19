# Domain Analysis A: Cross-Device Sync Fail-Closed Boundaries

Date: 2026-07-19

## Design Constraints From Codebase

- `read_sync_state()` currently maps every exception to `{}` and feeds device-id
  generation, peer high-water marks, and export gating.
- `import_knowledge()` is transactional per file; `autosync()` is not one global
  transaction across all files.
- Row import is content-idempotent, so retry after partial per-file progress is
  safe.
- Conflict files must remain in the synced directory until both import and local
  archive complete.
- JSON CLI output is consumed by `IncuratorClient.dbAutosync()`.

## Docs/Specs Invariants

- Device id is stable and generated once.
- Snapshot loops are prevented structurally, never by a content hash.
- A conflict is “merged” only after import plus archive.
- Tombstones delete before upsert and the deleted count reflects applied state.
- Plugin sync failures use the existing failed status/notice path.

## Alternatives & Trade-Offs

1. **Auto-reset corrupt state**: rejected; destroys identity and high-water data.
2. **Log and continue peer failures**: rejected; preserves false success.
3. **Global multi-file transaction**: rejected; requires redesigning streaming
   imports and offers little benefit because per-file retry is idempotent.
4. **Structured failure collection with partial success UI**: viable later, but
   larger than needed. This patch stops at the first failed peer with context.

## Final Decision

- Typed sync-state/autosync errors with structured JSON boundary handling.
- Absence-only state initialization.
- Propagate peer import, conflict archive, and tombstone delete exceptions.
- Add a conflict to the success list only after archive completion.
- Keep schema v12 unchanged.

## Implementation Pseudocode

```python
state = read_sync_state_or_raise(existing_file)
for peer in peers:
    try:
        stats = import_knowledge(peer)
    except EXPECTED_SYNC_ERRORS as exc:
        raise AutosyncError(f"peer {peer.name} failed; retry is safe") from exc

for conflict in detected_conflicts:
    stats = import_knowledge(conflict)
    archive_conflict(conflict)  # raises
    result.imported[conflict.name] = stats
    result.conflicts.append(conflict.name)

DELETE target  # exception aborts import transaction
INSERT tombstone
```

