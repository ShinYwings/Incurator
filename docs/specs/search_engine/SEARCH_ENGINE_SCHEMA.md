# Incurator Search Engine Schema (v0.25.0)

Audience: Incurator backend, Obsidian plugin, MCP clients, and coding agents.

This file is the concrete schema source of truth for the v0.3.2 DB-native search
engine. It is split out from `docs/specs/curator_schema/SCHEMA.md` so the
Curator DAG schema stays focused on knowledge records while search indexing,
retrieval providers, expansion, embeddings, and query traces have their own
contract.

The search engine still stores its state inside `.curator/state.sqlite`; the
split is documentation/contract separation, not a separate runtime database.

## 1. Configuration Schema

v0.3.2 DB-native search uses backend-owned embedding, query-expansion, and
reranker providers. The default local profile is llama-cpp Qwen3 0.6B for both
embedding and reranking:

```yaml
search:
  backend: native
  query_expansion: true
  expansion_recovery_only: true
  expansion_vector_confidence_floor: 0.35
  expansion_min_lex_hits: 5
  query_expander: ""              # "" | llama-cpp::<model-name>
  query_expander_model_path: ""   # optional machine-local GGUF path
  embedding: llama-cpp::qwen3-embedding-0.6b
  embedding_dim: 1024
  embedding_model_path: ""        # empty -> host cache fallback
  embedding_gguf_repo: Qwen/Qwen3-Embedding-0.6B-GGUF
  embedding_gguf_file: Qwen3-Embedding-0.6B-Q8_0.gguf
  rerank: true
  reranker: llama-cpp::qwen3-reranker-0.6b
  reranker_model_path: ""         # empty -> host cache fallback
  reranker_gguf_repo: ggml-org/Qwen3-Reranker-0.6B-Q8_0-GGUF
  reranker_gguf_file: qwen3-reranker-0.6b-q8_0.gguf
```

`embedding_model_path`, `query_expander_model_path`, and `reranker_model_path`
are machine-local paths and may be omitted from synced vault config. `wiki models
ensure` may persist embedding/reranker paths when a vault is available. If paths
are empty, providers first look in the host model cache
(`~/.cache/incurator/models/` unless `INCURATOR_MODELS_DIR` overrides it).

Query expansion is a separate provider concern from embeddings and reranking:

- `query_expansion` enables the Tier-2 expander path. Deterministic Tier-1
  lexical/vector expansion still runs when this is `false` or when the configured
  provider is unavailable.
- `expansion_recovery_only` defaults to `true`. When enabled, the engine must run
  raw lexical/vector retrieval first and call the Tier-2 expander only when
  lexical hit count is below `expansion_min_lex_hits` or raw vector top
  similarity is below `expansion_vector_confidence_floor`.
- `query_expander` is optional. Empty means "use the configured chat LLM client
  when Tier-2 expansion is enabled." `llama-cpp::<model-name>` means a local GGUF
  expander that emits structured expansion lines.
- `query_expander_model_path` is machine-local and must not be required in synced
  vault config. The structured GGUF parser accepts only `lex:`, `vec:`, and
  `hyde:` lines and remains fail-safe to deterministic Tier-1 expansion.
- Query traces must record whether expansion was recovery-gated, whether it ran,
  lexical hit count, vector confidence, thresholds, and whether HyDE was used.

## 2. Indexed Corpus Boundary

Search reads authoritative DB records materialized into `search_documents`;
`.curator/Collections/` markdown projection pages are not the canonical search
corpus. Re-emitted projection pages may be indexed only through their
authoritative DB rows.

The indexed corpus includes at minimum:

- `source_spans.section_title` and `source_spans.text_preview`
- `knowledge_units.canonical_name` and `knowledge_units.statement`
- `graph_entities.canonical_name` and `graph_entities.description`
- `graph_relations.relation_type` and `graph_relations.description`
- `community_reports.title`, `community_reports.summary`, and
  `community_reports.full_content`
- `synthesis_nodes.title`, `synthesis_nodes.statement`, and
  `synthesis_nodes.full_content`

## 3. `search_documents`

