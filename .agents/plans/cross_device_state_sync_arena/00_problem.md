# Briefing: Cross-Device State Sync (Zotero Profiles + Knowledge DB)

Date: 2026-07-02 | Source: user report + live vault forensics on `second_brain`

## 0. User Report (verbatim)
- "Zotero integration 할때 profiles 가 기기마다 다르게 뜸. 연동이 안돼..."
  (Zotero import profiles differ per device; integration doesn't sync.)
- "source 부분이 31개가 나와야하는데 아직도 5개만 나와요."
  (Dashboard Sources should show 31 but still shows 5.)
- Decision on scope (this session):
  - "sync db 해야지 그리고 db 안에 있는 파일들 상대경로 되어있지? reference path 변수랑 함께 말이야"
    → **Sync `state.sqlite`.** Confirmed the DB stores relative paths + portable
    reference-path variables.
  - DB write-safety strategy chosen: **Checkpoint + last-write-wins.**

## 1. Confirmed Root Cause (single family for BOTH symptoms)
Backend/plugin state that the user expects to be shared is deliberately
**device-local** via `.stignore`:

```
.obsidian/plugins/incurator-obsidian-agent/data.json   # holds zoteroProfiles + recentZoteroItems
.curator/state.sqlite                                   # holds source/L1-L4 tracking
```

- **Profiles differ per device** because `zoteroProfiles` + `recentZoteroItems`
  live in `data.json` (`plugin/src/types.ts:121-122`), persisted via
  `saveData()` → `data.json`, which `.stignore` excludes.
- **Sources show 5 not 31** because the note *files* in `03_Notes/` sync fine,
  but `state.sqlite` (which tracks *which files were ingested into L1-L4*) is
  `.stignore`'d and device-local. The user ingested 31 on linux; the other
  device's own DB only ever tracked 5. Verified: linux DB has 32 sources / 31
  L1-done; `wiki status --json` returns all 32; `renderSources` has no cap.
  **Not a UI bug — a sync/topology bug.**

## 2. Portability Forensics (why syncing the DB is path-safe)
Scanned **every TEXT column in every table** of `state.sqlite`:
**zero absolute paths.**
- `sources.relpath` — vault-relative (`03_Notes/...`, `04_Resources/...`).
- External/Zotero references use `path_refs.py` `PortablePathRef`: state stores
  `@<root_key>/<relpath>`; absolute roots resolve per-device from
  `external.path_roots` (machine-local config), never stored in the DB.
- The one reference-mode source stores identity only:
  `logical_source_id: zotero:PZBCB9LJ` + `zotero_attachment_key`, resolved
  per-device against each machine's Zotero DB.

→ **The only real hazard left is `PRAGMA journal_mode=WAL` + Syncthing**, not
paths.

## 3. The WAL/Syncthing Hazard
1. **Stale-main-file**: new rows live in `state.sqlite-wal` until checkpointed.
   `.stignore` excludes `*.sqlite-*`, so the WAL never ships; a receiver reads
   the stale main file. (This is literally the "5 vs 31".)
2. **Concurrent writers**: two backends writing at once → Syncthing
   `.sync-conflict` copies and possible corruption. This is why the DB was
   excluded originally.

## 4. Locked Decisions (from user this session)
- **Sync `state.sqlite`** (remove it from `.stignore`).
- **Keep WAL** but **checkpoint-truncate on close** so the main file is always
  complete before Syncthing picks it up (the `-wal`/`-shm` sidecars stay
  `.stignore`'d and are emptied by the truncate).
- **Last-write-wins**; surface `.sync-conflict` artifacts to the user rather
  than attempting an automatic 3-way DB merge.
- Keep the **search index** (`.curator/qmd/index.sqlite`) device-local
  (derived/disposable, rebuildable) — only the source-of-truth DB syncs.

## 5. Two-Part Scope
- **Part A — Zotero profiles** → move to `.curator/zotero_profiles.json`
  (identical to the already-shipped `sessions.json` migration). Pre-drafted in
  `.agents/drafts/zotero_profile_sync.md`.
- **Part B — Knowledge DB sync** → `.stignore` change + WAL checkpoint-truncate
  on close + one-time cross-device reconciliation guidance + docs.

## 6. Open Risks for the Arena to Resolve
- **R1 (schema_guardian)**: first-enable reconciliation — when we stop ignoring
  `state.sqlite`, the secondary device already has a divergent local DB.
  Syncthing will conflict. Need a safe, documented "authoritative device wins,
  wipe the other's local DB once" procedure + a stop-condition.
- **R2 (schema_guardian)**: cross-device schema drift — a device on a newer
  backend migrates the schema, then syncs to an older backend. Need a version
  guard / constraint (backends must match; plugin self-update already pushes
  this).
- **R3 (red_teamer)**: checkpoint-truncate cost/race — running
  `wal_checkpoint(TRUNCATE)` on every close vs only after mutating commands;
  ensure no reader/writer deadlock and acceptable latency.
- **R4 (red_teamer)**: partial-sync window — Syncthing ships the main file
  mid-write on the source device. Confirm checkpoint-on-close closes this
  window; document "don't build on two devices simultaneously".
