# Problem: Restore The Intended PDF Adaptive Routing Contract

Date: 2026-06-12
PR: #23 (`feature/pdf-add-source-assets`)

## Verified Defects

The documented PDF workflow promises two separate pipelines with an explicit
human-approved handoff:

1. Unregistered viewer chat uses ephemeral PDF.js/local context and writes no
   durable state.
2. Add Source creates durable instant L1.
3. Once L1 is complete, backend section/page context is served from durable
   L1 records rather than repeatedly parsing the PDF.

Current code violates that contract:

- `chatSidebar.buildIncuratorProviderContext()` fire-and-forgets
  `registerSource()` after an untracked backend fallback, so passive viewing can
  create durable state without approval.
- The plugin has no `l1_complete` routing branch that upgrades context serving
  to durable L1 sections.
- `plugin_api.pdf_context()` reparses the original PDF even for tracked sources.
- `fetch_document_section()` reparses the original source and does not serve
  registered L1 `source_spans`/CTX data directly.
- Existing tests validate individual helpers but do not cover the full routing
  state machine or the no-passive-registration invariant.

## Required Outcome

- Passive viewer chat never imports/registers a source.
- Unregistered PDFs use local PDF.js context first and read-only backend page
  fallback only when local context is unavailable.
- Explicit Add Source remains the only plugin path that creates durable source
  state.
- Registered + L1-complete PDFs use DB-native durable L1 page/section context.
- `toc_id` resolves through durable `source_spans`; page context resolves
  through durable L1 data without reparsing the PDF.
- If durable L1 data is unavailable or stale, serving visibly falls back to a
  read-only original-source parse without mutating state.
- L3-complete sources may additionally use `curator_query`; unregistered or
  L1-only PDF-specific questions must not be represented as concept-grounded.

## Scope Boundary

- No DB migration. Reuse `source_spans`, `source_pdf_pages`, and CTX projection.
- No L2/L3 compiler or RAG stabilization redesign.
- No changes to Add Source asset routing or Added badge behavior.
- Remains a corrective follow-up on PR #23 / v0.5.6.
