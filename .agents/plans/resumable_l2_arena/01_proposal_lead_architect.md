# Core Proposal: persist each batch as it lands, and let the publish gate stay atomic

Date: 2026-08-21 | Agent Persona: lead_architect

## 1. Core Logic & Implementation

### 1.1 The smallest change that makes Hartley ingestable

Do not build a checkpoint table. The briefing's §6 Q5 is the answer: the loss is
that units live in memory until batch 277 succeeds, and the fix is to write them
as they are produced.

```python
# knowledge_units.py, inside the existing batch loop (:387)
for index, batch in enumerate(batches, start=1):
    result = _run_batch_with_retry(...)
    if result.errors:
        all_errors.extend(result.errors); break
    pending_units.extend(result.units)

    # NEW: persist this batch's units immediately, unpublished.
    # `generation_id IS NULL` already means "extracted, not yet authoritative",
    # so no new state is invented -- the column exists for exactly this.
    _persist_units(db_path, source_id, result.units,
                   batch_key=_batch_key(batch), config_key=_config_key(client))
```

Publish is untouched: `compile_source_l2` still creates a generation, still
gates, still publishes atomically (§26.3). The only difference is that the rows
it stamps with `gen_id` were written incrementally rather than all at once.

### 1.2 Resumption falls out; it is not a separate mechanism

A re-run asks what is already extracted for this source **under the same
configuration**, and skips those batches:

```python
done = _extracted_batch_keys(db_path, source_id, config_key)
for index, batch in enumerate(batches, start=1):
    if _batch_key(batch) in done:
        continue                      # already extracted, still unpublished
    ...
```

`_batch_key` is a hash of the batch's span ids and text, **not its index** —
measured (briefing §5a): the index means different things under different
`optimal_chunk_chars`, so a hash is the only key that cannot silently misalign.

`_config_key` covers the prompt contract version, the model, and the chunk
budget. A change to any of them makes the stored keys unmatchable, so a partial
from a different configuration is ignored rather than mixed in.

### 1.3 The v0.52.0 hazards, answered directly

**"A checkpoint that could never be written."** The removed one was gated on its
own output existing. Here there is no gate: the write happens unconditionally
after every successful batch, on the same path that already runs. A first run
writes checkpoint rows exactly as a resumed one does.

**"A resume that returned the wrong list."** The removed one returned the
staged-unit list, which is empty after publish. Here the function returns what
it always returned — the full unit id list for this extraction — assembled from
rows it just wrote plus rows it skipped. A source that already published has no
rows with `generation_id IS NULL`, so a resume of it finds nothing to skip and
behaves exactly like a fresh run.

### 1.4 The one deletion that has to change

`_discard_unpublished_units(db_path, source_id)` runs at the START of every
extraction (`:335`) and is what makes a re-run clean today. It must become
conditional: discard only partials whose `config_key` does not match, keep the
ones that do.

That single line is where resumption is won or lost, and it is the line most
likely to be reverted by someone tidying up.

## 2. Pros & Cons

**Pros.**

- No new table, no schema migration. `generation_id IS NULL` already means
  "extracted, not authoritative"; the proposal gives it a second use rather than
  a second mechanism.
- The atomic publish gate (§26.3) is untouched, so the guarantee that a blocked
  gate leaves the prior generation intact is unaffected.
- Hartley's failure becomes survivable: the next attempt skips the batches it
  already paid for and reaches publish inside one window.
- Keyed by content, so the measured mis-alignment hazard cannot occur.

**Cons / limits.**

- **277 writes instead of 1.** Unmeasured. If each costs what `job_events`
  costs (~1.8 ms through `connect()`), that is half a second — but nobody has
  timed `_persist_units` for a single batch.
- It weakens "all-or-nothing" from a property of the *database* to a property of
  the *publish gate*. Rows now exist mid-extraction that did not before, and
  anything that reads `knowledge_units` without filtering on `generation_id`
  would see them. The proposal has not audited those readers.
- A partial that is never resumed is never cleaned up unless a config change
  invalidates it. There is no expiry.
- `_config_key` is a guess at what invalidates a partial. Prompt version, model
  and chunk budget are obvious; temperature, the span builder, and the section
  splitter are not, and any of them changing silently would corrupt a resume.
