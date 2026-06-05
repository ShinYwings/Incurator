# v0.3.2 Search Internalization — G. Spec Draft Addendum

Date: 2026-06-04
Status: Draft clauses for the active specs. Do not treat this as an active
contract until copied into `docs/specs/*_v0.3.2.md` after approval.

## 0. Spec Synchronization Mechanics

Current active roots are v0.3.1:

- `docs/specs/curator_schema/SCHEMA_v0.3.1.md`
- `docs/specs/system_behavior/SYSTEM_BEHAVIOR_v0.3.1.md`
- `docs/specs/plugin_schema/PLUGIN_SCHEMA_v0.3.1.md`

v0.3.2 must move all three together:

1. Copy active v0.3.1 specs to root v0.3.2 files.
2. Move v0.3.1 files into each domain's `archives/` folder.
3. Ensure each root contains exactly one active spec and it is v0.3.2.
4. Update spec-sync tests to expect v0.3.2 and schema version 6 or the chosen next
   schema integer.

## 1. Curator Schema Draft Clauses

### 1.1 DB-Owned Search Corpus

As of v0.3.2, `.curator/Collections/` is not the search corpus. It is an
optional Obsidian projection. Search is internal to `state.sqlite` and indexes
authoritative DB records directly.

### 1.2 Search Documents and Chunks

Add:

```sql
CREATE TABLE IF NOT EXISTS search_documents (
    doc_id TEXT PRIMARY KEY,
    record_type TEXT NOT NULL,
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

CREATE TABLE IF NOT EXISTS search_chunks (
    chunk_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL,
    record_type TEXT NOT NULL,
    record_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    char_start INTEGER NOT NULL,
    char_end INTEGER NOT NULL,
    text TEXT NOT NULL,
    text_hash TEXT NOT NULL,
    source_span_ids TEXT NOT NULL DEFAULT '[]',
    provenance_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(doc_id) REFERENCES search_documents(doc_id) ON DELETE CASCADE
);
```

Indexed record types include `source_span`, `knowledge_unit`, `graph_entity`,
`graph_relation`, `community_report`, and `synthesis_node`.

### 1.3 FTS5 Tables

Add primary unicode FTS and Korean/CJK/substring fallback:

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

The implementation may keep a rowid map if needed for deterministic targeted
delete/upsert. `wiki reindex` must be able to rebuild both FTS tables from
`search_documents`.

### 1.4 Embeddings

Add chunk-level vectors:

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

CREATE TABLE IF NOT EXISTS search_index_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

Vectors are per-device DB state. They are regenerated when provider/model/dim,
chunking format, input hash, or dependency hash changes.

### 1.5 Query Traces

Add `query_traces` as described in `F_dashboard_click_to_use.md`. Query traces
must persist retrieval-stage metadata: expansion, candidate lists, RRF
contributions, rerank scores, degradation warnings, evidence ids, prompt trace ids,
and insight candidate ids.

## 2. System Behavior Draft Clauses

### 2.1 Retire qmd

qmd is retired as a runtime backend, index owner, status dependency, and install
requirement. `wiki query`, `wiki reindex`, MCP search, and plugin query must work
with no qmd binary and no `.curator/qmd/`.

### 2.2 Native Retrieval Contract

Default retrieval is:

```text
deterministic expansion
  + configured query-expansion model when available
  -> FTS5 BM25 over `lex` expansions
  -> vector cosine over original/`vec`/`hyde` expansions
  -> graph/context seed expansion
  -> RRF
  -> configured reranker over best chunks
  -> evidence pack
```

Query expansion and reranking are architectural requirements, not optional
quality extras. They may degrade when unavailable, but the degraded trace must
say what was skipped and why.

### 2.3 Degradation

Degraded modes:

- no embeddings: FTS5-only with `vector_unavailable`
- embedding model mismatch: ignore stale vectors and request reindex
- query expander unavailable: deterministic expansion only
- reranker unavailable: RRF-only with `reranker_unavailable`
- source file missing under Reference Mode: use stored previews and mark
  hydration warning

None of these should hard-fail ordinary query unless no lexical index can be read.

### 2.4 Reindex

`wiki reindex` rebuilds internal DB search state:

- rebuild `search_documents`
- rebuild FTS5
- regenerate missing/stale embeddings
- report counts for FTS rows, chunks, embedded chunks, skipped unchanged, failures,
  provider/model, and degraded state

It no longer shells out to qmd or writes qmd config.

### 2.5 Backprop and Corrections

Any mutation to a searchable DB record updates:

- the authoritative row
- `search_documents`
- `search_chunks`
- FTS5 rows
- stale embedding markers or regenerated vectors

This occurs in the same transaction or an explicitly recoverable indexed-write
unit. There is no emit-to-markdown then external reindex step.

## 3. Plugin Schema Draft Clauses

### 3.1 Search Response Parity

Preserve `path`, `title`, `score`, `snippet`, `body`, `docid`, and existing query
trace fields where possible. Additive fields may include:

- `record_type`
- `record_id`
- `source_span_ids`
- `component_scores`
- `retrieval_trace`

### 3.2 Dashboard Trace and Insight Actions

The plugin uses hidden local JSON commands:

- `wiki plugin trace list`
- `wiki plugin trace show`
- `wiki plugin prompt trace`
- `wiki plugin insight list`
- `wiki plugin insight show`
- `wiki plugin insight promote`
- `wiki plugin insight reject`
- `wiki plugin correction propose`

Dashboard reads runtime snapshots but all durable changes go through backend
commands. It never writes DB files or projection/source directories directly.

## 4. Guide Update Map

Update English first, then Korean:

- `USER_GUIDE.md` / `USER_GUIDE_KR.md`
- `WORKFLOW_GUIDE.md` / `WORKFLOW_GUIDE_KR.md`
- `MCP_USER_GUIDE.md` / `MCP_USER_GUIDE_KR.md`
- `PLUGIN_GUIDE.md` / `PLUGIN_GUIDE_KR.md`
- `CONTRIBUTION_GUIDE.md` / `CONTRIBUTION_GUIDE_KR.md`
- `SYNC_IGNORE_GUIDE.md` / `SYNC_IGNORE_GUIDE_KR.md`
- `AGENT_WORKFLOW_GUIDE.md` / `AGENT_WORKFLOW_GUIDE_KR.md`

Remove or replace:

- qmd install guidance
- qmd doctor hints
- `.curator/qmd/` sync-ignore guidance
- qmd binary status rows
- "DB + qmd corpus" wording

Add:

- internal DB hybrid search
- query expansion/reranking requirements
- degraded search modes
- dashboard Trace/Insights tabs
- click-to-use insight promotion and correction proposal

## 5. Drift Guards

Add or update tests to fail if:

- active root specs are not synchronized at v0.3.2
- `SCHEMA_VERSION` does not match v0.3.2
- active docs/source still require qmd, `WIKI_QMD_BIN`, `.curator/qmd`, or
  `QmdNotInstalled`
- query expansion is absent from default hybrid retrieval
- reranking is skipped without an explicit degraded trace
- whole-record embeddings are used as the only vector unit
- dashboard actions write DB/projection/source files directly instead of hidden
  backend commands
