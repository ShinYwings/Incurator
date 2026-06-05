# v0.3.2 Search Internalization — Master Implementation Plan (integrated)

Date: 2026-06-04
Status: **APPROVED — implementing in phases.** Specs (SCHEMA/SYSTEM_BEHAVIOR/PLUGIN
v0.3.2) are already authored and document the query-expansion + reranking quality
requirements; tests are spec-first (TDD). This plan integrates the 4 committee
artifacts in this folder: `A_inventory_and_qmd_parity.md`,
`B_retrieval_engine_design.md`, `C_providers_lifecycle_sync.md`,
`D_spec_schema_tests_migration.md`. Read those for full detail.

## Strict quality condition (user-mandated, non-negotiable)
A naive Ollama-embedding drop-in is **below parity**. The Python backend MUST
replicate or exceed qmd's pipeline: **typed query expansion (lex/vec/hyde)** +
**chunk-level vectors** + **RRF** + a **dedicated reranker** (cross-encoder or
validated search-fine-tuned local model). A generic chat-model rerank is a
**degraded fallback only**, never the parity target. This is already written into
`SYSTEM_BEHAVIOR_v0.3.2.md` (§ search engine / query expansion / reranking) and is
enforced by the test matrix in artifact D.

## Locked design decisions (from committee A–D)
- **Lexical:** FTS5 external-content over `search_documents`; dual tokenizer
  (`unicode61 … tokenchars '_-.'` primary + `trigram` fallback for Korean/CJK and
  code identifiers). Rebuild-on-reindex maintenance (content-hash diffed), not
  triggers. BM25 with title weighting; fuse by rank (no score normalization).
- **Chunking:** sentence-window ~256 target / 384 max / 48 overlap / 32 min tokens;
  content-addressed `chunk_id` (reuse cached embeddings when text unchanged);
  per-chunk span provenance from the parent record.
- **Vector:** float32 BLOB, L2-normalized at write, keyed `(chunk_id, provider,
  model)`. **Brute-force NumPy cosine now** (≈<2 ms @1k, 10–20 ms @10k, 80–150 ms
  @100k); documented switch to `sqlite-vec` at >50k chunks or >250 ms p95. Add
  `numpy` as an explicit backend dependency (currently only transitive).
- **Typed expansion:** Tier-1 deterministic (CJK detect, phrase/negation/identifier
  handling, synonyms, `intent`) ALWAYS runs; Tier-2 LLM expander adds `lex`/`vec`
  paraphrases + `hyde` (HyDE recovery-only, reranker-validated). KRS/persona
  context injected as policy-allowed boosts.
- **RRF:** `k=60`; original-query weighting (lex 1.0 / vec 0.9 / expansions 0.6 /
  hyde 0.7); candidate cap ~100→40; top-rank bonus; full per-candidate
  contribution trace persisted to `query_traces`.
- **Rerank (answer path only):** default `bge-reranker-v2-m3` (GGUF); position-aware
  blend (alpha≈0.7 cross-encoder over RRF). Explicitly AVOID Qwen3-Reranker GGUF as
  default (commonly broken). Degraded fallbacks recorded in trace.
- **Providers:** separate duck-typed `Embedder`/`Reranker` client family +
  `build_embedder()`/`build_reranker()` mirroring `build_client()`; `expand_query()`
  reuses the chat client. Default embedder **`ollama::bge-m3` (1024-dim)** — chosen
  for Korean cross-lingual quality; cloud fallback `openai-api::text-embedding-3-small`
  (Matryoshka→1024). Embedder switch = **whole-corpus re-embed**, NOT per-request
  failover (different model = different vector space).
- **Sync:** embeddings are **per-device DB state, NOT synced** (no sidecar by
  default; regenerable from synced source truth). Optional `--export/--import-
  embeddings` escape hatch. Offline → FTS5-only with `vector_unavailable` in trace.
- **Traces:** every query persists a `query_traces` (`QTR-`) row (route, evidence
  ids, RRF contributions, rerank info, degraded reasons, latency).

