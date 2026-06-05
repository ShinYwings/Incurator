# Phase K: The Lint & Sync Performance Paradox

**Target Files**: `lint.py`, `sync.py`

**Panel**: Bob (Data Engineer), Hannah (QA Engineer)

## The Markdown Parsing Bottleneck

**Bob (Data Engineer)**:
"I traced the execution path of `wiki lint` and `wiki sync` and found a glaring architectural paradox.

In `lint.py`, the `_build_inventory` function (Lines 139-231) builds a DAG memory cache by reading and regex-parsing **every single Markdown file** in the Vault. It manually extracts wikilinks and frontmatter fields using regex string manipulation.

Similarly, in `sync.py`, functions like `run_mode_a` and `_trace_upstream` traverse the graph by physically opening Markdown files (`_read_node_page`), parsing the YAML frontmatter, and reading the text.

**Verdict**: We have a high-speed SQLite database (`state.sqlite`) containing all these relationships! Yet, `lint.py` and `sync.py` completely ignore the DB and opt for O(N) filesystem traversal.
1. **Performance Collapse**: At 10,000 nodes, `_build_inventory` parsing 10,000 Markdown files via Python string manipulation will take minutes. An equivalent SQL query `SELECT source, target FROM graph_relations` takes milliseconds.
2. **Source of Truth Conflict**: If the DB is the source of truth for L1-L3 (as dictated by our Dual-Track philosophy), `lint` and `sync` must query the DB, not the filesystem.

### Action Item [Architecture]
- **SQL-Driven Linting**: Rewrite `lint.py` to run its health checks (Orphans, Broken Links) via SQL queries against `state.sqlite`.
- **SQL-Driven Sync Verification**: Rewrite `sync.py` graph traversal (`downstream_concepts_for_atom`, `_trace_upstream`) to use SQL recursive CTEs (Common Table Expressions) rather than physical file reads.
