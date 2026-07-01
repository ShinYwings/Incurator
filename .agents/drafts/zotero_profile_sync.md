# Deep Analysis: Zotero Profile Cross-Device Sync Failure

## 0. Problem Statement
The user reports: "Zotero integration 할때 profiles 가 기기마다 다르게 뜸. 연동이 안돼..."
("When doing Zotero integration, profiles show up differently on each device. The integration doesn't work...")

## 1. Root Cause

### Storage Location of `zoteroProfiles`
`zoteroProfiles: ZoteroImportProfile[]` lives in `PluginSettings` (`types.ts` line 121).
Plugin settings are persisted via `persistSettings()` → `this.saveData(this._persistableSettings())` → Obsidian's `saveData` API → `.obsidian/plugins/incurator-obsidian-agent/data.json`.

This path is **not synced** by Obsidian Sync (plugin data is excluded from Sync by default), and **not synced** by Syncthing unless the user explicitly includes `.obsidian/` in their sync scope (uncommon and inadvisable — it contains device-specific data).

### Why Profiles Are Portable
`ZoteroImportProfile` contains only:
- `name` — string
- `templatePath` — vault-relative path
- `outputFolder`, `outputSubfolder`, `outputFilename` — vault-relative paths
- `assetFolder`, `assetSubfolder` — vault-relative paths
- `bibliographyStyle`, `lastUsedAt` — string / number

**No absolute paths. No device-specific data.** They are perfectly portable across devices.

### Established Pattern
The project already solved this exact problem for chat sessions: `SessionData` was moved from `data.json` to `.curator/sessions.json` (inside the vault, synced by Syncthing). The same solution applies here.

## 2. Scope of Change

### Files to Change
- `plugin/main.ts`: Add `_zoteroProfilesPath`, `loadZoteroProfiles()`, `saveZoteroProfiles()`. Migrate profiles from `data.json` on first load. Strip `zoteroProfiles` and `recentZoteroItems` from `_persistableSettings()`.
- `plugin/src/types.ts`: Remove `zoteroProfiles` and `recentZoteroItems` from `PluginSettings` (move to a new standalone type `ZoteroProfilesFile`).
- `plugin/src/settings.ts`: Update all read/write sites (`this.plugin.settings.zoteroProfiles`) to use a new accessor or property on the plugin.

### Files NOT to Change
- `ZoteroImportProfile` type definition — no fields change.
- Backend — Zotero profiles are plugin-only.
- Sessions handling — already correct.

## 3. New Storage Location
`.curator/zotero_profiles.json` — vault-resident, Syncthing-synced, identical to sessions pattern.

```typescript
interface ZoteroProfilesFile {
  profiles: ZoteroImportProfile[];
  recentItems: string[];
}
```

## 4. Migration Plan
On `loadZoteroProfiles()`:
1. Try to read `.curator/zotero_profiles.json`.
2. If missing, check `this.settings.zoteroProfiles` (legacy `data.json`).
3. If found in legacy, migrate: write to `.curator/zotero_profiles.json`, clear from settings, persist settings.
4. Store in a new top-level field `this.zoteroProfiles: ZoteroImportProfile[]` on the plugin.

## 5. `recentZoteroItems`
Also `recentZoteroItems: string[]` in settings. These are Zotero item keys (e.g. `PZBCB9LJ`) — portable, not device-specific. They should also move to `.curator/zotero_profiles.json`.

## 6. Risk Assessment
- **Low risk**: Pattern is identical to sessions migration (already battle-tested).
- **Migration is one-way and non-destructive**: profiles remain in `data.json` until successfully migrated.
- **No backend impact**: Zotero profiles are plugin-only.
- **Sync conflict resolution**: Last-write-wins (Syncthing default). Profiles are edited rarely and are not append-only like sessions, so no merge strategy needed.

## 7. Success Criteria
1. Creating a Zotero import profile on Device A appears on Device B after Syncthing sync.
2. Existing profiles are not lost after upgrade (migration preserved them).
3. `data.json` no longer contains `zoteroProfiles` or `recentZoteroItems`.
4. TypeScript compiles clean; tests pass.
