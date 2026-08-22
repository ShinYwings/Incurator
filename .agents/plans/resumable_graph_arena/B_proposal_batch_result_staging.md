# Storage Proposal: a dedicated batch-result staging table

## 1. Core Logic & Implementation

Keep the graph tables untouched. Persist each batch's **parsed payload** to a
side table as soon as it validates, and replay the payloads through the existing
`persist_graph_data` at publish time.

```sql
CREATE TABLE IF NOT EXISTS graph_batch_results (
    id          TEXT PRIMARY KEY,   -- GBR-[UUID8]
    source_id   TEXT NOT NULL,
    input_hash  TEXT NOT NULL,      -- from prompt_runs; the resume key
    trace_id    TEXT NOT NULL DEFAULT '',
    payload     TEXT NOT NULL,      -- JSON: {entities: [...], relations: [...]}
    created_at  TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_graph_batch_results_key
    ON graph_batch_results(source_id, input_hash);
```

`extract_graph_data` gains one lookup and one insert:

```text
for index, batch in enumerate(batches, 1):
    input_obj  = contract.input_model(...)
    input_hash = prompting.input_hash_for(contract, input_obj)   # same fn run_prompt uses
    cached = db.get_graph_batch_result(db_path, source_id, input_hash)
    if cached:                       # already paid for, in an earlier run
        collect(cached); continue
    result = run_prompt(...)         # unchanged, including the retry/capacity logic
    db.put_graph_batch_result(db_path, source_id, input_hash, payload, trace_id)
    collect(result.parsed)
```

Publish is unchanged — `persist_graph_data` still receives one complete
`GraphData` and still runs inside the publish transaction. The staged rows are
deleted in that same transaction once the flip succeeds.

## 2. Pros & Cons

**Pros**

- **The §26.3 invariant is preserved exactly.** Nothing enters `graph_entities`
  or `graph_relations` before the gate; the staging table is not the graph, and
  no reader of the graph learns it exists.
- `persist_graph_data`, the unique index, the entity-sharing semantics, and
  every existing graph reader are untouched.
- Additive migration on an empty new table — no cost on existing vaults.
- The resume key is `input_hash`, which `run_prompt` already computes, so the
  cache hit is provably the same prompt.

**Cons**

- Payload is stored twice in the failure window (side table, then graph tables).
  For source 45 this is bounded by the extraction size — tens of MB, deleted at
  publish.
- Needs its own garbage collection: an abandoned source leaves rows behind.
- One new serialization boundary — the parsed pydantic objects must round-trip
  through JSON faithfully, or resume silently produces different graph rows than
  a clean run would.
