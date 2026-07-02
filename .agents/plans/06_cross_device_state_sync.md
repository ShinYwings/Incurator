# v0.30.0 Master Implementation Plan — Cross-Device State Sync

Date: 2026-07-02
Status: APPROVED (user: "straight wo stops") — **PIVOTED at P1** after spec
reconciliation; see §0. Arena briefing:
`cross_device_state_sync_arena/00_problem.md`.

## 0. P1 PIVOT — Part B redirected from raw-file sync to autosync-trigger repair

During P1 docs-first review, SYSTEM_BEHAVIOR **§13.1 (Syncthing Auto-Sync,
One-Writer-Per-File)** surfaced: a shipped, spec-locked cross-device DB sync
already exists. `state.sqlite` is *intentionally* device-local; knowledge
crosses devices via per-device `.curator/sync/dev-<id>.jsonl` full snapshots
with row-level LWW + tombstones. `SYNC_TABLES` covers all 26 knowledge tables
including `sources`.

Live forensics on `second_brain` proved the "5 vs 31" bug is a **trigger hole**
in this existing mechanism, not a missing file sync:

- linux export snapshot was stale (5 sources, from Jun 30) while the DB had 32;
  macOS faithfully imported the stale snapshot → shows 5.
- Trigger chain dead on linux: plugin `incuratorEnabled=false` (CLI-primary
  device) disables `setupAutoSync()` entirely; CLI `auto_sync.enabled` defaults
  `false`; and `_maybe_auto_export` is wired **only into `wiki update`** even
  though `config.py` documents add/build/sync/update (code/doc divergence).
- A manual `wiki db autosync` exported all 32 sources correctly → the
  mechanism works; only the triggers fail.

Raw-file syncing `state.sqlite` (original Part B) would **fight** §13.1: two
transports for the same rows, whole-file LWW destroying row-level merges,
`sync_state.json` high-water marks desyncing. Per CLAUDE.md, specs win over
plans → Part B is now **autosync trigger repair** (same user-visible outcome:
all devices converge to the same source counts). The original Part B artifacts
(WAL checkpoint-truncate, schema-drift guard, `.stignore` change) are dropped;
their P0 RED tests are deleted.

## 1. Objective
Make the two pieces of state the user expects to be shared across their linux +
macOS devices actually sync through Syncthing:

- **A. Zotero import profiles** (`zoteroProfiles`, `recentZoteroItems`) —
  currently in the `.stignore`'d `data.json`; move to
  `.curator/zotero_profiles.json` (synced, like `sessions.json`).
- **B. Knowledge DB visibility** — repair the §13.1 autosync trigger hole so
  every device's Dashboard converges to the same source/L1 counts (the
  "31 vs 5" fix), without touching the `.stignore` contract:
  - **B1**: wire `_maybe_auto_export` into every mutating CLI command it
    documents (`add`, `build`, `sync`, `update`) — today only `update` has it.
  - **B2**: flip the `auto_sync.enabled` default to `true` (opt-out). The
    incident happened because three opt-ins all defaulted off; without
    Syncthing the export is a harmless local file.
  - **B3**: `wiki db autosync --dry-run` must report whether an export would
    run (the observability gap that hid this bug).

**Definition of done**: A profile created on device A appears on device B after
sync; after `wiki add`/`build`/`sync`/`update` on device A, the fresh
`dev-<id>.jsonl` snapshot ships via Syncthing and device B's import converges
its Dashboard to the same counts.

## 2. Explicit Non-Goals
- **No raw-file syncing of `state.sqlite`** — rejected at P1; conflicts with
  the shipped §13.1 row-level LWW architecture (see §0).
- **No thin-client / B-mode MCP topology** this milestone (that remains the
  documented long-term direction, deferred).
- **No changes to the LWW/tombstone merge semantics** of `db_sync.py` — only
  trigger coverage and observability change.
- **No syncing of the derived search index** (`.curator/qmd/index.sqlite`) — it
  stays device-local and rebuildable.
- **No change to `path_refs.py` / reference-path encoding** — already portable
  (verified: zero absolute paths in the DB).
- **No plugin trigger change** — `incuratorEnabled=false` legitimately turns
  the plugin off on CLI-primary devices; B1/B2 cover those devices via the CLI.

## 3. Strict Quality Conditions & Release Gates
- After `wiki add`/`build`/`sync`/`update` with default config, the device's
  `.curator/sync/dev-<id>.jsonl` reflects the post-mutation state — asserted by
  pytest for each command path.
- Peer simulation: import of that snapshot into a second (empty) vault DB
  yields identical `sources` counts — pytest + testbed smoke.
- `wiki db autosync --dry-run` reports export intent without writing.
- `data.json` no longer contains `zoteroProfiles` or `recentZoteroItems` after
  migration; `.curator/zotero_profiles.json` contains them.
- No profile loss across the migration (legacy values preserved).
- 100% tests passing; `ruff`, `mypy`, `vitest` clean.

## 4. Locked Design Decisions (Arena Consensus, revised at P1 pivot)
1. **Profiles → `.curator/zotero_profiles.json`**, shape
   `{ profiles: ZoteroImportProfile[]; recentItems: string[] }`. One-way,
   non-destructive migration from `data.json` on first load (mirror
   `loadSessionData`). Last-write-wins (profiles are rarely edited; no
   append-merge needed, unlike sessions).
