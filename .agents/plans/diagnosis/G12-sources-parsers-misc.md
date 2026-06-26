# Diagnosis: G12-sources-parsers-misc
Coverage: `backend/src/curator/zotero.py`, `backend/src/curator/zotero_integration.py`, `backend/src/curator/parsers/__init__.py`, `backend/src/curator/parsers/base.py`, `backend/src/curator/parsers/pdf.py`, `backend/src/curator/parsers/text.py`, `backend/src/curator/parsers/html.py`, `backend/src/curator/parsers/image.py`, `backend/src/curator/asset_identity.py`, `backend/src/curator/testbed_manager.py`, `backend/src/curator/workspace/provisioner.py`; supporting read-only context from relevant tests, `zotero_tools.py`, call sites, and specs/guides.

## Findings

### [G12-1] (a,f) S2 - `.docx` is advertised as supported but has no parser module
- Loc: `backend/src/curator/parsers/__init__.py:12`, `backend/src/curator/parsers/__init__.py:17`, `backend/src/curator/parsers/__init__.py:58`, `backend/src/curator/parsers/__init__.py:62`, `docs/specs/curator_schema/SCHEMA.md:169`
- Evidence: `_PARSERS` maps `.docx` to `"docx"` and `SUPPORTED_EXTENSIONS` therefore reports `.docx` as supported, but `backend/src/curator/parsers/` contains no `docx.py`. `parse()` only guards that the module name is in `{"text", "pdf", "docx", "html", "image"}` and then imports `curator.parsers.docx`, which will raise `ModuleNotFoundError` instead of a controlled `ParserError`. The schema also lists `docx` as a source tag/file type.
- Fix sketch: Either implement `parsers/docx.py` using the existing `python-docx` dependency, with title/text/metadata parity and tests, or remove `.docx` from `_PARSERS`/docs until the parser exists. Prefer implementation because the dependency and schema contract already exist.
- Blast radius: `wiki add`, MCP/source import, plugin source registration, and any UI that uses `SUPPORTED_EXTENSIONS` to pre-accept files.
- Suggested PR: `fix/docx-parser-contract`

### [G12-2] (g,f) S2 - `parse_page_window()` returns a page subset but still parses the whole PDF
- Loc: `backend/src/curator/parsers/pdf.py:236`, `backend/src/curator/parsers/pdf.py:245`, `backend/src/curator/parsers/pdf.py:246`, `backend/src/curator/plugin_api.py:597`, `backend/src/curator/plugin_api.py:638`, `docs/guides/MCP_USER_GUIDE.md:177`
- Evidence: The guide says ephemeral/degraded fallback uses `parse_page_window()` to read only requested pages and be safe for 600-page documents. The implementation calls `pymupdf4llm.to_markdown(str(path), page_chunks=True)` for the entire document, then filters chunks by page. Existing tests only assert excluded pages are absent from the return value, not that unrequested pages are skipped during parsing.
- Fix sketch: Use a true page-limited parser path if `pymupdf4llm` supports page selection; otherwise use PyMuPDF page-level extraction for the requested pages and keep the Markdown parser path for full ingest. Add a regression test that stubs `to_markdown` or uses a fixture to prove only requested pages are processed.
- Blast radius: `curator_get_pdf_context` degraded/ephemeral fallback, sidechat PDF context, long-PDF latency, and memory pressure.
- Suggested PR: `perf/pdf-page-window`

### [G12-3] (c,h,i) S2 - PDF context helpers silently turn parse failures into empty results
- Loc: `backend/src/curator/parsers/pdf.py:226`, `backend/src/curator/parsers/pdf.py:232`, `backend/src/curator/parsers/pdf.py:236`, `backend/src/curator/parsers/pdf.py:240`, `backend/src/curator/parsers/pdf.py:252`, `backend/src/curator/plugin_api.py:597`, `backend/src/curator/plugin_api.py:638`
- Evidence: `get_page_count()` catches every exception and returns `0`; `parse_page_window()` returns `{}` when `pymupdf4llm` is missing and also swallows all parse exceptions. Callers then proceed with empty page text or generic "Could not read PDF" errors, losing the distinction between missing dependency, encrypted/corrupt file, unsupported page extraction, and transient parser failure.
- Fix sketch: Introduce a small structured result or raise `ParserError` with a stable reason code for page-window reads. Keep user-facing plugin responses structured with `state`/`degraded_reason` instead of empty success-shaped payloads.
- Blast radius: Plugin PDF context, Sources & Trace diagnostics, long-document degraded fallback, and user repair guidance.
- Suggested PR: `fix/pdf-context-error-states`

