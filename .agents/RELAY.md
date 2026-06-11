# Agent Relay State

## Current Active Goal
**[Minor Update] PDF Add-Source Asset Routing + "Added" State** (ROADMAP To-Do #1) — IMPLEMENTATION IN PROGRESS (user greenlit 2026-06-12).

## Plan Reference
- Master plan: `.agents/plans/04_pdf_add_source_assets.md` (+ arena)
- Evidence ledger: `.agents/plans/04_pdf_add_source_assets_evidence.md`

## Branch
`feature/pdf-add-source-assets` (off `master` @ aee4995, v0.5.5 → target v0.5.6)

## Analysis & Reasoning (P0 key finding)
Images are written during **`source register`** (instant L1 via
`generate_l1_structural_context` → `_save_pdf_images`), NOT during `source
import`. So the new CLI arg is `wiki plugin source register --asset-dir`
(the master plan's "import" mention is corrected in the evidence ledger).
Worker L2/L3 never re-writes images. "Added" badge set = exactly
`l1_ready/l2_ready/l3_ready/l4_ready` (no literal `ready` state exists).

## Progress Status
- P0 ✅ branch + fact-checks + evidence ledger
- P1 ⏳ specs (PLUGIN_SCHEMA) + guides (PLUGIN_GUIDE EN→KR)
- P2 backend (`_save_pdf_images(asset_dir=...)`, `_safe_vault_subdir`, register plumbing) + pytest
- P3 plugin (`incuratorPdfAssetFolder`, `--asset-dir` wiring, Added badge) + vitest
- P4 testbed smoke
- P5 release v0.5.6 (bump + CHANGELOG + plan deletion + PR)

## Immediate Next Action
Execute P1 (spec-first docs), then P2 backend TDD.