## Contracts preserved (so callers don't change)
`search.SearchHit` / `search.SearchResults` field shapes and the
`search.query(paths, q, mode=, limit=, min_score=, hydrate=, rerank=)` signature
are preserved; new fields are additive/optional (artifact A §3, B §8).

## Phases (each: implement → unit tests → `uv run pytest` + `ruff` green)

- **P1 — DB schema (DONE):** `SCHEMA_VERSION=6`; `search_documents`,
  `search_chunks`, `search_documents_fts(+_tri)`, `search_embeddings`,
  `search_index_meta`, `query_traces` added to `SCHEMA_SQL`; backend `__version__`
  + pyproject → 0.3.2; spec-sync guard → active 0.3.2 / prev 0.3.1. Suite 342 green.
- **P2 — db.py accessors:** CRUD for the 6 tables incl. `insert/list/get_query_trace`
  (FK key = `prompt_runs.query_trace_id`), FTS upsert/delete/rebuild helpers,
  embedding upsert/fetch-by-model, `search_index_meta` get/set. Tests:
  `test_v032_search_db.py`.
- **P3 — Materializer:** project authoritative records (source_spans / knowledge_units
  / graph_entities / graph_relations / community_reports / synthesis_nodes) into
  `search_documents` + maintain both FTS tables; wire into `compile.py` +
  `wiki reindex`. Tests: materialization completeness + FTS rebuild determinism.
- **P4 — Lexical query + parser:** query parser (exact phrase, negation,
  hyphen/dotted identifiers, prefix, Korean→trigram fallback) + BM25 ranking over
  the two FTS tables. Tests: parser + BM25 determinism (no models needed).
- **P5 — Embedding providers + lifecycle:** `Embedder`/`Reranker` family + factories;
  chunking (P3 docs → `search_chunks`); embed during compile + `wiki reindex --embed`;
  fingerprint + `dependency_hash` invalidation; degradation matrix. Tests mock the
  embedder (no live model required); live smoke gated on Ollama availability.
- **P6 — Vector + expansion + RRF:** brute-force cosine KNN; deterministic Tier-1
  expansion + LLM Tier-2 (lex/vec/hyde); RRF k=60 fusion with contribution trace.
  Tests: cosine determinism, RRF determinism, expansion typing (LLM mocked).
- **P7 — Rerank + answer wiring + traces:** reranker integration (degraded
  fallback), position-aware blend; persist `query_traces`; wire into `query.py` /
  retrieval answer path. Tests: rerank ordering (mocked), trace persistence.
- **P8 — Swap engine:** replace `evidence._qmd_hits` + `search.query` internals with
  the native engine, preserving `SearchHit`/`SearchResults`; reindex/status/MCP
  parity; uniform FTS5-only degradation. Tests: retrieval parity + MCP status.
- **P9 — Retire qmd:** remove binary resolution/env, `qmd-index.yml` template,
  `qmd_dir`/`qmd_db` config + `DIR_QMD*` constants, the triplicated `qmd://` strip
  regex, and qmd prose in docs EN/KR — only after P8 parity tests pass.
- **P10 — Dashboard click-to-use:** plugin hidden JSON commands (`trace list/show`,
  `insight show/reject/promote`, `propose correction`) per PLUGIN_SCHEMA_v0.3.2 +
  Trace/Insights dashboard tabs; vitest + tsc.
- **P11 — Parity + guides + smoke:** qmd-parity comparison tests; guides EN/KR
  (search contract, `wiki reindex`, removed qmd); testbed smoke
  (`add`/`build`/`query`/`lint`/`sync`/`reindex`) incl. Reference Mode/Zotero.

## Model-availability note
P2–P4, P6 (RRF/expansion-structure), P8 are fully testable WITHOUT live models
(mock the embedder/reranker). P5/P7 live verification needs Ollama `bge-m3` +
`bge-reranker-v2-m3`; tests mock these and a testbed smoke runs them when present.

## Open items to confirm (optionally `/grill-me`)
- Pin default embedder/reranker models (bge-m3 / bge-reranker-v2-m3 recommended).
- Keep emitting `.curator/Collections/` markdown at all once search no longer needs
  it (recommend: optional Obsidian-only projection, decoupled from search).
