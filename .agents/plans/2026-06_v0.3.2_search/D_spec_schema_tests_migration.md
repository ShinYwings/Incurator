# v0.3.2 — SPEC DELTAS · SCHEMA (incl. query-trace persistence) · TEST MATRIX · qmd-REMOVAL MIGRATION

Author role: Senior Spec / QA engineer — committee deliverable **D**
Date: 2026-06-05
Status: **DRAFT for orchestrator.** This is a QA/spec consolidation artifact only.
It edits **no runtime code, no real specs, no other plan files** — the single
write is this one markdown file. The orchestrator turns the deltas below into the
real `docs/specs/` edits + tests + migration commits.

Parent goal & verdict: `.agents/plans/2026-06_v0.3.2_search_internalization_plan.md`
(APPROVED: retire external `qmd` → SQLite FTS5 BM25 + chunked in-process vector +
RRF k=60 + typed query expansion `lex`/`vec`/`hyde` + configured cross-encoder/
search reranker; persist a `query_traces` row per query; markdown projection
becomes non-authoritative for search).
Sibling drafts in this folder: `A_code_inventory.md`, `B_retrieval_design.md`,
`C_embeddings_and_sync.md`, `D_spec_test_migration.md` (an earlier D variant),
`E_qmd_parity_requirements.md`, `F_dashboard_click_to_use.md`,
`G_spec_draft_addendum.md`. This file is the schema/test/migration consolidation
and is intentionally exhaustive (additive, per the anti-compression rule).

---

## 0. Ground-truth reconciliation (READ FIRST — the brief is half-stale)

The task brief assumed "active specs today are v0.3.1" and "`SCHEMA_VERSION` in
db.py is 5." **Both are already out of date in the working tree.** I verified the
actual repo state so the orchestrator does not double-bump or re-archive:

| Brief assumption | Actual verified state | Evidence |
|---|---|---|
| Active specs are v0.3.1 | Active specs are **already v0.3.2**; v0.3.1 already archived | `docs/specs/{curator_schema,system_behavior,plugin_schema}/*_v0.3.2.md` exist; `.../archives/*_v0.3.1.md` exist |
| db.py `SCHEMA_VERSION = 5` | db.py `SCHEMA_VERSION = 5` **in the partial Read view (line 23)**, but the live test `test_schema_version_is_6` asserts `db.SCHEMA_VERSION == 6` and passes | `backend/tests/test_v031_db_schema.py:35-36`; `SCHEMA_v0.3.2.md:639` declares `SCHEMA_VERSION = 6` |
| qmd is still the engine in specs | Specs **already rewritten** to DB-native; **runtime still shells out to qmd** | `SYSTEM_BEHAVIOR_v0.3.2.md:688-705`; runtime `search.py`, `evidence.py`, `runtime_state.py:196-209` still call `get_qmd_binary()` |

> **Note on db.py line 23.** My Read of `db.py` was truncated/cached at an early
> revision showing `SCHEMA_VERSION = 5`. The authoritative live value is **6**
> (test + spec agree). The orchestrator MUST treat the *current* on-disk
> `db.SCHEMA_VERSION` as the source of truth and only bump if it is still below 6.
> **The DDL for the five new search tables is already present in `SCHEMA_SQL`** —
> `test_v031_db_schema.py:84` already asserts `search_documents_fts` /
> `search_documents_fts_tri` exist. So the *schema* side of v0.3.2 is largely
> landed; the gap this committee closes is **runtime wiring + tests + qmd removal**.

**Implication for deliverables 1 & 4:** the SCHEMA deltas below are written as a
*verification map* against the already-landed `SCHEMA_v0.3.2.md` / `SCHEMA_SQL`,
not as a fresh bump. The spec-sync checklist (§4) is therefore mostly a
"confirm already done + add the drift guards that are missing."

---

## 1. SCHEMA_v0.3.2 DELTAS (verification map + exact DDL)

### 1.1 `SCHEMA_VERSION` bump
- **Current (live):** `db.SCHEMA_VERSION = 6` (`SCHEMA_v0.3.2.md:639`,
  `test_v031_db_schema.py:36`). v0.3.1 was `5` (`SCHEMA_v0.3.1.md:632`).
- **Action:** none, *if* live value is already 6. If any branch still shows 5,
  bump to 6. Version history string in the spec: `4` → v0.3.1 curation tables,
  `5` → `synthesis_nodes`, `6` → DB-native search + `query_traces`
  (`SCHEMA_v0.3.2.md:649-653`).
