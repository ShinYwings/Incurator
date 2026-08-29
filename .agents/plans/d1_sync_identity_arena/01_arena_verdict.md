# D1 Arena — three independent proposals, and what decided it

Three agents worked in parallel from the same briefing: one assigned the
`sync_key` transport design, one assigned content-derived deterministic ids, one
assigned only to measure what is actually broken. Each was told to argue its
assignment as well as it honestly could and then state its real costs.

## The measurement changed the problem

My own first reading of the live vault — 0 duplicate natural keys, 0 dangling
relation endpoints — led me to write in the briefing that the defect was
"latent, not manifest" and consistent with single-device use. **That inference
was wrong**, and the measuring agent found the evidence:

- A real peer exists and has been imported:
  `second_brain/.curator/sync/dev-bd8d7f0753da.jsonl`, 691 entities, 675
  relations, checkpointed in `sync_state`.
- **The collision has already fired once.** `MipNeRF360` (`method`): the peer
  proposed `ENT-69af9626`, this device already held `ENT-bb26f12b`. The peer's
  id was skipped and does not exist here.
- No dangling relation resulted **only because that export happened to contain
  no relation touching that entity.** That is timing, not safety.
- That peer is now 6 weeks stale at `schema_version` 12 against local 14, so
  `import_knowledge`'s hard version gate currently blocks it from syncing again.

So the bug is real, has fired, and its damage is one co-occurrence away.

## What each proposal concluded

**Deterministic ids — rejected by its own author.** Three findings did it:

1. `authored_topology.py` already implements exactly this design (F9,
   `_stable_id`), and the spec deliberately fences it off from extracted
   entities: *"Existing extracted identity behavior is unchanged"*
   (`SYSTEM_BEHAVIOR.md`). The boundary this proposal wants to cross was drawn
   on purpose.
2. **Tombstones become permanent natural-key blocks.** If `id` is
   `hash(canonical_name, entity_type)`, then deleting one bad extraction
   tombstones the *natural key*, and every future extraction of that name/type
   on any device is blocked forever. Nothing in `deleted_records` carries scope
   or expiry. That is not what a delete means.
3. **LLM surface-form variance defeats the premise.** `canonical_name` is raw
   model output with no normalization; `"GPT-4"` vs `"GPT4"` still hash apart,
   so the convergence guarantee fails exactly where it is needed.

**`sync_key` transport — buildable, but it pays for a lookup improvement with a
migration the project deliberately removed.** Its author established the
decisive constraint honestly: **this codebase has no `ALTER TABLE` path.**
`init_db`/`connect` apply `CREATE TABLE IF NOT EXISTS` only, which is a silent
no-op on an existing table. `db_sync.py` says so in its own comment. The
migration machinery (`_add_column_if_missing`, `_apply_migrations`) existed once,
in `e5ed4ae`, and was deleted one release later in `f8b40be`. Adding a `sync_key`
column means resurrecting it, and every referencing surface grows: **15 tables,
8 scalar/composite columns, 11 JSON arrays**, plus a type-dispatched composite
transport field for `artifact_dependencies` that its own author called the
highest-risk piece in the plan.

**The measurement — no schema change is required.** Both tables already carry the
natural key as a `UNIQUE` index (`idx_graph_entities_name`,
`idx_source_spans_source_hash`). `sources` needed a separate `sync_key` column
because `relpath` alone was not enough; these two do not. What is missing is only
the **remap step** — the thing `sources` already does at
`db_sync.py` `_lw_upsert_source`: on a content duplicate, look up the local id
*"so the peer's child rows attach to it instead of being orphaned."*

## Verdict

**Ship the remap. Do not ship the schema change.**

The roadmap entry describes the remedy as "a schema change touching every
referencing column." That is what made D1 look like a Phase D structural item.
The measurement shows the referencing columns already exist and already hold the
right shape of data — only the translation between a peer's ids and ours is
absent. Closing that needs no new column, no migration, no `SCHEMA_VERSION` bump,
and no change to the export format, so a device running the fix and a device
running the old code still interoperate: the fixed one imports correctly, the old
one keeps the bug. Graceful degradation, not a fleet-wide gate.

This is the standing tiebreaker applied literally — fewer moving contracts,
smaller blast radius — and here it costs no capability, because the `sync_key`
design's extra value over the remap is a faster lookup path, not a correctness
property. Both designs converge on the same user-visible outcome.

## Deliberately NOT in this release

- **The `sync_key` transport redesign.** It is a lookup-path improvement. If it
  is ever wanted, it needs the `ALTER TABLE` mechanism back first, which is its
  own decision.
- **A real tombstone bug the `sync_key` agent found while working, unrelated to
  the remap.** `claim_supports` and `entity_resolution_lineage` embed a
  *device-local* id in their composite tombstone token. Device A deleting a
  `claim_supports` row records a token naming A's span id; B holds the same span
  under its own id, so `_apply_tombstone` matches zero rows and B's copy survives
  while the tombstone reports as applied. `source_pages`/`source_pdf_pages` do
  not have this because they already transport `source_sync_key`. Fixing it
  changes a transport field, so it needs a `SCHEMA_VERSION` bump and its own
  release. **Filed to ROADMAP.**
- **`graph_relations` row convergence.** Two devices asserting the same relation
  mint two `REL-` ids; there is no natural-key UNIQUE constraint on that table.
  Endpoints converge under this fix; rows do not. Separate item.
- **`prompt_runs.source_ids`** — a JSON array of `sources.id` that has never been
  remapped, a pre-existing gap in the `sources` transport itself. Same machinery
  would reach it, but folding it in silently would blur this plan's acceptance
  criteria.
