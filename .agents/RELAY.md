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

**Next action**: PR #78 open — awaiting human review/merge (then IDLE cleanup).

### Update (2026-07-02, Claude Code) — PR #78 review feedback addressed
Commit `0bbe2d1` on the branch:
1. Corrupt `.curator/zotero_profiles.json` no longer wipes data: read-vs-parse
   failure split (`parseZoteroProfilesFile`), corrupt JSON → read-only session
   + Notice, load guard stays unset so no overwrite.
2. Profile normalization requires string `name` ({}/junk dropped; empty-string
   names kept — settings UI allows blanking).
3. Migration saves wrapped (I/O failure logs + retries next load, never kills
   onload). 4. Committed the missed `package-lock.json` 0.30.0 bump (CI npm ci
   gate). 660 vitest + tsc green.

**Open from /code-review of PR #78 (not yet acted on — user decision pending)**:
- Stale-mirror LWW loss: `saveZoteroProfiles` writes without re-read/merge and
  no watcher on the file → unrelated settings save can erase a peer's newer
  profiles. (Candidate: read-merge-before-write like `saveSessionData`.)
- Unserialized profile writes: per-keystroke `saveSettings` overlaps
  `adapter.write` (candidate: settingsPersistPromise-style queue).
- MCP mutations never export (trigger hole persists for MCP-driven ingestion).
- Non-atomic snapshot export (no temp+rename) → cross-process corruption risk.
- `wiki update` exports up to 3×/run; duplicate LRU cap constant (50).

**User-facing follow-up (macOS)**: after merging + updating the plugin/backend
there, verify Dashboard shows 31/32 sources; if not, run
`wiki db autosync --dry-run` on each device to see which side is stale.
