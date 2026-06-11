# Master Implementation Plan — PDF Add-Source Asset Routing + "Added" State + Behavior

Date: 2026-06-11
Status: DRAFT — awaiting user approval (Arena concluded; user decisions A+B locked).
Priority: **TOP of ROADMAP** (per user). Target: patch on the 0.5 spec line (v0.5.6).

## Strict quality condition
- Add-source PDF images land in the **plugin-resolved asset folder** when provided,
  and **identically to today** (`05_Assets/<slug>/`) when not — zero regression.
- A successfully-tracked source shows a non-clickable **"Added"** badge; a
  `stale/moved/changed/error` source stays actionable/clickable.
- Embedded `![[...]]` image links always resolve to the file actually written.

## Locked design decisions (Arena Consensus + user)
1. **Asset routing = plugin passes `--asset-dir`** (user decision A). Zotero source →
   profile `assetFolder` via reused `resolveProfileAssetSpec`; non-Zotero → new
   `incuratorPdfAssetFolder` setting (default empty → omit → `05_Assets` fallback).
   Backend `_save_pdf_images` accepts `asset_dir`, guarded by `_safe_vault_subdir`
   (no `..`/abs escape), and derives the `obsidian_path` from the same root.
2. **"Added" badge = label + click-guard only** (user decision B). States
   `l1_ready/l2_ready/l3_ready/l4_ready/ready` → "Added", non-clickable; refresh
   re-derives `stale/moved/hash_drift` back to clickable. No new backend state.
3. **PDF math/VLM extraction is OUT of scope** → owned by RAG-stabilization plan B;
   this plan only cross-references it. Full annotation system + in-PDF search stay in
   ROADMAP #5.

## Evidence Ledger
- **Repo reality**: images written by `ingest_raw.py::_save_pdf_images` →
  `05_Assets/<slug>/`; add-source path = `incuratorClient.ingestPdf` →
  `wiki plugin source import` + `source register --build`; badge labels at
  `chatSidebar.ts:2055-2073`; status states from `normalizeStatus`
  (incuratorClient.ts:684-711). Reusable: `src/zotero/assetLocalization.ts`
  (`resolveProfileAssetSpec`) shipped v0.5.5.
- **Spec touch**: new hidden CLI arg `wiki plugin source import --asset-dir`
  (PLUGIN_SCHEMA §1) + new setting `incuratorPdfAssetFolder` (PLUGIN_SCHEMA §2.1).
- **Dirty worktree**: `feature/editor-latex-copy` (PR #22) + CODEX's uncommitted
  `.agents` RAG planning — both untouched by this plan.
- **Rollback**: additive; revert the branch. No DB/schema/DAG change (R6). No data
  migration.

## Execution Phases (TDD + CI at each phase)
- **P0 — Branch + fact-checks.** Branch from `master` (or `feature/editor-latex-copy`
  if user wants it bundled). Confirm the exact "ready/built" state strings the plugin
  emits post-build and the `source import` arg plumbing. Record in evidence ledger.
- **P1 — Spec + docs (spec-first).** PLUGIN_SCHEMA: `--asset-dir` arg + status→label
  "Added" mapping + `incuratorPdfAssetFolder`. PLUGIN_GUIDE EN then KR: what
  add-source ingests (L1 now, L2/L3 queued), where assets go, the "Added" state, and
  a note that PDF math fidelity is tracked by RAG plan B.
- **P2 — Backend (pytest first).** `_save_pdf_images(asset_dir=...)` +
  `_safe_vault_subdir`; `source import --asset-dir` plumbing. Tests: asset_dir used;
  `..`/abs/empty → safe fallback; `obsidian_path` matches write root; no asset_dir →
  legacy `05_Assets/<slug>/`. `ruff` + `mypy` (no new errors).
- **P3 — Plugin (vitest first).** `incuratorPdfAssetFolder` setting; ingestPdf passes
  `--asset-dir`; Zotero vs non-Zotero resolution; badge label map adds "Added" for
  the ready states; `onIncuratorStatusClick` no-ops on Added; `is-added` style.
  Tests: label-per-state, click-guard, asset-dir arg wiring (source assertions).
- **P4 — Testbed smoke.** Add a non-Zotero local PDF and a Zotero Reference-Mode PDF;
  verify L1 page + queued L2/L3, assets in the chosen vs fallback folder, embeds
  resolve, badge shows "Added" and is inert; move the file → badge becomes actionable.
- **P5 — Release.** Bump 0.5.6 (manifest/package/pyproject) + CHANGELOG; delete this
  plan + arena; PR (or merge onto the active branch per user). Update ROADMAP.

## Open question for approval
- Branch placement: a fresh `fix/pdf-add-source-assets` off `master`, OR bundle onto
  the current `feature/editor-latex-copy` (PR #22) like the last bugfix batch?
  (Recommend: fresh branch off `master`, since PR #22 is already large — but will
  follow your call.)
