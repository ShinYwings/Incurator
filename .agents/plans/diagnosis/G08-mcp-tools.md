# Diagnosis: G08-mcp-tools
Coverage: `backend/src/curator/mcp_server.py`, `backend/src/curator/plugin_api.py`, `backend/src/curator/source_tools.py`, `backend/src/curator/zotero_tools.py`; targeted supporting reads in `backend/src/curator/db.py`, `backend/src/curator/cli.py`, `backend/src/curator/zotero.py`, `backend/src/curator/zotero_integration.py`, `backend/tests/test_mcp_source_status_tools.py`, `backend/tests/test_mcp_source_tools.py`, `backend/tests/test_register_build_split.py`, `backend/tests/test_curator_get_pdf_context.py`, `docs/guides/MCP_USER_GUIDE.md`, and `docs/specs/curator_schema/SCHEMA.md`.

## Findings

### [G08-1] (a/f) S2 - `fetch_document_section(source_key=<file_hash>)` is documented but not implemented
- Loc: `backend/src/curator/mcp_server.py:1021`, `backend/src/curator/mcp_server.py:1036`, `backend/src/curator/db.py:1917`, `docs/specs/curator_schema/SCHEMA.md:533`, `docs/guides/MCP_USER_GUIDE.md:236`
- Evidence: The spec and guide describe `source_key` as `hash-or-source-path-or-logical-id` / `logical_source_id or file_hash`. The tool passes `source_key` through `_get_source_row(... source_path=lookup_key)`, and `db.get_source_row` only matches `relpath`, `external_path`, `import_origin`, and `logical_source_id`; it never checks `sources.content_hash`. Existing tests cover relpath and `source_id` lookup, but no hash lookup.
- Fix sketch: Add a hash lookup branch before path resolution, or add an explicit `file_hash` parameter and make `source_key` dispatch by exact content hash when it looks like a SHA-256. Add a regression test that imports a source, calls `check_source_status(file_hash=...)`, then calls `fetch_document_section(source_key=<same hash>, toc_id=...)`.
- Blast radius: MCP section fetch, agent PDF/source grounding, documented v0.2.1 source-status workflow.
- Suggested PR: `fix/mcp-fetch-document-section-hash-key`

### [G08-2] (a/b/e) S2 - MCP Zotero item tools bypass the shared Zotero helper and ignore configured roots/defaults
- Loc: `backend/src/curator/mcp_server.py:49`, `backend/src/curator/mcp_server.py:792`, `backend/src/curator/mcp_server.py:816`, `backend/src/curator/zotero_tools.py:30`, `backend/src/curator/zotero_tools.py:197`, `backend/src/curator/zotero_tools.py:219`
- Evidence: `curator_search_zotero_items` and `curator_get_zotero_item_metadata` reject calls without `custom_paths`, even though the guide marks `custom_paths` optional and `zotero_tools` already resolves from custom paths, `external.zotero.roots`, discovered prefs paths, and `~/Zotero`. This creates two Zotero resolution stacks with different behavior.
- Fix sketch: Delegate MCP tools directly to `zotero_tools.search_items()` and `zotero_tools.item_metadata()` after resolving `paths`; remove local `_zotero_db_candidates` call sites. Add MCP-level tests for configured `external.zotero.roots` with no `custom_paths`.
- Blast radius: MCP Zotero search/metadata, agent-driven Zotero import workflows, docs parity.
- Suggested PR: `fix/mcp-zotero-delegate-shared-tools`

### [G08-3] (a/b) S2 - MCP PDF resolution misses parent-item Zotero keys that `zotero_tools.resolve_pdf` already supports
- Loc: `backend/src/curator/mcp_server.py:861`, `backend/src/curator/mcp_server.py:883`, `backend/src/curator/zotero_tools.py:304`, `backend/src/curator/zotero_tools.py:307`, `backend/tests/test_zotero_tools.py:212`
- Evidence: `curator_resolve_zotero_pdf` calls `zotero.get_zotero_attachment_path_from_db`, which only resolves direct attachment keys. `zotero_tools.resolve_pdf` calls `resolve_pdf_attachment_for_key` so `zotero_app_url` parent item keys resolve to their child PDF attachment. The helper has regression coverage; the MCP wrapper does not use it.
- Fix sketch: Replace the MCP implementation with a thin call to `zotero_tools.resolve_pdf(attachment_key, paths, custom_paths)` and preserve the structured `state`, `roots_checked`, and `paths_checked` fields.
- Blast radius: MCP Zotero PDF navigation, `zotero://select/library/items/<parent>` links, cross-device reference mode.
- Suggested PR: `fix/mcp-zotero-parent-key-resolution`