```sql
CREATE TABLE IF NOT EXISTS search_documents (
    doc_id TEXT PRIMARY KEY,
    record_type TEXT NOT NULL,       -- source_span | knowledge_unit | graph_entity | graph_relation | community_report | synthesis_node
    record_id TEXT NOT NULL,
    source_id INTEGER,
    projection_path TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT '',
    content_hash TEXT NOT NULL,
    dependency_hash TEXT NOT NULL,
    provenance_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_search_documents_record ON search_documents(record_type, record_id);
CREATE INDEX IF NOT EXISTS idx_search_documents_source ON search_documents(source_id);
```

Rules:

- `doc_id` is the stable search document id and must survive FTS/chunk rebuilds
  while the underlying `record_type`/`record_id` content is unchanged.
- `record_type` identifies which authoritative table owns the row.
- `record_id` is the authoritative owner id.
- `projection_path` is a display locator only. It must not be treated as source
  truth.
- `content_hash` tracks normalized search body content.
- `dependency_hash` tracks upstream dependencies that should invalidate the row
  even when text stays superficially similar.
- `provenance_json` stores source-span and owner metadata needed for trace
  hydration.

## 4. `search_chunks`

Vector retrieval and reranking operate on chunks, not whole documents only.
Whole-record embeddings may exist as a cache, but they are below the search quality
target if used as the only vector unit.

```sql
CREATE TABLE IF NOT EXISTS search_chunks (
    chunk_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL,
    record_type TEXT NOT NULL,
    record_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    char_start INTEGER NOT NULL,
    char_end INTEGER NOT NULL,
    text TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    source_span_ids TEXT NOT NULL DEFAULT '[]',
    provenance_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(doc_id) REFERENCES search_documents(doc_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_search_chunks_doc ON search_chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_search_chunks_record ON search_chunks(record_type, record_id);
```

Rules:

- Chunk ids must be stable for a given `doc_id`, chunking profile, and text span.
- Chunking must keep stable positions for trace display.
- Chunking must avoid destructive splits of code fences, math blocks, and
  citation spans where practical.
- `source_span_ids` is JSON text and must be hydrated as a list.
- Deleting a search document cascades to chunks and embeddings.

## 5. Lexical FTS5 Tables

The lexical index is internal FTS5. The primary table uses `unicode61`; the
trigram table is a fallback for Korean/CJK and substring/code-identifier search.

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS search_documents_fts USING fts5(
    title,
    body,
    record_type UNINDEXED,
    record_id UNINDEXED,
    doc_id UNINDEXED,
    tokenize = "unicode61 remove_diacritics 2 tokenchars '_-.'"
);