2. **`state.sqlite` stays in `.stignore`** (per §13.1). The JSONL snapshots in
   `.curator/sync/` remain the only cross-device DB transport.
3. **`_maybe_auto_export` after every mutating command** (`add`, `build`,
   `sync`, `update`) — honoring the contract `config.py` already documents.
   Best-effort semantics preserved (failure never breaks the host command).
4. **`auto_sync.enabled` default flips to `true`** (opt-out). Spec §13.1 and
   guides updated from "opt-in" to "default-on". Explicit `enabled: false` in
   `settings.yml` still disables it.
5. **Dry-run observability**: `AutosyncResult` gains a `would_export` signal
   surfaced by `wiki db autosync --dry-run`.
6. **Production vault activation**: `second_brain/.curator/settings.yml`
   currently pins `auto_sync.enabled: false` (stamped by init, not a user
   choice); flip it during final validation so the fix is live.
   (Dropped at pivot: WAL checkpoint-truncate, schema-drift guard, `.stignore`
   edits, first-enable reconciliation — all raw-file-sync artifacts.)

## 5. Scope Exclusions & Stop Conditions
- **Exclusions**: thin-client topology; LWW merge-semantics changes;
  search-index sync; plugin trigger rework.
- **Stop Conditions**:
  - Stop if wiring `_maybe_auto_export` into `add`/`build`/`sync` surfaces an
    ordering hazard (export firing mid-job while background workers still
    mutate) → reassess placement.
  - Stop if the default flip breaks any existing autosync test in a way that
    implies a real behavioral regression (not just an updated expectation).
  - Stop and ask before changing anything else in the production vault beyond
    the `auto_sync.enabled` flip.

## 6. Evidence Ledger
- **Repo/schema reality**: `sources` table verified on live `second_brain`:
  32 rows, 31 `l1_status='done'`, 1 reference-mode; **no absolute paths in any
  table** (full scan). `PRAGMA journal_mode=wal` confirmed.
- **Current `.stignore`** (vault + `backend/.../templates/stignore.template`):
  excludes `.curator/state.sqlite`, `.curator/qmd/index.sqlite`, `*.sqlite-*`,
  `*.db-*`, `data.json`.
- **Anchors**: plugin `main.ts:1313-1376` (`sessions.json` load/save +
  legacy-migration pattern to mirror); `db/schema.py:1353-1370` (`connect()`
  context manager — checkpoint-truncate goes after `conn.commit()`).
- **Dirty worktree**: `plugin/package-lock.json` (M), untracked
  `.agents/drafts/sidechat_ui_regression_v0.29.0.md` (unrelated). Branch
  `fix/zotero-profile-sync`.
- **Rollback anchor**: created at coding start in
  `06_roadmap_evidence.md` (git SHA + a copy of the vault DB before any
  `.stignore`/checkpoint change).
- **Versions**: all three manifests at `0.29.1` → target `0.30.0` (Minor: new
  sync behavior + `.stignore` contract change).

## 7. Execution Phases (TDD + CI each phase)
- **P0 — Baseline & rollback anchor** *(done)*: snapshot `wiki status --json`
  counts; copy `state.sqlite`; `06_roadmap_evidence.md`. RED tests written for
  the original Part B — **deleted at the pivot** and replaced by P2 RED tests
  below.
- **P1 — Contract specs (docs-first)** *(pivoted)*:
  - `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md` §13.1: auto-export runs
    after every mutating CLI command; `auto_sync.enabled` is default-on
    (opt-out); dry-run reports export intent. Bump spec title to `v0.30`.
  - `docs/guides/SYNC_IGNORE_GUIDE.md` (+ `_KR`): correct the stale §Best
    Practices claim (the DB holds no machine paths; it stays local because the
    JSONL transport syncs the knowledge); document the default-on flip.
  - `docs/guides/PLUGIN_GUIDE.md` (+ `_KR`): Zotero profiles now sync via
    `.curator/zotero_profiles.json`; note `incuratorEnabled=false` also turns
    off plugin-side autosync triggers (CLI export covers such devices).
- **P2 — Backend trigger repair (TDD)**:
  - RED: pytest — `add`/`build`/`sync` do not export today (only `update`
    does); config default is `false`; dry-run silent about export.
  - GREEN: wire `_maybe_auto_export` into `add`/`build`/`sync`; flip
    `config.py` default; `would_export` in `AutosyncResult` + CLI dry-run
    output. `scripts/backend-check pytest/ruff/mypy` green.
- **P3 — Plugin profile migration**:
  - `main.ts`: `_zoteroProfilesPath`, `loadZoteroProfiles()`,
    `saveZoteroProfiles()`, in-memory `zoteroProfiles`/`recentZoteroItems`;
    strip both from `_persistableSettings()`; migrate from `data.json`.
  - `types.ts`: add `ZoteroProfilesFile`; route `PluginSettings` reads through
    plugin accessors (update `settings.ts`, `zoteroWizardModal.ts`,
    `incuratorClient.ts` read/write sites). `.test.ts` for load/migrate/save.
- **P4 — Integration**: wizard/settings/client read the synced profiles;
  vitest green.
- **P5 — Testbed smoke / peer simulation**: `wiki testbed init`; mutate in
  `testbed/`; verify fresh `dev-<id>.jsonl`; import into a second empty DB and
  compare `sources` counts. Flip `auto_sync.enabled: true` in the production
  vault. Then version bump `0.30.0` + `CHANGELOG.md` + four spec titles →
  `v0.30`.