- **Self-heal:** forward-only via `executescript(SCHEMA_SQL)` with `IF NOT EXISTS`
  on every table/index/virtual-table, run in both `init_db()` (`db.py:542`) and
  `connect()` (`db.py:570`). `init_db` stamps/updates `schema_version`
  (`db.py:544-555`). **No `_apply_migrations` ALTER is needed** — all five new
  tables are brand-new `CREATE TABLE IF NOT EXISTS`, so old vaults gain them on
  next connect with zero data migration. FTS5 virtual tables likewise self-create.

### 1.2 New v0.3.1 sections that change in v0.3.2 (cite section #s)
The following v0.3.1 SCHEMA sections describe qmd-as-search and become wrong:
- **§ "Storage model: DB is the single source of truth; markdown is a derived
  projection"** (`SCHEMA_v0.3.1.md:610-630`). The phrase *"Their sole purpose is
  to let `qmd` index them for high-quality hybrid (BM25 + vector) search"*
  (lines 620-622) and *"the affected projection page is re-emitted and qmd is
  re-indexed"* (line 630) MUST change to: the search corpus is the internal
  `search_documents` / `search_chunks` / FTS5 / `search_embeddings` tables built
  from authoritative rows; `.curator/Collections/` is an **optional Obsidian-only
  projection, not the search corpus**. Already done in `SCHEMA_v0.3.2.md:625-635,
  1040-1043`.
- **§11 header `SCHEMA_VERSION = 5`** (`SCHEMA_v0.3.1.md:632-643`) → `= 6`
  (`SCHEMA_v0.3.2.md:639-653`). Done.
- The line *"plus the qmd index"* in the v0.2.x carryover list
  (`SCHEMA_v0.3.1.md:636`) MUST drop the qmd index from "remain in use." Verify in
  `SCHEMA_v0.3.2.md:641-647`.
- **§ disposable-corpus mentions** (`SCHEMA_v0.3.1.md:1025`, `1097`) referencing
  `04_Synthesis/SYN-*.md` "as disposable qmd corpus" must drop the "qmd corpus"
  framing.

### 1.3 The five new tables — exact DDL (as landed in `SCHEMA_SQL` / §11.12–11.16)
These are the verbatim contracts the test matrix (§5) targets. Add them to the
canonical `SCHEMA_SQL` string in `db.py` (already present per the FTS test).

```sql
-- §11.12 search_documents — materialized authoritative records (the search corpus)
CREATE TABLE IF NOT EXISTS search_documents (
    doc_id          TEXT PRIMARY KEY,
    record_type     TEXT NOT NULL,   -- source_span|knowledge_unit|graph_entity|graph_relation|community_report|synthesis_node
    record_id       TEXT NOT NULL,
    source_id       INTEGER,
    projection_path TEXT NOT NULL DEFAULT '',
    title           TEXT NOT NULL DEFAULT '',
    body            TEXT NOT NULL,
    language        TEXT NOT NULL DEFAULT '',
    content_hash    TEXT NOT NULL,
    dependency_hash TEXT NOT NULL,
    provenance_json TEXT NOT NULL DEFAULT '{}',
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_search_documents_record ON search_documents(record_type, record_id);
CREATE INDEX IF NOT EXISTS idx_search_documents_source ON search_documents(source_id);

-- §11.13 search_chunks — vector/rerank unit (chunk-level, not whole-doc-only)
CREATE TABLE IF NOT EXISTS search_chunks (
    chunk_id        TEXT PRIMARY KEY,
    doc_id          TEXT NOT NULL,
    record_type     TEXT NOT NULL,
    record_id       TEXT NOT NULL,
    chunk_index     INTEGER NOT NULL,
    char_start      INTEGER NOT NULL,
    char_end        INTEGER NOT NULL,
    text            TEXT NOT NULL,
    input_hash      TEXT NOT NULL,
    source_span_ids TEXT NOT NULL DEFAULT '[]',
    provenance_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(doc_id) REFERENCES search_documents(doc_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_search_chunks_doc    ON search_chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_search_chunks_record ON search_chunks(record_type, record_id);

-- §11.14 FTS5 lexical index — unicode61 primary + trigram fallback (CJK/identifiers)
CREATE VIRTUAL TABLE IF NOT EXISTS search_documents_fts USING fts5(
    title, body,
    record_type UNINDEXED, record_id UNINDEXED, doc_id UNINDEXED,
    tokenize = "unicode61 remove_diacritics 2 tokenchars '_-.'"
);
CREATE VIRTUAL TABLE IF NOT EXISTS search_documents_fts_tri USING fts5(
    title, body,
    record_type UNINDEXED, record_id UNINDEXED, doc_id UNINDEXED,
    tokenize = "trigram"
);

-- §11.15 search_embeddings (per-device, fingerprinted) + search_index_meta
CREATE TABLE IF NOT EXISTS search_embeddings (
    chunk_id        TEXT NOT NULL,
    provider        TEXT NOT NULL,
    model           TEXT NOT NULL,
    dim             INTEGER NOT NULL,
    vector          BLOB NOT NULL,             -- normalized little-endian float32
    input_hash      TEXT NOT NULL,
    dependency_hash TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'ready',  -- ready|stale|error
    error           TEXT NOT NULL DEFAULT '',
    updated_at      TEXT NOT NULL,
    PRIMARY KEY(chunk_id, provider, model),
    FOREIGN KEY(chunk_id) REFERENCES search_chunks(chunk_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_search_embeddings_model ON search_embeddings(provider, model);

CREATE TABLE IF NOT EXISTS search_index_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- §11.16 query_traces — durable QTR- records (NEW persistence; v0.3.1 had them response-only)
CREATE TABLE IF NOT EXISTS query_traces (
    trace_id              TEXT PRIMARY KEY,         -- QTR-<UUID8>
    workspace_id          TEXT NOT NULL DEFAULT 'default',
    question_hash         TEXT NOT NULL,
    route                 TEXT NOT NULL,            -- local|global|explore|source-section
    route_reason          TEXT NOT NULL DEFAULT '',
    evidence_json         TEXT NOT NULL DEFAULT '[]',
    source_span_ids       TEXT NOT NULL DEFAULT '[]',
    community_report_ids  TEXT NOT NULL DEFAULT '[]',
    synthesis_node_ids    TEXT NOT NULL DEFAULT '[]',
    memory_path_ids       TEXT NOT NULL DEFAULT '[]',
    prompt_trace_ids      TEXT NOT NULL DEFAULT '[]',
    insight_candidate_ids TEXT NOT NULL DEFAULT '[]',
    retrieval_trace_json  TEXT NOT NULL DEFAULT '{}',  -- expansion variants, RRF contributions, rerank order/degradation
    warnings_json         TEXT NOT NULL DEFAULT '[]',
    latency_ms            INTEGER,
    created_at            TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_query_traces_workspace_created ON query_traces(workspace_id, created_at);
```