### [G12-4] (a,e,f,i,b) S2 - Legacy Zotero path resolution bypasses the structured backend resolver
- Loc: `backend/src/curator/zotero.py:254`, `backend/src/curator/zotero.py:258`, `backend/src/curator/zotero.py:262`, `backend/src/curator/ingest_raw.py:120`, `backend/src/curator/ingest_raw.py:134`, `backend/src/curator/mcp_server.py:884`, `backend/src/curator/mcp_server.py:914`, `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md:668`
- Evidence: `resolve_zotero_attachment_path()` only checks `<zotero_data_dir>/storage/<attachment_key>/*.pdf`. It ignores DB `storage:<file>`, `attachments:<relative>`, parent-item-key-to-child-attachment resolution, direct sqlite paths, configured linked roots, and prefs.js/ZotMoov discovery. `ingest_raw._resolve_reference_source()` still calls this legacy helper for Zotero reference stubs, and the MCP `curator_resolve_zotero_pdf` path hand-rolls another resolver that returns only `{"ok": False, "error": "PDF not found"}`. The spec requires structured states (`db_missing`, `attachment_key_missing`, `attachment_file_missing`) and linked-root resolution.
- Fix sketch: Route all Zotero PDF resolution through `zotero_tools.resolve_pdf()` or `asset_identity.resolve(..., zotero_key=...)`; retire the storage-only helper or keep it private behind the canonical resolver. Update tests to cover Reference Mode stubs with `attachments:` paths and parent item keys.
- Blast radius: Zotero-backed Reference Mode reload, cross-device linked attachments, sidechat Add-to-Incurator, MCP Zotero PDF resolution, and user-facing repair UX.
- Suggested PR: `fix/zotero-resolver-consolidation`

### [G12-5] (h,c,a) S2 - Zotero temp DB snapshots are collision-prone, and metadata copy fallback is broken
- Loc: `backend/src/curator/zotero.py:51`, `backend/src/curator/zotero.py:151`, `backend/src/curator/zotero.py:199`, `backend/src/curator/zotero_integration.py:14`, `backend/src/curator/zotero_integration.py:156`, `backend/src/curator/zotero_integration.py:157`
- Evidence: Several helpers use deterministic temp filenames keyed only by process id, or by process id plus DB hash for search. Concurrent requests in the same backend process can copy over or unlink each other's snapshot. `get_zotero_item_metadata()` is worse: if `shutil.copy2()` fails, it `pass`es but still connects to `temp_db_path`; SQLite may create an empty DB and later fail with "no such table" instead of falling back to the real DB as `search_zotero_items()` does.
- Fix sketch: Use `tempfile.NamedTemporaryFile(delete=False)`/`mkstemp` per call, always clean up only the file created by that call, and on copy failure either open the original DB read-only or return a structured unreadable-DB state. Avoid silent `pass` in metadata setup.
- Blast radius: MCP/CLI/plugin Zotero search, metadata, annotations, PDF resolution under concurrent requests or locked/copy-failing Zotero DBs.
- Suggested PR: `fix/zotero-temp-snapshots`

### [G12-6] (a,f,e) S2 - `AssetIdentity.resolve()` accepts `content_hash` but never resolves by it
- Loc: `backend/src/curator/asset_identity.py:98`, `backend/src/curator/asset_identity.py:104`, `backend/src/curator/asset_identity.py:131`, `backend/src/curator/asset_identity.py:136`, `backend/src/curator/asset_identity.py:153`, `backend/src/curator/db.py:105`, `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md:2466`
- Evidence: The resolver signature includes `content_hash`, and the spec says AssetIdentity matches an existing `sources` row by id / relpath / external path / hash. The implementation only queries by relpath, resolved absolute path, and logical source id; `content_hash` is merely echoed/backfilled after another lookup succeeds. The DB already has `idx_sources_hash`, and `plugin_api` still performs direct content-hash source lookups separately.
- Fix sketch: Add an isolated content-hash lookup to `asset_identity.resolve()` after path/logical lookups, with deterministic ambiguity handling when multiple sources share a hash. Then move direct plugin/source hash lookups to the authority.
- Blast radius: Cross-device PDF/source identity, plugin session rehydration by hash, Sources & Trace locators, and the "single authority" architectural contract.
- Suggested PR: `fix/asset-identity-hash-resolution`

### [G12-7] (a,h) S2 - Testbed initialization shallow-copies `DEFAULT_CONFIG` and mutates nested global defaults
- Loc: `backend/src/curator/testbed_manager.py:69`, `backend/src/curator/testbed_manager.py:70`, `backend/src/curator/testbed_manager.py:72`
- Evidence: `config = dict(cfg.DEFAULT_CONFIG)` is a shallow copy. The next lines mutate `config["llm"]["primary"]`, which shares the nested `llm` dict with `cfg.DEFAULT_CONFIG`. A testbed init with `--llm`/`--model` can therefore alter backend process defaults for subsequent config creation in the same process.
- Fix sketch: Use `copy.deepcopy(cfg.DEFAULT_CONFIG)` before mutating nested config. Add a test that calls `init_testbed(..., llm_provider=...)` and asserts `cfg.DEFAULT_CONFIG["llm"]["primary"]` is unchanged.
- Blast radius: CLI testbed flows, long-lived backend/MCP sessions that initialize testbeds, and any later vault config created in the same interpreter.
- Suggested PR: `fix/testbed-default-config-copy`

