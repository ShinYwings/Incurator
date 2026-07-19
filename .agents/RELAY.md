# Relay State (IDLE)

- **Goal**: IDLE. No active task.
- **Plan Reference**: N/A
- **Branch**: `master`

### Progress Status
- The previous milestone (v0.34.0) has been successfully shipped and merged. The repository is clean and idle.

### Critical Context / Blockers
- N/A

### Immediate Next Action
- Wait for a new user request or an autonomous milestone trigger from `.agents/ROADMAP.md`.

### Update (2026-07-19, Codex) — v0.34.1 Knowledge Sync Loop Hotfix

- **Branch**: `hotfix/v0.34.1-knowledge-sync-loop` (independent worktree based
  on `master`; the active v0.35.0 PL-1 worktree is untouched).
- **User report**: Obsidian Knowledge Sync runs endlessly after v0.34.0; current
  Claude/Codex model catalogue is also stale.
- **Root-cause evidence**:
  - Production `second_brain` dry-run returned `updated=6650` and
    `would_export=true` for an already imported peer snapshot.
  - Composite-PK and no-revision rows are always counted as updated, so a fresh
    `export_id` on an unchanged full snapshot creates cross-device re-export
    ping-pong.
  - The plugin watcher is documented as peer-only but watches its own JSONL too.
  - Dry-run ignores an already-recorded peer `last_export_id`, so it does not
    preview the real pass.
- **Implemented**:
  - Current-schema imports resolve complete SQLite primary keys, apply LWW to
    composite rows, skip equal immutable content, and deterministically converge
    malformed immutable conflicts.
  - Dry-run honors recorded peer `last_export_id` state.
  - The plugin ignores its known self snapshot in the incoming-file watcher.
  - EN specs/guides were updated before the paired KR guides.
  - Backend/plugin/lockfile versions agree at `0.34.1`.
- **Validation**:
  - Production read-only before/after: `updated=6650` / `would_export=true` →
    `imported_files=0`, `updated=0`, `would_export=false`.
  - Backend: 1,214 passed, 6 skipped, 5 xfailed.
  - Ruff: pass; mypy: 125 source files, pass.
  - Plugin: 65 files, 670 tests; production build pass.
  - Gaussian Splatting testbed: migrate/add/sync/lint/reindex pass, lint 100/100,
    622 search documents/chunks. External Zotero-style Reference Mode produced
    one `is_reference=1` Markdown stub and zero PDF hard copies.
- **Critical context**: the active v0.35.0 PL-1 worktree and its user-owned
  `plugin/package-lock.json` change remain untouched. Current Claude/Codex model
  IDs and effort levels were verified separately for the v0.35.0 plan; do not
  mix that user-facing catalogue change into this patch hotfix.
- **Immediate next action**: push and open the v0.34.1 draft PR; after human
  review/merge, rebase the independent v0.35.0 release from `master`, incorporate
  the model-catalogue plan update, and resume PL-1.