### 1.4 Query-trace persistence — the one genuinely new behavioral contract
- v0.3.1: `QTR-` traces existed only in the response JSON / `prompt_runs.query_trace_id`
  join key (`SCHEMA_v0.3.1.md:872`, `db.py:332,338`). **No `query_traces` table.**
- v0.3.2: every `wiki query` / `curator_query` writes one `query_traces` row;
  `prompt_runs.query_trace_id` (existing column, `db.py:332`) remains the FK join.
  `retrieval_trace_json` MUST carry: expansion variants (`lex`/`vec`/`hyde` +
  `intent`), each ranked list, RRF k and per-candidate contribution, reranker
  provider/model + best chunks + scores, and degradation reasons
  (`vector_unavailable`, `reranker_unavailable`, `expansion_unavailable`).
- **Required db.py accessors to add (none exist yet — confirm against live db.py):**
  `insert_query_trace(...)`, `list_query_traces(db_path, workspace_id, limit)`,
  `get_query_trace(db_path, trace_id)`. Mirror the existing `_new_id("QTR")`
  pattern (`db.py:1184-1186`) and JSON decode helpers (`_loads_list`/`_loads_obj`,
  `db.py:1189-1205`).

### 1.5 Embedding model fingerprint (invalidation contract)
An embedding row is **fresh** iff `(provider, model, dim)` match the configured
provider AND `input_hash` matches `search_chunks.input_hash` AND `dependency_hash`
matches the doc's `dependency_hash`. Any mismatch ⇒ `status='stale'` and the row
is excluded from KNN until `wiki reindex` regenerates it. `search_index_meta`
holds the active `(provider, model, dim, chunk_format_version)` so a provider/model
switch invalidates the whole vector layer deterministically.

---

## 2. SYSTEM_BEHAVIOR_v0.3.2 DELTAS (retrieval contract rewrite)

Already largely landed in `SYSTEM_BEHAVIOR_v0.3.2.md`; this is the verification map
+ the exact v0.3.1 sentences that must die.

### 2.1 Sections that change (cite v0.3.1 §s)
- **§12.2 Search Index Degradation** (`SYSTEM_BEHAVIOR_v0.3.1.md:681-687`) —
  "qmd indexing has two layers: `qmd update` … `qmd embed`" → REPLACE with native
  degradation ladder (below). Verify `SYSTEM_BEHAVIOR_v0.3.2.md:688-707`.
- **§12.1 Reset Behavior** (`v0.3.1:660-674`) — "qmd's generated index database"
  (line 674) → drop; reset now clears the in-DB search tables implicitly with
  `state.sqlite*` (line 666). Add explicit note that `.curator/qmd/` dir is no
  longer created.
