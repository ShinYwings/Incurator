# Storage Proposal: stage into the graph tables themselves

## 1. Core Logic & Implementation

Mirror v0.62.0 as literally as the schema allows. Add `generation_id` to
`graph_entities`, then treat `generation_id IS NULL` as "staged" on both graph
tables. Each batch upserts its entities and relations as it completes. The
publish transaction stamps the generation onto every staged row; a failure
releases them back to NULL for the next run to adopt.

```sql
ALTER TABLE graph_entities ADD COLUMN generation_id TEXT;  -- migration
```

Resume finds staged rows for the source and skips the batches that produced
them, keyed by `prompt_run_id -> prompt_runs.input_hash`.

## 2. Pros & Cons

**Pros**

- One mechanism for L2 and graph; the release-on-failure discipline is already
  written and tested in `compile.py`.
- No new table, no replay step — rows are already in their final home when the
  gate clears, so publish is a single UPDATE.

**Cons**

- **It breaks the canonical-entity invariant.** `UNIQUE(canonical_name,
  entity_type)` is what makes an entity shared across sources. A staged entity
  whose name already exists cannot be inserted as a second row, so staging must
  *upsert into the published row* — which mutates authoritative state before the
  publish gate. That is precisely the §26.3 violation the current in-memory
  design exists to prevent.
- A concurrent compile of another source would adopt or collide with these
  half-staged entities; `generation_id` on a globally shared row has no coherent
  meaning.
- The migration touches a hot, large table on every existing vault.
- Search and query read `graph_entities` with no generation filter today. Every
  such reader would need a new predicate, or partial extractions become visible.
