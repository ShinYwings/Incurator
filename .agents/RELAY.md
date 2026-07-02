# RELAY — v0.30.0 Cross-Device State Sync

**Branch**: `fix/zotero-profile-sync` — implementation complete, PR pending.

**Shipped in this branch**:
- Autosync trigger repair (the "5 vs 31 sources" fix): export hook after
  `add`/`build`/`sync`/`update`/`jobs run`, `auto_sync.enabled` default-on,
  `db autosync --dry-run` reports `would_export`.
- Zotero profiles → synced `.curator/zotero_profiles.json` (auto-migration
  from `data.json`).
- Docs: SYSTEM_BEHAVIOR §13.1, PLUGIN_SCHEMA, USER/PLUGIN/SYNC_IGNORE guides
  (+ KR). Version 0.30.0 across all manifests + 4 spec titles.
- Local CI: 1169 pytest / ruff / mypy / 655 vitest / tsc — all green.
- E2E peer simulation passed (device A add → export → device B import →
  identical sources).
- Production `second_brain`: `auto_sync.enabled` flipped to true; a fresh
  32-source snapshot was manually exported during diagnosis — once Syncthing
  ships it, the macOS device should converge after its next autosync pass.

**Next action**: push branch + open PR (then IDLE cleanup after merge).

**User-facing follow-up (macOS)**: after merging + updating the plugin/backend
there, verify Dashboard shows 31/32 sources; if not, run
`wiki db autosync --dry-run` on each device to see which side is stale.