- **§17 Query Routing** (`v0.3.1:876-916`) — two qmd sentences MUST change:
  line 905-906 *"the orchestrator falls back to qmd lexical/vector retrieval …
  qmd remains the fallback retrieval engine"* → falls back to **FTS5 + available
  chunk vectors + RRF over authoritative rows**; line 886 *"lexical + vector +
  graph"* now means in-DB FTS5 + chunk-vector + graph. Verify
  `SYSTEM_BEHAVIOR_v0.3.2.md:925-929`.
- **§ retrieval ladder / pipeline diagram** (`v0.3.1:1039-1103`) — the
  "qmd update/embed indexes .curator/Collections/" and "qmd is retained as the
  retrieval engine" lines (1059-1060, 1080-1088) → DB-native pipeline. Verify
  `SYSTEM_BEHAVIOR_v0.3.2.md:1082-1114`.
- **§ testbed validation** (`v0.3.1:763`, `1032`) — "If LLM or qmd … unavailable"
  → "If LLM, embedding, query-expansion, or reranker … unavailable." Verify
  `SYSTEM_BEHAVIOR_v0.3.2.md:784, 1054`.

### 2.2 Native hybrid retrieval contract (the replacement for "qmd is the engine")
Answer-producing routes (`local`, `global`) run this ordered pipeline; each stage
records into `query_traces.retrieval_trace_json`:
1. **Typed query expansion** — deterministic expansion of the user question into
   `lex` (FTS5 MATCH expression), `vec` (embedding text), `hyde` (hypothetical
   answer). A configured query-expansion model runs when available; otherwise
   deterministic-only and `expansion_unavailable` is recorded. `intent` + DAG/KRS
   context preserved.
2. **FTS5/BM25 lexical** over `search_documents_fts` (unicode61), with
   `search_documents_fts_tri` (trigram) fallback for Korean/CJK and dotted/hyphen
   identifiers. **Always available** for any SQLite build with FTS5 (bundled in
   CPython). This is the parity floor.
3. **Chunk-vector KNN** — in-process NumPy cosine over `search_embeddings` BLOBs
   for `search_chunks`. Whole-record embeddings alone are explicitly below parity.
4. **RRF fusion** — Reciprocal Rank Fusion, **k=60**, original-query weighting,
   candidate cap, top-rank bonus; full per-list contribution trace.
5. **Configured rerank** over best fused chunks for `local`/`global` — a search
   cross-encoder / GGUF reranker / validated search-fine-tuned model. Generic chat
   rerank is **degraded mode only**, never the parity target.

### 2.3 Degradation ladder (replaces §12.2)
- No embeddings / no embedding provider ⇒ **FTS5-only**, record `vector_unavailable`.
- No reranker ⇒ proceed in **RRF order**, record `reranker_unavailable`.
- No query-expansion model ⇒ **deterministic expansion only**, record
  `expansion_unavailable`.
- All three degradations are *non-fatal*; the query still returns an answer + trace.
- FTS5 itself missing (non-CPython exotic SQLite) is the only hard failure ⇒
  surface a clear error, never silently return empty.

### 2.4 `wiki reindex` redefinition
- v0.3.1: `wiki reindex` = "Rebuild QMD search index" (CLI help / `_refresh_qmd_index`
  → `qmd update` + `qmd embed`, `cli.py:473-494`).
- v0.3.2: `wiki reindex` = **rebuild DB-native search state**: re-materialize
  `search_documents` from authoritative rows, re-chunk into `search_chunks`,
  rebuild FTS5 rows, regenerate missing/stale `search_embeddings`. Reports counts
  (docs, chunks, FTS rows, embeddings ready/stale/error) and degradation reasons.
  Verify `SYSTEM_BEHAVIOR_v0.3.2.md:704-707`.

### 2.5 Provider selection + status parity
- `search_index_meta` pins active embedding `(provider, model, dim)` and reranker.
- `wiki status` / MCP `curator_status` MUST stop reporting `qmd_binary` /
  `qmd_ready` / `qmd_version` (`runtime_state.py:196-209`) and instead report:
  FTS5 readiness, doc/chunk/embedding counts, embedding provider/model/dim,
  reranker provider/model, and degradation flags. **Status parity test required**
  (§5).

---

## 3. PLUGIN_SCHEMA_v0.3.2 DELTAS (response shape preserved + dashboard click-to-use)

### 3.1 Preserve existing query/search response shape
`CuratorQueryResult` / `CuratorQueryTrace`
(`PLUGIN_SCHEMA_v0.3.2.md:425-443`) are **unchanged** — additive only. The
language-bridge fields (`input_language`, `english_query`, `final_output_language`)
and trace fields (`matched_concepts`, `source_ids`, `source_paths`, `section_ids`,
`latency_ms`, `l3_complete`) stay. No qmd-specific status field is added; any
plugin code reading `qmd_ready` must be dropped (clean-rebuild stance,
`PLUGIN_SCHEMA_v0.3.2.md:11-14`).

