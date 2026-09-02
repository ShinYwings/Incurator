# v0.79.0 Master Implementation Plan — the index holds the first 200 characters of a span

## 1. What the Arena changed about the entry

ROADMAP E2 said "span segmentation isolates fragments" and the user approved a
reindex on that basis. Three independent measurements changed the answer.

**The chunker is not the cause.** `chunk_text` defaults to `target_tokens=256`
and never fires: every record handed to it is already smaller than one chunk.
Atoms are one claim, entities one description — small *by design*.

**The index is.** `source_spans` has no full-text column. It stores
`content_hash` (over the full text) and `text_preview`, which is
`" ".join(text.split())[:200]` (`pipeline/source_spans.py:31,163`), and
`retrieval/materializer.py:372` indexes THAT as the span's searchable body.

Measured three times independently — by two Arena agents and by me:
**4,865 of 11,774 spans (41.3%) sit exactly at the 200-char cap.** Sampling 300
of them and hydrating their true text: median 418 chars, p90 1,426, max 3,407.
**118,733 characters invisible to the index in that sample alone.**

**And the original premise was mostly wrong.** Of the 6,909 spans that are short
for real reasons, the red team classified 40 by hand: 20% genuinely truncated
mid-thought (nearly all one pattern — a bare markdown heading whose body landed
in the next span), 37.5% complete-by-design (titles, one-line definitions), 42.5%
neither claims nor fixable (PDF picture placeholders, page furniture). So
re-segmentation would spend a cascade to fix a fifth of the smaller half.

## 2. Objective

The search index holds a span's full text, so a query matching a word past
character 200 can find it, and the primary search path stops handing the model a
sentence cut mid-word.

## 3. Explicit Non-Goals

- **Re-segmentation.** Rejected on measured cost, not taste: span identity is
  `(source_id, content_hash)`, so merging spans mints new ids, and 20,230
  `knowledge_units` plus 19,521 `claim_supports` anchor to span ids across 46 of
  49 sources (93.9%). That risks an LLM re-extraction cascade — the expensive
  thing, not the 3-hour embed. It fixes 20% of 58.7% of spans. → ROADMAP.
- **Retrieval-time neighbour expansion.** A real option, well argued, but it is a
  retrieval-time patch over a storage-time problem, and its neighbour ordering is
  a proxy: `start_char`/`end_char` are 100% NULL, and grouping by
  `(source_id, page_number, section_title, toc_id)` collapses 11,774 spans into
  1,176 groups — one holding 289 tied spans. → ROADMAP, reconsider after this.
- Widening `text_preview`. `SCHEMA.md:2213` locks it immutable.

## 4. Locked Design Decisions

### D1. The index body comes from the full span text, not the preview

`materializer.py` builds the doc. It is NOT in the D2 frozen set — verified
against `D2_HOLDOUT_RESULT.yml`, which pins `chunking/engine/lexical/fusion/
embedding/evaluation` and the whole `db/` package, but not the materializer.

Full text is recovered by `pipeline.compile.hydrate_spans`, which re-parses the
source and matches on `content_hash`. Verified working on this vault: 40/40 and
then 300/300 truncated spans hydrated successfully.

`text_preview` is untouched, so the spec invariant holds and span identity does
not move. No new ids, no cascade.

### D2. Hydration failure degrades to the preview, loudly

A span whose source file has moved or changed cannot hydrate. That is today's
behaviour for the evidence route (`evidence.py:297` already falls back), and this
keeps it: a truncated body is worse than no body. The count of fallbacks is
reported by the reindex, because a silent 40% fallback rate would look identical
to success.

### D3. It requires a reindex, and the cost is measured, not guessed

Re-materialising changes the body text of 4,865 documents, so their embeddings
must be recomputed — content-addressed by `input_hash`, so only those change.
Measured on this machine: **2.4 texts/sec**, so ~34 minutes for the changed
subset and ~3 hours if everything re-embeds. The provider is local
(`llama-cpp/qwen3-embedding-0.6b`): CPU time, no quota, no money.

Rollback: the DB backup taken before the run. Nothing else is mutated.

### D4. Measured by a script a reviewer can re-run, because the existing harness cannot

`failure_atlas_holdout.py` has `run_count=3`, one query, and a synthetic
1,217-char fixture with one span per document. It is structurally blind to this
change.

The measurement is instead: for a sample of truncated spans, take a distinctive
term that appears ONLY past character 200 of the true text, query for it, and
record whether the span is retrieved. Before the change that must fail; after, it
must succeed. That is a property, not a score, and it is falsifiable.

## 5. Stop Conditions

Stop and report if hydration succeeds on less than 95% of truncated spans on a
real vault — that would mean the recovery path is unreliable and D2's fallback is
carrying more weight than intended.

## 6. Execution Phases

- **P1** — the failing measurement first: a term past char 200 is not findable.
- **P2** — `materializer.py` indexes hydrated full text, with the fallback and
  the fallback count.
- **P3** — reindex the vault; record before/after and the fallback rate.
- **P4** — docs (SCHEMA §6 on what the index body is, SEARCH_ENGINE_SCHEMA),
  version bump, CHANGELOG, ROADMAP E2 marked with what was actually found.
