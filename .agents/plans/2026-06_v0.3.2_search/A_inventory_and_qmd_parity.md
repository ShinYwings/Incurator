# v0.3.2 Search Internalization — Part A: Exhaustive Code Inventory + qmd Parity Target

Date: 2026-06-05
Status: Analysis artifact (read-only research). No runtime code, specs, or other
plan files were modified in producing this document.

Scope of this artifact (per the approved
`.agents/plans/2026-06_v0.3.2_search_internalization_plan.md`): a code-grounded
inventory of every search / embedding / index / qmd touchpoint that must change
or be removed when the external `qmd` binary (npm `@tobilu/qmd`) is retired in
favor of in-DB hybrid search inside `.curator/state.sqlite`; a precise qmd parity
checklist the native engine must meet or exceed; the exact `SearchHit` /
`SearchResults` data contracts the rest of the system depends on; and an ordered
removal map.

All paths are absolute. Line numbers reflect the working tree at analysis time.

---

## 0. One-paragraph orientation (verified against code)

Today, **`backend/src/curator/search.py` is the only module that talks to qmd**,
and every other search path funnels through it. qmd is resolved as an external
binary (`get_qmd_binary`), invoked per-call via `subprocess` (`_run_qmd`), pinned
to a per-vault config + sqlite via env vars `QMD_CONFIG_DIR` / `INDEX_PATH`
(`_qmd_env`), and it indexes the **markdown projection** under
`.curator/Collections/` (NOT the authoritative `state.sqlite`). The Python side
parses qmd's `--json` output into `SearchHit` / `SearchResults`. Callers:
`retrieval/evidence.py` (`_qmd_hits`), `query.py` (`run_query` → `_search_for`),
`mcp_server.py` (`search_curator`, `curator_query` L3-incomplete fallback,
`curator_reindex`, `curator_status`, and inline `update_index` after ingest),
`plugin_api.py` (`curator_query` fallback + post-L1 `update_index`), `cli.py`
(`_refresh_qmd_index`, `query`, `reindex`, `status`), `lint.py` (post-fix
`update_index`), and `runtime_state.py` (status reporting). `search_source_pages`
/ `lexical_score` / `SourcePageHit` in `search.py` are a **separate, local,
non-qmd** lexical search over raw source files and are NOT part of qmd retirement
(they only need to stay importable). This is the v0.3.1 "Search Index Paradox":
the projection is supposedly disposable, yet qmd makes it load-bearing.

This contradiction is exactly the motivation in
`.agents/plans/2026-06_deep_analysis/Phase_H_Search_Index_Paradox.md` and the
philosophical verdict in
`.agents/plans/2026-06_v0.3.2_search_internalization_plan.md` §0.B.

---

## 1. Exhaustive code inventory (`file:line — what it does — change/remove`)

### 1.1 `backend/src/curator/search.py` — the qmd wrapper (whole-file read)

This file is the qmd shim. Almost all of it is **REPLACE** (rewrite to query
`state.sqlite` directly), except the local source-page lexical helpers, which are
qmd-independent and **KEEP**.

| Location | What it does | Action |
|---|---|---|
| `search.py:1-14` | Module docstring: "wraps the QMD binary"; documents binary resolution order (`WIKI_QMD_BIN`, PATH) and graceful degradation. | REPLACE docstring with in-DB hybrid description. |
| `search.py:17` | `from . import constants as consts` (used by `_normalize_qmd_path` layer aliases). | KEEP (constants still needed for layer mapping in result paths). |
| `search.py:19-28` | Imports: `json, os, re, shutil, subprocess`, dataclasses, `config as cfg`. | `subprocess`/`shutil`/`json` become unused after rewrite → REMOVE those imports; add `sqlite3`/numpy-equivalent + `db` imports. |
| `search.py:36-45` | **`SearchHit` dataclass** (`full_path, title, score, snippet, full_content, docid`). | KEEP shape (see §3). `docid` semantics shift from "qmd content-hash" to DB node id; `full_path` becomes a synthetic `LAYER/ID.md` relpath derived from DB row, not a disk file. |
| `search.py:48-59` | **`SearchResults` dataclass** (`hits`, `fallback_mode`, `__len__`, `__iter__`). | KEEP shape (see §3); now populate `fallback_mode` from native degradation (e.g. `"lex"` when no embeddings/reranker configured). |
| `search.py:62-72` | **`SourcePageHit` dataclass** (raw-source lexical hit w/ PDF page). | KEEP — unrelated to qmd; backs `search_source_pages`. |
| `search.py:75-83` | **`IndexUpdateResult` dataclass** (`updated, embedded, embed_requested, degraded, warning`). | KEEP shape (consumed by CLI/MCP) but re-point meaning to DB-index rebuild stages. |
| `search.py:91-92` | `SearchBackendError` exception. | KEEP (callers catch it). |
| `search.py:95-96` | `QmdNotInstalled(SearchBackendError)`. | KEEP the class name as an alias/subclass for backward compat OR retire after callers updated; callers at `query.py:546`, `mcp_server.py:1899`, `cli.py` no longer raise it. Decision: keep as inert subclass to avoid breaking `except` clauses, then remove in cleanup pass. |
| `search.py:104-138` | **`get_qmd_binary()`** — resolves binary via env, PATH, NVM dirs, Homebrew/local. | REMOVE (binary no longer exists). Used by `cli.py`, `mcp_server.py`, `runtime_state.py`. |
| `search.py:140-153` | **`is_available()`** — runs `qmd --version`. | REPLACE with a native readiness check (e.g. FTS5 tables exist / embeddings present). Used by `cli.py:480,2732,4398,4567`, `runtime_state.py:197,208`. |
| `search.py:155-169` | **`get_version()`** — qmd `--version`. | REPLACE with native engine/version string (or remove + update status callers). Used by `cli.py:2733`, `runtime_state.py:197`. |
| `search.py:172-179` | **`_require_binary()`** — raises `QmdNotInstalled`. | REMOVE. |
| `search.py:182-209` | **`_qmd_env()`** — sets `QMD_CONFIG_DIR`, `INDEX_PATH`, injects NVM node into PATH. | REMOVE (env-pinning + per-vault `qmd_db`/`qmd_dir` no longer used). |
| `search.py:212-240` | **`_run_qmd()`** — subprocess invoker w/ timeout. | REMOVE. |
| `search.py:248` | `_QMD_TEMPLATE = .../workspace/templates/qmd-index.yml`. | REMOVE (template retired, see §1.13). |
| `search.py:251-270` | **`write_qmd_config()`** — renders `index.yml` from template, substitutes `__COLLECTIONS_PATH__`. | REMOVE. Called by `cli.py:2304` (`wiki init`). |
| `search.py:278-313` | **`update_index()`** — `qmd update` (+optional `qmd embed`); returns `IndexUpdateResult`. | REPLACE with native: materialize FTS5 rows from authoritative DB tables + (re)compute chunk embeddings + invalidation. Same return type. Called widely (see callers list). |
| `search.py:321-337` | **`_normalize_qmd_path()`** + `_QMD_URI_RE` — strips `qmd://collection/` and remaps `01-Contexts/` → `01_Contexts/`. | REMOVE qmd:// handling; native results already carry canonical `LAYER/ID.md`. (Note: identical regex is duplicated in `query.py:157,196` and `lint.py:259`.) |
| `search.py:340-346` | **`_mode_to_subcommand()`** — maps `lex→search`, `vec→vsearch`, hybrid→`query`. | REPLACE with native mode dispatch (lex=FTS5 only, vec=vector only, hybrid=RRF+expansion+rerank). |
| `search.py:349-435` | **`query()`** — the core search entry. Builds qmd args, runs subprocess, parses brittle JSON (`find('[')`/`rfind(']')`), applies `min_score`, builds `SearchHit`s, optionally hydrates from disk. | REPLACE entirely with native pipeline (FTS5 + chunked vector + RRF + typed expansion + rerank + trace). **Signature must be preserved** (see §3.3): `query(paths, question, *, mode, limit, min_score, collections, hydrate, rerank)`. |
| `search.py:438-453` | **`_hydrate_hits()`** — reads `full_content` from `paths.collections / hit.full_path` on disk. | REPLACE: hydrate `full_content` from the authoritative DB row (statement/full_content), not disk; removes the projection dependency. |
| `search.py:456-473` | **`_snippet()`** — local snippet windowing. | KEEP (reused by source-page search; reusable for native snippets). |
| `search.py:476-477` | **`_query_tokens()`** — tokenizer incl. Hangul range. | KEEP (reusable for native lexical/CJK handling). |
| `search.py:480-486` | **`lexical_score()`** — naive term-count score. | KEEP (used by `mcp_server.py:1591`, `plugin_api.py:407`, `search_source_pages`). |
| `search.py:489-563` | **`search_source_pages()`** — lexical search over tracked raw sources w/ PDF page numbers; reads `sources` table + parses files. Docstring line 499-500 says "Curator DAG search still goes through qmd". | KEEP function; UPDATE docstring (no longer "through qmd"). This is the provenance path, qmd-independent. |

