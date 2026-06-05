# Relay State — v0.3.2 Search Internalization Plan / Spec Gate

## Goal
Proceed from the approved v0.3.2 direction: retire qmd as the runtime search
backend and internalize search in Python/SQLite, while preserving or exceeding
qmd retrieval quality. The user explicitly rejected a naive Ollama embedding
drop-in and requires query expansion plus reranking as architectural
requirements. Dashboard click-to-use for query traces and insight candidates is
queued as part of v0.3.2.

## Plan Reference
- Parent plan:
  - `.agents/plans/2026-06_v0.3.2_search_internalization_plan.md`
- Existing v0.3.2 search committee artifacts (Cleaned up: redundant A, B, C, D drafts removed):
  - `.agents/plans/2026-06_v0.3.2_search/A_inventory_and_qmd_parity.md`
  - `.agents/plans/2026-06_v0.3.2_search/B_retrieval_engine_design.md`
  - `.agents/plans/2026-06_v0.3.2_search/C_providers_lifecycle_sync.md`
  - `.agents/plans/2026-06_v0.3.2_search/D_spec_schema_tests_migration.md`
- New integrated artifacts from this Codex pass:
  - `.agents/plans/2026-06_v0.3.2_search/E_qmd_parity_requirements.md` (Crucial: Contains user's strict query expansion & LLM re-ranking requirements)
  - `.agents/plans/2026-06_v0.3.2_search/F_dashboard_click_to_use.md`
  - `.agents/plans/2026-06_v0.3.2_search/G_spec_draft_addendum.md`
- Active synchronized specs remain v0.3.1 until the next approved implementation
  pass:
  - `docs/specs/curator_schema/SCHEMA_v0.3.1.md`
  - `docs/specs/system_behavior/SYSTEM_BEHAVIOR_v0.3.1.md`
  - `docs/specs/plugin_schema/PLUGIN_SCHEMA_v0.3.1.md`

## Analysis & Reasoning
- Microsoft GraphRAG infrastructure remains rejected as a runtime dependency.
  Incurator should keep its own SQLite IR, source-span provenance, KRS, and
  local-first plugin/MCP split, while selectively borrowing ideas like Leiden,
  DRIFT-style routing, and disciplined invalidation where useful.
- qmd retirement is approved, but the replacement must replicate/exceed qmd's
  actual retrieval stack:
  - FTS5/BM25 lexical retrieval with robust parsing.
  - Chunk-level vector retrieval, not whole-record vectors only.
  - Typed query expansion: `lex`, `vec`, `hyde`, plus intent/context.
  - RRF with qmd-compatible defaults/tracing (`k=60`, original-query weighting,
    candidate window, top-rank protection).
  - Best-chunk reranking with a configured cross-encoder/search reranker or
    search-fine-tuned model. Generic chat rerank is degraded mode only.
  - Explicit degraded traces when embeddings, query expansion, or reranker are
    unavailable.
- qmd source inspection confirmed that a simple embedding drop-in would regress:
  qmd uses separate local GGUF models for embedding, query expansion, and
  reranking through `node-llama-cpp`, plus RRF, chunking, caching, fingerprints,
  stale-vector detection, and FTS-only degradation.
- Dashboard click-to-use requires durable `QTR-` query traces. Current v0.3.1
  has `QTR-` ids and `prompt_runs.query_trace_id`, but no first-class query-trace
  list/show API.

## Progress Status
- [x] Read `.agents/relay.md` before work.
- [x] Inspected active v0.3.1 specs and existing v0.3.2 search plans.
- [x] Cloned and inspected qmd source locally at `/tmp/qmd-inspect`.
- [x] Ran four read-only sub-agent analyses:
  - qmd parity inventory and risks.
  - Python retrieval architecture.
  - synchronized v0.3.2 spec migration.
  - dashboard trace/insight click-to-use.
- [x] Strengthened the parent v0.3.2 plan to reject naive embeddings and require
  query expansion/reranking.
- [x] Tightened older v0.3.2 design/test plan language that still said rerank was
  optional/default-off.
- [x] Added qmd parity requirements artifact (`E_qmd_parity_requirements.md`, specifically fulfilling user's mandate for query expansion & LLM re-ranking).
- [x] Added dashboard click-to-use artifact.
- [x] Added v0.3.2 spec draft addendum.
- [x] Cleaned up redundant early drafts (A, B, C, D drafts) from `.agents/plans/2026-06_v0.3.2_search/`.
- [x] P1 — DB schema v6 + version bump + spec-sync guard (Claude Code)
- [x] P2 — db.py search accessors + tests (Claude Code)
- [x] P3 — materializer (records → search_documents + FTS + chunks) wired into compile/reindex + tests
- [x] P4 — lexical query parser + BM25 over FTS5 (phrases/negation/identifiers/Korean) + tests
      (`retrieval/lexical.py`, `test_v032_lexical_search.py`, 8 green)
- [x] P5 — Embedder/Reranker provider family + chunking + embedding lifecycle + tests
      (`retrieval/{chunking,providers,embedding}.py`, `reindex --embed`, numpy dep, 8 green)
- [x] P6 — vector cosine KNN + typed expansion (lex/vec/hyde) + RRF k=60 + tests
      (`retrieval/{vector,expansion,fusion}.py`, `test_v032_vector_rrf.py`, 9 green)
- [x] P7 — HybridEngine answer path + rerank blend + query_traces persistence + tests
      (`retrieval/engine.py`, `test_v032_engine.py`, 5 green). NOTE: concrete GGUF
      reranker NOT yet wired (`providers.build_reranker` returns None → `no_rerank`
      degraded mode); engine fully supports an injected reranker (tested via mock).
- [x] P8 — swapped `search.query`/`search.update_index`/`evidence._search_hits` to the
      native engine; `is_available`→True, `get_version`→`native-<ver>`; CLI `status`/
      `reindex`/`query` + `runtime_state` + `mcp_server` status report native (qmd_*
      back-compat shim kept until P10 migrates the plugin). Full suite 384 green.
- [x] P9 — retired qmd plumbing: deleted get_qmd_binary/_require_binary/_qmd_env/
      _run_qmd/write_qmd_config/_QMD_TEMPLATE/_QMD_URI_RE/_normalize_qmd_path/
      _mode_to_subcommand/_hydrate_hits/QmdNotInstalled; removed qmd_dir/qmd_config_file/
      qmd_db (config.py) + DIR_QMD/FILE_QMD_YML/FILE_INDEX_YML/FILE_QMD_INDEX_SQLITE
      (constants); deleted qmd-index.yml template; dropped qmd lines from git/stignore
      templates; removed write_qmd_config from `wiki init` + testbed_manager; removed
      QmdNotInstalled excepts in query.py/mcp_server.py; fixed test_cli_reset. Full
      suite 385 green. (qmd PROSE in docs/guides still pending → folded into P11.)
- [~] P10 — DONE: backend click-to-use commands `wiki plugin trace list|show`,
      `wiki plugin insight show|reject`, `wiki plugin correction propose` (cli.py) +
      `test_v032_plugin_clicktouse.py` (4 green); plugin status keys migrated
      qmd_*→search_* in `plugin/main.ts` + `incuratorDashboardModal.ts` (tsc clean).
      REMAINING: the Trace/Insights dashboard TAB RENDERING UI (panels + buttons wired
      to the new commands) per F_dashboard_click_to_use.md §1 + vitest. Backend status
      still emits qmd_* shim AND search_* — drop the shim once the UI fully uses search_*.
- [ ] P11 — parity tests (recall@k/MRR vs qmd on testbed) + guides EN/KR (search
      contract, `wiki reindex --embed`, removed qmd prose) + testbed smoke
      (add/build/query/lint/sync/reindex incl. Reference Mode/Zotero). BLOCKED on a
      live reranker + embedder (Ollama bge-m3 + llama-cpp GGUF) for true parity numbers.

## Critical Context / Blockers
- Spec-first gate is active. Do not modify active specs/code until the user
  explicitly approves moving from plan/spec drafts into implementation.
- When implementation begins, v0.3.2 must bump all three spec domains together
  and archive v0.3.1 from the roots.
- Backward compatibility is not required per user direction, but quality parity
  with qmd is required before qmd can be retired.
- Worktree is already dirty from previous cleanup and existing plan/doc edits.
  Preserve unrelated changes. Do not revert user/agent work.
- Important provider decisions:
  - Embedding and Query Expansion proceed exactly as defined in the master plan.
  - **USER OVERRIDE (Reranker):** Do NOT use the baseline `bge-reranker-v2-m3`. Upgrade to a premium LLM-based reranker (e.g., `bge-reranker-v2-gemma` 2B or `Qwen` 1.5B GGUF) to fully utilize the remaining ~1.3GB of the 2.5GB VRAM budget.
  - whether `.curator/Collections/` remains emitted by default or becomes opt-in

## Immediate Next Action
P1–P9 complete; P10 backend + status migration complete. qmd is fully retired from
backend code/config/templates/constants. Full backend suite **389 green**; plugin
`tsc --noEmit` clean. User decisions captured: reranker=llama-cpp GGUF (wired,
fail-closed → degrades to `no_rerank` until model installed), proceed with P9 (done),
Collections markdown = keep opt-in (default emission unchanged, already decoupled).

Resume with the two remaining pieces:

1. **P10 UI (frontend)** — add Trace and Insights tabs to the Obsidian dashboard
   (`plugin/src/ui/incuratorDashboardModal.ts`) that call the new backend commands:
   - `wiki plugin trace list/show` → render route, RRF/rerank contributions, warnings.
   - `wiki plugin insight show/reject` + existing `insight promote` → candidate panel.
   - `wiki plugin correction propose` → correction dialog showing the classification.
   Add vitest coverage. Then drop the backend qmd_* status shim once the UI reads
   search_* exclusively (runtime_state.py + mcp_server.py).

2. **P11** — guides EN/KR first (English then faithful _KR): document the native
   search contract, `wiki reindex --embed`, the `[rerank]` extra + `reranker_model_path`,
   and strip qmd prose from docs/guides. Add parity tests + testbed smoke
   (`VAULT_ROOT=testbed wiki add/build/query/lint/sync/reindex`, incl. Reference
   Mode/Zotero). True recall@k/MRR parity numbers require a live embedder
   (Ollama bge-m3) + the llama-cpp GGUF reranker installed.

KEY FILES THIS SESSION (P4–P10):
- `backend/src/curator/retrieval/{lexical,chunking,providers,embedding,vector,
  expansion,fusion,engine}.py` (new); `materializer.py` (chunks); `search.py` (native
  rewrite); `evidence.py` (_search_hits); `cli.py` (reindex --embed, status, plugin
  trace/insight/correction); `config.py`/`constants.py` (search config + reranker);
  `runtime_state.py`/`mcp_server.py` (status); `pyproject.toml` (numpy, [rerank]).
- Tests: `test_v032_{lexical_search,embedding,vector_rrf,engine,plugin_clicktouse}.py`,
  rewrote `test_search_index_fallback.py`, fixed `test_cli_reset.py`.
- Plugin: `main.ts` + `incuratorDashboardModal.ts` status keys → search_*.
