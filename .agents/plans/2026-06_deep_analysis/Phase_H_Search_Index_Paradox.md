# Phase H: The Search Index Paradox — Senior Committee Deep Analysis

**Target Files**: `evidence.py` (214 lines), `qmd` external dependency, `db.py` schema

**Panel**: Bob (Data), Alice (Architect), Diana (Docs), Hannah (QA)

---

## Debate Transcript

### 1. The Architectural Paradox

**Bob (Data Engineer)**:
"Phase A concluded that we should stop depending on Markdown file generation as a core data flow step. But look at `evidence.py:39-56` — the `_qmd_hits()` function:

```python
def _qmd_hits(paths, query, limit, warnings):
    from .. import search
    results = search.query(paths, query, mode='hybrid', limit=limit,
                           min_score=0.3, hydrate=True, rerank=True)
```

`qmd` is an external search daemon that indexes Markdown files in `.curator/Collections/`. If we stop generating Markdown files per Phase A's recommendation, `qmd` becomes blind to all new knowledge. This is a direct contradiction between two architectural recommendations."

**Alice (Chief Architect)**:
"I researched two solutions:

**Option A: Transactional Outbox Pattern (CDC)**
When `db.py` commits a write, a trigger inserts a record into a `search_sync_queue` table. A background worker reads this queue and pushes changes to `qmd`. This maintains `qmd` as the search engine but adds complexity.

**Option B: SQLite FTS5 Internalization**
Replace `qmd` entirely with **SQLite's native Full-Text Search (FTS5)** extension. FTS5 operates on virtual tables that shadow our existing SQLite tables. No external daemon, no Markdown file generation, no synchronization headaches.

Given our system's scale (personal knowledge base, not enterprise search), **FTS5 is the overwhelmingly superior choice**. It eliminates an entire class of synchronization bugs."

**Hannah (QA Engineer)**:
"I strongly support Option B. Currently, our CI pipeline requires installing and configuring `qmd` as an external binary — which fails on many GitHub Actions runners. FTS5 is built into SQLite. Zero external dependencies. Our test setup becomes trivially simple."

**Diana (Documentation Specialist)**:
"The `qmd.yml` / `qmd index.yml` configuration system would also be deprecated. All search configuration would move into the SQLite schema, which is already our source of truth for everything else."

### 2. The Hybrid Search Still Works with FTS5

**Alice (Chief Architect)**:
"Looking at `evidence.py:207-213`, the `local` route already combines entity evidence, source spans, and qmd hits. If we replace `_qmd_hits()` with an FTS5 query, the hybrid architecture is preserved:

| Retrieval Layer | Current Implementation | FTS5 Replacement |
|----------------|----------------------|-----------------|
| Graph entities | `db.find_graph_entities()` | Unchanged |
| Source spans | `db.get_source_spans_by_ids()` | Unchanged |
| Full-text search | `search.query()` (external qmd) | `FTS5 MATCH` query on `synthesis_nodes.statement` + `knowledge_units.statement` |
| Memory paths | `mp.build_memory_paths()` | Unchanged |

The replacement is surgical: only `_qmd_hits()` changes. Everything else stays."

### 📝 Consensus & Action Items

1. **[Architecture]** Deprecate `qmd` as an external search dependency.
2. **[Backend]** Create FTS5 virtual tables mirroring `synthesis_nodes`, `knowledge_units`, and `community_reports` for full-text search.
3. **[Backend]** Replace `_qmd_hits()` in `evidence.py` with FTS5 `MATCH` queries.
4. **[QA]** Remove `qmd` binary dependency from CI pipeline setup.
