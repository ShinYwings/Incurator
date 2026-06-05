# B — Retrieval Engine Design (v0.3.2 in-DB hybrid search)

Date: 2026-06-05
Status: DESIGN ARTIFACT (no runtime code changed by this document)
Scope: concrete engine design for the native, in-`state.sqlite` hybrid search
that retires the external `qmd` binary, per
`.agents/plans/2026-06_v0.3.2_search_internalization_plan.md`.

This is the engine-level companion to `A_code_inventory.md` (what exists today),
`C_embeddings_and_sync.md` (embedding lifecycle/invalidation), and
`D_spec_test_migration.md` (spec + test plan). Where those documents already cover
something (e.g. embedding invalidation discipline), this file references rather
than re-derives it, and focuses on the **retrieval algorithm**: FTS5 layer,
chunking, vector layer, typed expansion, RRF fusion, rerank, per-route flow, and
the public API contract.

---

## 0. Design constraints discovered from the codebase

These are the hard constraints the engine must honor. They come directly from the
files read during this design pass.

1. **Authoritative records live in DB tables, not files.** The searchable text
   columns confirmed in `backend/src/curator/db.py`:
   - `source_spans.text_preview` (`TEXT NOT NULL DEFAULT ''`), with provenance
     `source_id`, `relpath`, `span_type`, `page_number`, `section_title`,
     `toc_id`, `start_char`, `end_char`, `content_hash`.
   - `knowledge_units.statement` + `knowledge_units.canonical_name`
     (with `unit_type`, `source_span_ids` JSON, `source_id`, `confidence`,
     `truth_status`, `atom_node_id`).
   - `community_reports.title` + `.summary` + `.full_content`
     (with `entity_ids`, `relation_ids`, `source_span_ids`, `rank`,
     `dependency_hash`).
   - `synthesis_nodes.title` + `.statement` + `.full_content`
     (with `community_report_ids`, `concept_ids`, `source_span_ids`,
     `confidence`, `dependency_hash`).
   - Secondary but useful: `graph_entities.canonical_name` + `.description`,
     `graph_relations.description`.

2. **`state.sqlite` is single source of truth; markdown is a disposable
   projection.** The whole reason for v0.3.2 is that `qmd` indexes
   `.curator/Collections/*.md`, which makes the projection load-bearing and
   re-introduces DB↔file drift. The engine MUST read text *from the DB rows*, not
   from disk markdown. (Plan §0.B.)

3. **`SearchHit` / `SearchResults` / `search.query(...)` shapes are a caller
   contract.** `query.py` and `retrieval/evidence.py._qmd_hits` both consume
   `SearchHit.full_path / title / score / snippet / full_content`. We must keep
   those field names alive even though `full_path` will no longer be a markdown
   relpath but a DB node id / locator (see §8). Callers in `query.py`
   (`_build_synthesis_user_prompt`) build `[[wikilink]]`s from `full_path`, so the
   locator must still be projectable to a node-style wikilink.

4. **SQLite is bundled FTS5-capable; zero new hard dependency for lexical.**
   Python's stdlib `sqlite3` ships FTS5 in CPython's bundled SQLite on macOS/Linux
   wheels. The vector layer must also default to **zero new dependency**
   (NumPy is already a transitive dep through parsers/embeddings work in
   `C_embeddings_and_sync.md`); `sqlite-vec` is an *optional accelerator*, not a
   baseline requirement.

5. **Graceful degradation is mandatory.** Today `_qmd_hits` swallows a missing
   backend and appends a warning. The new engine must degrade in the same spirit:
   no embeddings → FTS5-only with a warning; no reranker → RRF order with a
   warning; never hard-fail a query because an optional model is absent.

6. **Personal-KB scale.** Hundreds to low-tens-of-thousands of nodes; after
   chunking, low-tens-of-thousands to ~100k chunks worst case. This is the
   regime where brute-force NumPy cosine is correct and ANN is premature.

---

## 1. FTS5 lexical layer

### 1.1 Table topology: standalone external-content FTS5, one per record family