### 1.2 `backend/src/curator/retrieval/evidence.py` — evidence packs

| Location | What it does | Action |
|---|---|---|
| `evidence.py:1-7` | Module docstring: "Combines the DB graph … with qmd search over the derived `.curator/Collections` corpus. qmd is the fallback retrieval engine". | REWRITE docstring: native FTS5/vector over authoritative DB rows. |
| `evidence.py:39-56` | **`_qmd_hits()`** — calls `search.query(..., mode="hybrid", min_score=0.3, hydrate=True, rerank=True)`; wraps each `SearchHit` as `EvidenceItem(kind="qmd_hit")`; appends `"qmd unavailable: …"` warning on failure. | REPLACE call to native search; rename to e.g. `_fts_hits` and emit `kind` accordingly (see EvidenceItem note below). This is the surgical replacement Phase H calls out. |
| `evidence.py:165-179` | `global` route: warning `"no synthesis or community reports; falling back to qmd"` → `pack.items = _qmd_hits(...)`. | UPDATE warning text + native call. |
| `evidence.py:207-212` | `local` route: `pack.items.extend(_qmd_hits(paths, q, limit, warnings))`. | UPDATE native call. |
| `retrieval/models.py:39-42` | `EvidenceItem.kind` enum comment includes `qmd_hit`. | UPDATE the `kind` vocabulary (e.g. rename `qmd_hit` → `fts_hit`/`hybrid_hit`); check no consumer string-matches `"qmd_hit"`. |
| `retrieval/models.py:66` | `to_prompt` chunk format uses `item.kind` (cosmetic, appears in prompt). | Verify rename does not break prompt assertions in tests. |

### 1.3 `backend/src/curator/query.py` — query pipeline

| Location | What it does | Action |
|---|---|---|
| `query.py:1-12` | Docstring: "Call search.query() to get top-K matching Curator pages." | KEEP intent; wording fine. |
| `query.py:24` | `from . import search`. | KEEP (still imports search module). |
| `query.py:46` | `hits: list[search.SearchHit]` field on a result dataclass. | KEEP (contract preserved). |
| `query.py:86` | `def on_search_done(self, results: search.SearchResults)` callback. | KEEP (contract preserved). |
| `query.py:131,137` | `_build_user_message(results: search.SearchResults, ...)` builds synthesis context from hits. | KEEP; relies on `hit.full_path`/`full_content`. |
| `query.py:153-157` | Strips `qmd://collection/` prefix from hit path to build `[[wikilink]]`. | SIMPLIFY: native paths are already canonical; the regex strip becomes a no-op but harmless. Recommend removing the qmd:// regex. |
| `query.py:196` | Another `re.sub(r"^/?qmd://[^/]+/", ...)` path cleanup. | Same — remove qmd:// handling. |
| `query.py:200,218` | `translate_to_english()` — comment "for BM25/vector search". | KEEP (still relevant to native FTS/vector). |
| `query.py:389-393` | Docstring: "answered by the v0.3.1 QueryOrchestrator (DB graph + qmd … `.curator/Collections/`)". | UPDATE wording. |
| `query.py:490-495` | **VRAM-management hack**: unloads Ollama model "before qmd runs" because qmd's llama-cpp needs GPU for query expansion. | REMOVE/REVISIT: native engine controls its own embedding/rerank model lifecycle; this `client.unload()` workaround for qmd's separate llama-cpp process is obsolete (native expansion/rerank may reuse the same provider). |
| `query.py:497-543` | `_search_for()` → `search.query(...)`; multi-stage fallback (English → base → extras → keyword → boost terms); line 517-519 comment "qmd has no native path filter" applies `layer_prefix` post-hoc. | KEEP fallback ladder; UPDATE comment; native engine CAN filter by layer (do it in SQL) — optional optimization, but post-hoc filter still works. |
| `query.py:546-567` | `except search.QmdNotInstalled` / `except search.SearchBackendError` → error result. | KEEP `SearchBackendError`; `QmdNotInstalled` branch becomes dead unless alias retained. |

