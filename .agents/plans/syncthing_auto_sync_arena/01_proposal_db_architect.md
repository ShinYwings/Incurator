# DB Architect Proposal: One-Writer-Per-File Topology + LWW Idempotent Loop Prevention

Date: 2026-06-07 | Agent Persona: DB Architect

## 1. Core Logic & Implementation

### 1.1 File topology — one export file per device

The reverted attempt used a single shared filename → guaranteed Syncthing write-write
conflicts. The fix is the **one-writer-per-file** rule (the same pattern CRDT folder
syncs use):

```
<vault>/.curator/sync/
├── dev-<deviceA>.jsonl      ← only device A ever WRITES this; others READ it
├── dev-<deviceB>.jsonl      ← only device B ever writes this
└── dev-<deviceC>.jsonl
```

- Each device exports **only its own** `dev-<id>.jsonl`. It **imports every peer file
  except its own**. No two devices write the same file ⇒ Syncthing produces **no
  write-write conflict** under normal operation.
- `device_id` comes from `.curator/devices.json` (already exists as a per-device local
  override per Shared Architecture Memory). If absent, generate a uuid4 once and persist.
- High-water-mark state lives in `.curator/sync_state.json` — **device-local, NOT in the
  synced `sync/` dir, and added to `.stignore`** so Syncthing never propagates it.

```json
// .curator/sync_state.json  (local only)
{
  "device_id": "deviceA",
  "peers": {
    "dev-deviceB.jsonl": { "last_imported_mtime": 1718000000.0, "last_max_ts": "2026-06-07T01:22:33Z" },
    "dev-deviceC.jsonl": { "last_imported_mtime": 1717900000.0, "last_max_ts": "2026-06-06T20:10:00Z" }
  }
}
```

### 1.2 Loop prevention WITHOUT a hash guard

The reverted hash guard was the disease. The correct prevention is structural:

1. **LWW is already idempotent.** Re-importing a row whose `updated_at` is not strictly
   greater than the local row is a no-op (`_lw_upsert` → `"skipped"`). Import copies the
   *source* timestamp; it never stamps `now()`. So importing the same data twice changes
   nothing.
2. **Import is not a "mutation" for auto-export purposes.** Auto-export is scheduled
   ONLY by user/CLI-initiated DB writes (`wiki add/build/sync/update`, promotions,
   tombstones) — never by `wiki db import`. This severs the export→import→export cycle
   at the source. A boolean `suppress_auto_export` context guards the import path.

Together these make `A.export → B.import → (B does real work) → B.export → A.import`
converge: A importing B's file only re-exports if A *itself* later mutates the DB.

### 1.3 Incremental (delta) export via high-water mark

Full exports grow unbounded (the large-file edge case). Use the existing
`export_knowledge(..., since=...)` parameter:

- On auto-export, write a **full** file the first time, then **incremental** files keyed
  by the device's own `last_export_ts` (stored in `sync_state.json`).
- Each `dev-<id>.jsonl` header records `min_ts` / `max_ts` so a fresh peer knows whether
  it needs a full re-bootstrap (request via a one-shot `wiki db export --full`).
- Tombstones (`deleted_records.deleted_at`) participate in the same `since` window.

### 1.4 New backend surface (thin, db_sync.py owns logic)

```python
# db_sync.py additions
def export_for_device(paths, *, full=False) -> ExportStats:
    """Write .curator/sync/dev-<id>.jsonl; incremental unless full. Updates sync_state."""

def import_all_peers(paths, *, dry_run=False) -> dict[str, ImportStats]:
    """Import every peer file newer than its recorded mtime; skip own + unchanged.
    Returns {filename: stats}. Honors suppress_auto_export."""

def detect_conflict_files(paths) -> list[Path]:
    """Return any .curator/sync/*.sync-conflict-*.jsonl present."""
```

CLI wrappers: `wiki db autosync` (import peers → export self, one shot, `--dry-run`),
reusing existing `wiki db export/import` for manual use.

## 2. Pros & Cons

**Pros**
- Eliminates write-write conflicts by construction (one writer per file).
- No hash guard ⇒ the `[PR 픽스]` bug cannot recur.
- Reuses `--since` and tombstones already in `db_sync.py`; **zero schema change**.
- All heavy I/O stays in the backend subprocess.

**Cons / limits**
- A brand-new device must do one full bootstrap import of every peer (O(total rows))
  once. Acceptable; one-time.
- `sync_state.json` must be reliably excluded from Syncthing (`.stignore`) or peers will
  fight over high-water marks. Mitigated by placing it outside `sync/` and documenting
  the `.stignore` entry.
- Per-device files accumulate if a device is retired. Need a `wiki db sync prune
  --older-than` housekeeping command (low priority, note in plan).
