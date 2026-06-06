# Edge-Case Auditor Proposal: The Four Hazards + Reference-Mode + Security

Date: 2026-06-07 | Agent Persona: Edge-Case / Security Auditor

Maps directly to the four edge cases enumerated in `user_report.md`, plus two the user
did not list but that the codebase forces us to handle.

## 1. Core Logic & Implementation

### Hazard 1 — Syncthing `*.sync-conflict-*` files (user edge case #1)

With one-writer-per-file (DB Architect §1.1), true write-write conflicts are rare, but
they still occur if a device is cloned with a duplicate `device_id`, or if the user edits
`.curator/sync/` manually. Strategy:

- `detect_conflict_files()` globs `.curator/sync/*.sync-conflict-*`.
- **A conflict file is just another LWW-mergeable export.** Import it as an ordinary peer,
  then move it to `.curator/sync/_archive/<ts>/`. No user decision needed for data safety;
  the modal is informational + offers "show files" for the curious.
- Guard: never import a conflict file of the device's **own** id without first detecting
  duplicate-id misconfiguration → warn loudly ("two devices share an id; regenerate one").

### Hazard 2 — Obsidian-load vs Syncthing-download race (user edge case #2)

- On-load import is **not** terminal. The `fs.watch` (Plugin Expert §1.2) keeps running,
  so a peer file that lands 30 s after Obsidian opens triggers a live import + a
  "new sync data arrived — applied N changes" Notice.
- `sync_state.json` records `last_imported_mtime` per peer; the watcher re-imports only
  files whose mtime advanced, so a late delivery is never missed and never double-applied.

### Hazard 3 — Overwrite data loss on concurrent offline edits (user edge case #3)

- **Never whole-file replace.** Import is row-level LWW upsert (existing `_lw_upsert`) +
  tombstone reconciliation (existing `_apply_tombstone`). Both devices' newer-per-row
  edits survive; deletes propagate via `deleted_records`.
- Add a regression test: device A edits atom X at T2, device B deletes atom X at T1<T2,
  both sync → X survives (edit newer than tombstone), and the reverse ordering → X stays
  deleted. This locks the tie-break the user is worried about.

### Hazard 4 — Large JSONL freezes UI (user edge case #4)

- Parsing/DB writes stay in the **backend subprocess** — the Obsidian main thread only
  spawns it and reads a small JSON summary. No large-string handling in plugin JS.
- Incremental `--since` exports (DB Architect §1.3) keep per-sync files small.
- Status-bar `⟳ Syncing…` indicator covers the rare full-bootstrap case.

### Hazard 5 (codebase-forced) — Reference Mode path divergence

`sources.is_reference=1` rows carry `external_path` that is **device-specific** (a Zotero
storage path differs per machine). LWW on the whole row would clobber the local path with
a peer's path. Mitigation in `_lw_upsert`:

- For `sources` where `is_reference=1`, **preserve the local `external_path`** (and any
  local-only path columns) on update; merge all other columns by LWW. I.e. column-level
  exclusion for known device-local columns, not row-level replace.

### Hazard 6 (security) — Importing executable-ish content from synced files

JSONL import only writes DB rows; it never executes code. But:

- **Hard schema_version check stays** (already present): mismatched file aborts with a
  clear error — no silent partial import.
- Validate `table` ∈ allowlist (`SYNC_TABLES`) and ignore unknown tables (already done).
- Size/line sanity guard: refuse a file whose header claims a wildly different
  schema or whose first line is not a valid header (already done) — keep these.

## 2. Pros & Cons

**Pros**
- Every user-listed edge case has a concrete, testable mechanism.
- Reference-mode column-exclusion prevents a silent, hard-to-debug path corruption.
- Security posture: import is data-only, version-gated, allowlisted.

**Cons / limits**
- Column-level exclusion for reference sources adds a special case in `_lw_upsert` — must
  be unit-tested and documented in SCHEMA.md so future tables don't forget it.
- `_archive/` of conflict files can grow; needs the same prune housekeeping as retired
  device files.