### 1.4 `backend/src/curator/cli.py` — CLI surface

| Location | What it does | Action |
|---|---|---|
| `cli.py:39` | `from . import search`. | KEEP. |
| `cli.py:473-504` | **`_refresh_qmd_index()`** helper — checks `search.is_available()`, prints "Install … `npm install -g @tobilu/qmd`" hints, calls `search.update_index`, prints qmd-flavored messages. | REWRITE: rename to `_refresh_search_index`, drop npm hints, native rebuild messaging. Called at `cli.py:2971,3091,3167,3828`. |
| `cli.py:484-485,489-490` | npm install hint + "`qmd --version`" diagnostic. | REMOVE. |
| `cli.py:494,497-499,501,503-504` | "Updating qmd index…", "qmd vector embedding skipped", "qmd BM25 index updated", "qmd index updated", "qmd index update failed", `wiki reindex` hints. | REWRITE to native wording. |
| `cli.py:336` | LLM-persona description string mentioning "QMD" as an output format. | Cosmetic prose; leave unless doing a docs sweep (not search-engine related). |
| `cli.py:2038,2040` | `wiki reset` deletes `paths.qmd_db` and collections dir. | UPDATE: `qmd_db` path goes away; reset should clear the new in-DB search tables (or drop `state.sqlite` search tables). |
| `cli.py:2302-2309` | `wiki init`: writes qmd `index.yml` via `search.write_qmd_config(paths)`, prints "QMD cfg:" / warnings. | REMOVE this init block (no qmd config to write). |
| `cli.py:2696,2729-2738` | `wiki status` / config table: reads `search_cfg`, prints "Search backend", and the **"QMD binary"** row (version/`not built`/`not found`) via `get_qmd_binary`/`is_available`/`get_version`. | REPLACE "QMD binary" row with native engine readiness (FTS5/embeddings/reranker availability). |
| `cli.py:2971` | After `wiki sync` (or add) → `_refresh_qmd_index(paths, embed=False)`. | KEEP call site; helper rewritten. |
| `cli.py:3091,3167` | `wiki build` paths → `_refresh_qmd_index(paths, embed=True)`. | KEEP call site; helper rewritten. |
| `cli.py:3751` | Help text: "re-index qmd. Use after DB corrections." | UPDATE wording. |
| `cli.py:3828,3830` | After a rebuild → `_refresh_qmd_index(paths)`; prints "qmd re-indexed." | UPDATE wording. |
| `cli.py:4216,4232` | Query progress msgs ("no search needed", "GPU OOM — fell back to BM25 search"). | KEEP "lex fallback" concept; reword "GPU OOM" if native fallback differs. |
| `cli.py:4286-4442` | **`wiki query`** command. Modes `hybrid|lex|vec` (4292-4306), `--route` help mentions "DB graph + qmd" (4324-4326), `is_available()` gate (4398-4404) prints npm hint, collections-empty check counts disk `.md` files (4406-4415), pipeline docstring "QueryOrchestrator routing over DB graph + qmd search" (4356-4359). | UPDATE: keep modes/flags; rewrite `is_available()` gate (no npm hint); the "collections empty" check should arguably count DB rows, not disk `.md` (projection-independence); reword route/pipeline docstrings. |
| `cli.py:4559-4587` | **`wiki reindex`** command — "Force a full rebuild of the QMD search index"; `is_available()` gate w/ npm hint; `search.update_index(paths, embed=True)`; "qmd doctor" hint. | REWRITE: native DB-index rebuild; remove npm + `qmd doctor` references. |
| `cli.py:4686` | lint `--save` help mentions writing report to `04_Synthesis/` (not qmd). | No change (unrelated). |
| `cli.py:5685-5696` | `plugin pdf search` command → `search_source_pages` path (raw-source). | KEEP (qmd-independent). |
| `cli.py:5900-5907` | `plugin zotero search` (title/author). | KEEP (unrelated). |

### 1.5 `backend/src/curator/mcp_server.py` — MCP tools

| Location | What it does | Action |
|---|---|---|
| `mcp_server.py:8-10` | Module docstring: "the `search` tool shells out to the globally installed `qmd` binary to leverage qmd's BM25 + vector + LLM-rerank pipeline." | REWRITE: native in-DB hybrid. |
| `mcp_server.py:675` | `from . import search, ...` inside builder. | KEEP. |
| `mcp_server.py:691-697` | "SEARCH PROTOCOL" agent guidance incl. "Call `curator_reindex` only after manually editing vault files outside MCP." | UPDATE wording (reindex now means rebuild DB search tables). |
| `mcp_server.py:1366-1370` | Ingest-source tool: `search.update_index(paths, embed=False)` to make L1 searchable. | KEEP call; native rebuild. |
| `mcp_server.py:1450-1460` | Build-source tool: `search.update_index(paths, embed=True)` after ingest. | KEEP call; native rebuild. |
| `mcp_server.py:1526-1540` | `curator_search_source` → `search.search_source_pages(...)`. | KEEP (raw-source, qmd-independent). |
| `mcp_server.py:1591` | `from .search import lexical_score`. | KEEP. |
| `mcp_server.py:1806-1920` | **`search_curator`** tool — the DAG search. Docstring "derived qmd corpus" (1817), Korean→English translate (1869-1877), `search.query(... hydrate=True, rerank=True)` w/ unboosted retry (1879-1898), `except QmdNotInstalled` (1899-1900), `except SearchBackendError` → `"qmd error: …"` (1901-1902), result dict has `path/title/score/snippet/body/docid` (1904-1914). | UPDATE: docstring; remove qmd error wording; keep response shape (`hits[]` with path/title/score/snippet/body/docid + count). `docid` now a DB id. |
| `mcp_server.py:1985-2009` | `curator_query` L3-incomplete fallback → `search.query(mode="lex", min_score=0.0, rerank=False)`. | KEEP; native lex. |
| `mcp_server.py:2529` | Help text: `search_curator('<query>', ...)` example. | No change. |
| `mcp_server.py:2902-2909` | `curator_get_version` (backend version, not qmd). | No change. |
| `mcp_server.py:2921-2989` | **`curator_status`** — returns `qmd_binary` (path) and `qmd_ready` (bool) via `search.get_qmd_binary()` (2931, 2986-2987). | REPLACE `qmd_binary`/`qmd_ready` keys with native search-readiness fields (e.g. `search_ready`, `fts_ready`, `embeddings_ready`, `reranker_ready`). NOTE: plugin/dashboard may read these keys — coordinate with `PLUGIN_SCHEMA` (Part B). |
| `mcp_server.py:3126-3152` | **`curator_reindex`** tool — "Rebuild the QMD search index over all Collections pages"; `search.update_index(paths, embed=True)`; returns `{updated, embedded, degraded, warning}`. | REWRITE docstring; keep return shape; native rebuild. |
| `mcp_server.py:3159-3194` | `curator_add_knowledge` → after writing wiki page calls `search.update_index(paths, embed=True)` (3192). | KEEP call; native. |