### [G08-4] (b/e) S2 - Source API logic is duplicated between MCP and plugin wrappers instead of sharing `plugin_api`/`source_tools`
- Loc: `backend/src/curator/mcp_server.py:718`, `backend/src/curator/mcp_server.py:756`, `backend/src/curator/mcp_server.py:1138`, `backend/src/curator/mcp_server.py:1235`, `backend/src/curator/mcp_server.py:1284`, `backend/src/curator/mcp_server.py:1326`, `backend/src/curator/mcp_server.py:1528`, `backend/src/curator/plugin_api.py:41`, `backend/src/curator/plugin_api.py:82`, `backend/src/curator/plugin_api.py:156`, `backend/src/curator/plugin_api.py:209`, `backend/src/curator/plugin_api.py:275`, `backend/src/curator/plugin_api.py:310`
- Evidence: `_source_dict`, source lookup, status, import, register, rebind, and search are implemented twice. The duplicate surfaces are already drifting: plugin registration accepts `asset_dir`, Zotero import accepts `zotero_attachment_key`, and plugin query has richer language fields; MCP wrappers have separate copies.
- Fix sketch: Keep `source_tools.py` as the pure source-state core, keep `plugin_api.py` as the JSON contract layer, and make MCP source tools delegate to `plugin_api` where signatures overlap. Add parity tests that compare MCP wrapper output to `plugin_api` output for status/import/register/rebind/search.
- Blast radius: MCP tools, plugin hidden CLI, source status dashboard, PDF ingest.
- Suggested PR: `refactor/mcp-plugin-source-api-parity`

### [G08-5] (c/h) S2 - Several long-lived MCP paths swallow failures without structured diagnostics
- Loc: `backend/src/curator/mcp_server.py:702`, `backend/src/curator/mcp_server.py:715`, `backend/src/curator/mcp_server.py:1378`, `backend/src/curator/mcp_server.py:2133`, `backend/src/curator/mcp_server.py:2248`, `backend/src/curator/mcp_server.py:2866`, `backend/src/curator/mcp_server.py:3314`, `backend/src/curator/plugin_api.py:252`, `backend/src/curator/plugin_api.py:1001`
- Evidence: Background worker startup, post-register index refresh, workspace auto-install, LLM-assisted rule integration, Zotero root discovery, Ollama provisioning, plugin index refresh, and promotion classification all use broad `except Exception: pass`. Some best-effort behavior is reasonable, but callers receive no warning field and operators have no log trail.
- Fix sketch: Standardize best-effort failure capture: return `warnings: [...]` for tool calls, log daemon-only failures, and narrow exceptions where possible. Keep genuinely non-fatal behavior non-blocking, but never invisible.
- Blast radius: MCP daemon startup, source registration freshness, workspace setup, model provisioning, support/debuggability.
- Suggested PR: `fix/mcp-structured-best-effort-warnings`

### [G08-6] (c/h) S2 - `curator_build_all` and `curator_sync` leak LLM clients
- Loc: `backend/src/curator/mcp_server.py:2937`, `backend/src/curator/mcp_server.py:2940`, `backend/src/curator/mcp_server.py:2958`, `backend/src/curator/mcp_server.py:2963`
- Evidence: Both tools call `build_client(...)` and never close the returned client on success or failure. Nearby tools use context managers or `finally: client.close()`, so these two stand out in the long-lived MCP process.
- Fix sketch: Use `with build_client(config_dict) as client:` or a `try/finally` close block. Add a mock-client test that asserts `close()` is called for success and exception paths.
- Blast radius: MCP daemon stability, local model processes, network client resources.
- Suggested PR: `fix/mcp-build-sync-client-lifecycle`

### [G08-7] (d/f) S3 - Retired EXH/static Exhibition language remains in MCP docs/comments
- Loc: `backend/src/curator/mcp_server.py:15`, `backend/src/curator/mcp_server.py:2545`, `backend/src/curator/mcp_server.py:2608`
- Evidence: The module docstring still says traversal follows `EXH -> CON -> ATM`, and contradiction comments mention `EXH or CON`, even though the locked architecture says EXH is retired and valid prefixes are `CTX-`, `ATM-`, `CON-`, `SYN-`. The same file correctly says "there is no per-workspace Exhibition" later, so this is stale local guidance.
- Fix sketch: Replace EXH references with SYN/L4 language and ensure all MCP tool descriptions match current dynamic curation terminology.
- Blast radius: Agent instruction quality, docs-code parity, future maintenance.
- Suggested PR: `docs/mcp-remove-retired-exh-language`

