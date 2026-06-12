# Backend Serving Proposal: Durable L1 Read Model
Date: 2026-06-12 | Agent Persona: Backend Retrieval Engineer

## 1. Core Logic & Implementation

Use existing L1 records as the registered-source serving substrate:

- Add DB accessors that return ordered `source_spans` by `toc_id` and by page.
- Durable page responses concatenate full span text when available.
- Current `source_spans` store only previews, so exact durable serving must read
  the registered CTX projection's `Source Sections` by section marker, keyed by
  the DB `toc_id`. This avoids reparsing the PDF and preserves the existing
  no-migration constraint.
- `plugin_api.pdf_context()`:
  - registered + L1 complete + CTX exists: serve CTX/source-span-derived page
    sections and mark `context_source="durable_l1"`;
  - otherwise: use existing read-only `parse_page_window()` fallback and mark
    `context_source="ephemeral_parse"`.
- `fetch_document_section()`:
  - registered + L1 complete + requested `toc_id`: resolve from CTX projection;
  - otherwise retain original-source read-only fallback.

Do not claim `state.sqlite` stores full source text. DB stores authoritative
identities/provenance; CTX is the current durable full-text read projection.

## 2. Pros & Cons

Pros:
- Achieves the requested no-reparse handoff without schema migration.
- Reuses current CTX section markers and `source_spans.toc_id`.
- Preserves original-source fallback for missing/corrupt projections.

Cons:
- CTX is documented as derived/disposable, so it must be regenerated when
  missing; serving cannot treat it as the authoritative source of truth.
- Full-text DB-native serving would require a future schema change storing span
  text or a dedicated durable read model.