### 1.6 `backend/src/curator/plugin_api.py` — plugin JSON surface

| Location | What it does | Action |
|---|---|---|
| `plugin_api.py:16` | `from . import db, ingest_raw, llm, query, search, source_tools`. | KEEP. |
| `plugin_api.py:244-247` | After L1 generation: `search.update_index(paths, embed=False)` (best-effort). | KEEP call; native. |
| `plugin_api.py:302-345` | `search_sources()` → `search.search_source_pages(...)` (raw-source). | KEEP (qmd-independent). |
| `plugin_api.py:407` | `from .search import lexical_score`. | KEEP. |
| `plugin_api.py:513` | `_normalize_link` strips `.curator/Collections/` prefix. | KEEP (projection-link normalization; cosmetic). |
| `plugin_api.py:556-564` | `curator_query` L3-incomplete fallback → `search.query(mode="lex", min_score=0.0, rerank=False)`. | KEEP; native lex. |

### 1.7 `backend/src/curator/runtime_state.py` — status/health snapshot

| Location | What it does | Action |
|---|---|---|
| `runtime_state.py:24` | `from . import search`. | KEEP. |
| `runtime_state.py:196-209` | Builds status dict: `qmd_bin = search.get_qmd_binary()`, `qmd_version = get_version() if is_available()`, fields `qmd_binary`, `qmd_ready`, `qmd_version`. | REPLACE qmd_* fields with native search-readiness (mirror the `curator_status` change). Plugin/dashboard consumers must be checked (Part B / PLUGIN_SCHEMA). |
| `runtime_state.py:222` | Surfaces `config.get("search", {})`. | KEEP; the `search` config block changes (see §1.10). |

### 1.8 `backend/src/curator/lint.py` — post-fix reindex + link normalization

| Location | What it does | Action |
|---|---|---|
| `lint.py:57` | `LintIssue.page` doc: "Relpath inside .curator/Collections/". | KEEP (lint still operates on projection pages). |
| `lint.py:140-193` | `PageInventory` walks `.curator/Collections/` subdirs. | KEEP (lint is projection-oriented; out of search scope). |
| `lint.py:237-259` | Wikilink normalization strips `qmd://collection/` prefixes (regex `^/?qmd://[^/]+/`). | KEEP for backward-compat reading old pages, OR remove qmd:// support once projection no longer uses qmd:// links. Low priority; not a search dependency. |
| `lint.py:569-571` | Doc/example text referencing `qmd://curator/...` link forms. | UPDATE comment/example wording (cosmetic). |
| `lint.py:1306-1314` | After `--fix` modifications: `from . import search; search.update_index(paths, embed=True)`. | KEEP call; native rebuild. |

### 1.9 `backend/src/curator/sync.py`

| Location | What it does | Action |
|---|---|---|
| `sync.py:221-263,404-424` | Collections traversal / page-path resolution for DAG sync. | KEEP — projection-level, not search. `sync.py` does NOT call `update_index`/reindex (verified: no `update_index` reference). No search change required here. |

### 1.10 `backend/src/curator/config.py` — config schema + qmd paths

| Location | What it does | Action |
|---|---|---|
| `config.py:156-173` | **`WikiPaths.qmd_dir`** (`.curator/qmd/`), **`qmd_config_file`** (`index.yml`), **`qmd_db`** (`index.sqlite`). | REMOVE these three properties once nothing references them (`search.py`, `cli.py:2038`, `test_cli_reset.py:24`, `test_search_index_fallback.py`). |
| `config.py:214-217` | `DEFAULT_CONFIG["search"] = {"backend": "qmd", "rerank": True}`. | REPLACE: `backend: "native"` (or remove `backend`), add native knobs: embedding provider/model/dim, reranker provider/model, query-expansion provider/model, RRF `k`, candidate limit, min_score defaults. (Spec-pinned in Part B / SYSTEM_BEHAVIOR.) |
| `config.py:231-233` | `curate.auto_update_index` flag. | KEEP semantics (now triggers native rebuild). |

### 1.11 `backend/src/curator/constants.py` — qmd-related constants

| Location | What it does | Action |
|---|---|---|
| `constants.py:11` | `DIR_QMD = "qmd"`. | REMOVE after `config.qmd_dir` removed. |
| `constants.py:16` | `FILE_QMD_YML = "qmd.yml"`. | REMOVE (check no other use). |
| `constants.py:17` | `FILE_INDEX_YML = "index.yml"`. | REMOVE after `qmd_config_file` removed (verify not reused elsewhere). |
| `constants.py:25` | `FILE_QMD_INDEX_SQLITE = "index.sqlite"`. | REMOVE after `qmd_db` removed. |

### 1.12 `backend/src/curator/db.py` — authoritative tables + the new search tables

The search engine will read FROM these existing authoritative tables and write
NEW search tables. None of the existing tables are removed.

