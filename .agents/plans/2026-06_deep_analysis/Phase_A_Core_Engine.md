# Phase A: Core Engine — Senior Committee Deep Analysis

**Target Files**: `sync.py` (1539 lines), `db.py` (2004 lines), `insight_lifecycle.py` (131 lines)

**Panel**: Alice (Architect), Bob (Data), Charlie (Security), Frank (Backend), Hannah (QA)

---

## Debate Transcript

### 1. The Logseq Lesson: Filesystem as Data Dependency

**Bob (Data Engineer)**:
"I read `insight_lifecycle.py` line by line. The `promote_insight()` function (lines 99-131) takes an approved insight candidate and writes it to `02_Wiki/` as a Markdown file. It then updates the candidate's status to `promoted` in the DB. But crucially, **the new knowledge only re-enters the retrieval pipeline when `sync.py` later parses that Markdown file back into the DB**. This is a round-trip through the filesystem.

I researched **Logseq's** architectural history. Logseq started with Markdown files as the Source of Truth. They suffered massive sync conflicts (two devices writing the same file simultaneously) and performance degradation on large graphs. They ultimately pivoted to **SQLite DB-centric storage**, demoting Markdown to a read-only mirror/export. We are repeating the exact anti-pattern Logseq already abandoned."

**Frank (Backend Specialist)**:
"Looking at `db.py:561-576`, the `connect()` context manager opens a SQLite connection with WAL mode and foreign keys, but there is **no explicit transaction isolation level**. The connection auto-commits at the end of the `with` block. If two processes (e.g., the plugin backend and a CLI `wiki sync` command) attempt to write simultaneously, WAL mode helps but doesn't prevent logical conflicts.

More critically, `insight_lifecycle.py:128` writes to the filesystem (`out_path.write_text(body, encoding='utf-8')`) **outside of any database transaction**. If the process crashes between the file write (line 128) and the DB status update (line 129), the system enters an inconsistent state: a Markdown file exists on disk with no corresponding `promoted` status in the DB."

**Hannah (QA Engineer)**:
"This is why our CI tests are flaky. Testing `sync.py`'s filesystem watcher requires actual I/O, which introduces non-deterministic timing. Testing a direct SQLite UPSERT is deterministic and takes milliseconds. The filesystem dependency makes every integration test inherently unreliable."

### 2. The db.py Schema: A Hidden GraphRAG Engine

**Alice (Chief Architect)**:
"Here's what everyone missed. I went through `db.py`'s `SCHEMA_SQL` (lines 25-406) meticulously. The v0.3.1 schema contains:

| Table | Line | Purpose | SOTA Equivalent |
|-------|------|---------|-----------------|
| `graph_entities` | 250 | Named graph nodes with typed entities | Microsoft GraphRAG entity extraction |
| `graph_relations` | 265 | Typed, directed, confidence-scored edges | GraphRAG relationship extraction |
| `community_reports` | 283 | Hierarchical community summaries | GraphRAG community detection + summarization |
| `memory_paths` | 303 | Associative walks over the graph | **HippoRAG** Personalized PageRank |
| `synthesis_nodes` | 391 | Corpus-wide cross-cutting insights | GraphRAG global answer synthesis |
| `source_spans` | 210 | Precise, hashed regions of source text | Fine-grained citation anchors |
| `knowledge_units` | 231 | Typed L2 knowledge units citing spans | Structured claim extraction |
| `artifact_dependencies` | 376 | Staleness/invalidation tracking | CDC dependency graph |

This is not a toy system. This is a production-grade hybrid **GraphRAG + HippoRAG** architecture. The schema is on par with Microsoft Research's 2024 GraphRAG paper. But the **runtime code** (sync.py, evidence.py) doesn't fully leverage these tables — it still falls back to filesystem-based workflows inherited from v0.1.0."

**Bob (Data Engineer)**:
"Alice is right. The `artifact_dependencies` table (line 376) already provides dependency tracking between knowledge units, entities, relations, and community reports. This means we already have the infrastructure for **Change Data Capture (CDC)**. When an insight is promoted, we could use `artifact_dependencies` to identify every downstream artifact that needs invalidation — without touching the filesystem at all."

### 3. Missing Database Constraints

**Charlie (Security Lead)**:
"In `db.py:358-373`, the `insight_candidates` table stores provisional insights with a `status` column (`pending|accepted|rejected|promoted|needs_review`). But there is **no database-level CHECK constraint** enforcing valid status values. If an agent manages to insert an arbitrary status string (e.g., 'approved' instead of 'accepted'), the system silently accepts it.

More importantly, when `evidence.py` fetches data for queries, it queries `synthesis_nodes`, `community_reports`, and `graph_entities` — but **never filters by a 'validated' or 'approved' status**. Any unverified data that enters these tables pollutes every subsequent query."

### 📝 Consensus & Action Items

1. **[Backend]** Redesign `promote_insight()` to perform an atomic DB transaction: `UPSERT` the promoted insight directly into `synthesis_nodes` or `knowledge_units`, then asynchronously export a Markdown file as a side effect. Never depend on the filesystem for data flow.
2. **[Backend]** Add `CHECK` constraints to the `insight_candidates.status` column and implement row-level security filtering in all retrieval queries.
3. **[Architecture]** Leverage the existing `artifact_dependencies` table for CDC-based invalidation instead of filesystem scanning.
4. **[QA]** Replace filesystem-dependent integration tests with deterministic SQLite transaction assertions.
