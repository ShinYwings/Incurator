# v0.5.6 PDF Adaptive Routing Corrective Plan

Date: 2026-06-12
Status: IMPLEMENTED — final verification and PR update pending.
Arena: `.agents/plans/pdf_adaptive_routing_fix_arena/`
Branch: `feature/pdf-add-source-assets` / PR #23

## Strict Quality Condition

- Passive PDF viewing/chat creates no source row, reference stub, CTX, asset, or
  ingest job.
- Local PDF.js text/selection/crop stays the first and fastest context source.
- Explicit Add Source remains the only plugin registration path.
- Registered + L1-complete fallback/section requests are served from durable L1
  CTX/source-span locators without reparsing the PDF.
- Missing/stale durable projection degrades visibly to read-only PDF parsing.
- Unregistered and L1-only PDF-specific turns are never presented as
  concept-grounded `curator_query` results.

## Locked Design Decisions

1. Remove passive `registerSource()` from provider-context assembly.
2. Adaptive routing is priority-based:
   local explicit/viewer context → durable L1 projection → ephemeral backend
   parse fallback.
3. Durable routing requires `registered && l1_complete`; tracked import rows
   without L1 do not qualify.
4. Reuse current `source_spans.toc_id`, `sources.context_id`, and CTX section
   markers. No DB migration in this corrective PR.
5. Backend responses expose `context_source` and optional `degraded_reason`.
6. CTX is a derived durable read projection, not SQLite source truth. If absent,
   fallback parses the original source without mutation.
7. `curator_query` remains an L3/workspace operation, distinct from L1 section
   serving. PDF-focused turns with an unregistered/L3-incomplete source do not
   use it as if the source were compiled.

## Evidence Ledger

- **Current repository reality**:
  - local viewer gating works in `providerContextPolicy`;
  - `chatSidebar` passively registers untracked backend fallback results;
  - tracked `plugin_api.pdf_context` reparses via `parse_page_window`;
  - `fetch_document_section` reparses the original source;
  - `source_pdf_pages` stores metadata only;
  - `source_spans` stores identities, locators, hashes, and previews, not full
    text;
  - CTX projection contains section markers and exact/preview text.
- **Current tests**: targeted baseline passes (backend 24, plugin 46), but no
  integration test covers no-passive-registration or L1 handoff.
- **Current dirty worktree**: clean before planning changes.
- **Rollback**: revert follow-up commits on PR #23. No DB migration/data rewrite.

## Execution Phases

- **P1 — Specs/guides first**: correct `SYSTEM_BEHAVIOR`, `PLUGIN_SCHEMA`,
  `WORKFLOW_GUIDE` EN→KR, and `PLUGIN_GUIDE` EN→KR. Define exact routing priority,
  approval boundary, context-source markers, and CTX projection limitation.
- **P2 — Backend TDD**:
  - tests: registered L1 context avoids `parse_page_window`; `toc_id` section
    resolves from CTX; missing CTX degrades to parse; unregistered parse mutates
    nothing;
  - implement shared CTX section reader and route `plugin_api.pdf_context` plus
    `fetch_document_section` through it;
  - verify pytest + ruff + mypy no-new-errors.
- **P3 — Plugin TDD**:
  - add integration/source-contract tests proving provider context never calls
    `registerSource`;
  - route from status (`registered/l1_complete/l3_complete`) and preserve local
    viewer fast path;
  - gate PDF-focused `curator_query` when the relevant source is unregistered or
    L3-incomplete;
  - verify Vitest + tsc + build.
- **P4 — Testbed smoke**:
  - unregistered PDF chat/fallback leaves DB/source count unchanged;
  - explicit Add Source creates instant L1;
  - next missing-local-context request reports `durable_l1_projection` and does
    not invoke PDF parse;
  - delete CTX projection and verify visible `ephemeral_parse` degradation
    without mutation;
  - verify Reference Mode/Zotero path behavior.
- **P5 — Finalize existing PR**: full local CI, role review, update CHANGELOG and
  PR description, delete completed plan/arena/evidence files, commit/push to
  PR #23, and report unresolved review/thread state. Keep version 0.5.6 because
  this corrects the unmerged release contract.

## Approval Gate

Approved by the user on 2026-06-12.