### 3.2 New hidden plugin JSON commands (dashboard click-to-use) — already specified
Confirmed present in `PLUGIN_SCHEMA_v0.3.2.md:666-685, 791-874`:
```
wiki plugin trace list   --workspace-path PATH --limit N --json   → TraceListResult
wiki plugin trace show   --trace-id QTR-... --workspace-path PATH --json
wiki plugin insight show    --insight-id INS-... --workspace-path PATH --json
wiki plugin insight promote --insight-id INS-... --workspace-path PATH --json   (only promotion path; writes 02_Wiki/)
wiki plugin insight reject  --insight-id INS-... --workspace-path PATH --reason TEXT --json
wiki plugin propose-correction  (maps curator_propose_correction; classify + patch-plan, --dry-run)
```
Plugin API map (`:681-685`): `listQueryTraces`, `getQueryTrace`,
`getInsightCandidate`, `promoteInsight`, `rejectInsight`.
- **Read-only/no-direct-DB rule:** dashboard Trace/Insights tabs call these hidden
  `wiki plugin … --json` commands; they MUST NOT edit `state.sqlite`,
  `Collections/`, or FTS rows directly (`PLUGIN_SCHEMA_v0.3.2.md:870-874`).
- `trace list` reads `query_traces` (newest first, by
  `idx_query_traces_workspace_created`); `trace show` returns the full
  `retrieval_trace_json` (expansion/RRF/rerank) for audit.
- `insight show/reject/promote` read/write `insight_candidates`
  (`db.py:358-373`); promote ⇒ `status='promoted'`, writes only `02_Wiki/`.

### 3.3 Delta to confirm in the real plugin spec
The v0.3.1 plugin spec text referencing qmd evidence wording
(`PLUGIN_SCHEMA_v0.3.1.md`) must read "DB-native search evidence." Verify the
v0.3.2 header note (`PLUGIN_SCHEMA_v0.3.2.md:9`) and §5 trace rules
(`:475` "QTR- trace over selected DB-native search and graph evidence").

---

## 4. SPEC-SYNC CHECKLIST (file moves + drift guard)

### 4.1 File-move state (verified — already done; orchestrator confirms)
```
docs/specs/curator_schema/SCHEMA_v0.3.2.md              ✅ active
docs/specs/curator_schema/archives/SCHEMA_v0.3.1.md     ✅ archived
docs/specs/system_behavior/SYSTEM_BEHAVIOR_v0.3.2.md    ✅ active
docs/specs/system_behavior/archives/SYSTEM_BEHAVIOR_v0.3.1.md  ✅ archived
docs/specs/plugin_schema/PLUGIN_SCHEMA_v0.3.2.md        ✅ active
docs/specs/plugin_schema/archives/PLUGIN_SCHEMA_v0.3.1.md      ✅ archived
```
All three domains are at v0.3.2; each domain root holds exactly one active file;
v0.3.1 lives in `archives/`. **No moves remain.** (Per AGENTS.md spec-sync rule:
all three bump together, old versions to `archives/`.) The orchestrator's only
job here is to *confirm* none drifted back.

### 4.2 Lightweight drift guards (tests — extend existing `test_v031_db_schema.py`)
- `test_schema_version_is_6` — already exists (`:35-36`). Keep.
- `test_spec_declares_matching_schema_version` — already exists (`:39-45`); asserts
  the active SCHEMA spec text contains `` `SCHEMA_VERSION = 6` ``. Keep.
- **ADD** `test_all_three_domains_at_v0_3_2`: glob each domain root, assert exactly
  one `*_v0.3.2.md` and **zero** `*_v0.3.1.md` in the root (only in `archives/`).
  This is the spec-sync guard so versions cannot drift apart.
- **ADD** `test_no_qmd_in_active_specs`: assert the three active v0.3.2 spec files
  contain no `qmd` token **except inside explicit "retire/removed/legacy" framing**
  (allow a small whitelist of lines that say qmd is gone). Prevents silent
  reintroduction of qmd-as-engine wording.

---

## 5. TEST MATRIX (concrete pytest names + asserts)

New file unless noted. All under `backend/tests/`. Run: `cd backend && uv run pytest`.

