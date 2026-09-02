# Retrieval Granularity Proposal: Family A — Fix Segmentation At The Source

Date: 2026-09-02 | Agent Persona: segmentation_architect

## 0. Summary position

Family A is worth doing, but not as the single blunt "merge short spans" move
the briefing sketches. Investigation surfaced a **second, larger, and
strictly cheaper bug in the same neighborhood**: 41.3% of the corpus's spans
are silently hard-truncated to 200 characters before they ever reach the
search index, independent of whether the paragraph itself was too short. That
bug has zero identity cost to fix. The genuine "982/3,569 spans with no
context" problem does have a real identity cost, and I quantify it below
rather than wave it away, per the correction that landed while researching
this.

I recommend shipping both, in this order:

- **Tier 1 (do first): stop truncating spans at the materializer, not at
  `source_spans`.** No identity change, no reconciliation, no re-extraction.
  Fixes 4,865 already-adequate paragraphs that are currently invisible to
  ranking past their first 200 characters.
- **Tier 2 (the assigned ask): merge sub-minimum paragraphs into a neighbour
  at segmentation time.** This is the real Family A move from the briefing.
  It changes span identity for a measured-bounded subset of the corpus, and
  it goes through this repo's existing §26.4 source-edit reconciliation
  machinery — not a bespoke migration.

Both are confined to files **outside** the D2 frozen fingerprint set. Neither
one requires touching a frozen file for its core logic; only the identity
fallout of Tier 2 optionally touches `db/_entities.py`, and only additively,
in the same "rearm" style this repo has used a dozen times already.

---

## 1. Core Logic & Implementation

### 1.1 Tier 1 — the truncation bug (context, not scope of this Arena, but load-bearing)

