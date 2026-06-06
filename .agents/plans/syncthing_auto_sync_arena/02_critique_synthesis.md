# Cross-Critique & Consensus

Date: 2026-06-07 | Participants: DB Architect, Plugin Expert, Edge-Case Auditor

## 1. Vulnerabilities & Flaws raised

### Auditor → DB Architect
- **"`sync_state.json` leaking into Syncthing recreates the loop disease."** If the local
  high-water-mark file is synced, peers overwrite each other's marks and re-import storms
  happen. → **Accepted.** Consensus: `sync_state.json` lives directly under `.curator/`
  (NOT under the synced `sync/` dir is not enough — `.curator/` itself is synced). It MUST
  be added to `.stignore`, and the plan's P1 includes the `.stignore` entry + a test that
  asserts the file is gitignored/stignored. This is a release blocker, not a nicety.

### Plugin Expert → DB Architect
- **"`wiki db autosync` doing import-then-export in one call can still ping-pong if export
  always runs."** → **Accepted & refined.** `autosync` exports self **only if the local DB
  actually changed since `last_export_ts`** (compare max(updated_at) vs stored mark). A
  pure import pass with no local mutation writes no new self-file. This is the structural
  loop cut, complementing "import is not a mutation."

### DB Architect → Plugin Expert
- **"`fs.watch` is unreliable; you'll miss events and users will think sync is broken."**
  → **Accepted.** Consensus: `fs.watch` is best-effort; a `registerInterval` poll (default
  60 s) that calls the same debounced import is the safety net. Both feed one coalescing
  scheduler so we never run two imports at once.

### Auditor → Plugin Expert
- **"Mobile has no Node `fs` — your watcher will throw on load."** → **Accepted.** Feature-
  detect `require("fs")`; on failure, disable watch + poll, keep on-load + manual button.
  Wrap in try/catch so plugin load never fails.

### DB Architect → Auditor
- **"Column-level exclusion for reference sources is fragile if new device-local columns
  appear later."** → **Accepted.** Centralize the exclusion list as
  `_DEVICE_LOCAL_COLUMNS: dict[table, set[col]]` next to `EXCLUDE_TABLES` in `db_sync.py`,
  documented in SCHEMA.md, with a test. Future columns get added in one place.

## 2. Locked Consensus (carried into the Master Plan)

1. **Topology**: one `dev-<id>.jsonl` per device under `.curator/sync/`; import all peers
   except own. No shared file.
2. **Loop prevention = structural, not hash-based**: (a) LWW idempotency with preserved
   source timestamps, (b) import never schedules auto-export, (c) `autosync` exports self
   only when local DB changed since `last_export_ts`. **No `sync_meta.json` hash guard —
   ever.** A test must assert `import` after `export` still reports/applies the true delta.
3. **State file**: `.curator/sync_state.json`, device-local, in `.stignore`. Release
   blocker test for exclusion.
4. **Triggers**: on-load + `fs.watch` (desktop) + 60 s poll fallback + manual ribbon;
   backend fires export at end of mutating commands. Never on `vault.on("modify")`.
5. **Edge cases**: conflict files → import-as-peer then archive; race → live watcher +
   per-peer mtime marks; overwrite → row-level LWW + tombstone (no whole-file replace);
   large files → backend subprocess + incremental `--since` + status indicator.
6. **Reference safety**: `_DEVICE_LOCAL_COLUMNS` column-level exclusion for
   `sources.external_path` when `is_reference=1`.
7. **Security**: data-only import, hard `schema_version` gate, table allowlist (all already
   present — keep, add tests).
8. **No SQLite schema change.** `SCHEMA_VERSION` stays 7.

## 3. Open question deferred (not blocking)

- Retired-device file pruning (`wiki db sync prune --older-than`) and `_archive/` cleanup:
  noted as a P-later housekeeping task, not in the first implementation slice.
