# Critique on both proposals

## 1. Vulnerabilities & Flaws

### A is rejected: it mutates authoritative state before the gate

Proposal A's fatal flaw is not the migration cost, it is that
`UNIQUE(canonical_name, entity_type)` makes staging impossible without touching
published rows. An entity named "Plücker coordinates" already exists, published
by another source. Staging a new extraction of it cannot insert a second row, so
it must UPDATE the canonical one — before the publish gate, outside the publish
transaction, visible to every reader immediately. A failed compile would then
have to *undo* an update to a row it does not own, with no record of the prior
value. This is worse than the problem being solved.

Adding `generation_id` to a globally shared table also gives the column no
coherent meaning: which generation owns an entity asserted by nine sources?

**B is adopted.** The remaining critique is against B.

### The failure that already happened once, and would happen again here

v0.62.0 shipped per-batch L2 persistence and was **worthless on its own**,
because `compile.py`'s error handler DELETED the staged rows. Every unit test
passed — 19 of them — because none reached that handler. The bug was found only
by a live run.

B has the identical exposure. If `put_graph_batch_result` joins the compile's
staging transaction, a rollback discards exactly the rows whose entire purpose is
to survive a rollback. **The write must commit in its own transaction,
immediately, and the compile's error path must never delete it.** A test that
only checks "the row is written" will pass against the broken version; the test
has to roll the outer transaction back and then assert the row is still there.

### Silent cache misses are the likely real-world failure

The resume key is `input_hash` over the fully-rendered prompt, which includes the
units block. Two upstream things can shift it without any visible error:

1. **Batch boundaries move.** Batches are cut at `client_optimal_chunk_chars`. A
   provider failover or a config change resizes every batch, so all 87
   `input_hash` values change and every batch is re-paid at full price.
2. **Unit ids move.** Resume depends on v0.62.0 releasing staged units
   (`generation_id = NULL`) so the next run *adopts* them. If adoption fails and
   units are re-extracted with fresh ids, the units block differs.

Either way the run silently pays 87 batches again and looks exactly like a run
that had no cache at all. **The mitigation is not to prevent the miss — a miss is
correct behavior — but to make it loud**: log a resume summary (`reused N/M,
extracted K`), and when staged rows exist for the source but none matched, say so
explicitly with the recorded chunk size.

### Serialization must be exact

The staged payload replaces the model's own parsed output on resume. If the JSON
round-trip drops a field — optional `description`, an empty `source_span_ids`,
float precision on `confidence` — a resumed run publishes a *different graph*
than a clean run, and nothing would flag it. Store with the pydantic model's own
`model_dump_json()` and rebuild with `model_validate_json()`, and test the round
trip on a populated instance, not an empty one.

### A poisoned entry is permanent

A batch that validates but extracts nonsense is cached forever; every retry
replays it. Only `ok` results are stored (the existing `result.ok and
result.parsed is not None` gate), and `wiki` needs a way to clear a source's
staged batches.

### Abandoned rows accumulate

A source that is never published leaves its payloads behind. They are harmless —
keyed by an `input_hash` that will not recur — but they are not free. Delete a
source's rows when its generation publishes, and when the source is removed.

## 2. Suggested Alternatives

None of the above changes the choice of B; they are conditions on it. They become
Locked Decisions D2–D6 in the master plan.
