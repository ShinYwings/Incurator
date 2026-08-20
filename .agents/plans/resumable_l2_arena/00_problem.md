# Briefing: a completed extraction is discarded because the step after it was rate-limited

Date: 2026-08-21 | Author: main agent (measured on the live vault)

## 1. The case, in six rows

One source — Hartley, `sources.id=45`, 673 pages, 277 extraction batches — has
now failed six times across three days. Its own `job_events` history:

```
08-19 11:24  attempt 1  reached 277/277  -> 429 at publish
08-19 11:26  attempt 2  reached 0/1      -> 429 immediately    (pre-v0.61.1)
08-19 11:28  attempt 3  reached 0/1      -> 429 immediately
08-20 12:58  attempt 1  reached 277/277  -> 429 at publish
08-20 17:46  attempt 1  reached 277/277  -> 429 at publish
08-20 18:48  attempt 2  reached 183/277  -> 429 mid-extraction (after a 5-min wait)
```

**Three times it finished every batch and lost all of it at the last step.**

## 2. Retrying cannot fix this, and v0.61.1 is the proof

v0.61.1 made a rate-limited job wait rather than restart instantly. It worked:
the waited retry reached **183** where the instant ones reached **0**. It was
still not enough — the window recovers roughly 183 batches' worth in five
minutes and the job needs 277 **plus** the publish after it.

Every attempt spends the budget from batch 1. Longer backoffs move where it
dies; they cannot make the budget stretch. **A source this size cannot complete
by retrying, ever.**

## 3. Why nothing survives — measured, and it is not the discard-on-failure

The obvious suspect is the failure handler: `compile_source_l2` creates a
generation, and on any error calls `_discard_staged_units` +
`discard_compiler_generation`. That is real but it is not what loses the work.

The batch loop and the write are 60 lines apart:

```
knowledge_units.py:387   for index, batch in enumerate(batches, start=1):   # 277 iterations
knowledge_units.py:447   all_unit_ids = _persist_units(...)                 # ONCE, after all of them
```

**All 277 batches accumulate in memory.** Nothing touches the database until
every batch has succeeded. Confirmed on the live vault after the failure:

```
knowledge_units for source 45        : 0
unpublished units across all sources : 0
```

Not "discarded after being written" — never written. The staged-generation
machinery below it is irrelevant to the loss, because there is nothing staged
yet when the loop is interrupted.

## 4. The constraint any design must respect

`extract_knowledge_units`' docstring states the current contract and the reason
for it:

> Extraction is all-or-nothing: staged units from a previous interrupted run are
> discarded first, then units accumulate in memory and are bulk-persisted only
> on full success. An interrupted run therefore re-processes every batch.
>
> A checkpoint-resume mechanism used to sit here and was removed in v0.52.0
> because it could never run — checkpoints were written only inside the branch
> that required checkpoints to already exist, so the table stayed empty forever
> (verified: 0 rows across 36 sources and 2,799 units). Resumable L2 is still
> worth having; see the roadmap. It needs designing rather than re-enabling,
> because the old resume path also returned the staged-unit list, which is empty
> after a successful publish and would have retired the source's entire
> authoritative unit set.

Two hazards named there, both non-negotiable:

- **A checkpoint that can never be written.** The removed one was gated on its
  own output existing. Any design must state how the first checkpoint is
  written.
- **A resume that returns the wrong list.** The removed one returned staged
  units, which are empty after publish — resuming a published source would have
  retired every unit it had. Any design must say what a resumed run returns and
  what happens when it resumes a source that already published.

## 5. What is already there to build on

- `compiler_generations` exists, with `create` / `discard` / `publish` and a
  `status` column. Hartley has two rows, both `discarded`.
- `knowledge_units.generation_id` is NULL for staged rows, so "written but not
  published" is already representable.
- `_discard_unpublished_units(db_path, source_id)` runs at the START of an
  extraction (`:335`), which is what makes a re-run clean today — and is exactly
  what a resume would have to stop doing unconditionally.
- v0.59.0's `job_events` gives per-batch progress, so a resume has an existing
  observability surface rather than needing a new one.

## 5a. Measured — the batch index is stable per CONFIGURATION, not per source

§6's first question decides the rest, so it was measured before being asked.

**Within one configuration, batching is deterministic.** Parsed the same PDF
twice and fingerprinted every batch's contents:

```
run 1: 12 batches   run 2: 12 batches
identical batch boundaries across runs: True
first three fingerprints: ['c8ec8a117234', '5af7c4ba01ea', '947639e4ddcd']  (both runs)
```

So "batch 143 succeeded" is a meaningful thing to record — **as long as nothing
about the client changes.**

**Across configurations it is meaningless.** Batch boundaries come from
`client_optimal_chunk_chars(client)`, which the client declares:

| `optimal_chunk_chars` | batches for the same source |
|---|---|
| 60,000 | 12 |
| 32,000 | 23 |
| 16,000 | 46 |
| 8,000 | 93 |

A resume keyed on batch number would, after a provider or model change, replay
"batch 7 of 12" against a run that now has 46 batches — silently extracting from
different text than the number implies.

**Consequence for the design.** A checkpoint cannot be `(source, batch_index)`.
It has to be keyed by something the batching cannot silently redefine — the span
ids in the batch, or a hash of its content — and it has to record the
configuration it was produced under, so a changed budget invalidates it instead
of misaligning it. That also answers §6 Q2 in part: `optimal_chunk_chars` is not
an incidental tuning value, it is part of the checkpoint's identity.

## 6. Questions for the Arena

1. What is the unit of resumption — a batch, a span range, or the whole
   extraction? The loop already numbers batches `1..N` deterministically, but
   whether that numbering is stable across runs of the same source is
   **unverified** and decides everything.
2. What invalidates a partial extraction? The source changing is obvious. The
   prompt contract version, the model, the chunk budget (`optimal_chunk_chars`,
   which varies by client) are not.
3. Where does a partial live — staged rows with `generation_id IS NULL`, or a
   separate table? The first reuses machinery and collides with
   `_discard_unpublished_units`; the second is what v0.52.0 removed.
4. What does a resumed run return, given the removed mechanism got exactly this
   wrong?
5. Is there a cheaper answer than resumption — persist per batch and let the
   publish gate sort it out? That trades one all-or-nothing for many small
   writes and must be checked against §26.3's atomic-publish guarantee.
