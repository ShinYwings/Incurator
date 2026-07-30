# Phase A Diagnosis — Module-Group Index (durable resume map)

STATUS: Phase A closed. All group reports are folded into
`01_roadmap_evidence.md`; `merged` is the only live state below.

Findings categories: (a) bugs (b) redundancy (c) error-handling smells
(d) legacy/dead (e) architectural debt (f) docs↔code drift (g) perf
(h) robustness/races (i) UI/UX. Severity S1/S2/S3.

| # | Group | Files | Status |
|---|---|---|---|
| G01 | ingest-core | `ingest_raw.py`, `ingest_llm.py`, `ingest_worker.py`, `ingest_orchestrator.py` | merged |
| G02 | pipeline | `pipeline/*.py` (source_spans, knowledge_units, synthesis, compile, claim_support, community_reports, graph_index, projection, memory_paths, formula_recovery) | merged |
| G03 | db | `db.py`, `db_sync.py` | merged |
| G04 | sync-migrate | `sync.py`, `migrate.py` | merged |
| G05 | retrieval | `retrieval/*.py` (engine, fusion, vector, lexical, chunking, embedding, expansion, query_expander, router, orchestrator, materializer, evidence, evaluation, providers, models) | merged |
| G06 | query-search-context | `query.py`, `search.py`, `context_service.py` | merged |
| G07 | cli | `cli.py` (7389 LOC — god-file) | merged |
| G08 | mcp-tools | `mcp_server.py`, `plugin_api.py`, `source_tools.py`, `zotero_tools.py` | merged |
| G09 | llm-prompts | `llm.py`, `llm_identity.py`, `model_setup.py`, `vision.py`, `prompts.py`, `prompting/*.py` | merged |
| G10 | config-runtime | `config.py`, `constants.py`, `runtime_state.py`, `secret_store.py`, `device_registry.py`, `git_manager.py` | merged |
| G11 | quality-analysis | `lint.py`, `contradiction.py`, `backprop_classifier.py`, `backprop_agents.py`, `insight_lifecycle.py`, `intent.py`, `curate_yml.py`, `inspection/synthesis_audit.py` | merged |
| G12 | sources-parsers-misc | `zotero.py`, `zotero_integration.py`, `parsers/*.py`, `asset_identity.py`, `testbed_manager.py`, `workspace/provisioner.py` | merged |
| G13 | plugin-agent | `plugin/src/agent/*.ts` (llmClient, incuratorClient, mcpClient, sandboxWrapper) | merged |
| G14 | plugin-chatsidebar | `plugin/src/ui/chatSidebar.ts` (4828 LOC — god-file) | merged |
| G15 | plugin-ui | `plugin/src/ui/*.ts` (diffViewer, quickQueryPopover, inlinePrompt, incuratorDashboardModal, incuratorQueryTrace, externalPdfView, zotero*Modal) | merged |
| G16 | plugin-context | `plugin/src/context/*.ts` (systemPrompt, promptRegistry, quickQueryContext, crossReferenceResolver, pdf*), `plugin/src/utils/*.ts` | merged |
| G17 | plugin-rest | `plugin/src/auth/*`, `plugin/src/zotero/*`, `plugin/src/types.ts`, `plugin/src/settings.ts`, `main.ts` | merged |
| G18 | docs-code-parity | specs/guides surfaces vs code (CLI cmds, MCP tools, config fields, plugin settings) | merged |
| G19 | docs-redundancy | cross-doc duplication, stale/useless docs, EN↔KR drift (anti-compression guardrail) | merged |

## Per-group output file format (`<group>.md`)

```
# Diagnosis: <group>
Coverage: <files actually read>
## Findings
### [Gxx-1] (cat) Sxx — Title
- Loc: file:line
- Evidence: <what you saw>
- Fix sketch: <surgical fix idea>
- Blast radius: <what it touches>
- Suggested PR: <branch-ish label>
## Positives (keep / do-not-break)
- ...
## Open questions for the human
- ...
```
