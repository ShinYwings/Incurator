# Agent Relay State

## Current Active Goal
**[Corrective Follow-up] PDF Adaptive Routing Fix** (PR #23 Review Feedback)

## Plan Reference
- Completed corrective plan preserved in Git commit `2c85ea3`.

## Branch
`feature/pdf-add-source-assets` (PR #23, target v0.5.6)

## Analysis & Reasoning
- Review feedback addressed:
  1. Passive PDF chat auto-registration must be removed; only explicit Add Source allows permanent registration.
  2. Priority routing: Local PDF.js → Registered L1 CTX → read-only original parsing fallback.
  3. Context/toc_id-based lookup is allowed only after `l1_complete`.
  4. Block inappropriate `curator_query` for unregistered or L3-incomplete PDFs.
  5. Reuse existing CTX/source-span locator without DB migration.

## Progress Status
- [x] P0–P5 of `04_pdf_add_source_assets.md` implemented, PR #23 open.
- [x] Corrective plan drafted (`06_pdf_adaptive_routing_fix.md`).
- [x] User approved implementation on 2026-06-12.
- [x] Implement application code changes on the same branch.
- [x] Verify with TDD, full local CI, and testbed smoke.
- [x] Preserve and delete completed corrective plan artifacts.
- [x] Push updates and confirm PR #23 CI.
- [x] Deep logical audit of docs against current implementation.
- [x] Reconcile DB authority, adaptive PDF routing, CLI/plugin ingest split,
  sessionless query, correction proposal behavior, and internal links.
- [x] Verify backend 526 tests, plugin 361 tests, ruff, typecheck, plugin build,
  spec-sync guard, and internal links.
- [x] Push documentation audit follow-up (`26d2d98`) and confirm PR #23 CI.

## Immediate Next Action
- User reviews and merges PR #23.