CREATE VIRTUAL TABLE IF NOT EXISTS search_documents_fts_tri USING fts5(
    title,
    body,
    record_type UNINDEXED,
    record_id UNINDEXED,
    doc_id UNINDEXED,
    tokenize = "trigram"
);
```

Rules:

- FTS rows are maintained from `search_documents`.
- `wiki reindex` may fully rebuild both FTS tables.
- Implementations may keep an additional rowid map if needed for deterministic
  targeted delete/upsert.
- CJK or substring-heavy queries may prefer `search_documents_fts_tri`.

## 6. `search_embeddings` And `search_index_meta`

Embeddings are per-device DB state. They are generated for `search_chunks`,
stored as normalized little-endian float32 vectors, and invalidated when provider,
model, dimension, chunking format, `input_hash`, or `dependency_hash` changes.

```sql
CREATE TABLE IF NOT EXISTS search_embeddings (
    chunk_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    dim INTEGER NOT NULL,
    vector BLOB NOT NULL,
    input_hash TEXT NOT NULL,
    dependency_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ready',
    error TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL,
    PRIMARY KEY(chunk_id, provider, model),
    FOREIGN KEY(chunk_id) REFERENCES search_chunks(chunk_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_search_embeddings_model ON search_embeddings(provider, model);

CREATE TABLE IF NOT EXISTS search_index_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

Rules:

- `vector` must encode `dim` little-endian float32 values.
- Stored vectors should be L2-normalized so cosine search can use dot product.
- `provider` and `model` are part of the primary key because different vector
  spaces cannot be compared.
- `status='ready'` means the row is usable for vector search. Other statuses must
  be treated as unavailable and traced as degraded state.
- `search_index_meta` stores lightweight engine metadata such as chunking profile
  fingerprints, model fingerprints, and rebuild timestamps when needed.

## 7. `query_traces`

An orchestrated query owns exactly one authoritative `QTR-` row. Its
`retrieval_trace_json` contains the DB-native engine retrieval details; an
internal engine search performed while assembling orchestrated evidence must
not persist a disconnected second `QTR-`. Public hydrated search hits preserve
their `source_span_ids` through evidence assembly.

`QTR-` traces are durable first-class records so the plugin dashboard and MCP
clients can list and inspect query evidence after the immediate response.

```sql
CREATE TABLE IF NOT EXISTS query_traces (
    trace_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL DEFAULT 'default',
    question_hash TEXT NOT NULL,
    route TEXT NOT NULL,
    route_reason TEXT NOT NULL DEFAULT '',
    evidence_json TEXT NOT NULL DEFAULT '[]',
    source_span_ids TEXT NOT NULL DEFAULT '[]',
    community_report_ids TEXT NOT NULL DEFAULT '[]',
    synthesis_node_ids TEXT NOT NULL DEFAULT '[]',
    memory_path_ids TEXT NOT NULL DEFAULT '[]',
    prompt_trace_ids TEXT NOT NULL DEFAULT '[]',
    insight_candidate_ids TEXT NOT NULL DEFAULT '[]',
    retrieval_trace_json TEXT NOT NULL DEFAULT '{}',
    warnings_json TEXT NOT NULL DEFAULT '[]',
    latency_ms INTEGER,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_query_traces_workspace_created ON query_traces(workspace_id, created_at);
```

`prompt_runs.query_trace_id` remains the join key for prompt-level traces.

## 8. Retrieval Trace JSON Contract

`retrieval_trace_json` must be a JSON object. When DB-native search executes,
it must include enough detail for the dashboard and MCP clients to explain
ranking without re-running the query. Routes that do not execute search may
store `{}`; the authoritative QTR still records their route and evidence.

Required top-level fields:

```json
{
  "mode": "hybrid",
  "intent": "default",
  "is_cjk": false,
  "expansion": {
    "recovery_only": true,
    "recovery_needed": false,
    "used": false,
    "lex_hit_count": 12,
    "min_lex_hits": 5,
    "top_vector_score": 0.62,
    "vector_confidence_floor": 0.35,
    "hyde_used": false
  },
  "lists": {
    "lex_raw": {"weight": 1.0, "count": 12},
    "vec_raw": {"weight": 0.9, "count": 12}
  },
  "fused": [
    {
      "doc_id": "KNU-...",
      "rrf_score": 0.025,
      "contributions": [
        {"list": "lex_raw", "rank": 1, "weight": 1.0, "contribution": 0.024}
      ]
    }
  ],
  "fallback_mode": "",
  "weights": {
    "lex_raw": 1.0,
    "vec_raw": 0.9,
    "lex_exp": 0.6,
    "vec_exp": 0.6,
    "vec_hyde": 0.7
  },
  "fuse_cap": 40,
  "latency_ms": 123
}
```

Rules:

- `lists` keys must identify every candidate list fused by RRF.
- `fused[].contributions` must show each list, rank, weight, and numeric
  contribution used for the document.
- `fallback_mode` is empty for full-quality search and set to a degraded mode
  such as `lex` or `no_rerank` otherwise.
- Warnings should use stable machine-readable prefixes such as
  `vector_unavailable`, `query_expander_unavailable`, and `reranker_failed`.

## 9. Rebuild And Invalidation

`wiki reindex` rebuilds DB-native search state: `search_documents`,
`search_chunks`, FTS5 rows, and missing/stale chunk embeddings. It does not shell
out to an external search binary.

Rules:

- Materialization from authoritative records must update `search_documents`, FTS5
  rows, chunks, and stale embedding state consistently.
- `wiki reindex` without `--embed` rebuilds FTS5/chunk state only.
- `wiki reindex --embed` also regenerates missing/stale chunk embeddings using
  the configured embedding provider.
- If embeddings are unavailable, lexical search remains usable and vector search
  must be traced as degraded.
- If the query expander or reranker is unavailable, answer-producing retrieval
  still returns ranked candidates from the available stages and records explicit
  warnings.

## 10. Compiler-Generation Publish And Full-Span Evidence Hydration (v0.8.0)

Plan B (Evidence Compiler Integrity) binds search-derived state into the
staged compiler generation contract (SCHEMA.md §20.3, SYSTEM_BEHAVIOR §26.3)
and removes the preview-as-evidence defect (Failure Atlas F10).

### 10.1 Generation-Aware Materialization

- Search materialization derived from Plan-B-owned compiled records (knowledge
  units and their projections) is gated at MATERIALIZATION time, not query
  time: it is (re)built ONLY from authoritative-generation units, AFTER the
  generation publishes. A staged generation's units are never materialized, so
  the retrieval/query read path needs no generation filter and is unchanged.
- A discarded generation leaves prior search state untouched (no staged search
  doc was ever written); rollback after a failed publish re-emits search-derived
  state from the prior authoritative generation, never from staged leftovers.
  Because projections and search rows are disposable, a materialization failure
  re-emits from the authoritative DB rather than leaving partial state.
- Retired (`retired_at` set), non-`verified`, and non-authoritative-generation
  claims are excluded from materialization. The compiler audit asserts zero
  retired/staged records in the served index (SCHEMA §20.5 #4).
- Unchanged rebuild produces byte-identical search rows for unchanged records
  (the existing `(record_type, record_id)` upsert idempotency is preserved
  and now asserted per generation).

### 10.2 Full-Span Evidence Hydration (F10)

- `source_spans.text_preview` remains a 200-character display preview in the
  DB; it is NEVER presented as the sufficient source evidence for a span
  longer than the preview.
- Evidence surfaces (evidence packs, source-section route items,
  entity-derived span items) hydrate the exact span text from the registered
  source file at evidence-build time. Hydration re-parses the registered
  source with the SAME deterministic parser + span splitter that produced the
  stored spans, then selects the re-derived span whose `content_hash` matches
  the stored span's hash. Because `content_hash` is the SHA-256 of the exact
  span text, the match IS the verification — the returned text is guaranteed to
  hash to the stored value. (`start_char`/`end_char` remain stored as
  best-effort locators; the content hash, not the offsets, is the retrieval and
  verification key, so the contract is robust to parser-normalization and
  source-format differences such as PDF text extraction.)
- An unreadable/missing source or a content-hash drift (no re-derived span
  matches) marks the evidence item explicitly `stale` (`evidence_status` field
  on the evidence item) — the preview is retained only as a clearly-flagged
  degraded fallback and is never silently presented as the full evidence.
- Hydrated long spans may be served in explicitly chunked, expandable form;
  each chunk carries its parent `SPAN-` id so citation provenance is
  unchanged.
- Central-formula spans (`span_type='equation'`) hydrate with exact source
  text and delimiters; destructive truncation of formula-bearing statements
  in graph input and search materialization is removed (SYSTEM_BEHAVIOR
  §26.2).

## 11. Graph-Quality Materialization (Plan C, v0.9.0)

Plan C (Graph Quality, SCHEMA.md §21, SYSTEM_BEHAVIOR §27) compiles entity
resolution, support-aware relations, and a deterministic community hierarchy.
Search-derived state over those records inherits the same generation-gated,
authoritative-only materialization contract as §10 — the retrieval/query read
path stays unchanged because only authoritative records are ever materialized.

### 11.1 Canonical-Entity And Active-Relation Materialization

- Graph-derived search materialization (entity-derived span items, relation
  evidence, community-report documents) is (re)built ONLY from the authoritative
  graph generation, AFTER it publishes (SYSTEM_BEHAVIOR §27.8). A staged graph/
  report generation is never materialized.
- **Redirected entities are resolved before materialization.** A search document
  or evidence item that would reference a `redirected` `graph_entities` row
  (SCHEMA §21.4) is materialized against its canonical survivor
  (`redirect_to_entity_id`) instead. No served search row references a redirected
  entity directly; the graph audit (SYSTEM_BEHAVIOR §27.6) asserts this.
- **Only `active` relations and their eligible supports materialize.**
  `provisional`, `quarantined`, and `retired` relations (SCHEMA §21.6) are
  excluded from relation evidence materialization, exactly as non-`verified` /
  retired claims are excluded in §10.1. Relation evidence hydrates the cited
  span text via the §10.2 full-span hydration contract (no preview-as-evidence).
- An accepted-merge reversal or a source edit/delete that changes the
  authoritative graph generation re-emits the affected graph-derived search state
  from the post-reconciliation authoritative DB; it never leaves materialized
  rows pointing at a reversed merge or a retired relation.

### 11.2 Community-Report Documents And Retirement

- Community-report search documents materialize ONLY from non-retired
  (`retired_at IS NULL`, SCHEMA §21.7) reports whose findings cite eligible active
  claim support. A community whose identity changed (new
  `member_hash`/`support_hash`/`config_hash`) retires its prior report; the stale
  report's search document is removed in the same publish, so `global`-route
  retrieval (SYSTEM_BEHAVIOR §17) never serves a retired community.
- Unchanged rebuild produces byte-identical graph/report search rows for unchanged
  records (the §10.1 `(record_type, record_id)` upsert idempotency extends to
  entity/relation/community documents); no count amplification.
- The degraded filtered-connected-components hierarchy fallback (SYSTEM_BEHAVIOR
  §27.4) materializes its reports under its own `config_hash` identity — the
  fallback is recorded, never a silent mode change in the served index.

---

## 12. Plan-A Retrieval Result Boundary (v0.10.0)

### 12.1 Internal Retrieval Result

The internal retrieval result produced by `build_evidence` (SYSTEM_BEHAVIOR §28–
§30) is a transport-neutral `EvidencePack`.  Its Plan-A contract fields are:

| Field | Source | Plan-F handoff |
|-------|--------|---------------|
| `retrieval_execution_id` | generated in `build_evidence` | MUST be forwarded unchanged |
| `items` | route-selected, policy-filtered `EvidenceItem` list | MUST NOT be replaced |
| `source_span_ids` | union of all selected item `source_span_ids` | MUST be forwarded |
| `omitted_counts` | per-route omission counts | MUST be surfaced in public pack |
| `warnings` | degradation / policy / locator warnings | MUST be forwarded |
| `retrieval_trace` | serializable dict for `retrieval_trace_json` | MUST be stored in QTR |

Plan F MUST NOT initiate a second `build_evidence` call to enrich the pack.
Progressive expansion handles and client budgeting added by Plan F are stored
alongside (not replacing) the Plan-A fields.

### 12.2 EvidenceItem Locator Contract

Every `EvidenceItem` backed by at least one `source_span_id` MUST carry a
`StructuredLocator` (SYSTEM_BEHAVIOR §29.2) with a resolved `locator_status`.
Items without a backing span (standalone community reports, synthesis nodes with
`source_span_ids=[]`) carry `locator=None`.

Plan F navigation (vault link, PDF jump, external URI) reads `item.locator` and
MUST NOT fabricate its own locator from item metadata.  Rendering a non-`exact`
or non-`fallback_file` locator as a clickable link is a Plan F release-blocking
violation (see SYSTEM_BEHAVIOR §29.3).

### 12.3 RTR-* Persistence

`build_evidence` stores the RTR-* ID and retrieval metadata into the caller-
provided `EvidencePack`.  The orchestrator then serializes
`pack.retrieval_trace` to `query_traces.retrieval_trace_json` via
`db.insert_query_trace`.  No separate persistence call is needed.

Pre-Plan-A `query_traces` rows retain their pre-existing `retrieval_trace_json`
shape.  A reader MUST check `"contract_version"` before accessing Plan-A fields.
