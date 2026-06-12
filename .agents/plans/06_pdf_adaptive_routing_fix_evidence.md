# Evidence Ledger — PDF Adaptive Routing Corrective Follow-Up

Date: 2026-06-12
Branch: `feature/pdf-add-source-assets`
Rollback anchor: `a13afe1`

## Pre-Implementation Evidence

- Worktree was clean at planning start.
- Targeted backend routing/status/L1 tests: 24 passed.
- Targeted plugin capture/policy/client/format tests: 46 passed.
- Testbed source id 2:
  - `l1_status=done`, `l2_status=pending`, `l3_status=pending`;
  - CTX `CTX-ede97ed1` exists with `toc` and section markers;
  - `source_pdf_pages`: 2 metadata-only rows;
  - `source_spans`: 3 locator/preview rows.
- Verified defects:
  - passive auto-register at `chatSidebar.ts` provider-context path;
  - tracked `plugin_api.pdf_context` calls `parse_page_window`;
  - `fetch_document_section` reparses source;
  - no integration tests cover the intended adaptive handoff.

## Post-Implementation Evidence

- Passive provider-context registration removed; explicit Add Source remains the
  only plugin registration path.
- `plugin_api.pdf_context` and MCP `curator_get_pdf_context` now share one
  adaptive route:
  - registered + L1-complete + readable CTX:
    `context_source=durable_l1_projection`;
  - missing CTX or incomplete L1: read-only
    `context_source=ephemeral_parse` with `degraded_reason`;
  - unregistered read-only parse creates no source/job state.
- `fetch_document_section` serves inline exact CTX sections without reparsing.
  `source_text_policy=on_demand` continues to read the original source for exact
  evidence and reports visible degradation.
- Plugin status normalization now preserves `l1_complete` through
  `l4_complete`; active PDF-focused turns do not run concept-grounded
  `curator_query` until the active source is L3-complete.
- Targeted validation:
  - backend adaptive routing + asset safety: 27 passed;
  - plugin policy/client/source contract: 40 passed;
  - ruff changed files: passed;
  - TypeScript `tsc --noEmit`: passed.
- Full validation:
  - backend pytest: 526 passed;
  - plugin Vitest: 361 passed;
  - plugin production build: passed;
  - backend ruff: passed;
  - mypy: existing repository-wide baseline errors remain; no new errors in
    the adaptive routing code.
- Testbed smoke (`testbed`, existing PDF source id 2):
  - registered L1 request returned `durable_l1_projection`;
  - unregistered PDF copy returned `ephemeral_parse`, `source_tracked=false`;
  - source rows remained 2 → 2 and jobs remained 1 → 1;
  - temporarily hidden CTX returned
    `ephemeral_parse/degraded_reason=missing_l1_projection`;
  - CTX restored and test copy removed.