### 5.1 Query parser / expansion — `test_v032_query_parser.py`
| Test | Assert |
|---|---|
| `test_exact_phrase_quoted` | `parse_query('"neural scaling"')` → FTS5 `MATCH '"neural scaling"'`; phrase kept intact |
| `test_negation_excludes_term` | `parse_query('scaling -dropout')` → FTS5 expr with `NOT dropout`; chunk containing only "dropout" excluded |
| `test_dotted_identifier_preserved` | `parse_query('torch.nn.Linear')` not split on `.` (tokenchars `'_-.'`); matches doc with that identifier |
| `test_hyphen_identifier_preserved` | `parse_query('bge-m3')` matches `bge-m3` not `bge OR m3` |
| `test_korean_routes_to_trigram` | Hangul query has no `unicode61` token hits → trigram-table fallback used; recorded in trace |
| `test_typed_expansion_lex_vec_hyde` | expansion returns all three variants + `intent`; deterministic path stable across runs |
| `test_expansion_degraded_when_no_model` | no expansion model ⇒ deterministic-only + `expansion_unavailable` in trace |

### 5.2 Chunking determinism — `test_v032_chunking.py`
| Test | Assert |
|---|---|
| `test_chunk_positions_stable` | same `search_documents.body` ⇒ identical `(chunk_index, char_start, char_end, input_hash)` across two runs |
| `test_chunk_input_hash_changes_on_edit` | body edit ⇒ different `input_hash` for affected chunk only |
| `test_chunk_preserves_code_fence` | code-fenced block not split mid-fence where avoidable |
| `test_chunk_carries_source_span_ids` | chunks inherit `source_span_ids` from their doc/record |

### 5.3 FTS5 BM25 — `test_v032_fts.py`
| Test | Assert |
|---|---|
| `test_fts_bm25_ranks_relevant_first` | doc with more term hits ranks above sparse doc (bm25 score order) |
| `test_fts_prefix_match` | `scal*` matches "scaling"/"scalable" |
| `test_fts_trigram_substring` | trigram table returns substring/CJK hit the unicode61 table misses |
| `test_fts_rebuild_from_documents` | wipe + rebuild FTS rows from `search_documents` ⇒ identical hit set |

### 5.4 Vector KNN determinism — `test_v032_vector.py`
| Test | Assert |
|---|---|
| `test_cosine_knn_order_deterministic` | fixed BLOB vectors ⇒ identical top-k order over repeated calls |
| `test_normalized_float32_roundtrip` | BLOB encode→decode preserves dim + values (little-endian f32) |
| `test_stale_embedding_excluded` | row with mismatched `input_hash`/`dependency_hash` (`status='stale'`) excluded from KNN |
| `test_provider_switch_invalidates_all` | changing `(provider,model,dim)` in `search_index_meta` ⇒ all vectors treated stale |

### 5.5 RRF determinism — `test_v032_rrf.py`
| Test | Assert |
|---|---|
| `test_rrf_k_is_60` | fusion uses k=60; `1/(60+rank)` contributions in trace |
| `test_rrf_deterministic_tie_break` | equal RRF scores break deterministically (stable doc_id order) |
| `test_rrf_contribution_trace_complete` | each fused candidate lists `(source, query_type, rank, weight, contribution)` |
| `test_rrf_fts_only_when_no_vectors` | with no embeddings, RRF == FTS5 order |

### 5.6 Rerank ordering — `test_v032_rerank.py`
| Test | Assert |
|---|---|
| `test_rerank_reorders_best_chunks` | configured reranker (stub) changes order vs RRF; trace records scores |
| `test_rerank_position_aware_blend` | blend of rerank score + RRF position applied as specified |
| `test_rerank_degraded_no_reranker` | no reranker ⇒ RRF order + `reranker_unavailable` (non-fatal) |

### 5.7 Degradation — `test_v032_degradation.py`
| Test | Assert |
|---|---|
| `test_no_embeddings_fts_only` | empty `search_embeddings` ⇒ FTS5-only answer + `vector_unavailable` |
| `test_no_reranker_rrf_order` | as 5.6 degraded; answer still returned |
| `test_no_expansion_deterministic_only` | as 5.1 degraded |
| `test_fts_missing_is_hard_error` | (skip if FTS5 always present) simulate ⇒ clear error, never empty-silent |

### 5.8 Reindex — `test_v032_reindex.py`
| Test | Assert |
|---|---|
| `test_reindex_rebuilds_documents_chunks_fts` | after authoritative row changes, `wiki reindex` re-materializes docs/chunks/FTS counts |
| `test_reindex_regenerates_stale_embeddings` | stale rows regenerated; ready count rises; report includes ready/stale/error |
| `test_reindex_reports_degradation` | no embedding provider ⇒ report flags `vector_unavailable`, exit non-error |