| Location | What it does | Action / relevance |
|---|---|---|
| `db.py:3` | Comment: "separate from the QMD search index". | UPDATE comment: search index now lives IN this DB. |
| `db.py:210-228` | **`source_spans`** (`id, source_id, relpath, span_type, page_number, section_title, toc_id, start_char, end_char, content_hash, text_preview, metadata`). | SOURCE for L1/CTX lexical + provenance. `text_preview` is the indexable text. `content_hash` drives invalidation. |
| `db.py:231-247` | **`knowledge_units`** (`statement, canonical_name, unit_type, source_span_ids, confidence, truth_status, atom_node_id, …`). | SOURCE for L2/ATM FTS (`statement`, `canonical_name`). |
| `db.py:250-262` | **`graph_entities`** (`canonical_name, entity_type, description, source_span_ids, …`). | SOURCE for entity lexical/vector (already used by `evidence._entity_evidence`). |
| `db.py:265-280` | **`graph_relations`**. | Optional FTS over `relation_type`/`description`. |
| `db.py:283-300` | **`community_reports`** (`title, summary, full_content, finding_json, …, rank, dependency_hash`). | SOURCE for L3/REP FTS. `dependency_hash` already present → invalidation primitive. |
| `db.py:303-313` | **`memory_paths`**. | Not text-searched; explore route only. |
| `db.py:316-338` | **`prompt_runs`** — note existing `query_trace_id` column (332) + index (338). | The v0.3.2 `query_traces` table (new) will be the parent of these; `prompt_runs.query_trace_id` already anticipates trace persistence. |
| `db.py:341-355` | `curation_plans` (retrieval_policy_json). | Holds per-workspace retrieval policy → feeds native query config. |
| `db.py:376-385` | **`artifact_dependencies`** (`dependency_hash`). | Invalidation backbone for embeddings/FTS staleness. |
| `db.py:391-405` | **`synthesis_nodes`** (`title, statement, full_content, …, dependency_hash`). | SOURCE for L4/SYN FTS. |
| `db.py:1214-1290` | `source_spans` accessors (`list_source_spans`, `get_source_spans_by_ids`, insert). | KEEP; native materializer reads these. |
| `db.py:1292-1362` | `knowledge_units` accessors. | KEEP; add a "list all for FTS materialization" helper if needed. |
| `db.py:1542-1614` | `community_reports` accessors (`list_community_reports`, `get`). | KEEP. |
| `db.py:1680-1749` | `prompt_runs` accessors incl. `list_prompt_runs_for_query(query_trace_id)`. | KEEP; query-trace persistence will join here. |
| `db.py:1931-2003` | `synthesis_nodes` accessors. | KEEP. |
| `db.py:26-28` (schema_version), `db.py:550` (version mismatch handling) | `SCHEMA_VERSION` machinery. | BUMP `SCHEMA_VERSION` when adding the search/trace tables. |
| **NEW (to add)** | `search_documents`, `search_chunks`, `search_embeddings`, `search_index_meta`, FTS5 virtual table(s), `query_traces` (per the plan §3). | ADD these tables + accessors. Embeddings as BLOBs; FTS5 contentless or external-content table shadowing the authoritative rows. |

### 1.13 Workspace templates (`backend/src/curator/workspace/templates/`)

| Location | What it does | Action |
|---|---|---|
| `workspace/templates/qmd-index.yml` (entire file) | The qmd collection config rendered by `write_qmd_config` (`global_context`, `collections.curator.path = __COLLECTIONS_PATH__`, per-layer `context` steering for 01_Contexts/02_Atoms/03_Concepts/04_Synthesis). | REMOVE the file once `write_qmd_config` is removed. NOTE: the per-layer `context` descriptions encode useful "context steering" prose — migrate this intent into the native engine's default per-layer steering/intent context (don't lose it; see parity item P9). |

### 1.14 `setup.sh` / `pyproject.toml` / CI

| Location | What it does | Action |
|---|---|---|
| `setup.sh:1-36` | Builds plugin (`npm install && npm run build`) and installs backend. **Does NOT install qmd** (verified — no `@tobilu/qmd` line). The npm calls are for the Obsidian plugin, unrelated to qmd. | NO removal needed in setup.sh. (The qmd install is purely a manual `npm install -g @tobilu/qmd` referenced only in CLI hint strings and docs.) |
| `backend/pyproject.toml:11-27` | Runtime deps: `typer, rich, pyyaml, onnxruntime<1.24.0, pymupdf4llm, python-docx, beautifulsoup4, lxml, httpx, cryptography, pydantic, hatchling, scikit-learn`. | NO qmd dep exists. ADD nothing for FTS5/cosine (FTS5 bundled in stdlib `sqlite3`; cosine via NumPy — **note NumPy is currently only a transitive dep of scikit-learn/onnxruntime**, so an explicit `numpy` dep should be ADDED to be safe). Optional future: `sqlite-vec` (deferred per plan §4). Embedding/reranker model deps (e.g. llama-cpp-python / sentence-transformers) TBD per provider decision (plan §4 risks). |
| CI | No `.github/` workflows found (verified `fd`/`rg` returned nothing). | No CI qmd-install lines to remove. The Phase_H claim that "CI requires installing qmd" is NOT reflected in any committed workflow. |

### 1.15 Tests (`backend/tests/`) touching search/qmd

| File:line | What it tests | Action |
|---|---|---|
| `tests/test_search_index_fallback.py` (whole file) | Mocks `search._run_qmd`; asserts `update_index` runs `["update"]` then `["embed"]`, and that embed-failure degrades while update-failure raises. Sets up `paths.qmd_dir`/`qmd_config_file`. | REWRITE for native rebuild stages (lexical materialize → embed → degrade), or replace with native-engine equivalent. Hard-coded `_run_qmd`/`qmd_dir` go away. |
| `tests/test_mcp_search_curator.py` (whole file) | Patches `curator.search.query` (returns `SearchResults`/`SearchHit`), asserts `search_curator` retries unboosted query and returns `hits[0].path`. | KEEP largely as-is — it patches `search.query`, so it survives if the contract is preserved. Verify `SearchHit(full_path=..., title=..., score=..., full_content=...)` still constructs (it will). |
| `tests/test_plugin_query_language.py:40-62` | `_seed_concept` builds a `search.SearchResults` with a `search.SearchHit(...)`; used to stub search in plugin-language tests. | KEEP if contract preserved; verify `SearchHit` fields unchanged. |
| `tests/test_mcp_source_tools.py:251,266,281,300` | Calls `search.search_source_pages(...)` (raw-source). | KEEP (qmd-independent). |
| `tests/test_cli_reset.py:24` | Asserts `wiki reset` deletes `curator/"qmd"/"index.sqlite"`. | UPDATE: qmd path removed; assert native search tables cleared instead. |
| `tests/test_v031_synthesis.py:91` | Comment "Projection emitted to the disposable qmd corpus." | UPDATE comment; verify the test asserts projection emission, not search. |
| `tests/test_v031_query_router.py:79` | Asserts `"qmd fallback" in reason` for the router's fallback reason string. | UPDATE expected string when the router's fallback reason text changes (e.g. "native search fallback"). The router reason string lives in `retrieval/router.py` — must be updated together. |

