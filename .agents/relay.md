# Relay State — IDLE (2026-06-07)

No active goal. Last shipped: `v0.4.1` (hotfix/v0.4.1-device-local-paths → PR pending merge).

## Last Completed Work
- Fixed machine-local config leakage: `llm/search/external` migrated from vault config to global cache on `load_config()`.
- Fixed `zotero_init()` to write Zotero roots to global config only.
- Fixed `runtime_state._source_summary()` to return portable `zotero://open-pdf/library/items/<key>` as `source_path`.
- Fixed plugin dashboard to always refresh local snapshots before reading sources (`readFreshRuntimeJson`).
- Fixed plugin `config set llm.fallback` to use global scope (no `--local`).

### Update (2026-06-07, Antigravity)

- Committed and pushed residual unstaged changes (`deviceRegistry.ts`, `buildManifest.json`, etc.) to the `hotfix/v0.4.1-device-local-paths` branch.
- Synced and cleaned up `.agents/plans` based on `user_report.md` as ground truth (deleted completed `syncthing_auto_sync` plans, aligned headers in `minor_quick_wins.md`, `stabilization.md`, and `roadmap.md`), then committed and pushed these changes.
- Added `knowledge_sync_bridge.md` and `pdf_annotation_system.md` to `user_report.md`'s To-Do list, and synced their respective plan files to point back to the new `user_report.md` entries, followed by a commit and push.
