# RAG Surface Proposal: Keep Transport Adapters Thin

Date: 2026-07-09 | Agent Persona: source_pair_analyst

## 1. Core Logic & Implementation

The RAG/DAG pipeline should remain behind shared services:

- `QueryOrchestrator`
- `ContextService`
- `ingest_raw`
- `ingest_worker`
- `source_tools`
- `search`
- `db`

CLI, MCP, and plugin API modules should remain transport adapters. The split
should not move pipeline algorithms into command packages or create new command
specific query paths.

Risk areas:

- `plugin_api.curator_query` and MCP `curator_query` must keep using the same
  retrieval/query services and trace fields.
- PDF context paths must keep the same priority order:
  registered durable L1 projection, read-only original-source parse, and no
  passive source registration.
- Hidden plugin commands must continue calling backend-owned code rather than
  plugin-owned state mutation.
- Autosync hooks after CLI mutations must remain attached to the same commands.

Required characterization:

- Snapshot selected JSON command responses for `wiki plugin source status`,
  `wiki plugin query` with mocked services, and `wiki db autosync --help`.
- Assert `curator.plugin_api` exports the existing direct functions.
- Assert MCP `curator_get_pdf_context`, `curator_query`,
  `curator_fetch_context`, and source registration tools are still present after
  `build_server()`.

## 2. Pros & Cons

Pros:

- Prevents duplicated RAG logic across transport layers.
- Maintains the source-truth boundary documented in the specs.
- Allows future cleanup of command wrappers without touching retrieval.

Cons:

- Some modules will import many shared services until a later service-layer pass.
- Tool registrar files may still be large because tool behavior itself is broad.