### 1.16 Other modules flagged by grep but NOT search touchpoints (verified, no change)

`page_writer.py` (`re.search` only), `mcp_server` various `re.search`/`pattern.search`, `parsers/text.py` & `parsers/pdf.py` (parsing), `pipeline/*.py` & `pipeline/projection.py` (projection emission, not querying), `prompts.py` / `prompting/*` (`search` appears only in prose), `testbed_manager.py`, `ingest_raw.py`, `llm.py`. These contain the substring "search"/"embed" but are unrelated to the qmd retrieval path. `retrieval/router.py` is relevant only for the fallback-reason string (see test 1.15) and for routing into `evidence.build_evidence`.

---

## 2. qmd Parity Target — what qmd provides today + parity checklist

### 2.1 What qmd does (from `search.py` usage + qmd README/docs)

Verified from code: the Curator invokes qmd subcommands `update`, `embed`,
`query` (hybrid), `search` (BM25), `vsearch` (vector), pins config via
`QMD_CONFIG_DIR`/`INDEX_PATH`, and parses `--json` (`search.py:340-346,
278-313, 376`).

Verified from qmd upstream (`github.com/tobi/qmd` README and the
`@tobilu/qmd` npm/lobehub/tessl pages — see Sources):

- **Query modes / subcommands**:
  - `search` = BM25 full-text only (fastest).
  - `vsearch` = vector semantic only.
  - `query` = **hybrid**: FTS + Vector + Query Expansion + Re-ranking (highest
    quality).
- **Typed query expansion** (`lex` / `vec` / `hyde`):
  - The SDK accepts **pre-expanded queries** with typed sub-queries `lex`
    (lexical/BM25), `vec` (vector), and `hyde` (hypothetical-document expansion,
    a 50–100 word generated answer to boost recall).
  - In the default CLI path, expansion = **original query (×2 weight) + 1 LLM
    variation** → 3 total query variants; each variant runs through both BM25 and
    vector.
  - Expansion model: a fine-tuned `qmd-query-expansion` GGUF (per plan §4).
- **Chunking**: ~**900-token chunks with 15% overlap**. Two strategies:
  `regex` (default; markdown break-point scoring — H1=100, code block=80) and
  `auto` (AST/tree-sitter for `.ts/.tsx/.js/.jsx/.py/.go/.rs`, regex fallback
  otherwise). **Chunk-level embeddings**, not whole-doc.
- **Embedding model**: `embeddinggemma-300M-Q8_0` (ggml-org, ~300 MB) via
  node-llama-cpp GGUF. Document prompt format: `"title: {title} | text:
  {content}"`. Overridable via `QMD_EMBED_MODEL` (e.g. Qwen3-Embedding /
  multilingual).
- **RRF fusion**: `k = 60`, score `= Σ 1/(k + rank + 1)`. **Top-rank bonus**:
  +0.05 for #1, +0.02 for #2–3. Original query weighted ×2.
- **Rerank**: **Qwen3-Reranker cross-encoder** `qwen3-reranker-0.6b-q8_0`
  (~640 MB), `rankAndSort()`, outputs 0.0–1.0. **Top 30 candidates** advance to
  rerank. **Position-aware blend** of retrieval vs reranker:
  - ranks 1–3: 75% retrieval / 25% reranker,
  - ranks 4–10: 60% / 40%,
  - ranks 11+: 40% / 60%.
- **Index lifecycle**: `update` (re-scan filesystem; `--pull` to git-pull repos),
  `embed` (`-f` force re-embed; `--chunk-strategy auto`), `query`.
- **Config knobs**: `qmd.yml`/`index.yml` with `collections` (`path`, `pattern`
  glob, `ignore` rules) + `global_context` + per-path `context` steering
  (`qmd context add qmd://path "description"`); CLI `--min-score` (default 0),
  `-n` (default 5; 20 for `--json`), `-c` collection, `--all`, `--explain`
  (score traces).

### 2.2 Parity checklist — the v0.3.2 native engine MUST meet or exceed each

| # | qmd capability | Parity requirement for native engine | Notes / source-of-truth shift |
|---|---|---|---|
| P1 | BM25 lexical (`search`) | FTS5 BM25 over authoritative rows (`knowledge_units.statement/canonical_name`, `synthesis_nodes.title/statement/full_content`, `community_reports.title/summary/full_content`, `source_spans.text_preview`). | Indexes the **DB**, not markdown. Robust parsing: phrases, negation, hyphen/dotted IDs, prefix, **CJK/Korean via FTS5 trigram** (plan §3.2). |
| P2 | Vector semantic (`vsearch`) | Chunk-level embeddings stored as BLOBs in `state.sqlite`; cosine via NumPy brute force; top-K. | NumPy must be an explicit dep (currently transitive). `sqlite-vec` deferred. |
| P3 | Chunking ~900 tok / 15% overlap, heading-aware | Semantic chunks with stable positions + source-span provenance + model/provider/dim/fingerprint. Whole-node embeddings are **explicitly below parity** (plan §3.3). | Must carry `source_span_ids` for provenance. |
| P4 | Embedding model (embeddinggemma-300M; multilingual override) | Pin provider/model/dim in spec; bge-m3 (KR/EN) vs nomic-embed-text candidates (plan §4). Must run offline/local. | Provider decision is a §4 risk; spec must pin. |
| P5 | Typed query expansion `lex`/`vec`/`hyde` | Deterministic expansion first; configured query-expansion model when available; produce typed `lex`, `vec`, `hyde` variants; preserve `intent` + DAG/KRS context. | Naive single-query embedding = **below parity** (plan §0 critical correction). |
| P6 | Original-query ×2 weighting + N variants | Weight original query higher; multiple variants each fan out to FTS + vector. | Match weighting in RRF contribution. |
| P7 | RRF k=60, +0.05/#1, +0.02/#2-3 | RRF with **qmd-compatible defaults** (`k=60`, original-query weighting, candidate limit, top-rank bonus) + **full contribution trace** (plan §3.5). | Trace persisted to `query_traces`. |
| P8 | Cross-encoder rerank (Qwen3-Reranker 0.6b), top-30, position-aware blend | Rerank best chunks after RRF with a configured cross-encoder / search-fine-tuned model; **position-aware blend** of rerank vs RRF. Generic chat-prompt rerank = degraded fallback only, never the parity target (plan §0/§4). | Reranker provider is a §4 risk; spec must pin. |
| P9 | `global_context` + per-layer `context` steering (in `qmd-index.yml`) | Migrate the per-layer steering prose (01_Contexts…04_Synthesis descriptions) + global context into native intent/context injection. | Don't lose the steering text when deleting the template. |
| P10 | Index lifecycle `update`/`embed`/`query` | `wiki reindex` = native DB-index rebuild (materialize FTS + (re)embed chunks + invalidation via `dependency_hash`/`artifact_dependencies`). | No filesystem scan; rebuild from DB. |
| P11 | `--min-score`, `-n`, `-c`, mode flags, `--explain` | Preserve `query(... min_score, limit, collections, mode)`; expose `--explain`-equivalent via persisted query trace. | Signature preserved (§3.3). |
| P12 | Graceful degradation when models missing | Native must degrade explicitly (lex-only) and set `SearchResults.fallback_mode`, while still exposing expansion/rerank stages in the trace (plan §3 execution gate). | Prevents naive-embedding from silently becoming the accepted path. |

