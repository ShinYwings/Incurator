# Agent Relay State

## Current Active Goal
**[Minor Update] PDF Add-Source Asset Routing + "Added" State (v0.5.6)** — IMPLEMENTED. PR #23 review feedback addressed; awaiting user review/merge.

## Branch
`feature/pdf-add-source-assets` (off `master` @ aee4995). Version bumped to v0.5.6 (pyproject/package/manifest/lockfile agree).

## What shipped on this branch
- Backend: `wiki plugin source register --asset-dir` → `plugin_api.register_source`
  → `generate_l1_structural_context` → `_save_pdf_images(asset_dir=...)`, guarded
  by new `_safe_vault_subdir` (abs/`..`/escape → legacy `05_Assets/<slug>/`
  fallback; `obsidian_path` always matches the actual write root).
- Plugin: `incuratorPdfAssetFolder` setting (non-Zotero PDFs); Zotero PDFs reuse
  profile asset spec (`resolveProfileAssetSpec`) + display-name subfolder;
  `l1..l4_ready` badge states collapse to inert "Added" (click no-op, `is-added`
  style, tooltip keeps layer state).
- Specs/guides: PLUGIN_SCHEMA §1.1/§2.1/§4.1.1; PLUGIN_GUIDE EN+KR.
- Key P0 correction vs the original plan: `--asset-dir` lives on `register`
  (where instant-L1 writes images), NOT on `import`. Evidence ledger with full
  validation log is preserved in git history (deleted from worktree per Step 11).

## Validation
pytest 522 passed; ruff clean; mypy 84 pre-existing (no new); vitest 359 passed;
tsc clean; esbuild production OK; testbed smoke green (routed / unsafe-fallback /
legacy / queued-build / review-reroute cases). Smoke artifacts remain in
disposable `testbed/`.

## Immediate Next Action
User merges the v0.5.6 PR. After merge: truncate this file to IDLE, then the next
milestone is ROADMAP To-Do #1 (RAG & Knowledge Quality Stabilization, Batch 1
D1 → E → D2) — implementation still requires explicit user approval.
