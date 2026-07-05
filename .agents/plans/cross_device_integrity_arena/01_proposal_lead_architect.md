# Cross-Device Integrity Proposal: Portable Keys, Local Replicas
Date: 2026-07-05 | Agent Persona: lead_architect

## 1. Core Logic & Implementation

### Storage boundary

Derive `<repo>/.cache/vaults/<sha256(resolved-vault-root)[:16]>/` and place
`state.sqlite`, runtime snapshots, staging, sync reports, event logs, rendered
PDF page text, PDF crops, and CLI temporary files there. Keep settings, JSONL
transport, sessions, Zotero profiles, and Collections projections in
`.curator/`.

Automatically relocate the one existing `.curator/state.sqlite` replica during
upgrade. After relocation, runtime code has no read fallback to the old path.
If both old and new DBs exist, fail instead of guessing which is authoritative.

### Database transport

Schema v12 adds:

```sql
ALTER TABLE sources ADD COLUMN sync_key TEXT;
CREATE UNIQUE INDEX idx_sources_sync_key ON sources(sync_key);
ALTER TABLE compiler_generations ADD COLUMN updated_at TEXT;
```

Backfill `sync_key` from the first portable identity available:
`zotero:<key>` / portable logical id, `external_ref`, then `vault:<relpath>`.
Backfill generation `updated_at` from discarded/published/created timestamps.

JSONL source import uses `sync_key`, never remote integer `id`. It records
`remote source id -> local source id` and rewrites every imported `source_id`
foreign key before applying child rows. Source tombstones also carry
`sync_key`.

Import accepts only `SYNC_TABLES` and only columns present in the target table.
Each export header gets a UUID `export_id`; peer high-water state keys on that
ID rather than filesystem mtime.

Source and generation revision triggers must produce a value greater than the
previous row revision even if the local wall clock is behind.

### Shared files

Move device event logs, dashboard snapshots, sync reports, and conflict archives
to the machine cache. Keep deterministic/per-record Collections projections in
`.curator`; make projection/index writes atomic and no-op when bytes are
unchanged. Preserve shared sessions during `wiki reset`. Serialize session and
profile-store writes and add profile deletion tombstones.

## 2. Pros & Cons

Pros:

- Numeric SQLite identities never cross the device boundary.
- A local replica can be rebuilt from portable snapshots without sharing WAL
  files.
- Storage placement is structural and no longer depends on `.stignore`.
- Snapshot replacement and deletion are explicit protocol events.

Cons:

- v11 snapshots cannot be imported by v12 code.
- Both devices must update before normal autosync resumes.
- Moving runtime snapshots requires coordinated backend/plugin path changes.