---

## 3. `SearchHit` / `SearchResults` contract (must be preserved)

The replacement engine must keep these shapes so `query.py`, `mcp_server.py`,
`evidence.py`, `plugin_api.py`, and the existing tests keep working unchanged.

### 3.1 `SearchHit` (`search.py:36-45`)

```python
@dataclass
class SearchHit:
    full_path: str        # currently 'LAYER/ID.md' relpath inside .curator/Collections/
    title: str = ""
    score: float = 0.0
    snippet: str = ""
    full_content: str = ""  # populated when hydrate=True
    docid: str = ""         # was qmd content-hash short id (#abc123)
```

Consumer dependencies (all must keep reading these field names):
- `query.py:46` types a field as `list[search.SearchHit]`; `query.py:153,521,545`
  read `hit.full_path`; `_build_user_message` reads `full_content`/`snippet`.
- `evidence.py:48-54` reads `hit.full_content`, `hit.snippet`, `hit.full_path`,
  `hit.title`, `hit.score`.
- `mcp_server.py:1904-1914` emits `hit.full_path` (as `path`), `title`, `score`,
  `snippet`, `full_content` (as `body`), `docid`.
- `mcp_server.py:1999-2007` and `plugin_api.py:561-563` read
  `full_path/title/score/snippet`.
- `tests/test_mcp_search_curator.py:59-63`, `tests/test_plugin_query_language.py:56`
  construct `SearchHit(full_path=, title=, score=, full_content=)`.

Semantic shifts (fields stay, meaning changes):
- `full_path` becomes a synthetic canonical `LAYER/ID.md` derived from the DB row
  (the projection file need not exist). The qmd:// prefix never appears.
- `docid` becomes the DB node id (e.g. `ATM-…`, `SYN-…`) instead of a qmd hash.
- `full_content` is hydrated from the authoritative DB row, not disk.

### 3.2 `SearchResults` (`search.py:48-59`)

```python
@dataclass
class SearchResults:
    hits: list[SearchHit] = field(default_factory=list)
    fallback_mode: str = ""   # e.g. "lex" when hybrid degraded
    def __len__(self): ...
    def __iter__(self): ...
```

Consumers: `query.py:506` (`-> search.SearchResults`, `len(results)`,
`results.hits.sort`), `mcp_server.py:1889` (`len(results) == 0`), all tests above
build `SearchResults(hits=[...])`. `fallback_mode` is currently set nowhere on
the qmd path (always `""`) but is read conceptually for degradation; the native
engine SHOULD populate it (parity P12).

### 3.3 `query()` signature (must be preserved) — `search.py:349-359`

```python
def query(paths, question, *, mode="hybrid", limit=8, min_score=0.6,
          collections=None, hydrate=True, rerank=True) -> SearchResults
```

Callers and the exact kwargs they pass:
- `query.py:507-516`: `mode, limit, min_score, collections=None, hydrate=True, rerank=rerank`.
- `mcp_server.py:1880-1888 / 1890-1898`: `mode, limit, min_score, hydrate=True, rerank=True`.
- `mcp_server.py:1990-1998`: `mode="lex", limit=8, min_score=0.0, hydrate=False, rerank=False`.
- `plugin_api.py:560`: `mode="lex", limit=8, min_score=0.0, hydrate=False, rerank=False`.
- `evidence.py:43`: `mode="hybrid", limit=limit, min_score=0.3, hydrate=True, rerank=True`.

`collections` is effectively always `None` (single `curator` collection); the
native engine can ignore it but must accept it. `mode ∈ {hybrid, lex, vec}`.

### 3.4 Supporting types that stay as-is

- `IndexUpdateResult` (`search.py:75-83`): consumed by `cli.py:4578-4584`,
  `mcp_server.py:3143-3150` (`updated/embedded/degraded/warning`). Keep fields.
- `SourcePageHit` (`search.py:62-72`) + `search_source_pages` /
  `lexical_score`: keep verbatim (qmd-independent provenance search).
- `EvidenceItem.kind` currently includes `"qmd_hit"` (`retrieval/models.py:41`) —
  the ONE string-value that should be renamed; check `to_prompt` (models.py:66)
  and any test asserting the literal.

---

## 4. Removal map (ordered — execute only AFTER native parity tests pass)

The guiding rule (plan §3 step 7): wire the native engine and prove parity FIRST;
delete qmd surfaces SECOND. Suggested order:

1. **Native engine lands behind the preserved `search.query` / `update_index` /
   `is_available` / `get_version` API** (no caller edits yet). Parity tests
   (FTS, vector, RRF, expansion, rerank, trace, degradation) green.

2. **Repoint callers' wording + status fields** (no behavior change to the
   public contract):
   - `cli.py:473-505` → `_refresh_search_index` (drop npm/`qmd --version` hints).
   - `cli.py:2729-2738` status "QMD binary" row → native readiness.
   - `cli.py:4398-4404, 4567-4573` query/reindex gates → native (drop npm hint).
   - `cli.py:4559-4587 reindex` docstring + "qmd doctor" → native rebuild.
   - `mcp_server.py:2921-2989 curator_status` + `runtime_state.py:196-209` →
     replace `qmd_binary`/`qmd_ready`/`qmd_version` with native readiness keys
     (coordinate with PLUGIN_SCHEMA — dashboard may read these).
   - `mcp_server.py:8-10, 691-697, 1817, 1899-1902, 3129-3152` docstrings/error
     strings.
   - `evidence.py:1-7, 39-56, 172`; `retrieval/models.py:41` (`qmd_hit` rename);
     `retrieval/router.py` fallback-reason string; `query.py:389-393, 517-519`.

