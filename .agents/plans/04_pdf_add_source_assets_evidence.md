# Evidence Ledger — PDF Add-Source Asset Routing + "Added" State (v0.5.6)

Date: 2026-06-12
Branch: `feature/pdf-add-source-assets` (off `master`)
Rollback anchor: `aee49954341999fa39f4a7cfd8fc3b863560829c` (master, post PR #22, v0.5.5)

## P0 Fact-Checks (verified against repo reality, 2026-06-12)

### 1. Where PDF images are actually written

- `backend/src/curator/ingest_raw.py::_save_pdf_images` (line ~1092) writes
  embedded PDF images to `paths.root / consts.DIR_ASSETS / <slug>/` and returns
  `obsidian_path = f"{consts.DIR_ASSETS}/{slug}/{filename}"`.
- Call sites:
  - `generate_l1_structural_context` (line ~1284) — the **instant L1** path used
    by `wiki plugin source register` (via `plugin_api.register_source`), the CLI,
    and MCP server.
  - `generate_l1_summary` non-instant path (line ~1566) — legacy full-LLM L1
    (`wiki add` with `llm.instant_l1: false`). NOT used by the plugin add-source
    flow.
- `ingest_worker.py` (L2/L3 build) does **not** call `_save_pdf_images` or any
  `generate_l1*` function — queued builds never re-write images.

### 2. CORRECTION to the master plan: `--asset-dir` belongs on `register`, not `import`

- Plugin add-source flow (`incuratorClient.ts::ingestPdf`, line ~170):
  `wiki plugin source import` (copy/reference the file only — `import_source_file`
  parses but never saves images) → `wiki plugin source register --build`
  (generates instant L1 → writes images).
- Therefore the new CLI arg is `wiki plugin source register --asset-dir`
  (plumbed `plugin_source_register` → `plugin_api.register_source` →
  `generate_l1_structural_context` → `_save_pdf_images`). The plan's
  "spec touch" line naming `source import` was written before this P0 check;
  P1 specs document the corrected location. No DB persistence of asset_dir
  (no schema change, per locked R6).

### 3. Plugin state vocabulary (post-build "ready" strings)

- `normalizeStatus` (incuratorClient.ts ~684): derives
  `l1_ready | l2_ready | l3_ready | l4_ready` from `state` + `l{1..4}_status`
  fields; `l1 && pending jobs > 0` → `queued`. There is **no literal `ready`
  state** in `IncuratorSourceState`; `normalizeState` maps a raw string
  containing "ready"/"done"/"index" → `l3_ready` and "curated" → `l4_ready`.
  → The "Added" badge set is exactly `l1_ready, l2_ready, l3_ready, l4_ready`.
- Badge labels: `chatSidebar.ts::getIncuratorStatusLabel` (~2043) currently maps
  the ready states to "L1 ready"… "L4 ready" — all clickable; clicking a built
  source falls through `onIncuratorStatusClick` (~2104) into re-ingest
  (Zotero auto-register or `IngestDestinationModal`). That re-ingest fallthrough
  is the bug decision B removes.

### 4. Reusables confirmed

- `plugin/src/zotero/assetLocalization.ts::resolveProfileAssetSpec` +
  `joinVaultPath` exist on master (shipped v0.5.5) — used to derive the Zotero
  profile asset folder for `--asset-dir`.
- Settings shape: `incuratorDefaultDestination` / `incuratorDefaultImportMode`
  live in `plugin/src/types.ts` (~104) + `DEFAULT_SETTINGS` (~186) + UI in
  `plugin/src/settings.ts` (~530-605). New `incuratorPdfAssetFolder` follows the
  same pattern.

## Current Dirty Worktree

- None. `master` was clean at branch time (post PR #22 merge; RAG plans A–F and
  arena folders are committed).

## Rollback Requirements

- Purely additive feature; no DB/schema/DAG change, no data migration.
- Rollback = revert/delete branch `feature/pdf-add-source-assets`; anchor above.

## Validation Log (filled per phase)

- P2 pre: `uv run --directory backend pytest -q` baseline green on branch start.
- (append results here)