**Verified against the live corpus** (`.cache/vaults/13ed51f8b06cb88e/state.sqlite`,
49 sources, 11,774 spans — the same corpus the briefing's numbers come from):

```
sqlite3 state.sqlite "SELECT COUNT(*) FROM source_spans WHERE LENGTH(text_preview)=200;"
-> 4865   (41.3% of 11,774)
```

`source_spans` (`db/schema.py:383-398`) has **no column that stores full span
text.** `SpanRecord.text_preview` (`pipeline/source_spans.py:160-163`)
truncates to `_PREVIEW_CHARS = 200` unconditionally:

```python
_PREVIEW_CHARS = 200
@property
def text_preview(self) -> str:
    preview = " ".join(self.text.split())
    return preview[:_PREVIEW_CHARS]
```

`content_hash` is computed on the **untruncated** text (`_hash(para)` in
`_emit_prose`, `pipeline/source_spans.py:190-199`) — so this is purely a
retrieval-corpus bug, not an identity bug. But `retrieval/materializer.py:372`
builds the indexed `search_documents.body` for a `source_span` record
directly from that truncated column:

```python
body = str(row.get("text_preview") or "")   # materializer.py:372
```

That body then flows unmodified into `materialize_chunks` (`embedding.py:164`,
`title + "\n" + body`) and gets embedded. So **any paragraph longer than 200
characters is only half-searchable, and any paragraph longer than ~1000
characters loses 80%+ of itself from both lexical and vector ranking** — not
because the chunker or the span is too small, but because the preview column
was never meant to be the retrieval text. This directly explains part of the
"57% under 200 chars" statistic in the briefing: 4,865 of those 200-char
entries are truncation artifacts of paragraphs that were never short to begin
with, sitting in the same histogram bucket as genuinely short ones.

**Why this must NOT be fixed by widening or backfilling `text_preview`
itself.** `docs/specs/curator_schema/SCHEMA.md:2213` states the invariant
explicitly: *"Raw parser/source span text is immutable. A recovery candidate
never overwrites `text_preview`, `content_hash`, or any source file."* And
`§26.2c` (`SYSTEM_BEHAVIOR.md:3163-3187`) establishes that `source_spans` has
no `updated_at`; cross-device LWW merge derives its revision **only** from
`created_at` and timestamps embedded in `metadata`. Mutating `text_preview`
in place, even idempotently, is invisible to that revision derivation — a
remote device merging an older row would silently win and drop the wider
preview, with no error and no report, exactly the failure mode §26.2c was
written to prevent for a different column. `text_preview` is spec-locked as
an immutable, intentionally-lossy display artifact. Do not touch it.

**The fix instead lives entirely in the derived layer.** The full,
untruncated span text is already recoverable deterministically: `hydrate_spans`
(`pipeline/compile.py:264-306`) re-parses each cited source exactly once per
`relpath` and returns `content_hash -> full text`, verified against the
stored hash — this is the exact mechanism `retrieval/evidence.py:36-40`
already uses to give `wiki query` answers their full text at hydration time
(`_hydrate_full_texts`, lazy-imported for the same reason: `evidence.py`
imports `pipeline.compile`, which imports `retrieval.materializer`, so the
import must stay inside the function). **`materialize_search_documents` is
the one caller in the source_span path that does not do this** — it reads
`text_preview` straight off the row instead. The fix is a ~10-line change at
`materializer.py:368-374`:

```python
# materializer.py, inside materialize_search_documents, before the `for row in spans` loop:
from ..pipeline.compile import hydrate_spans   # lazy: same cycle evidence.py avoids
full_texts = hydrate_spans(db_path, [str(row["id"]) for row in spans])

# inside the loop, replacing `body = str(row.get("text_preview") or "")`:
body = full_texts.get(str(row["id"])) or str(row.get("text_preview") or "")
```

`hydrate_spans` batches by `relpath` (49 file re-parses for this corpus, not
11,774), is pure deterministic parsing with no LLM call, and already has a
documented, tested fallback contract: "spans whose source is unavailable or
whose hash drifted are omitted" — so a moved/deleted source file degrades to
today's truncated behavior for just that source, not a hard failure for the
whole reindex. `materializer.py` is **not in the D2 frozen file list** (see
§4) and is not referenced in any of its ~30 rearm entries.

**Cost:** zero span-identity change (no new `SPAN-` ids, no `delete_source_spans`
call, no `knowledge_units`/`dag_edges`/`claim_supports` impact — the loop never
touches `source_spans` rows, only what gets written into the derived,
disposable `search_documents`/`search_chunks` tables). All 4,865 previously-
truncated chunks get a new `input_hash` (their text changed) and re-embed;
everything else is untouched. This is a `wiki reindex` with no source
re-parse-and-reconcile cascade — the cheapest possible move in this Arena,
and it should ship regardless of what happens to Tier 2.

### 1.2 Tier 2 — the actual merge (the assigned Family A ask)

**Target.** `_emit_prose` (`pipeline/source_spans.py:190-199`), called from
`_block_spans` (`:174-213`), which is called from `spans_from_sections`
(`:216-242`). Both call sites that feed the DB (`ingest_raw.py:1522`,
`pipeline/compile.py:365`) already re-derive spans from source text on every
add/recompile, so a code change here takes effect the next time either path
runs — there is no separate migration entry point to build.

**Algorithm.** Add one module constant and rewrite `_emit_prose` from
"emit every paragraph" to "accumulate until a floor, then emit":

```python
_MIN_SPAN_CHARS = 100   # see §1.2.1 for why 100, not 50 or 200

def _emit_prose(chunk: str) -> None:
    paras = [p.strip() for p in re.split(r"\n\s*\n", chunk) if p.strip()]
    buf: list[str] = []
    buf_len = 0
    def _flush() -> None:
        nonlocal buf, buf_len
        if not buf:
            return
        merged = "\n\n".join(buf)
        spans.append(
            SpanRecord(
                "paragraph", merged, _hash(merged), page, title, toc_id,
                classify_span_loss(merged),
            )
        )
        buf, buf_len = [], 0
    for para in paras:
        buf.append(para)
        buf_len += len(para)
        if buf_len >= _MIN_SPAN_CHARS:
            _flush()
    if buf:                      # trailing remainder under the floor
        if spans and spans[-1].span_type == "paragraph":
            prev = spans[-1]
            merged = prev.text + "\n\n" + "\n\n".join(buf)
            spans[-1] = SpanRecord(
                "paragraph", merged, _hash(merged), prev.page_number,
                prev.section_title, prev.toc_id, classify_span_loss(merged),
            )
        else:
            _flush()              # no prior paragraph in THIS prose region to fold into
```

This mirrors, deliberately, the exact "absorb a sub-floor trailing buffer
into the previous chunk" shape already used one file over in
`retrieval/chunking.py:112-126` (`chunk_text`'s `min_tokens` handling) — same
codebase, same pattern, applied one layer up. Two rules, stated precisely
per the brief's ask:

1. **Forward accumulation.** Consecutive paragraphs in one prose region are
   concatenated with `\n\n` until the running length crosses
   `_MIN_SPAN_CHARS`, then emitted as one span. This is what directly kills
   the "982 spans under 50 chars" and most of the "3,569 under 100 chars"
   population — a run of three 30-char captions becomes one ~100-char span.
2. **Backward absorption of the remainder.** A trailing sub-floor buffer at
   the end of a prose region folds into the immediately preceding paragraph
   span (**not** into a following code/equation block, and not into the next
   section) — mirroring `chunk_text`'s own remainder rule. If there is no
   preceding paragraph span *in that same prose region* to fold into, the
   sub-floor buffer is emitted standalone. This happens in exactly one place:
   a short paragraph that is the very first thing in a prose region bounded
   by a code or equation block on one or both sides.

**What happens to fenced code and `$$` blocks — explicitly, per the ask.**
Nothing. `_block_spans`'s block-scanning loop (`:182-186`) still finds every
`_CODE_BLOCK` / `_EQUATION_BLOCK` match first and calls `_emit_prose` only on
the prose *between* them (`:201-212`); the merge logic lives entirely inside
`_emit_prose` and never sees block text. A code or equation block of any
length — `$$x=1$$` at 8 characters included — is **never** a candidate for
merging, in either direction, regardless of `_MIN_SPAN_CHARS`. This is not
an oversight the algorithm works around; it is the existing invariant
(module docstring: "kept as specialized spans with their exact
text/delimiters") left completely alone. One direct consequence, disclosed
rather than hidden: a short paragraph sitting directly against a code or
equation block boundary (case 2's "no preceding paragraph in this prose
region" branch) stays standalone and sub-floor, because merging it across
the block would require carrying a non-contiguous excerpt as one span's
text — the same objection the module already applies to blocks themselves.
Measured impact of this residual gap is part of the P0 dry run in §1.2.1.

**`spans_from_sections`'s existing single-span collapse (`:232-239`,
`len(sub) <= 1`) is untouched** — a section whose entire prose merges into
one span under the floor already becomes a single `heading_section` span
today; my change doesn't add or remove behavior there, it only changes what
`sub` looks like going in.

**Loss classification is preserved by construction.** `classify_span_loss`
(`:49-73`) is called on the *merged* text at `_flush()` time, exactly as it
is called on each unmerged paragraph today — an "intentionally omitted"
picture placeholder that gets folded into a real-text neighbour still matches
the regex wherever it sits in the combined string, so `formula_status`/loss
reporting (§26.2b) does not regress.

#### 1.2.1 Why 100, and the honest uncertainty in that number

The briefing gives p10=56, median=182 (on `search_chunks.text`, which is
`title + "\n" + text_preview` — see §1.1's discrepancy note below), and the
correction adds 982 spans under 50 chars, 3,569 under 100. I chose 100 chars
as the headline recommendation — roughly one short sentence, enough to carry
a subject and a predicate — over the more aggressive 200 (which would fold
in over half the corpus, 6,264 of 11,774 spans measured on `search_chunks.text`)
specifically to avoid overclaiming a number I have not measured precisely.
**I could not compute the exact post-merge span count from the live DB**:
`source_spans.id` is a UUID, not a document-order key, and the table has no
stored adjacency column, so simulating my own merge algorithm against
already-stored rows would require re-parsing all 49 source files — which is
exactly the P0 step this needs anyway, done for real rather than approximated
here.

**Required P0 before this ships**: a small, throwaway script (not a
committed test) that runs old `spans_from_sections` and new
`spans_from_sections` over the same 49 parsed sources and reports:
`len(old_hashes) - len(new_hashes)` (net span count change),
`len(old_hashes - new_hashes)` (span ids that disappear — an exact,
non-estimated figure), and the resulting corpus-wide char-length histogram.
That number, not this section's estimate, is what the master plan should
gate the threshold decision on. My worst-case bound: at most
`2 × 3,569 = 7,138` span identities change (every sub-100 span plus a
distinct neighbour each) if no two sub-floor spans are ever adjacent to each
other; the true number is lower because runs of adjacent short spans (e.g.
consecutive figure captions) collapse into one merge event that invalidates
several old ids but mints only one new one. **Treat "30%-60% of the 11,774
spans" as the range to plan around, not a result.**

### 1.3 Identity, `knowledge_units`, `dag_edges`, and `db_sync` (the part I was told not to hand-wave)

`upsert_source_span` (`db/_entities.py:112-160`) keys on
`(source_id, content_hash)` (`idx_source_spans_source_hash`,
`db/schema.py:400-401`). A merge that changes a paragraph's text changes its
hash; a *new* row is minted for the merged text, and the paragraphs it
absorbed simply never appear again in the next `spans_from_sections` output.
Their old rows are not deleted by this alone — they become orphaned until
something calls `delete_source_spans` on them.

**This is not a new problem this proposal invents.** It is exactly the
scenario `SYSTEM_BEHAVIOR.md §26.4` ("Source Edit/Delete/Split
Reconciliation") already exists for, and `delete_source_spans`
(`db/_entities.py:229-334`) already implements the cleanup:

- deletes `claim_supports` rows citing the removed span id,
- deletes `artifact_dependencies` rows depending on it,
- scrubs the id out of every `graph_entities`/`graph_relations.source_span_ids`
  JSON array so no graph record carries a dangling reference,
- writes a `deleted_records` tombstone (`db_sync.py`) for the removed span so
  other devices apply the same deletion on import — `source_spans` is a
  `SYNC_TABLES` member (`db_sync.py:55`), so this is not new sync surface,
  it is the existing tombstone path exercised at wider scope.

**What `delete_source_spans` does *not* do**: it does not touch
`knowledge_units.source_span_ids` (the JSON array on the claim row itself).
A KU that cited an orphaned span keeps citing a dead id until something
re-derives it. That "something" is `recompile_source`
(`pipeline/compile.py:1046`, called by the source-edit path §26.4
describes): it re-extracts L2 over the source's new spans inside a staged
generation, and reconciles claims via `semantic_hash` candidates —
**unchanged claims keep their id and verified support; changed claims are
re-extracted.** Because the merge algorithm concatenates original paragraph
text verbatim (`\n\n`.join, no rewriting), a claim's cited *statement* text is
almost always still findable inside its now-merged span, so I expect most
`semantic_hash` candidates to match and most KUs to survive with an updated
`source_span_ids` pointer rather than a full LLM re-extraction — but this is
an expectation, not a measurement, and it is the second thing the P0 dry run
in §1.2.1 must confirm empirically over a handful of real sources before the
master plan commits to a corpus-wide run.

**The honest bottom line on cost**: resegmenting the whole corpus is not "a
reindex" in the sense the briefing's cost framing suggests — it is "trigger
the existing source-edit reconciliation for every source that contains at
least one sub-floor span," which cascades through L2 (`recompile_source`),
not just the retrieval layer (`materialize_chunks`/`embed_corpus`). That
cascade is bounded (per-source, per-claim, existing machinery, not a new
code path) but it is not free, and it is not merely CPU time for an embedder
— it may issue LLM calls for claims whose evidence text genuinely doesn't
survive semantic-hash matching. **This must be measured on a real subset
before it is approved for the full 49-source corpus**, exactly as CLAUDE.md's
stored-contract rule requires ("It IS an automatic plan, a release of its
own, and a migration rehearsal").

**Cross-device convergence.** `spans_from_sections` is a pure, deterministic
function of source bytes and code version (no LLM, no config). Two devices
running the same code against the same source file produce byte-identical
`content_hash` values — this is not a new invariant, it is why
content-hash-keyed sync already works for every other deterministic-recompute
change in this repo's history (the dozen D2 rearms in §4 are the same
argument applied to code, not spans). The failure mode to rehearse
explicitly is a device that is slow to upgrade: it keeps serving from old
spans/KUs until it re-syncs and re-derives, receiving the new rows plus
tombstones for the old ones via the existing `deleted_records` import path.
This needs a migration rehearsal (two-DB import/export test), not new
mechanism.

---

## 2. Frozen files: what I touch, what I don't (§4 of the brief's required answers)

**I checked the live D2 frozen fingerprint set directly**
(`docs/specs/failure_atlas/D2_HOLDOUT_RESULT.yml:594-606`,
`file_sha256`):

```
backend/scripts/failure_atlas_holdout.py
backend/src/curator/retrieval/evaluation.py
backend/src/curator/retrieval/engine.py
backend/src/curator/retrieval/lexical.py
backend/src/curator/retrieval/fusion.py
backend/src/curator/retrieval/embedding.py
backend/src/curator/retrieval/chunking.py
backend/src/curator/db/__init__.py
backend/src/curator/db/schema.py
backend/src/curator/db/_entities.py
backend/src/curator/db/jobs.py
backend/src/curator/db/sources.py
```

**`pipeline/source_spans.py` and `retrieval/materializer.py` — the two files
both my tiers actually edit — are in neither this list nor any of the ~30
`*_rearm` entries above it.** This is not a coincidence I get to claim credit
for; I verified *why* by reading `failure_atlas_holdout.py` itself
(`_seed_authoritative_corpus`, lines 39-68): the Q06 holdout **INSERTs
`source_spans` rows and calls `db.upsert_search_document` directly**, with
hand-authored, pre-chunked fixture "documents" from `fixture_corpus.yml`. It
never calls `spans_from_sections`, `_block_spans`, or
`materialize_search_documents` — the holdout was built to bypass the L1
pipeline entirely and test the ranking stack against a fixed, already-
materialized corpus. Neither of my tiers is reachable from the harness at
all, at any commit.

**`db/_entities.py` is frozen and Tier 2's reconciliation does route through
`delete_source_spans`, which already exists there — I don't need to add or
change anything in it.** `upsert_source_span` already accepts `start_char`/
`end_char` as optional keyword arguments (`db/_entities.py:122-123`); I
don't pass them (see §3), so I call existing frozen-file functions
unchanged. **Zero required edits to any frozen file for Tier 1 or Tier 2's
core logic.**

**If the P0 measurement in §1.2.1 or §1.3 surfaces a genuine gap** (for
example, if `recompile_source`'s reconciliation needs a bulk "list spans
whose text changed but claim didn't" helper that doesn't exist yet), the
precedent for adding it is already established a dozen times over in this
same file's rearm history — an additive function, a new
`v0790_span_merge_rearm` block in `D2_HOLDOUT_RESULT.yml` stating which db.*
symbols the frozen harness actually imports (`connect`, `init_db`,
`upsert_search_document` — confirmed by reading the harness), and a
non-impact argument following the same template as
`v0630_graph_batch_staging_rearm` or `db2_slice2_jobs_sources_rearm`. This is
routine maintenance in this codebase, not a special case I'm inventing for
this plan — but it is not needed for the design as specified above.

**No proposal in this Arena needs to touch `retrieval/chunking.py`,
`engine.py`, `lexical.py`, `fusion.py`, or `evaluation.py` at all** — none of
those implement segmentation; they consume whatever `search_chunks` already
contains.

---

## 3. `start_char`/`end_char`: not needed

Both are `NULL` on all 11,774 live rows (confirmed:
`SELECT SUM(start_char IS NULL), SUM(end_char IS NULL), COUNT(*) FROM
source_spans` → `11774|11774|11774`). I traced every consumer of full span
text — `_hydrate_full_texts` (`evidence.py:36`) →
`hydrate_spans`/`hydrate_span_text` (`pipeline/compile.py:235-306`) — and
none of them read `start_char`/`end_char`. Full-text recovery works by
**re-parsing the source and matching on `content_hash`**, not by seeking into
stored byte offsets. `materializer.py:378-386` writes `start_char`/`end_char`
into `provenance_json` on the search document, but nothing reads them back
out for hydration. They appear to be a schema field reserved for a PDF-page
byte-offset feature that was never wired up, and Tier 1/Tier 2 as specified
do not need to change that. I do not propose populating them — doing so
would be scope creep unconnected to this Arena's problem, and the existing
hydration path already gets the job done without them.

---

## 4. Reindex cost and rollback

**Corrected cost model** (per the coordinator's note, confirmed against the
live `search_embeddings` table showing every row on
`provider='llama-cpp', model='qwen3-embedding-0.6b'`): embedding is local,
so cost is wall-clock/CPU, not provider spend. `embed_corpus`
(`embedding.py:227-307`) is already content-addressed by
`(chunk_id, provider, model)` with an `input_hash` staleness check
(`:253-258`): a chunk whose text is byte-identical to what's already embedded
is skipped, not recomputed. Both tiers benefit from this automatically —
neither needs new code to get partial re-embedding.

- **Tier 1**: exactly 4,865 chunks get new `input_hash` (their body grows
  past the old 200-char cap); the rest are untouched. `materialize_chunks`
  itself is a full rebuild-and-diff over all 25,778 rows (cheap — no model
  call, just string ops and one `INSERT...ON CONFLICT` pass), but
  `embed_corpus` only computes new vectors for those 4,865.
- **Tier 2**: bounded by the P0 measurement in §1.2.1, worst case ~7,138 of
  11,774 `source_span`-type chunks (60%) get new `input_hash`.
  `knowledge_unit`-type chunks whose citing span moved will also re-embed if
  their `statement` text is unaffected but a downstream field changes — this
  needs confirming against the P0 output, not assumed here.

**Wall-clock, explicitly unmeasured**: I found no recorded throughput
benchmark for `llama-cpp::qwen3-embedding-0.6b` anywhere in this repo's docs
or CHANGELOG. Rather than invent a precise-looking number, I recommend timing
a 200-chunk batch first (`embed_corpus` already batches at `batch_size=32`)
and extrapolating; as an order-of-magnitude placeholder only, short-text CPU
batched inference on a model this size is commonly in the tens-to-low-
hundreds of embeddings/sec range, which would put 4,865-7,138 changed chunks
at roughly one to several minutes — small, but a number the master plan
should replace with a real measurement, not this estimate, before it becomes
a release gate.

**Rollback.** Tier 1 rolls back by reverting `materializer.py` and re-running
`wiki reindex` — `source_spans` was never touched, so this is a pure
retrieval-layer revert with no data loss. Tier 2 is not a clean single-step
rollback once `recompile_source` has run on real sources: reverting
`pipeline/source_spans.py` and re-triggering reconciliation would re-derive
the *original* per-paragraph spans (same determinism argument as cross-device
convergence, §1.3), re-orphaning the merged spans and re-running claim
reconciliation a second time. That is mechanically safe (the same F7 path,
run twice) but is not instantaneous, and every source touched pays the
reconciliation cost again on the way back. The master plan should stage Tier
2 behind a flag that can hold at "old algorithm, new code path present" so a
bad merge threshold is a config revert, not a second full reconciliation
pass — the same pattern this repo already uses for provider/model config
(`search_embed_fingerprint` gates a re-embed on model change; an analogous
`segmentation_profile` value in `search_index_meta` could gate this).

---

## 5. Measurement (§6 of the brief's required answers)

**`failure_atlas_holdout.py` cannot score this, structurally, not just by
policy.** Proven in §2: the Q06 fixture bypasses `spans_from_sections` and
`materialize_search_documents` entirely, seeding pre-chunked fixture rows
directly. Family A's entire mechanism — how a real source document gets cut
into spans, and how much of a span's own text reaches the index — is outside
what that harness exercises at any commit. Running D2 before/after this
change would show byte-identical output, which is a null result, not
evidence.

**What I propose instead, concretely and re-runnable:**

1. **A structural, LLM-free "segmentation shift" script** — new file, e.g.
   `backend/scripts/measure_span_merge_shift.py` — not a committed pytest,
   not `failure_atlas_holdout.py`'s single-consumption model. It re-parses
   the 49-source live/testbed corpus with old vs new
   `spans_from_sections`, and reports (a) net span count change, (b) the
   `char-length` histogram before/after (reproducing the 982/3,569/6,264
   buckets this proposal cites, so a reviewer can regenerate them, not take
   my word for them), (c) the exact `old_ids - new_ids` set size (§1.2.1's
   P0), and (d) how many `knowledge_units.source_span_ids` entries point at
   an id that disappears. This is the tool that turns §1.2.1's "30%-60%"
   estimate into a number, and it is safe to re-run any number of times
   because it writes nothing.
2. **A new, freely-rerunnable retrieval-quality fixture**, built the way I
   argue Q06 should have been built for this question: real (or realistic)
   multi-paragraph source documents where the answer to a query needs BOTH a
   claim sentence and an adjacent short supporting/qualifying sentence
   currently split into a separate span. Score it by importing and calling
   `retrieval.evaluation.evaluate_rankings` **unchanged** (it's frozen, but
   calling a frozen function from a new script doesn't touch its hash or its
   D2 pin) — same recall@k / MRR / citation-completeness metrics D2 uses, so
   the numbers are apples-to-apples, but over a corpus that actually
   exercises segmentation. Unlike Q06 this fixture is not single-consumption
   by design — it exists specifically so a reviewer can re-run it after
   changing `_MIN_SPAN_CHARS` and see the metric move.
3. **A direct citation-completeness check on Tier 1 alone**, independent of
   §1.2.1: pick the 4,865 currently-truncated spans, confirm their full
   hydrated text now appears in `search_chunks.text` post-fix, and spot-check
   that a query whose answer lives past character 200 of one of those
   paragraphs now retrieves it. This one needs no new fixture — it is a
   direct measurement against the live corpus before/after the
   `materializer.py` change.

---

## 6. Pros & Cons

**Pros**

- Tier 1 is a real, verified, previously-undocumented bug fix (41.3% of the
  corpus silently truncated) with zero identity cost, discoverable and fixable
  independent of any decision on Tier 2.
- Tier 2's merge algorithm is a small, local change that reuses an existing
  pattern in the same codebase (`chunk_text`'s remainder-absorption rule) and
  an existing reconciliation mechanism (§26.4 / F7) rather than inventing new
  machinery.
- Neither tier touches a single D2-frozen file for its core logic — verified
  by reading the holdout harness, not by policy compliance alone.
- The fix is where the problem is: the stored unit genuinely carries more of
  its own context afterward, which Family B (expand-at-retrieval) does not
  change — B still stores spans that don't mean anything alone, it just
  papers over that at query time.
- `start_char`/`end_char` are confirmed dead for this purpose; the proposal
  correctly does not spend effort populating a column nothing reads.

**Cons — named, not hidden**

- **Tier 2's true cost is not fully known.** §1.2.1 and §1.3 both terminate
  in "must be measured before shipping," not a number. This proposal cannot
  honestly promise a reindex-sized cost; it can only promise the cost is
  bounded by existing, tested reconciliation machinery and give the exact
  script that will produce the real number.
- **Tier 2 may issue LLM calls.** If `semantic_hash` reconciliation
  candidates don't match as cleanly as I expect (§1.3), affected claims get
  genuinely re-extracted, which is a materially different cost profile than
  "re-embed changed chunks" — this is the gap between what the briefing
  assumed ("re-embeds the corpus") and what §26.4's mechanism actually does
  when triggered corpus-wide instead of one edited source at a time. Nobody
  has run this reconciliation at this scope before; there is no existing
  data point for how well `semantic_hash` matching holds up at 3,500+
  simultaneous span changes.
- **The 100-char threshold is a starting recommendation, not a validated
  one.** It trades off against the residual gap at code/equation-block
  boundaries (§1.2, case 2's standalone branch) — a real, if probably small,
  population of paragraphs that will keep being too short by design.
- **Rollback is not free once Tier 2 has actually run against real sources**
  (§4) — this is a one-way door in practice even though it is mechanically
  reversible, so the master plan needs a staged/flagged rollout, not a "ship
  and see."
- **This proposal does not solve the same problem Family B solves for
  free**: nothing here helps a query whose needed context spans a section
  boundary, crosses a code block, or needs a WHOLE document's framing — Tier
  2's merge only reaches as far as one prose region within one section.
  Family B's neighbour-expansion, if it's cheap and reversible as the brief
  claims, may cover more of the failure surface than this proposal does, for
  less cost. I am not in a position to make that trade-off call from inside
  the Family A brief alone — the cross-critique should weigh Tier 1 (which I
  believe is a clear win regardless of outcome) against Tier 2 vs. B on that
  basis, not treat A and B as mutually exclusive when Tier 1 sits genuinely
  outside that choice.