3. **Delete `wiki init` qmd config wiring**:
   - `cli.py:2302-2309` (the `write_qmd_config` block).
   - `search.py:248, 251-270` (`_QMD_TEMPLATE`, `write_qmd_config`).
   - `backend/src/curator/workspace/templates/qmd-index.yml` (after migrating its
     `global_context` + per-layer `context` steering into native intent context).

4. **Delete binary-resolution + subprocess plumbing in `search.py`**:
   `get_qmd_binary` (104-138), `_require_binary` (172-179), `_qmd_env` (182-209),
   `_run_qmd` (212-240), `_mode_to_subcommand` (340-346), `_normalize_qmd_path` +
   `_QMD_URI_RE` (321-337). Re-point `is_available`/`get_version` to native.
   Decide on `QmdNotInstalled`: keep as inert `SearchBackendError` subclass for
   one release (callers `query.py:546`, `mcp_server.py:1899` catch it) or remove
   and drop those `except` branches.

5. **Remove qmd paths/constants/config**:
   - `config.py:156-173` (`qmd_dir`, `qmd_config_file`, `qmd_db`).
   - `constants.py:11 (DIR_QMD), 16 (FILE_QMD_YML), 17 (FILE_INDEX_YML),
     25 (FILE_QMD_INDEX_SQLITE)` — after verifying no other references.
   - `config.py:214-217` `search` block: `backend: "qmd"` → native + new knobs.
   - `cli.py:2038,2040` `wiki reset` `paths.qmd_db` deletion → clear native search
     tables.

6. **Update env / docs / hints (no binary install anywhere)**:
   - `WIKI_QMD_BIN` env: referenced only in `search.py:106` (`get_qmd_binary`) and
     in docstrings/docs — remove with `get_qmd_binary`.
   - Doc strings "`npm install -g @tobilu/qmd`": `search.py:177` (`_require_binary`
     msg), `cli.py:484-485, 4402, 4571`.
   - Docs (Part B will own the EN/KR guide edits): `docs/guides/USER_GUIDE.md`,
     `WORKFLOW_GUIDE.md`, `MCP_USER_GUIDE.md`, `PLUGIN_GUIDE.md` + `_KR.md`
     counterparts; `docs/philosophy/ABOUT.md` + `_KR.md`. (`SCHEMA_v0.3.2.md`,
     `SYSTEM_BEHAVIOR_v0.3.2.md`, `PLUGIN_SCHEMA_v0.3.2.md` already mention qmd
     and must be reconciled to the native contract.)
   - **`setup.sh`: nothing to remove** (it never installed qmd; its npm steps
     build the Obsidian plugin).
   - **CI: nothing to remove** (no `.github/` workflows exist in-tree).

7. **Migrate/replace tests** (Part C territory, listed here for completeness):
   - REWRITE `tests/test_search_index_fallback.py` (no `_run_qmd`).
   - UPDATE `tests/test_cli_reset.py:24` (no `qmd/index.sqlite`).
   - UPDATE `tests/test_v031_query_router.py:79` ("qmd fallback" string).
   - UPDATE `tests/test_v031_synthesis.py:91` comment.
   - VERIFY `tests/test_mcp_search_curator.py`,
     `tests/test_plugin_query_language.py` still pass against preserved contract
     (they patch `search.query` / build `SearchHit`/`SearchResults`).
   - KEEP `tests/test_mcp_source_tools.py` (raw-source `search_source_pages`).

---

## 5. Key cross-cutting findings / cautions

- **One chokepoint, many callers**: only `search.py` touches qmd; everything else
  is reachable through its public API. Preserving `query()` / `update_index()` /
  `is_available()` / `get_version()` / `SearchHit` / `SearchResults` /
  `IndexUpdateResult` lets the swap be mostly internal, with wording/status edits
  at the edges. This matches Phase H's "the replacement is surgical" claim.
- **The qmd:// regex is triplicated**: `search.py:321`, `query.py:157` & `196`,
  `lint.py:259`. Native results never emit qmd:// — these become no-ops; remove
  for clarity but they are harmless if left.
- **`search_source_pages` is NOT qmd** despite living in `search.py` and a
  misleading docstring ("Curator DAG search still goes through qmd",
  `search.py:499-500`). It must remain functional; only fix the comment.
- **NumPy is not a declared dependency** (only transitive via scikit-learn /
  onnxruntime). Add an explicit `numpy` pin in `pyproject.toml` for the cosine
  path.
- **Phase_H's "CI installs qmd" premise is unverified**: no `.github/` workflow
  exists, and `setup.sh` never installs qmd. The only qmd install instruction is
  manual prose in CLI hints/docs. So "remove qmd from CI" is a no-op; the real
  removals are CLI hint strings, `wiki init` config wiring, the template, and the
  `search.py` subprocess layer.
- **Status-field rename has a plugin blast radius**: `qmd_binary`/`qmd_ready`/
  `qmd_version` appear in both `curator_status` (MCP) and `runtime_state`. The
  Obsidian plugin / dashboard likely reads these — Part B must reconcile the
  `PLUGIN_SCHEMA_v0.3.2` JSON contract before renaming.
- **`prompt_runs.query_trace_id` already exists** (`db.py:332,338`), so the new
  `query_traces` parent table slots in cleanly for the mandated trace
  persistence; reuse `dependency_hash` + `artifact_dependencies` for embedding/FTS
  invalidation rather than inventing a new mechanism.

---

## Sources (qmd upstream, accessed June 2026)

- [qmd README — tobi/qmd (GitHub)](https://github.com/tobi/qmd/blob/main/README.md)
- [tobi/qmd repository](https://github.com/tobi/qmd)
- [@tobilu/qmd — npm](https://www.npmjs.com/package/@tobilu/qmd)
- [qmd — lobehub Skills Marketplace](https://lobehub.com/skills/tobi-qmd-qmd)
- [qmd — Tessl registry](https://tessl.io/registry/skills/github/tobi/qmd/qmd)
- [pi-qmd (BM25 + vector + LLM reranking description)](https://github.com/hjanuschka/pi-qmd)