### [G08-8] (e) S2 - `mcp_server.py` is a god file with mixed transport, workflow, source, Zotero, query, and workspace responsibilities
- Loc: `backend/src/curator/mcp_server.py:1`, `backend/src/curator/mcp_server.py:670`, `backend/src/curator/mcp_server.py:3289`
- Evidence: The file is 3362 lines. `build_server()` contains nested classes, helper functions, source tools, Zotero tools, provider settings, workspace initialization, DAG traversal, contradiction resolution, search, query, promotion, model tools, and install snippets. This makes parity with plugin/CLI wrappers hard and encourages the duplicate bugs above.
- Fix sketch: Split registration into focused modules such as `mcp/source_tools.py`, `mcp/zotero_tools.py`, `mcp/query_tools.py`, `mcp/workspace_tools.py`, each delegating to shared service functions. Keep `build_server()` as a thin registry.
- Blast radius: MCP testability, future refactors, docs parity, broad exception cleanup.
- Suggested PR: `refactor/mcp-tool-registry-modules`

### [G08-9] (f) S2 - MCP guide signatures drift from live source-tool signatures
- Loc: `docs/guides/MCP_USER_GUIDE.md:97`, `docs/guides/MCP_USER_GUIDE.md:145`, `docs/guides/MCP_USER_GUIDE.md:430`, `backend/src/curator/mcp_server.py:1284`, `backend/src/curator/mcp_server.py:1528`, `backend/src/curator/mcp_server.py:792`
- Evidence: The guide says `curator_import_source` may use `destination_policy`, but the tool only accepts `policy`. The guide says `curator_search_sources` supports `page_start`, `page_end`, and `mode`, but the tool only accepts `query`, source selectors, `limit`, and `workspace_path`. The Zotero guide marks `custom_paths` optional, while two MCP Zotero tools require it.
- Fix sketch: Decide whether the code or docs are canonical per endpoint. For each mismatch, either add compatibility aliases/parameters or update EN and KR guides in the same PR.
- Blast radius: Agent tool selection, MCP client generated schemas, user guides.
- Suggested PR: `docs/mcp-tool-signature-parity`

### [G08-10] (g) S2 - `search_curator` pays an LLM startup/translation cost on every search path
- Loc: `backend/src/curator/mcp_server.py:1772`, `backend/src/curator/mcp_server.py:1776`, `backend/src/curator/mcp_server.py:1782`
- Evidence: Before native search runs, the tool always tries to build an LLM client and translate the query to English, then silently falls back on any exception. This affects even `mode="lex"` and already-English queries. Search is the cheap first-call MCP tool, so hidden LLM startup can make basic retrieval slow or flaky.
- Fix sketch: Gate translation behind language detection or an explicit parameter, reuse the same language bridge as `plugin_api.curator_query`, and surface a warning when translation is unavailable only if translation was attempted.
- Blast radius: MCP search latency, offline/degraded mode, first-session responsiveness.
- Suggested PR: `perf/mcp-search-translation-gating`

### [G08-11] (g/h) S2 - `fetch_document_section` can parse and return whole sources without an explicit budget
- Loc: `backend/src/curator/mcp_server.py:1055`, `backend/src/curator/mcp_server.py:1062`, `backend/src/curator/mcp_server.py:1115`
- Evidence: If no `toc_id`, `section_id`, page, or page range is provided, the tool parses the resolved source and returns `parsed.text` in full. For non-PDF and fallback PDF paths there is no `max_chars`, `max_pages`, or "range required for large source" guard in this endpoint.
- Fix sketch: Add explicit budget parameters with conservative defaults, require section/page selectors for large sources, and return a structured `degraded_reason` or `needs_selector` response instead of full text.
- Blast radius: MCP response size, memory use, long-PDF handling, agent context budgets.
- Suggested PR: `fix/mcp-fetch-document-section-budget`

