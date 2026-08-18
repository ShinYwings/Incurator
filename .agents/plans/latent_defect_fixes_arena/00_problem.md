# Briefing: two latent defects found alongside v0.59.0

Date: 2026-08-18 | Author: main agent (triage from a direct user report)

## 0. Provenance

These were found while reading the job-progress code for v0.59.0 (plan 06) and
reported by the user in chat, not through `.agents/USER_REPORT.md`. Both were
verified to reproduce on `master` at `0c0ebeb` with a clean worktree, so neither
is a v0.59.0 regression and neither belongs in that PR.

## 1. Defect 1 — `claim_next_job` cannot claim on a fresh state DB, forever

### Observed

```
$ .venv-dev/bin/python -c "
import tempfile
from pathlib import Path
from curator.db import jobs as J
p = Path(tempfile.mkdtemp())/'state.sqlite'
for i in (1,2,3):
    try: print('call', i, '->', J.claim_next_job(p))
    except Exception as e: print('call', i, '->', type(e).__name__+':', e)
"
call 1 -> OperationalError: cannot start a transaction within a transaction
call 2 -> OperationalError: cannot start a transaction within a transaction
call 3 -> OperationalError: cannot start a transaction within a transaction
schema_version rows after 3 failed calls: []
```

### Mechanism

`db/schema.py connect()` performs, in order: `PRAGMA journal_mode=WAL`,
`PRAGMA foreign_keys = ON`, `executescript(SCHEMA_SQL)`, an optional
`_refresh_current_triggers`, then `_stamp_schema_version(conn)` — and only then
`yield conn`. The commit sits *after* the yield.

On a brand-new database `_stamp_schema_version` takes its first branch and runs
`INSERT INTO schema_version (version) VALUES (?)`. Python's `sqlite3` module, at
its default `isolation_level=""`, opens an implicit transaction before any DML
and holds it open until an explicit `commit()`. `connect()` has not committed
yet, so the connection is handed to the caller *inside an open transaction*.

`db/jobs.py:112` then executes `BEGIN IMMEDIATE`, which SQLite rejects with
`cannot start a transaction within a transaction`.

### Why it never heals

The raise propagates out of the `with connect(...)` body, so `conn.commit()` on
the line after `yield` never runs. The `finally` closes the connection, and
SQLite rolls the uncommitted `INSERT` back. The database is left with the schema
DDL applied (DDL committed by `executescript`'s implicit pre-commit) but **no
`schema_version` row** — which is precisely the state that makes
`_stamp_schema_version` take the INSERT branch again. Every subsequent call
reproduces the same failure in the same way. The final line of the transcript
above (`schema_version rows: []`) is the proof.

### Blast radius

Only `claim_next_job` issues an explicit `BEGIN`; it is the sole caller that can
observe the open transaction as an error. Every other caller runs plain
statements that happily join the implicit transaction. This is why the defect is
narrow, not why it is unimportant: `claim_next_job` is the entry point of
`wiki jobs run` and of the MCP embedded worker.

It is rarely seen because `wiki init` and `wiki add` call `init_db` first, and
`init_db` *does* commit. It bites whenever a job claim is the first thing to
touch a state DB — a repo-cache DB that was deleted, never initialised, or
created by a code path that only ever opened `connect()`.

A second, quieter case has the same shape: a DB whose stored `schema_version`
differs from `SCHEMA_VERSION` takes the `UPDATE` branch, which is also DML, so
the *first* job claim after any schema-version bump fails identically.

## 2. Defect 2 — a negative chunk size, paid for in LLM calls

### Observed

Simulating `extract_knowledge_units`'s own subdivision and batching loops
against eight 3,000-character sections with a client reporting
`optimal_chunk_chars = 200`:

```
max_chars = 200 -> chunk_size passed to _chunk_text = -300
refined spans: 24000
BATCHES (= LLM calls): 3920
```

### Mechanism

`pipeline/knowledge_units.py:348`:

```python
sub_texts = _chunk_text(text, chunk_size=max_chars - 500, overlap=500)
```

`max_chars` is whatever `client_optimal_chunk_chars(client)` returned. Nothing
guarantees it exceeds 500, so `chunk_size` can be zero or negative.

`ingest_raw.py _chunk_text` does not reject that. It computes
`end = start + chunk_size`, which for a non-positive `chunk_size` lands at or
behind `start`, and then hits its own forward-progress guard:

```python
if next_start <= start:
    next_start = start + 1
```

So the "chunker" advances one character per iteration and emits a chunk at every
start position. Those chunks are not small — `text[start:end]` with a negative
`end` is `text[start:-300]`, nearly the whole remaining text. Measured on a
3,000-character input with `chunk_size=-300`:

```
chunks: 3000
first 3 lens: [2700, 2700, 2700]
last 3 lens: [0, 0, 0]
total chars emitted: 810000
```

3,000 chunks and a 270x character amplification: the text is not split, it is
replicated once per start position with a sliding 300-character tail removed.
The guard was written to prevent an infinite loop and it succeeds at that — it
converts a hang into an enormous, expensive, *successful-looking* run. Each of
those near-full-length chunks then exceeds the (tiny) batch budget on its own,
so nearly every one becomes its own LLM call.

`pipeline/graph_index.py:91` carries the identical unchecked subtraction in a
different position — `statement[:max_chars - 500]` — where a negative bound
silently drops the *tail* of every statement and then labels the result
`... [TRUNCATED]`, which is a truthfulness defect rather than a cost one.

### Why it is latent, and why it still matters

No production client reports a window that small. The floor across the real
clients is `OllamaClient`'s smallest RAM tier: a 4,096-token context ->
`int(4096 * 0.8) * 4 = 13,107` chars. `AntigravityCliClient` returns 18,000,
`ClaudeCliClient` 12,000, DeepSeek 50,000, and the helper's own default is
60,000.

It matters because the trigger is one config value, the failure mode is spending
rather than erroring, and the spend is unbounded in the document's length.
