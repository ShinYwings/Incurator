# Briefing: graph extraction cannot survive an interruption

## The measured problem

`extract_graph_data` (`pipeline/graph_index.py:218`) collects every batch's
entities and relations **in memory**:

> `# Collect parsed objects IN MEMORY (no DB writes); persisted only after the
> publish gate clears (copy-on-stage, §26.3).`

Every batch must succeed in one process lifetime. A capacity deferral, a
provider refusal past `_MAX_BATCH_ATTEMPTS`, or a SIGKILL throws away everything
already paid for.

Measured across three windows on the live vault, each ending at a 429:

| window | graph calls | usable (`ok`) |
|---|---|---|
| 15:15 → 15:24 | 20 | **3** |
| 15:45 | 1 | 0 |
| 17:40 → 17:47 | 8 | **3** |

Source 45 (Hartley) needs **~87** batches — 1,551,159 prompt chars at 18,000
each. At ≤3 usable batches per capacity window, all discarded at the end of each
window, **it cannot converge**. No number of retries reaches 87. This is not a
slow path; it is an unreachable one.

## Why the v0.62.0 fix cannot simply be copied

v0.62.0 solved exactly this for L2 by persisting each batch of knowledge units
as it completed, keying resume on `prompt_runs.input_hash`, and *releasing*
(`generation_id = NULL`) rather than deleting on failure.

The graph layer does not have the shape that fix relies on:

- **`graph_entities` has no `generation_id` column at all.** It is a globally
  deduplicated canonical table — `UNIQUE INDEX idx_graph_entities_name ON
  graph_entities(canonical_name, entity_type)` — shared across every source. An
  entity is not owned by a generation, so there is no NULL marker to stage it
  under and no safe way to distinguish "staged by the run that is still going"
  from "published long ago by another source".
- **`graph_relations` does have `generation_id`**, so the NULL trick would work
  there — but only there. A design that stages relations one way and entities
  another has two publish paths to keep atomic.
- **Relations reference entity ids**, so staging relations without their
  entities produces rows pointing at ids that do not exist yet.

## The invariant that must not break

`compile.py:436` states it:

> `# Graph LLM extraction runs DURING staging (returning data IN MEMORY) so a
> graph failure occurs BEHIND the publish gate: it discards the staged units and
> never leaves a published generation without its graph (§26.3).`

Persist + reconcile + flip happen in **one transaction**, so any exception rolls
back the prior authoritative state and the graph together. Whatever resumability
mechanism is chosen, a half-finished graph extraction must remain invisible to
the published graph, and publish must stay atomic.

## What the fix must achieve

1. A completed batch is never re-paid after an interruption of any kind —
   capacity deferral, refusal, or SIGKILL.
2. The published graph is unchanged in shape and semantics; `persist_graph_data`
   keeps working as the single publish-time writer.
3. No partial extraction is ever visible to search, query, or another source's
   compile.
4. A stale or abandoned resume state cannot silently poison a later run.