### [G08-12] (g/h) S3 - Reference moved-file rediscovery is synchronous, bounded by count, and may miss valid candidates silently
- Loc: `backend/src/curator/source_tools.py:167`, `backend/src/curator/source_tools.py:181`, `backend/src/curator/source_tools.py:186`, `backend/src/curator/source_tools.py:193`, `backend/src/curator/source_tools.py:199`
- Evidence: `find_moved_candidate()` runs `root.rglob(filename)`, parses each candidate to hash it, stops at `max_candidates=200`, and suppresses parse/OS errors. In large Zotero/external roots, the first 200 same-name hits can miss the real moved file and report `missing` with no "search truncated" signal.
- Fix sketch: Return search diagnostics (`checked`, `truncated`, `roots_checked`), prefer stable logical/Zotero resolution before filesystem crawl, and consider a cached external-file index for large roots.
- Blast radius: Reference-mode self-healing, Zotero library scale, source status latency.
- Suggested PR: `perf/reference-rebind-discovery-diagnostics`

### [G08-13] (i/h) S3 - Source list mode hides drift/missing state behind "Cached status from database"
- Loc: `backend/src/curator/plugin_api.py:52`, `backend/src/curator/plugin_api.py:73`, `backend/src/curator/plugin_api.py:139`, `backend/src/curator/plugin_api.py:151`, `backend/src/curator/mcp_server.py:728`, `backend/src/curator/mcp_server.py:1205`
- Evidence: List mode uses `light=True`, returns a DB-derived state, sets `requires_rebind=False`, and does not check whether `external_path` exists or hash drifted. The full per-source path can detect `missing`, `moved`, and `hash_drift`, but dashboards/source lists can show stale healthy-looking rows until a single-source status is requested.
- Fix sketch: Add a cheap reference existence check in list mode, or return `live_check: "not_checked"` so UI can avoid implying the file is verified. Keep expensive hash parsing opt-in.
- Blast radius: Obsidian source dashboard, MCP list mode, user trust in Reference Mode status.
- Suggested PR: `fix/source-list-live-state-signals`

### [G08-14] (i/e) S3 - MCP PDF context has a narrower identity surface than the plugin API
- Loc: `backend/src/curator/mcp_server.py:1588`, `backend/src/curator/mcp_server.py:1590`, `backend/src/curator/mcp_server.py:1618`, `backend/src/curator/plugin_api.py:492`, `backend/src/curator/plugin_api.py:500`, `docs/guides/PLUGIN_GUIDE.md:936`
- Evidence: The MCP `curator_get_pdf_context` wrapper only accepts `file_path`, while `plugin_api.pdf_context` accepts `source_id`, `relpath`, `source_path`, `file_hash`, and `zotero_attachment_key`. Plugin docs say backend PDF context should accept identifiers such as source id, hash, path, and Zotero attachment key. Agents using MCP must manually resolve portable identities to absolute paths first.
- Fix sketch: Expand the MCP signature to match `plugin_api.pdf_context` and pass all selectors through. Keep `file_path` for compatibility.
- Blast radius: Agentic PDF navigation, Zotero-backed restored views, cross-device portability.
- Suggested PR: `feat/mcp-pdf-context-identity-parity`

## Positives (keep / do-not-break)

- `source_tools.py` is dependency-light and has focused behavior for reference source state, hash drift, moved-file proposals, and human-approved rebinding.
- `zotero_tools.py` is the right shared home for Zotero path/status logic; it already supports configured roots, prefs discovery, linked attachments, and parent-item-key PDF resolution.
- `plugin_api.py` keeps the Obsidian plugin JSON contract free of MCP dependencies, which is valuable for fast CLI tests and plugin fallback behavior.
- The register/build split is well characterized by tests: `curator_register_source` can generate L1 without an LLM, and `curator_build_source` can enqueue L2/L3 separately.
- Durable L1 projection paths are tested so `fetch_document_section` and `curator_get_pdf_context` can avoid reparsing registered sources when inline CTX text exists.

## Open questions for the human

- Should MCP source tools become exact wrappers over `plugin_api.py`, or should plugin and MCP intentionally expose different contracts?
- Should `curator_import_source` grow `zotero_attachment_key`, `zotero_custom_paths`, and `asset_dir` parity with plugin import/register, or should Zotero import remain plugin-only?
- Should source list mode perform cheap live checks by default, or should the UI explicitly show "cached/not live checked" until users request per-source status?
- Are global mutating MCP tools such as `curator_add_all`, `curator_build_all`, and `curator_sync` still desired as agent-facing tools, or should they be CLI-only to reduce accidental long-running work?
- Should every MCP tool standardize on an `{ok: bool, error?: string, warnings?: [...]}` envelope, including legacy read tools that currently return bare `{"error": ...}`?