### 5.9 Query-trace persistence — `test_v032_query_trace_persist.py`
| Test | Assert |
|---|---|
| `test_query_writes_one_trace_row` | one `wiki query` ⇒ one `query_traces` row with `QTR-` id |
| `test_trace_carries_retrieval_json` | `retrieval_trace_json` has expansion variants + RRF k + rerank/degradation |
| `test_prompt_runs_join_on_query_trace_id` | `prompt_runs.query_trace_id` == the QTR row id |
| `test_list_and_get_query_trace` | `list_query_traces(ws, limit)` newest-first; `get_query_trace(id)` round-trips JSON fields |

### 5.10 MCP / status parity — `test_mcp_search_curator.py` (extend existing)
| Test | Assert |
|---|---|
| `test_search_curator_db_native` | `search_curator` returns hits from DB-native search, no `QmdNotInstalled` path |
| `test_curator_status_no_qmd_fields` | `curator_status` has no `qmd_binary`/`qmd_ready`/`qmd_version`; has FTS/embedding/reranker fields |
| `test_status_cli_mcp_parity` | `wiki status` JSON and MCP `curator_status` agree on search-readiness fields |

### 5.11 qmd-PARITY comparison — `test_v032_qmd_parity.py` (gates removal; can be skip-marked until both engines coexist)
| Test | Assert |
|---|---|
| `test_parity_top_k_overlap` | on a seeded testbed corpus, native top-k vs recorded qmd top-k overlap ≥ threshold (e.g. ≥0.7 Jaccard@10) |
| `test_parity_known_query_returns_known_doc` | each curated (query→expected doc) pair returns the expected doc in native top-k |
| `test_parity_korean_query` | Korean query parity via trigram path |
> These compare against **golden fixtures** captured from the last qmd run (stored
> as JSON), so they keep gating after qmd is uninstalled. Removal (§6) is blocked
> until these pass.

### 5.12 Testbed smoke — `test_v032_testbed_smoke.py` (or manual checklist)
`wiki testbed init <scenario> --force` then:
```
VAULT_ROOT=testbed wiki add      # ingest (Reference Mode / Zotero sources included)
VAULT_ROOT=testbed wiki build    # L1–L4 + materialize search_documents/chunks/embeddings
VAULT_ROOT=testbed wiki query "<seeded question>"   # returns answer + QTR trace
VAULT_ROOT=testbed wiki lint
VAULT_ROOT=testbed wiki sync
VAULT_ROOT=testbed wiki reindex  # DB-native rebuild, prints counts
```
Assert: query returns a `QTR-` trace; reindex prints doc/chunk/embedding counts;
Reference-Mode/Zotero sources are searchable without hard-copying into the vault.
Document any LLM/embedding/reranker blocker explicitly per AGENTS.md.

---

## 6. qmd-REMOVAL / MIGRATION PLAN (ordered; removal AFTER parity passes)

### 6.0 Gate
Removal begins **only after** §5.11 parity tests + §5.10 status parity + §5.12
testbed smoke pass with the native engine. Until then qmd coexists (dead but
present) so golden fixtures can be regenerated.

### 6.1 Exact removal targets (verified locations)
1. **Binary resolution + env** — `backend/src/curator/search.py`: delete
   `get_qmd_binary()` (`:104`), `is_available()` (`:140`), `get_version()`,
   `QmdNotInstalled` (`:95`), `SearchBackendError` qmd wording, and the
   `WIKI_QMD_BIN` env lookup (`:106`). Replace `search.py` with the DB-native
   search module (FTS5 + vector + RRF + rerank) keeping the public
   `SearchHit`/`SearchResults` dataclasses where MCP/`search_curator` consume them.
2. **Evidence fallback** — `backend/src/curator/retrieval/evidence.py`: replace
   `_qmd_hits()` (`:39`) and its two call sites (`:173`, `:211`) with DB-native
   FTS5+vector+RRF retrieval; drop the "qmd unavailable"/"falling back to qmd"
   warnings (`:44-45`, `:172`).
3. **CLI** — `backend/src/curator/cli.py`: replace `_refresh_qmd_index()`
   (`:473-494`, `qmd update`/`qmd embed`) with the DB-native reindex; update
   `wiki reindex` + `wiki query --help` text (drop "legacy qmd synthesis").
4. **MCP** — `backend/src/curator/mcp_server.py`: rewrite `search_curator`
   (`:1806-1902`) to DB-native (drop `search.QmdNotInstalled` catch `:1899`);
   update module docstring (`:9-10`); update `curator_status` (`:2898+`) to drop
   qmd readiness; fix the agent-hint text referencing `curator_reindex` (`:697`).
5. **Runtime status** — `backend/src/curator/runtime_state.py`: remove `qmd_bin`,
   `qmd_version`, `qmd_binary`, `qmd_ready`, `qmd_version` fields (`:196-209`);
   emit FTS/embedding/reranker readiness instead.
