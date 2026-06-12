# Agent Relay State

## Current Active Goal
**[Corrective Follow-up] PDF Adaptive Routing Fix** (PR #23 Review Feedback)

## Plan Reference
- Corrective plan: `.agents/plans/06_pdf_adaptive_routing_fix.md`
- Master plan (shipped to PR): `.agents/plans/04_pdf_add_source_assets.md`

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
- [ ] Push updates to PR #23.

## Immediate Next Action
- Commit the verified correction, clean completed plan artifacts, and push PR #23.
