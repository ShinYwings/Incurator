# Relay State — IDLE (2026-06-07)

No active goal. Last shipped: `v0.4.1` (hotfix/v0.4.1-device-local-paths → PR pending merge).

## Last Completed Work
- Fixed machine-local config leakage: `llm/search/external` migrated from vault config to global cache on `load_config()`.
- Fixed `zotero_init()` to write Zotero roots to global config only.
- Fixed `runtime_state._source_summary()` to return portable `zotero://open-pdf/library/items/<key>` as `source_path`.
- Fixed plugin dashboard to always refresh local snapshots before reading sources (`readFreshRuntimeJson`).
- Fixed plugin `config set llm.fallback` to use global scope (no `--local`).
