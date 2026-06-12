# Critique On PDF Adaptive Routing Proposals
Date: 2026-06-12 | Agent Persona: Red Teamer

## 1. Vulnerabilities & Flaws

- Merely removing auto-register is insufficient: an ordinary PDF question can
  still run a workspace-wide `curator_query`, creating the appearance that an
  unregistered PDF was used by durable RAG.
- Treating `sourceTracked=true` as L1-ready is unsafe. Import creates a tracked
  row before instant L1 completes; routing must require `l1_complete`.
- Serving CTX text without checking the source hash can expose stale content.
- CTX may be missing because it is derived/disposable. A hard failure would
  break viewer chat after cleanup.
- `source_pdf_pages` contains metadata only. Any implementation that calls it a
  cached text store is false.
- `fetch_document_section` is an MCP tool used outside the plugin. Changing its
  registered behavior must preserve unregistered and non-PDF behavior.
- Local viewer text should remain the fastest path even after registration;
  automatic handoff must not force a backend round trip on every visible page.

## 2. Suggested Alternatives

- Define the handoff as a priority order, not a total replacement:
  explicit local selection/crop/page context first; durable L1 for missing local
  context, section requests, and expansion; ephemeral backend parse last.
- Require `registered && l1_complete && context_id && CTX exists` before durable
  projection serving.
- Return `context_source` and `degraded_reason` in backend responses.
- Add tests proving passive chat never invokes `source import/register`.
- Add tests proving tracked-L1 context does not call `parse_page_window`.
