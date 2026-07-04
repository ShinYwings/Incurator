# Sync Identity Hotfix Briefing

Date: 2026-07-04

## Problem

The Linux Dashboard reports L1-L4 `32/0/0/0` while macOS reports
`28/353/1/1`. The Dashboard reads each local authoritative DB, so this is real
state divergence.

Production evidence shows:

- both devices use `device_id=0782dbcf0ff4`;
- only `.curator/sync/dev-0782dbcf0ff4.jsonl` exists;
- macOS `.curator/sync_state.json` records the shared id;
- production `.stignore` omits `.curator/sync_state.json`;
- `wiki db autosync --dry-run --json` reports zero peer files.

Both devices therefore classify the same JSONL file as their own, never import
it, and overwrite it independently.

## Constraints

- Both backends may run concurrently and either device may read while the other
  is writing. The user does not modify the same source file concurrently on
  both devices.
- Preserve `state.sqlite` schema 11 and row-level LWW behavior.
- Keep `.curator/sync/dev-*.jsonl` synchronized.
- Do not migrate or trust the shared `sync_state.json`.
- Machine-local state must live under the backend checkout's ignored `.cache`.
- Prove two-device convergence for sources and L2-L4 records.
- Concurrent reads and disjoint-file work must remain safe. General
  same-record concurrent-write reconciliation is out of scope.
