# D1 — Briefing: sync transports entity/span identity on a surrogate id

## The claim under test (ROADMAP.md, "### D1.")

`graph_entities` and `source_spans` both carry a natural identity —
`UNIQUE(canonical_name, entity_type)` and `UNIQUE(source_id, content_hash)` — but
sync transports them on the surrogate `id`. Two devices that independently
extract the same thing mint different ids: the key lookup misses, the insert
collides on content, and convergence is classified after the fact rather than
found directly. Nothing remaps `graph_relations.source_entity_id` /
`target_entity_id` when an entity converges.

`sources` already solved this with a `sync_key` transport identity.

## Measured before designing anything

Live vault (`/Users/shin/shinywings/second_brain`,
`.cache/vaults/13ed51f8b06cb88e/state.sqlite`), 2026-08-29:

| table | rows |
|---|---|
| `graph_entities` | 2,481 |
| `source_spans` | 11,847 |
| `graph_relations` | 2,787 |
| `knowledge_units` | 18,162 |
| `community_reports` | 575 |

**The bug has not fired here.**

- entities sharing a natural key under different ids: **0**
- `graph_relations` rows with an endpoint missing from `graph_entities`: **0**

That is consistent with this vault having only ever run on one device. The defect
is **latent, not manifest** — which does not make it unreal (the second device is
the whole point of the sync feature) but does change how much migration risk is
worth accepting to close it. A plan that trades a working single-device vault for
a theoretical multi-device correctness win is a bad trade; say so if that is what
the design costs.

## The cost driver: ids embedded in JSON arrays

Both candidate designs have to move ids that are not in a column of their own.
Counted on the live vault:

| column | rows | embedded ids |
|---|---|---|
| `knowledge_units.source_span_ids` | 18,162 | 23,162 |
| `community_reports.entity_ids` | 575 | 4,017 |
| `graph_relations.source_span_ids` | 2,618 | 3,186 |
| `community_reports.source_span_ids` | 575 | 2,715 |
| **total** | | **33,080** |

The difference between the designs is not *whether* JSON arrays must be rewritten
but **once (migration) versus on every import (remap)**.

## What the plan must answer

1. Every referencing column, scalar and JSON, with file:line.
2. Whether `canonical_name` is mutable — entity merges and
   `redirect_to_entity_id` exist. If it is, an id derived from it is a lie.
3. Tombstones: a `deleted_records` row written under the old identity must still
   match after migration, or deletes silently stop working.
4. Mixed-version sync: one device migrated, one not.
5. Rollback: what restores the pre-migration state, and how it is rehearsed.

## Non-goals

- Not fixing D2/D3 in this release. Phase D is one structural change per release.
- Not reindexing or re-extracting the vault.
