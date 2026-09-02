# v0.79.0 Briefing — the retrieval unit is smaller than an answer

## The entry, and what re-measuring changed about it

ROADMAP E2, confirmed 2026-08-31: retrieval chunks have a median of 179 chars and
57% are under 200. Approved by the user on the understanding that fixing it
re-embeds the corpus.

**Measuring the cause first changed the shape of the problem.** The chunker is
not producing small chunks. `chunk_text` defaults to `target_tokens=256` — roughly
a thousand characters — and it never fires, because the records handed to it are
already smaller than one chunk:

| record type | chunks | avg chars |
|---|---|---|
| `source_span` | 11,774 | 160 |
| `knowledge_unit` | 8,618 | 220 |
| `graph_relation` | 2,540 | 116 |
| `graph_entity` | 2,442 | 122 |
| `community_report` | 404 | 811 |

An atom is one claim and an entity is one description; those are small *by
design*, and making them bigger would be making them not atoms. The only record
type the chunker meaningfully acts on is the community report.

So "increase the chunk size" is the wrong instruction. The real question is what
the RETRIEVAL UNIT should be when the stored unit is deliberately atomic.

## Where the fragments actually come from

`pipeline/source_spans.py:191` splits on `re.split(r"\n\s*\n", chunk)` — blank
lines, with **no minimum length**. Measured over the 11,774 span chunks: p10 = 56
chars, median 182, and **982 spans are under 50 characters**. ROADMAP I1 already
records this ("splits on blank lines with no minimum length") as a known leftover.

That is the audit's original finding, and it is real: a claim's supporting
sentence lands in a neighbouring span, so a span that matches retrieves without
the context that makes it mean anything.

## The cause found mid-Arena, and independently verified

`source_spans` has **no full-text column**. It stores `content_hash` (computed on
the full text) and `text_preview`, and `text_preview` is
`" ".join(text.split())[:200]` (`pipeline/source_spans.py:31,163`).

`retrieval/materializer.py:372` then indexes THAT:

```python
body = str(row.get("text_preview") or "")
```

So the searchable body of a span is a 200-character preview of it.

Verified independently against the live DB, not taken from the proposal:
**4,865 of 11,774 span rows (41.3%) sit exactly at the 200-char cap** — that is
what a truncated preview looks like, and the longest preview in the corpus is
exactly 200.

This reframes the entry. Spans are not merely segmented small; **41% of them are
indexed truncated**, and no amount of re-segmentation or retrieval-time expansion
recovers text the index never held. It also explains the measured distribution
directly: span chunks have p90 = 244 and a hard maximum of 321, which is the cap
plus a title prefix, not a natural length.

`SCHEMA.md:2213` locks `text_preview` as immutable ("A recovery candidate never
overwrites `text_preview`, `content_hash`, or any source file"), so widening that
column is not the fix. The fix has to put full text into the index by another
route. `materializer.py` is NOT in the D2 frozen set.

**Any proposal must now address this first.** A plan that improves segmentation
or expands neighbours while the index still holds 200-char previews is treating
the smaller half of the problem.

## The decision this Arena exists to make

Two families, and they cost very different amounts:

**A — change what is stored.** Merge short spans into their neighbours at
segmentation time, so the stored unit carries its own context. Requires
re-segmenting and **re-embedding the corpus** — the reindex the user approved.
Changes `pipeline/source_spans.py`.

**B — change what is returned.** Leave the stored units atomic and expand at
retrieval time: when a span matches, also return its neighbours. Costs no
re-embedding at all, and keeps atoms atomic.

Decide between them on evidence, not preference. B is cheaper and reversible; A
is what the ROADMAP entry assumed. They are not exclusive.

## Hard constraints

- **`retrieval/chunking.py`, `engine.py`, `lexical.py`, `fusion.py`,
  `embedding.py` and `evaluation.py` are ALL pinned by content hash in
  `docs/specs/failure_atlas/D2_HOLDOUT_RESULT.yml`**, which freezes a retrieval
  evaluation against exactly that code. Touching any of them invalidates a
  recorded result. This is not a soft rule — it has already caught two drafts in
  this repo, one of them mine last release. Any proposal MUST say which frozen
  files it needs and what it does about the record.
- Search is DB-native (FTS5 + vector + RRF + rerank). No second engine.
- A reindex re-embeds 25,778 chunks / 4.7M chars. **Measured 2026-09-01: the
  embedding provider is LOCAL** — `llama-cpp/qwen3-embedding-0.6b`, all 25,778
  rows on that one model. So a reindex costs wall-clock and CPU, not provider
  quota and not money. And embeddings are content-addressed by
  `(chunk_id, provider, model)` with an `input_hash`, so only chunks whose TEXT
  changes need recomputing — a re-segmentation that leaves most spans untouched
  re-embeds only what it moved.

  This weakens the strongest argument against family A, so weigh it honestly
  rather than reaching for the cheaper option out of habit. Still say what the
  reindex costs; "local" is not "free".
- 64 pre-existing orphaned child rows exist; do not fold their repair into this.

## What a proposal must answer

1. Which family, and on what measured evidence?
2. Exactly which files change, and which of them are frozen?
3. If a reindex is needed: what does it cost, and what is the rollback?
4. How is the improvement MEASURED rather than asserted? The repo has an
   evaluation harness (`backend/scripts/failure_atlas_holdout.py`) — say whether
   it can score this, and if not, what can.
5. What breaks if you are wrong?
