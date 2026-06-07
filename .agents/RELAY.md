# Relay State — IDLE (2026-06-07)

No active goal. Last shipped: `v0.4.1` (hotfix/v0.4.1-device-local-paths → PR pending merge).

## Last Completed Work
- Fixed machine-local config leakage: `llm/search/external` migrated from vault config to global cache on `load_config()`.
- Fixed `zotero_init()` to write Zotero roots to global config only.
- Fixed `runtime_state._source_summary()` to return portable `zotero://open-pdf/library/items/<key>` as `source_path`.
- Fixed plugin dashboard to always refresh local snapshots before reading sources (`readFreshRuntimeJson`).
- Fixed plugin `config set llm.fallback` to use global scope (no `--local`).

### Update (2026-06-07, Antigravity)
- Separated complex milestone details from `ROADMAP.md` into individual 1st-level analysis skeleton files under `.agents/plans/` (e.g. `minor_quick_wins.md`, `stabilization.md`). 
- Updated `ROADMAP.md` to cleanly list the To-Do queue with pointers to these `.agents/plans/*.md` files.
- Updated `AGENTS.md` and `CLAUDE.md` to formalize the rule: Agents must perform a 1st-level analysis and create a separate `.md` skeleton in `.agents/plans/` for complex requests, rather than bloat `ROADMAP.md`.