### [G12-8] (h,c,i) S2 - `merge_mcp_settings()` can overwrite malformed user settings with a new minimal file
- Loc: `backend/src/curator/workspace/provisioner.py:151`, `backend/src/curator/workspace/provisioner.py:153`, `backend/src/curator/workspace/provisioner.py:154`, `backend/src/curator/workspace/provisioner.py:167`
- Evidence: If the target settings file exists but JSON parsing fails or reading raises `OSError`, the function sets `data = {}` and later writes a fresh JSON object to the same path. That can discard unrelated user MCP settings or comments/trailing-comma JSONC-like content when the user's original file was recoverable by manual edit.
- Fix sketch: On parse/read failure, do not overwrite by default. Return/raise a structured error with the path and parse message, or write a `.bak` before replacing only when the caller explicitly requests repair.
- Blast radius: `wiki workspace ... --mcp` setup, Claude Code settings, user trust in workspace provisioning, and support burden when third-party MCP settings disappear.
- Suggested PR: `fix/workspace-settings-preserve-invalid`

### [G12-9] (c,h) S3 - Workspace provisioning suppresses rule-template failures and reports partial success
- Loc: `backend/src/curator/workspace/provisioner.py:321`, `backend/src/curator/workspace/provisioner.py:324`, `backend/src/curator/workspace/provisioner.py:327`, `backend/src/curator/workspace/provisioner.py:336`, `backend/src/curator/workspace/provisioner.py:407`
- Evidence: `_install_rule_templates()` writes owned templates, then installs managed blocks for all known agents inside a broad `except Exception: pass`. Missing templates, unexpected render errors, and write failures for top-level rule files are swallowed, leaving `WorkspacePrepareResult` with no indication that agent start files were skipped.
- Fix sketch: Catch only expected unsupported-agent cases. For template/read/write failures, append an error field to the result or raise a typed exception so CLI/MCP callers can surface the partial install.
- Blast radius: Workspace onboarding, managed rule synchronization, multi-agent relay behavior, and diagnosis of "Curator hooks did not install" reports.
- Suggested PR: `fix/workspace-provision-errors`

### [G12-10] (d,b) S3 - Small dead/legacy helpers add noise in already-sensitive setup code
- Loc: `backend/src/curator/workspace/provisioner.py:270`, `backend/src/curator/parsers/html.py:69`, `backend/src/curator/parsers/image.py:14`, `backend/src/curator/zotero.py:254`
- Evidence: `_replace_yaml_list()` is not referenced in the repo; `html._walk(skip_if_heading=False)` never passes a non-default value; `SUPPORTED_IMAGE_EXTENSIONS` duplicates the dispatcher extension list and has no call sites; `resolve_zotero_attachment_path()` remains a legacy storage-only resolver even though the structured resolver exists in `zotero_tools`. Individually these are small, but they obscure the actual contracts in parsers/workspace/Zotero code.
- Fix sketch: Remove unused helpers/constants after adding focused tests for the surviving behavior. For Zotero, fold any needed storage-directory fallback into the canonical resolver before deleting the legacy public function.
- Blast radius: Low direct runtime risk, but cleanup reduces future mistakes in parser support and workspace/Zotero resolution changes.
- Suggested PR: `chore/g12-dead-helper-cleanup`

## Positives (keep / do-not-break)
- `asset_identity.from_source_row(..., verify_exists=True)` correctly downgrades missing external Reference Mode paths to `path_unresolved`; existing tests cover this.
- `AssetIdentity.resolve()` already delegates explicit Zotero-key path lookup to `zotero_tools.resolve_pdf()`, which is the right canonical direction.
- Parser modules normalize output through a single `ParsedDocument` shape, and PDF parsing already preserves page metadata (`pdf_pages`) and TOC metadata for downstream CTX/source context.
- `_merge_raw_text_fallback()` is a pragmatic guard against `pymupdf4llm` dropping math-like text-layer lines; there is a focused test for omitted formula recovery.
- `testbed_manager.list_scenarios()` correctly requires `MASTER_PLAN.md`, matching the current scenario contract.
- Workspace provisioning uses managed blocks instead of overwriting user-authored rule files wholesale when the files are parseable.

## Open questions for the human
- Should `.docx` remain a supported source type for the next stability PR, or should it be temporarily removed from advertised support until there is a real parser?
- Should old public MCP Zotero tools be kept as compatibility wrappers around `zotero_tools`, or can they be deprecated/removed during the stability overhaul?
- For content-hash identity, what should `AssetIdentity.resolve()` return when multiple source rows share the same hash: newest row, deterministic ambiguity state, or all candidates?
- Is `merge_mcp_settings()` expected to support JSONC/commented settings files, or should it strictly require valid JSON and fail without writing?