Three FTS5 table-topology options exist
([SQLite FTS5 docs](https://sqlite.org/fts5.html)):

| Topology | Stores text? | Maintenance | Verdict for us |
|---|---|---|---|
| **Standard** (`content` defaults to itself) | Yes (duplicated) | FTS5 owns a copy | Wastes space; text is already in base tables. |
| **External-content** (`content='base_table', content_rowid='id'`) | No (reads base table) | Triggers OR explicit rebuild | **Recommended.** No duplication; `snippet()`/`highlight()` still work by reading the base row. |
| **Contentless** (`content=''`) | No, and cannot reconstruct | Insert-only; can't `snippet()` | Rejected — we want `snippet()` and we re-index on rebuild. |

**Decision: external-content FTS5, but rebuilt-on-reindex rather than
trigger-synchronized (see §1.3).** External-content gives us `bm25()`,
`snippet()`, and `highlight()` for free while keeping the authoritative text in
the base tables.

**One FTS5 table per record family**, not one mega-table. Rationale: the four
families have different column weightings and different rowid spaces
(`source_spans.id` etc. are `SPAN-xxxx` *text* PKs, while FTS5 `rowid` must be an
integer). We therefore introduce a thin physical projection table
`search_documents` that assigns every searchable record an integer `doc_rowid`,
and FTS5 indexes that projection. This is cleaner than four parallel FTS5 tables
fighting over rowid mapping, and it is the join anchor the vector layer also uses
(§3).

```sql
-- Physical projection: one row per searchable record family member.
-- This is a *search index artifact*, rebuildable from authoritative tables.
CREATE TABLE search_documents (
    doc_rowid     INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id       TEXT NOT NULL,          -- SPAN-/KNU-/REP-/SYN-/ENT- id
    family        TEXT NOT NULL,          -- source_span|knowledge_unit|community_report|synthesis_node|entity
    title         TEXT NOT NULL DEFAULT '',
    body          TEXT NOT NULL DEFAULT '',  -- the primary searchable text
    layer         TEXT NOT NULL DEFAULT '',   -- L1..L4 hint, for scope filtering
    source_id     INTEGER,                -- provenance roll-up where available
    source_span_ids TEXT NOT NULL DEFAULT '[]',
    content_hash  TEXT NOT NULL DEFAULT '',   -- hash(title||body) for staleness
    UNIQUE(family, node_id)
);

-- External-content FTS5 over the projection.
CREATE VIRTUAL TABLE search_fts USING fts5(
    title,
    body,
    content='search_documents',
    content_rowid='doc_rowid',
    tokenize='unicode61 remove_diacritics 2'
);
```

The `title`/`body` mapping per family (column choices justified in §1.2):

| family | title column(s) | body column(s) |
|---|---|---|
| `source_span` | `section_title` | `text_preview` |
| `knowledge_unit` | `canonical_name` | `statement` |
| `community_report` | `title` | `summary` + `\n` + `full_content` |
| `synthesis_node` | `title` | `statement` + `\n` + `full_content` |
| `entity` (optional) | `canonical_name` | `description` |

### 1.2 Which columns to index, and BM25 column weights

We index `title` and `body` as two FTS5 columns so BM25 can weight a title hit
above a body hit. FTS5's `bm25()` accepts per-column weights:

```sql
-- title weighted 2x over body (qmd-comparable behavior: name/heading hits matter)
SELECT doc_rowid, bm25(search_fts, 2.0, 1.0) AS bm25_raw
FROM search_fts WHERE search_fts MATCH :q
ORDER BY bm25_raw LIMIT :cap;
```

Note FTS5 `bm25()` returns a value that is **more negative = more relevant**
(it returns the negated BM25). We normalize in §1.5.

We deliberately do NOT index `truth_status`, `confidence`, JSON id arrays, or
hashes — those are filters/metadata, not free text.

### 1.3 Maintenance: rebuild-on-reindex (default) with optional triggers

Two maintenance strategies:

- **Trigger-based incremental** — `AFTER INSERT/UPDATE/DELETE` triggers on each
  base table keep `search_documents` + FTS5 in sync transactionally. Pro: always
  fresh. Con: five base tables × three triggers = brittle, and our base rows are
  written through many `upsert_*` paths in `db.py`; a missed path silently
  desyncs the index — exactly the drift class we are trying to kill.

- **Rebuild-on-reindex** — `wiki reindex` (and the post-ingest hook) recomputes
  `search_documents` from the authoritative tables, diffing by `content_hash`, and
  issues `INSERT INTO search_fts(search_fts) VALUES('rebuild')` only when rows
  changed. Pro: one deterministic code path, trivially correct, matches the
  existing "emit the projection on demand" mental model. Con: search can lag
  ingest until reindex runs.

**Decision: rebuild-on-reindex as the contract, made cheap by content-hash
diffing, and triggered automatically at the end of `wiki add`/`wiki sync` so the
lag window is effectively zero in normal use.** This mirrors the v0.3.1 compile
model (DB is truth; index is a derived projection refreshed by an explicit
compile step) and avoids the multi-writer trigger fragility. `C_embeddings_and_sync.md`
already proposes content-hash invalidation for embeddings; we reuse the *same*
`content_hash` on `search_documents` so lexical and vector rebuilds share one
staleness signal.

Incremental upsert (not full rebuild) per changed record:

```python
def _upsert_search_document(conn, family, node_id, title, body, layer,
                            source_id, source_span_ids):
    content_hash = sha256(f"{title}\x00{body}".encode()).hexdigest()
    row = conn.execute(
        "SELECT doc_rowid, content_hash FROM search_documents "
        "WHERE family=? AND node_id=?", (family, node_id)).fetchone()
    if row and row["content_hash"] == content_hash:
        return row["doc_rowid"], False            # unchanged → skip FTS write
    if row:
        doc_rowid = row["doc_rowid"]
        # external-content FTS5: delete-then-insert keeps the index consistent
        conn.execute("INSERT INTO search_fts(search_fts, rowid, title, body) "
                     "VALUES('delete', ?, "
                     "(SELECT title FROM search_documents WHERE doc_rowid=?), "
                     "(SELECT body  FROM search_documents WHERE doc_rowid=?))",
                     (doc_rowid, doc_rowid, doc_rowid))
        conn.execute("UPDATE search_documents SET title=?, body=?, layer=?, "
                     "source_id=?, source_span_ids=?, content_hash=? "
                     "WHERE doc_rowid=?",
                     (title, body, layer, source_id, source_span_ids,
                      content_hash, doc_rowid))
    else:
        cur = conn.execute(
            "INSERT INTO search_documents(node_id,family,title,body,layer,"
            "source_id,source_span_ids,content_hash) VALUES(?,?,?,?,?,?,?,?)",
            (node_id, family, title, body, layer, source_id,
             source_span_ids, content_hash))
        doc_rowid = cur.lastrowid
    conn.execute("INSERT INTO search_fts(rowid, title, body) VALUES(?,?,?)",
                 (doc_rowid, title, body))
    return doc_rowid, True
```

(The `'delete'` command form is the documented way to maintain an
external-content FTS5 table when the underlying content changes; see
[FTS5 §4.4.3](https://sqlite.org/fts5.html).)

### 1.4 Tokenizer: dual-index `unicode61` + `trigram` for CJK/identifiers

This is the most consequential lexical decision. The candidates:

- **`porter`** — English stemming on top of `unicode61`. Helps recall on English
  morphology (`optimize`/`optimization`) but **destroys exact technical
  identifiers** and does nothing for Korean. Rejected as the primary.
- **`unicode61`** (default) — Unicode-aware word tokenizer. Good for
  English/Latin and for Korean *word-spaced* tokens, supports prefix queries
  (`term*`), phrase queries (`"a b"`), and `NOT`. **But** it splits on
  punctuation, so `nn.Conv2d` tokenizes to `nn` + `conv2d`, and CJK text without
  spaces is poorly segmented.
- **`trigram`** — character-3-gram tokenizer. Substring/`LIKE`-style matching;
  the practical way to get usable **Korean/CJK** recall in FTS5 without a
  morphological analyzer, and it also matches *inside* identifiers
  (`Conv2d` is findable inside `nn.Conv2d`). Caveats from the SQLite forum:
  trigram + external-content has known sharp edges, and trigram needs ≥3 chars
  per token so it can't match 1–2 char queries.

**Decision: maintain TWO FTS5 indexes over the same projection and union them at
query time.**

```sql
CREATE VIRTUAL TABLE search_fts USING fts5(            -- primary
    title, body,
    content='search_documents', content_rowid='doc_rowid',
    tokenize='unicode61 remove_diacritics 2 tokenchars ''.-_/'''
);
CREATE VIRTUAL TABLE search_fts_tri USING fts5(        -- CJK + substring recall
    title, body,
    content='search_documents', content_rowid='doc_rowid',
    tokenize='trigram'
);
```

Two non-obvious but deliberate choices:

1. **`tokenchars '.-_/'` on the unicode61 index.** This tells `unicode61` to treat
   `.`, `-`, `_`, `/` as *token characters* rather than separators, so
   `nn.Conv2d`, `bge-m3`, `state.sqlite`, and `source_span_ids` survive as single
   tokens — exactly the dotted/hyphenated technical identifiers the plan calls
   out. We accept that this slightly reduces recall for naturally hyphenated
   prose, which the trigram index recovers.
2. **The trigram index is the Korean/CJK and substring safety net.** A query like
   `합성` (2 chars) is below trigram's 3-char floor, so for very short CJK queries
   we additionally fall back to a `LIKE '%term%'` scan over `search_documents.body`
   (bounded, personal-KB scale). The expansion layer (§4) flags `is_cjk` so the
   router knows to engage trigram + LIKE.

Query-time union (the lexical retriever returns the *best* rank a doc achieves in
either index):

```python
def lexical_search(conn, fts_query, *, cap, weights=(2.0, 1.0), is_cjk=False):
    rows = {}
    for table in ("search_fts", "search_fts_tri" if is_cjk else "search_fts"):
        try:
            res = conn.execute(
                f"SELECT rowid AS doc_rowid, bm25({table}, ?, ?) AS s "
                f"FROM {table} WHERE {table} MATCH ? ORDER BY s LIMIT ?",
                (*weights, fts_query, cap)).fetchall()
        except sqlite3.OperationalError:
            continue                      # malformed MATCH → skip this index
        for r in res:
            # bm25 is negated; smaller = better. Keep the strongest per doc.
            rows.setdefault(r["doc_rowid"], r["s"])
            rows[r["doc_rowid"]] = min(rows[r["doc_rowid"]], r["s"])
    if is_cjk and len(rows) == 0:         # very short CJK fallback
        rows = _like_scan(conn, raw_terms, cap)
    ranked = sorted(rows.items(), key=lambda kv: kv[1])   # ascending = best first
    return [doc_rowid for doc_rowid, _ in ranked]
```

### 1.5 FTS5 query construction: phrases, negation, prefix, identifiers

A raw user question must be converted into a **safe FTS5 MATCH string**. Passing
the question verbatim is unsafe (FTS5 syntax errors on stray quotes/operators)
and low-precision. The builder (deterministic, in the expansion layer §4) does:

```python
FTS_SPECIAL = re.compile(r'["()*]')

def build_fts_match(terms, *, phrases=(), excludes=(), prefix=True):
    """terms: required OR-group; phrases: quoted exact; excludes: NOT terms."""
    parts = []
    for ph in phrases:                                  # exact phrase
        parts.append('"' + ph.replace('"', '') + '"')
    or_group = []
    for t in terms:
        t = FTS_SPECIAL.sub(" ", t).strip()
        if not t:
            continue
        # quote dotted/hyphenated identifiers so '.' '-' aren't operators
        if re.search(r'[.\-/_]', t):
            or_group.append(f'"{t}"' + ("*" if prefix else ""))
        else:
            or_group.append(t + ("*" if prefix else ""))   # prefix match
    if or_group:
        parts.append("(" + " OR ".join(or_group) + ")")
    match = " ".join(parts) if parts else ""
    for ex in excludes:                                  # negation
        match += f' NOT "{ex}"'
    return match.strip()
```

Behaviors this yields:
- **Exact phrase**: user quotes (`"reciprocal rank fusion"`) → preserved as an
  FTS5 phrase token.
- **Negation**: a leading `-term` or an LLM-expander `excludes` list →
  `... NOT "term"`.
- **Hyphenated/dotted identifiers**: `nn.Conv2d` → `"nn.Conv2d"*` (quoted so the
  tokenizer's `tokenchars` keep it whole; trailing `*` allows
  `nn.Conv2d` to match `nn.Conv2dTranspose`-style suffixes when tokenized whole).
- **Prefix matching**: every plain term gets a trailing `*` by default
  (recall-favoring; the expander can disable it for precision-critical intents).
- **OR-grouping**: terms are OR'd (recall) rather than AND'd; precision is
  recovered by BM25 ranking + RRF + rerank rather than by hard AND filtering,
  matching the qmd "retrieve wide, rank hard" philosophy.

### 1.6 BM25 scoring + normalization

FTS5 `bm25()` returns a *negated* score (smaller = better). RRF (§5) only needs
*rank order*, so the lexical layer can hand RRF a ranked `doc_rowid` list and never
normalize at all — this is a key reason RRF is the right fusion choice
([BigData Boutique](https://bigdataboutique.com/blog/reciprocal-rank-fusion-how-it-works-and-when-to-use-it)).
For the rare callers that want a 0–1 lexical score for display (snippets, debug
traces), we min-max normalize within the result set:

```python
def normalize_bm25(scored):  # scored: [(doc_rowid, negated_bm25)]
    if not scored:
        return {}
    vals = [-s for _, s in scored]            # flip so larger = better
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    return {d: (-s - lo) / span for (d, s) in scored}
```

This normalized score is **for display/trace only**; fusion uses ranks.

---

## 2. Chunking

### 2.1 Why whole-node embeddings are insufficient

The plan is explicit ("naive whole-node Ollama embeddings are below parity") and
the codebase confirms why:

- `synthesis_nodes.full_content` and `community_reports.full_content` are
  *multi-paragraph documents*. A single embedding of a 1,500-token report is a
  centroid that washes out the one paragraph that actually answers a narrow query
  — the classic "lost in the middle" dilution. Cosine to a query about one
  sub-finding is dragged down by four unrelated findings in the same vector.
- `source_spans.text_preview` is already span-sized, but spans vary wildly
  (`span_type` ∈ heading_section | paragraph | page | equation | code | table),
  so a `page`-type span can be far larger than a `paragraph` span. Without
  chunking, page-spans embed poorly while paragraph-spans embed fine — an
  inconsistent vector space.
- qmd's quality (per the plan's "critical correction") comes partly from
  **chunk-level embeddings**; matching parity requires the same granularity.

### 2.2 Chunking strategy: sentence-window with token budget + overlap

**Decision: a deterministic sentence-window chunker with a target token budget
and fixed overlap, never a fixed character split.**

Parameters (defaults; configurable under `search.chunking` in `config.yml`):

| param | default | rationale |
|---|---|---|
| `target_tokens` | 256 | Sweet spot for retrieval embeddings (bge-m3 / nomic) — large enough for a coherent idea, small enough to stay specific. |
| `max_tokens` | 384 | Hard cap; never exceed the embedder's effective window for short-doc quality. |
| `overlap_tokens` | 48 | ~1–2 sentences of carry-over so a fact split across a boundary is still retrievable from both chunks. |
| `min_tokens` | 32 | Below this, merge with the previous chunk (avoid orphan fragments). |

Algorithm (semantic-aware: respect paragraph and sentence boundaries first, only
fall back to hard token windows for pathological un-delimited text):

```python
def chunk_text(text, *, target=256, maxt=384, overlap=48, mint=32):
    paras = split_paragraphs(text)                 # on blank lines / markdown
    sentences = []
    for p in paras:
        sentences.extend(split_sentences(p))       # regex + CJK '。' aware
    chunks, buf, buf_tok = [], [], 0
    for sent in sentences:
        st = count_tokens(sent)
        if buf_tok + st > maxt and buf:
            chunks.append(" ".join(buf))
            # start next buffer with overlap tail of the previous one
            buf, buf_tok = _overlap_tail(buf, overlap)
        buf.append(sent); buf_tok += st
        if buf_tok >= target:
            chunks.append(" ".join(buf))
            buf, buf_tok = _overlap_tail(buf, overlap)
    if buf:
        if chunks and buf_tok < mint:
            chunks[-1] = chunks[-1] + " " + " ".join(buf)   # absorb orphan
        else:
            chunks.append(" ".join(buf))
    return chunks
```

`count_tokens` should use the *embedding model's* tokenizer when available
(exact budget) and fall back to a `len(text)//4` heuristic when the tokenizer is
not loaded (the chunker must work even in FTS5-only degraded mode so that
`search_chunks` provenance stays stable).

### 2.3 Stable chunk positions + provenance

Each chunk is a row in `search_chunks`, keyed so positions are **stable across
re-chunking when the source text is unchanged** (so embeddings aren't needlessly
recomputed — see `C_embeddings_and_sync.md`):

```sql
CREATE TABLE search_chunks (
    chunk_id      TEXT PRIMARY KEY,        -- CHK-<sha8(doc_rowid|ord|chunk_hash)>
    doc_rowid     INTEGER NOT NULL,        -- FK -> search_documents
    node_id       TEXT NOT NULL,           -- denormalized for fast hit hydration
    family        TEXT NOT NULL,
    ordinal       INTEGER NOT NULL,        -- 0-based position within the document
    text          TEXT NOT NULL,
    char_start    INTEGER,                 -- offset into the document body
    char_end      INTEGER,
    chunk_hash    TEXT NOT NULL,           -- sha256(text) — embedding cache key
    source_span_ids TEXT NOT NULL DEFAULT '[]',  -- provenance carried from parent
    UNIQUE(doc_rowid, ordinal),
    FOREIGN KEY (doc_rowid) REFERENCES search_documents(doc_rowid) ON DELETE CASCADE
);
CREATE INDEX idx_search_chunks_doc ON search_chunks(doc_rowid);
CREATE INDEX idx_search_chunks_hash ON search_chunks(chunk_hash);
```

Provenance rules:
- For `source_span` documents, `source_span_ids` = `[the span's own id]`.
- For `knowledge_unit`, it inherits the unit's `source_span_ids`.
- For `community_report` / `synthesis_node`, it inherits the report/node's
  `source_span_ids`. Because chunks subdivide `full_content`, every chunk carries
  the *parent's* full span set — coarser than ideal but always citation-valid
  (every chunk traces back to real source spans, preserving the v0.3.1
  source-grounding invariant). A later refinement can attribute spans per chunk
  via offset overlap; not required for parity.

The `chunk_id` is content-addressed (`sha8` of `doc_rowid|ordinal|chunk_hash`) so
re-running the chunker on unchanged text reproduces identical ids → the embedding
cache (`search_embeddings.chunk_hash`) hits and no re-embedding occurs.

---

## 3. Vector layer

### 3.1 Storage layout in SQLite

Embeddings are stored as raw `float32` BLOBs alongside a **model fingerprint** so
a model/dim change invalidates cleanly (detailed lifecycle in
`C_embeddings_and_sync.md`; the *layout* is fixed here):

```sql
CREATE TABLE search_embeddings (
    chunk_hash    TEXT PRIMARY KEY,        -- cache key (shared by identical text)
    dim           INTEGER NOT NULL,        -- e.g. 1024 (bge-m3) / 768 (nomic)
    model_fp      TEXT NOT NULL,           -- 'provider::model::dim::vN' fingerprint
    vector        BLOB NOT NULL,           -- dim * 4 bytes, little-endian float32
    created_at    TEXT NOT NULL
);

CREATE TABLE search_index_meta (          -- one row; global index state
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    embed_model_fp TEXT NOT NULL DEFAULT '',
    dim           INTEGER NOT NULL DEFAULT 0,
    chunk_count   INTEGER NOT NULL DEFAULT 0,
    embedded_count INTEGER NOT NULL DEFAULT 0,
    fts_rebuilt_at TEXT,
    vec_rebuilt_at TEXT
);
```

Keying embeddings by `chunk_hash` (not `chunk_id`) means two chunks with
identical text (common for boilerplate headers, duplicated definitions) share one
vector — free dedup. Vectors are stored as L2-normalized float32 at write time so
cosine reduces to a dot product at query time.

Serialization:

```python
import numpy as np
def pack_vec(v: np.ndarray) -> bytes:
    v = v.astype(np.float32)
    n = np.linalg.norm(v) or 1.0
    return (v / n).tobytes()              # store normalized
def unpack_vec(b: bytes, dim: int) -> np.ndarray:
    return np.frombuffer(b, dtype=np.float32, count=dim)
```

### 3.2 Brute-force NumPy cosine vs `sqlite-vec`

**Decision: brute-force NumPy cosine now; `sqlite-vec` behind a documented switch
threshold.**

Brute-force KNN: load all candidate vectors once into a single contiguous matrix,
matrix-multiply by the (normalized) query vector, `argpartition` the top-k.

```python
def vector_search(conn, query_vec, *, cap, dim, model_fp):
    rows = conn.execute(
        "SELECT c.doc_rowid, c.chunk_id, e.vector "
        "FROM search_chunks c JOIN search_embeddings e ON c.chunk_hash = e.chunk_hash "
        "WHERE e.model_fp = ?", (model_fp,)).fetchall()
    if not rows:
        return []                                   # → degrade to FTS5-only
    mat = np.frombuffer(b"".join(r["vector"] for r in rows),
                        dtype=np.float32).reshape(len(rows), dim)
    q = query_vec / (np.linalg.norm(query_vec) or 1.0)
    sims = mat @ q                                   # cosine (all normalized)
    k = min(cap, len(rows))
    top = np.argpartition(-sims, k - 1)[:k]
    top = top[np.argsort(-sims[top])]
    return [(rows[i]["chunk_id"], rows[i]["doc_rowid"], float(sims[i])) for i in top]
```

**Why brute-force is correct at our scale** (KNN latency, single query, 768–1024
dim float32):

| chunk count | matrix size (1024-dim f32) | matmul + sort | verdict |
|---|---|---|---|
| 1k | ~4 MB | < 2 ms | trivial |
| 10k | ~40 MB | ~10–20 ms | imperceptible |
| 100k | ~400 MB | ~80–150 ms | acceptable for an answer-path query |

These align with published sqlite-vec brute-force numbers (≤75 ms for ≤1024-dim
at 100k vectors; larger dims 105–214 ms)
([sqlite-vec benchmarks](https://alexgarcia.xyz/blog/2024/sqlite-vec-stable-release/index.html)).
Our own NumPy path is in the same order of magnitude and needs **no new
dependency**. The only real cost is the ~400 MB load at 100k chunks; we mitigate
with a process-lifetime LRU cache of the vector matrix keyed by `model_fp` +
`chunk_count` so repeated queries in one CLI/daemon session don't re-load.

**Documented switch threshold:** when `search_index_meta.embedded_count` exceeds
**50,000 chunks** *or* per-query vector latency (traced) exceeds **250 ms p95**,
switch to `sqlite-vec` (pip wheel, optional dependency). The engine probes
`import sqlite_vec` at startup; if present AND over threshold, it routes KNN
through a `vec0` virtual table instead of the NumPy path. The fusion/expansion/
rerank layers are unchanged — only the KNN primitive swaps. (Plan §4 records this
same recommendation: "brute-force now; revisit if a real vault exceeds ~50k
nodes".)

### 3.3 Embedding provider + fingerprint

Provider/model selection is owned by `config.yml` `search.embedding`
(`provider::model`), defaulting per `C_embeddings_and_sync.md`'s recommendation
(`bge-m3` for EN/KR parity where available, `nomic-embed-text` as the simple
local Ollama default). The engine treats the embedder as an injected interface:

```python
class Embedder(Protocol):
    fingerprint: str          # 'ollama::nomic-embed-text::768::v1'
    dim: int
    def embed(self, texts: list[str]) -> np.ndarray: ...   # (n, dim), may raise
```

A missing/failed embedder is non-fatal: the vector layer returns `[]` and the
engine sets `fallback_mode='lex'` (see §7).

---

## 4. Typed query expansion

The expander turns one user question into the three typed variants the plan
mandates — `lex`, `vec`, `hyde` — plus the extracted `intent` and injected
DAG/KRS context. It runs in two tiers.

### 4.1 Tier 1 — deterministic expansion (always runs, zero LLM)

```python
@dataclass
class ExpandedQuery:
    raw: str
    intent: str = "default"          # default|definition|comparison|procedure|navigational
    is_cjk: bool = False
    lex_match: str = ""              # FTS5 MATCH string (from build_fts_match)
    lex_terms: list[str] = field(default_factory=list)
    vec_texts: list[str] = field(default_factory=list)  # texts to embed for KNN
    hyde_text: str = ""             # hypothetical answer doc (Tier 2 fills this)
    phrases: list[str] = field(default_factory=list)
    excludes: list[str] = field(default_factory=list)
    boosts: list[str] = field(default_factory=list)     # KRS/persona terms
```

Deterministic steps (reusing logic that already exists in
`retrieval/evidence.py.seed_terms` and `query.py._keyword_fallback`, consolidated):
1. **CJK detection** — `is_cjk` if non-ASCII ratio > 0.15 (drives trigram + LIKE).
2. **Phrase extraction** — pull `"..."` quoted spans into `phrases`.
3. **Negation** — pull leading-`-` tokens into `excludes`.
4. **Identifier preservation** — keep dotted/hyphenated tokens whole
   (`nn.Conv2d`, `bge-m3`).
5. **Stopword strip + dedup** — reuse the existing `_STOP` set for `lex_terms`.
6. **Synonym/identifier splitting** — a small static map expands known acronyms
   bidirectionally (`RRF`↔`reciprocal rank fusion`, `KNU`↔`knowledge unit`) into
   *additional* OR terms — improves recall without an LLM.
7. **`build_fts_match(...)`** (§1.5) → `lex_match`.
8. **`vec_texts = [raw]`** initially (the raw query is always one vector probe).
9. **Intent heuristic** — keyword cues (`what is`/`define`→definition;
   `vs`/`compare`→comparison; `how to`/`steps`→procedure) set `intent`, which the
   router uses to tune prefix/AND behavior and rerank engagement.

### 4.2 Tier 2 — configured LLM/query-expander (when available)

When `search.query_expansion` is configured (a local GGUF expander, a small
transformer, or a validated prompt contract — the plan leaves provider open), a
single structured call enriches the deterministic result:

- adds paraphrase terms to `lex_terms` (multi-query lexical expansion),
- adds 1–2 paraphrase strings to `vec_texts` (multi-vector probing),
- produces `hyde_text`: a short hypothetical answer paragraph
  ([HyDE](https://machinelearningplus.com/gen-ai/hypothetical-document-embedding-hyde-a-smarter-rag-method-to-search-documents/)),
  embedded as an *additional* vec probe.

**HyDE engagement policy (cost control):** HyDE is the most expensive variant
(an LLM generation per query). Per 2025 best practice — "fall back on HyDE only
when query–document similarity confidence is low" — the engine generates
`hyde_text` **only** when (a) the answer path is active AND (b) the raw-query
vector search's top similarity is below a confidence floor (default 0.35) OR the
lexical layer returned < N hits. This makes HyDE a *recovery* mechanism, not a
fixed tax on every query. Generated HyDE docs are post-validated by the reranker
(§6), guarding against off-topic hallucinated expansions.

### 4.3 Intent + DAG/KRS context injection

Context enters expansion from two existing sources:
- **Persona/domain boost** — `query.py` already appends
  `curator_persona.domain` + `topics` as boost terms; we move that into
  `ExpandedQuery.boosts`, which are OR'd into `lex_match` at low weight and
  appended to one `vec_texts` probe.
- **KRS (`curate.yml`) context** — the `QueryOrchestrator` resolves a
  `CurationPolicy` per workspace (`retrieval/orchestrator.py._resolve_policy`).
  The policy's `allowed_routes` already constrains routing; for expansion we
  additionally pass the workspace's declared topics/keywords as `boosts` and let
  `intent` interact with the policy's `prompt_profile`. This keeps the KRS as the
  authority over *what* a workspace is allowed to retrieve, while expansion only
  *steers* within those bounds.

---

## 5. RRF fusion

### 5.1 Formula and defaults

Reciprocal Rank Fusion over the per-variant ranked lists. For a document `d`
appearing at rank `r_i` (1-based) in ranked list `i` with list weight `w_i`:

```
RRF(d) = Σ_i  w_i * 1 / (k + r_i)
```

with **`k = 60`** (the Cormack et al. TREC default; benchmarks find k∈[40,80]
equivalent, vendors standardized on 60 —
[BigData Boutique](https://bigdataboutique.com/blog/reciprocal-rank-fusion-how-it-works-and-when-to-use-it)).
RRF uses **only ranks**, never raw scores, which is exactly why it tolerates the
BM25-negated vs cosine score-scale mismatch with zero normalization.

### 5.2 Lists fused, weights, original-query weighting

The candidate ranked lists, each capped at `candidate_cap` (default 100):

| list | source | weight `w` |
|---|---|---|
| `lex_raw` | FTS5 on the **original** query terms | **1.0** |
| `vec_raw` | KNN on the **original** query embedding | **0.9** |
| `lex_exp` | FTS5 on expander paraphrase terms | 0.6 |
| `vec_exp` | KNN on paraphrase embeddings | 0.6 |
| `vec_hyde` | KNN on HyDE doc embedding (if generated) | 0.7 |

**Original-query weighting:** the raw-query lex/vec lists carry the highest
weights (1.0 / 0.9) so expansion can *add* recall but cannot *overwhelm* the
user's literal intent — directly implementing the plan's "original-query
weighting" requirement and the common 1.0-lex / ~0.7-vec lexical-favoring bias
([Hybrid Search guide](https://www.youngju.dev/blog/culture/2026-03-18-hybrid-search-bm25-vector-rag.en)).
Lexical is weighted slightly above vector because for a technical KB exact-term
hits are usually the trustworthy signal.

### 5.3 Top-rank bonus + candidate cap

Two qmd-parity refinements the plan lists:
- **Candidate cap** — each list is truncated to `candidate_cap` before fusion so
  one noisy list can't flood the fused set; the fused output is then truncated to
  `fuse_cap` (default 40) before rerank.
- **Top-rank bonus** — a small additive bonus for documents that appear at rank 1
  in *any* list (`bonus = top_rank_bonus / (k+1)`, default `top_rank_bonus=0.5`),
  rewarding strong agreement at the head of a list without discarding RRF's
  rank-only robustness.

### 5.4 Implementation with full per-candidate trace

```python
def rrf_fuse(ranked_lists, *, k=60, cap=100, fuse_cap=40, top_bonus=0.5):
    """ranked_lists: dict[name, (weight, [doc_rowid in rank order])]"""
    scores = defaultdict(float)
    trace = defaultdict(list)               # doc_rowid -> contributions
    for name, (weight, docs) in ranked_lists.items():
        for rank, doc in enumerate(docs[:cap], start=1):
            contrib = weight * (1.0 / (k + rank))
            if rank == 1:
                contrib += top_bonus / (k + 1)
            scores[doc] += contrib
            trace[doc].append({"list": name, "rank": rank,
                               "weight": weight, "contribution": contrib})
    fused = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:fuse_cap]
    return [(doc, score, trace[doc]) for doc, score in fused]
```

The `trace` (every list a doc appeared in, its rank there, the weight, and the
numeric contribution) is persisted to `query_traces` (schema in
`D_spec_test_migration.md`) so the dashboard "click-to-use" trace view can show
*why* each candidate ranked where it did — a hard requirement of the plan.

---

## 6. Rerank

### 6.1 Where it runs: answer path only

Rerank is the most expensive stage and only improves the *final* ordering the
synthesizer sees. It therefore runs **only on the answer-producing path**
(`wiki query`, MCP query, dashboard query) and **never** on the
`fetch_context`/evidence-pack-only path or on cheap navigational lookups. The
fused RRF order is the answer for non-answer callers.

### 6.2 Reranker options + recommendation

| option | mechanism | pros | cons |
|---|---|---|---|
| **`bge-reranker-v2-m3` (GGUF via llama.cpp)** | cross-encoder; query+passage → relevance logit, sigmoid → [0,1] | strong EN+KR (m3 is multilingual), local, GGUF Q8_0 is small; sigmoid gives a clean normalized score ([HF model card](https://huggingface.co/gpustack/bge-reranker-v2-m3-GGUF)) | needs `llama-cpp-python` or a `llama-server` rank endpoint |
| sentence-transformers cross-encoder | same, via transformers | easy pip | heavier dep, weaker offline story |
| search-fine-tuned LLM rerank prompt | LLM scores passages | reuses existing LLM client | slower, prompt-fragile |
| generic chat rerank prompt | LLM ranks list | no new model | **degraded only** — plan forbids it as parity target |

**Recommendation: `bge-reranker-v2-m3` GGUF via llama.cpp as the configured
default**, with a search-fine-tuned/validated LLM rerank prompt as a secondary
configured option, and the generic chat prompt strictly as degraded fallback. The
sigmoid-normalized [0,1] score is what we blend in §6.3.

The reranker scores the **best chunk per candidate document** (not whole
documents) — chunking (§2) is what makes cross-encoder reranking precise, because
the cross-encoder sees a focused 256-token passage, not a diluted full report.

```python
def rerank(reranker, query, fused, chunk_text_by_doc, *, top_n):
    pairs = [(query, chunk_text_by_doc[doc]) for doc, _, _ in fused]
    logits = reranker.score(pairs)                 # raw logits
    ce = 1 / (1 + np.exp(-np.asarray(logits)))     # sigmoid -> [0,1]
    return ce
```

### 6.3 Position-aware blend of rerank score with RRF

We do not discard the RRF signal — a cross-encoder is sharp but can be confidently
wrong on a single passage, while RRF encodes cross-list agreement. We blend, with
the cross-encoder dominant but RRF retained as a stabilizer, and add a mild
position prior so a candidate the cross-encoder demotes from a strong RRF position
isn't dropped off a cliff:

```python
def blend(fused, ce_scores, *, alpha=0.7):
    rrf_norm = minmax([s for _, s, _ in fused])    # 0..1
    out = []
    for (doc, rrf_s, tr), ce, rn in zip(fused, ce_scores, rrf_norm):
        final = alpha * ce + (1 - alpha) * rn      # position-aware blend
        out.append((doc, final, ce, rrf_s, tr))
    out.sort(key=lambda x: x[1], reverse=True)
    return out[:top_n]
```

Default `alpha = 0.7` (cross-encoder-led). The blend weights, the per-candidate
`ce` and `rrf_s`, and the final order are all written to the trace.

### 6.4 Degraded fallback rules

- Reranker not configured / model load fails / scoring raises → skip §6, return
  RRF order, set `fallback_mode = "no_rerank"`, append a warning.
- Embedder missing → no vec lists → RRF over lexical lists only; if a reranker is
  still present it can run on the lexical candidates (a perfectly valid degraded
  mode), else `fallback_mode = "lex"`.
- Both embedder and reranker missing → pure FTS5 BM25 order, `fallback_mode =
  "lex"`, warning surfaced exactly like today's `_qmd_hits` "qmd unavailable"
  warning so callers/UX are unchanged.

---

## 7. Per-route flow

The engine exposes one `query(...)` entry, but the four existing routes
(`retrieval/evidence.py.build_evidence`) consume it differently. The key change:
`_qmd_hits(...)` is replaced by `engine.search(...)` reading the DB, and the
route decides *which families* to search and *whether* to rerank.

```
            ┌──────────────── ExpandedQuery (Tier1 + optional Tier2) ───────────┐
            │ lex_match • vec_texts • hyde_text • intent • boosts • is_cjk       │
            └───────────────────────────────────────────────────────────────────┘
                        │                         │
                 ┌──────▼──────┐           ┌──────▼──────┐
                 │  FTS5 (×2)  │           │  Vector KNN │   (skipped if no embedder)
                 │ unicode61 + │           │ brute-force │
                 │  trigram    │           │  NumPy      │
                 └──────┬──────┘           └──────┬──────┘
                        └───────────┬─────────────┘
                                ┌───▼───┐
                                │  RRF  │  k=60, original-query weighted, capped, +bonus
                                └───┬───┘
                        ┌───────────▼───────────┐
                        │   answer path only:    │
                        │   cross-encoder rerank │  (skipped → fallback_mode)
                        │   + position blend     │
                        └───────────┬───────────┘
                                ┌───▼───┐
                                │ Hits  │  → SearchResults (+ fallback_mode, + trace)
                                └───────┘
```

Per route:

- **local** — family filter `{knowledge_unit, source_span, entity}`. Today
  `build_evidence` already gathers entity + spans from the graph and then calls
  `_qmd_hits`; the replacement runs `engine.search(..., families=local_set,
  rerank=True)` to add lexical+vector hits over the *same* DB rows. The graph
  entity/span evidence stays exactly as-is (the design plan's "surgical" promise).
- **global** — family filter `{synthesis_node, community_report}`. The route still
  leads with synthesis nodes + community reports from the DB (unchanged), and
  only calls `engine.search(..., families=global_set, rerank=True)` as the
  *fallback* when there are no synthesis/reports — replacing the existing
  `"no synthesis or community reports; falling back to qmd"` branch with a
  DB-native equivalent.
- **explore** — family filter is broad `{entity, knowledge_unit, synthesis_node}`;
  `memory_paths` traversal is unchanged. Expansion `intent` is forced toward
  recall (prefix on, AND off). Rerank is optional here (associative breadth >
  precision) — default `rerank=False` to keep explore cheap.
- **source-section** — **does not use the hybrid engine at all**; it is a direct
  `db.list_source_spans(source_id)` enumeration (already the case). The engine is
  bypassed; no FTS/vector/RRF/rerank involved. Left documented here so the route
  table is complete.

Degradation per route is uniform (§6.4): any route that engages the engine
degrades to FTS5-only-with-warning when embeddings/reranker are absent, and the
warning flows into `EvidencePack.warnings` / `QueryResult.warnings` exactly as the
current `_qmd_hits` warning does.

---

## 8. Public API

The engine lives in a rewritten `backend/src/curator/search.py` whose **public
surface is source-compatible** with today's callers (`query.py`,
`retrieval/evidence.py`, MCP, plugin). `SearchHit` / `SearchResults` keep their
field names; `IndexUpdateResult` is reused for `wiki reindex`. The one semantic
shift: `SearchHit.full_path` now carries a **node locator** (e.g.
`02_Atoms/ATM-9f8e7d6c` projected from the node id) rather than a markdown file
path — this is the same string callers already feed into `[[wikilink]]`
construction, so `query.py._build_synthesis_user_prompt` and
`evidence.py._qmd_hits` need no change to their *consumption* logic.

```python
# ---- result types: UNCHANGED field names (callers depend on these) ----
@dataclass
class SearchHit:
    full_path: str           # node locator, e.g. '02_Atoms/ATM-9f8e7d6c'
    title: str = ""
    score: float = 0.0       # final blended score (or RRF score in degraded mode)
    snippet: str = ""
    full_content: str = ""   # hydrated from the DB node row when hydrate=True
    docid: str = ""          # node_id (KNU-/REP-/SYN-/SPAN-/ENT-)
    # --- additive, optional; ignored by old callers ---
    family: str = ""
    chunk_id: str = ""
    rrf_score: float = 0.0
    rerank_score: float = 0.0
    contributions: list[dict] = field(default_factory=list)  # RRF trace

@dataclass
class SearchResults:
    hits: list[SearchHit] = field(default_factory=list)
    fallback_mode: str = ""          # ""|"no_rerank"|"lex"  (same field as today)
    trace_id: str = ""               # additive: links to query_traces row
    def __len__(self): return len(self.hits)
    def __iter__(self): return iter(self.hits)


# ---- signature-compatible entry point ----
def query(
    paths: cfg.WikiPaths,
    question: str,
    *,
    mode: str = "hybrid",            # 'hybrid'|'lex'|'vec' (kept; maps to engine knobs)
    limit: int = 8,
    min_score: float = 0.6,
    collections: list[str] | None = None,   # kept for compat; now → family filter
    hydrate: bool = True,
    rerank: bool = True,
    *,
    families: set[str] | None = None,        # additive: route-scoped families
    workspace_path: str = "",                # additive: KRS context for expansion
) -> SearchResults:
    db_path = paths.state_db
    engine = HybridEngine(db_path, _load_search_config(paths))

    expanded = engine.expand(question, workspace_path=workspace_path,
                             want_hyde=(mode == "hybrid" and rerank))
    lists = {}
    if mode in ("hybrid", "lex"):
        lists["lex_raw"] = (1.0, engine.lexical(expanded, families))
        for i, terms in enumerate(expanded.lex_terms_expanded):
            lists[f"lex_exp{i}"] = (0.6, engine.lexical_terms(terms, families))
    if mode in ("hybrid", "vec") and engine.has_embedder:
        lists["vec_raw"] = (0.9, engine.vector(expanded.vec_texts[0], families))
        for i, t in enumerate(expanded.vec_texts[1:], 1):
            lists[f"vec_exp{i}"] = (0.6, engine.vector(t, families))
        if expanded.hyde_text:
            lists["vec_hyde"] = (0.7, engine.vector(expanded.hyde_text, families))

    fused = rrf_fuse(lists)                      # §5
    fallback = "" if (engine.has_embedder and mode != "lex") else "lex"

    if rerank and mode == "hybrid" and engine.has_reranker:
        ranked = engine.rerank_and_blend(question, fused, top_n=limit)   # §6
    else:
        ranked = [(d, s, 0.0, s, tr) for d, s, tr in fused][:limit]
        if rerank and mode == "hybrid":
            fallback = fallback or "no_rerank"

    hits = engine.hydrate(ranked, hydrate=hydrate)        # DB row → SearchHit
    hits = [h for h in hits if h.score >= min_score] or hits[:1]  # never empty-on-borderline
    trace_id = engine.persist_trace(question, expanded, lists, ranked)
    return SearchResults(hits=hits, fallback_mode=fallback, trace_id=trace_id)
```

Notes on compatibility:
- `mode`, `limit`, `min_score`, `collections`, `hydrate`, `rerank` are all
  preserved; `collections` (rarely used — always the single `curator` collection
  today) is reinterpreted as an optional family filter, a no-op for current
  callers passing `None`.
- `min_score` still filters, but the engine guards against returning an empty list
  on a single borderline hit (the old code returned `[]` and the caller then ran
  several fallback re-queries; the engine subsumes most of that with expansion, so
  it keeps at least the top hit rather than forcing the caller's retry ladder).
- `IndexUpdateResult` + `update_index(paths, embed=...)` are retained for
  `wiki reindex`, now meaning "rebuild `search_documents`/`search_fts`/
  `search_chunks` from the DB and (optionally) embed missing chunks", with
  `degraded`/`warning` set when the embedder is unavailable — same struct, new
  internals.
- `is_available()` / `get_version()` (qmd binary probes) become engine
  capability probes (`embedder_available()`, `reranker_available()`); the qmd
  binary-resolution code (`get_qmd_binary`, `_qmd_env`, `_run_qmd`) is deleted in
  the wiring step (Plan §3.7), not here.

---

## 9. Defaults summary (recommended, not just optional)

| knob | default | where |
|---|---|---|
| FTS5 topology | external-content, rebuild-on-reindex | §1.1/§1.3 |
| Tokenizers | `unicode61` (+`tokenchars '.-_/'`) primary, `trigram` for CJK/substring | §1.4 |
| BM25 column weights | title 2.0 / body 1.0 | §1.2 |
| Chunk size | 256 target / 384 max / 48 overlap / 32 min tokens | §2.2 |
| Embedding storage | float32 BLOB, normalized, keyed by `chunk_hash` + `model_fp` | §3.1 |
| Embedding model | `bge-m3` (EN/KR) or `nomic-embed-text` (simple local) | §3.3 |
| KNN | brute-force NumPy now; `sqlite-vec` at >50k chunks or >250 ms p95 | §3.2 |
| HyDE | recovery-only (low vec confidence / sparse lexical) | §4.2 |
| RRF | `k=60`, lex_raw 1.0 / vec_raw 0.9 / exp 0.6 / hyde 0.7, cap 100→40, top-rank bonus 0.5 | §5 |
| Reranker | `bge-reranker-v2-m3` GGUF (llama.cpp), sigmoid-normalized | §6.2 |
| Rerank blend | `alpha=0.7` (cross-encoder-led) + RRF stabilizer | §6.3 |
| Rerank scope | answer path only | §6.1 |
| Degradation | no embed → `lex`; no rerank → `no_rerank`; both → FTS5-only + warning | §6.4 |

---

## 10. Open items handed to sibling docs

- Embedding generation timing, incremental invalidation via `dependency_hash`,
  and `wiki reindex` embed semantics → `C_embeddings_and_sync.md`.
- `search_documents` / `search_chunks` / `search_embeddings` / `search_index_meta`
  / `query_traces` DDL finalization, `SCHEMA_VERSION` bump, and the v0.3.2
  three-domain spec sync → `D_spec_test_migration.md` + `G_spec_draft_addendum.md`.
- Concrete qmd-parity acceptance thresholds (recall@k, MRR vs qmd on the testbed)
  → `E_qmd_parity_requirements.md`.
- Dashboard trace/insight "click-to-use" rendering of the RRF/rerank trace
  persisted here → `F_dashboard_click_to_use.md`.

---

## Sources

- [SQLite FTS5 Extension (official: external-content, contentless, trigram, bm25)](https://sqlite.org/fts5.html)
- [SQLite forum: trigram + external-content caveats](https://sqlite.org/forum/info/281c93ee10e32665)
- [Alex Garcia — Hybrid full-text + vector search with SQLite (FTS5 + sqlite-vec, RRF SQL)](https://alexgarcia.xyz/blog/2024/sqlite-vec-hybrid-search/index.html)
- [Alex Garcia — sqlite-vec v0.1.0 (brute-force KNN latency benchmarks)](https://alexgarcia.xyz/blog/2024/sqlite-vec-stable-release/index.html)
- [MarkTechPost — sqlite-vec v0.1.0 (1M vectors, brute-force scale)](https://www.marktechpost.com/2024/08/04/sqlite-vec-v0-1-0-released-portable-vector-database-extension-for-sqlite-with-support-for-1-million-128-dimensional-vectors-binary-quantization-and-extensive-sdks/)
- [BigData Boutique — Reciprocal Rank Fusion: how it works / k=60 origin](https://bigdataboutique.com/blog/reciprocal-rank-fusion-how-it-works-and-when-to-use-it)
- [Hybrid Search Guide — BM25 + vector + lexical-favoring RRF weights](https://www.youngju.dev/blog/culture/2026-03-18-hybrid-search-bm25-vector-rag.en)
- [Digital Applied — Hybrid Search: BM25, Vector & Reranking (2026)](https://www.digitalapplied.com/blog/hybrid-search-bm25-vector-reranking-reference-2026)
- [gpustack/bge-reranker-v2-m3-GGUF (llama.cpp local reranking, sigmoid score)](https://huggingface.co/gpustack/bge-reranker-v2-m3-GGUF)
- [MachineLearningPlus — HyDE explained / when to use](https://machinelearningplus.com/gen-ai/hypothetical-document-embedding-hyde-a-smarter-rag-method-to-search-documents/)
- [Chitika — HyDE query expansion: recovery-only / cross-encoder post-validation](https://www.chitika.com/hyde-query-expansion-rag/)