6. **Config** — `backend/src/curator/config.py`: remove `qmd_dir` (`:161`),
   `qmd_config_file` (`:166`), `qmd_db` (`:171`); change default config
   `"backend": "qmd"` (`:215`) to the DB-native backend id.
7. **Constants** — `backend/src/curator/constants.py`: remove `DIR_QMD` (`:11`),
   `FILE_QMD_YML` (`:16`), `FILE_QMD_INDEX_SQLITE` (`:25`).
8. **Template** — delete `backend/src/curator/workspace/templates/qmd-index.yml`;
   remove its references in `qmd-index.yml` writers and in `gitignore.template` /
   `stignore.template` (the `.curator/qmd/` ignore lines).
9. **Other backend refs** — clean qmd mentions in `ingest_raw.py`, `llm.py`,
   `lint.py`, `query.py`, `testbed_manager.py`, `pipeline/{projection,compile,
   synthesis,__init__}.py`, `plugin_api.py` (grep `qmd` ⇒ ~25 files). Each is a
   comment/wiring touchpoint surfaced by `grep -rln qmd backend/src/curator/`.
10. **setup.sh / CI** — `setup.sh` currently has **no** qmd install line
    (verified: `grep qmd setup.sh` → empty), so nothing to remove there beyond
    confirming. Remove any `npm install -g @tobilu/qmd` from CI/docs if present.
11. **Docs EN + KR** — no `docs/guides/*` currently mention qmd (verified: grep
    returned only specs). Confirm guides describe `wiki reindex` as a DB-index
    rebuild and search as DB-native; if any KR guide lags its EN counterpart,
    update in the same commit (CLAUDE.md docs rule).

### 6.2 Ordered execution
1. Land native search module + tests §5.1–5.9 (qmd still present, unused).
2. Capture golden qmd fixtures; land §5.11 parity + §5.10 status parity; make green.
3. Wire MCP/CLI/evidence/runtime to native (steps 6.1.2–6.1.5); keep qmd code
   importable but unreferenced.
4. Run §5.12 testbed smoke; document blockers.
5. **Removal commit**: delete steps 6.1.1, 6.1.6–6.1.8 (binary, config, constants,
   template) + clean comment refs (6.1.9); update docs (6.1.10–6.1.11) EN then KR.
6. Add drift guards §4.2 (`test_no_qmd_in_active_specs`, version-sync test).

### 6.3 Rollback / degradation
- Pre-removal: feature-flag the engine (`search.backend: db_native | qmd` in
  config) so a single config flip restores qmd while both coexist. Remove the flag
  only in the final removal commit.
- Post-removal rollback = `git revert` of the removal commit (qmd code is a pure
  deletion, no schema rollback needed — the search tables are additive and
  harmless if qmd returns).
- Runtime degradation (not rollback): native engine always degrades to FTS5-only,
  so an absent embedding/reranker provider never blocks search.

### 6.4 Risks
- **Parity threshold subjectivity** — a too-low Jaccard@10 ships a quality
  regression. Mitigation: pin the threshold in `E_qmd_parity_requirements.md` and
  require the curated known-query pairs (§5.11) to be 100%.
- **FTS5 availability** — assumed bundled in CPython's sqlite3; exotic builds may
  lack it. Mitigation: `test_fts_missing_is_hard_error` + a startup capability
  probe written to `search_index_meta`.
- **Korean/CJK quality** — trigram fallback is coarser than a CJK-aware analyzer.
  Mitigation: `test_korean_routes_to_trigram` + parity Korean case; revisit
  `bge-m3` embeddings (plan §4) if lexical Korean recall is weak.
- **Embedding cost/latency on large vaults** — brute-force cosine is fine to
  ~50k nodes (plan §5); document the `sqlite-vec` escape hatch in
  `search_index_meta` without adopting it now.
- **Stale golden fixtures** — once qmd is uninstalled, parity fixtures freeze;
  treat them as a regression baseline, not a live oracle.

---

## 7. Open items for the orchestrator (do not silently decide)
1. Confirm live `db.SCHEMA_VERSION` is 6 (not 5 as the truncated Read showed) before
   any bump. Re-bump only if a branch regressed.
2. Pin embedding provider/model/dim and reranker provider in `search_index_meta`
   and in `SYSTEM_BEHAVIOR_v0.3.2` (plan §4 leaves `bge-m3` vs `nomic-embed-text`
   and the reranker open — a `/grill-me` candidate).
3. Decide whether `.curator/Collections/` markdown emission stays opt-in once
   search no longer needs it (plan §4 recommends: keep, default-off, decoupled).
4. Confirm the `query_traces` accessors (`insert/list/get_query_trace`) are added
   to db.py — none exist in the live file yet.
