# Retrieval Proposal: Family B — Span-Neighbour Inlining at Evidence Assembly
Date: 2026-09-02 | Agent Persona: retrieval_engineer

## 0. Recommendation, in one paragraph

Leave `source_spans` and `search_chunks` exactly as they are stored today. Add
one new pass, entirely inside `backend/src/curator/retrieval/evidence.py`
(NOT frozen), that runs once at the end of `build_evidence()`: for every
`EvidenceItem` that is a bare source-span (short by construction, per the
00_problem.md measurement — median 182 chars, 982 spans under 50 chars), look
up its immediate sibling spans inside the *same document section* and splice
their text around it, in reading order, before the item ever reaches
`context_service._apply_budget`. No file on the D2 frozen list is touched. No
`search_chunks` row changes, so no re-embedding, so the reindex the ROADMAP
entry assumed is not needed for this fix. The mechanism is capped so it cannot
silently consume the whole context-pack token budget, and it composes with the
policy-scope filter that already runs in `evidence.py` without any change to
that filter's code.

I am calling this **"span-neighbour inlining"**, deliberately not
"expansion" — see §1.7 for why that word is already taken twice in this
codebase for two different mechanisms, and reusing it a third time would be a
real hazard for whoever implements this.

---

## 1. Core Logic & Implementation

### 1.1 Where expansion belongs, and which files are frozen

I re-verified the frozen set directly rather than trusting the 00_problem.md
prose, because the prose names `chunking.py, engine.py, lexical.py, fusion.py,
embedding.py, evaluation.py` but the actual current pin recorded in
`docs/specs/failure_atlas/D2_HOLDOUT_RESULT.yml` (`evaluated_code.file_sha256`,
the single active mapping in that document — I loaded it with `yaml.safe_load`
rather than eyeballing the file, since the file is 671 lines of appended
rearm history and a grep can land on a stale historical block) is **wider**
than the brief states:

```
backend/scripts/failure_atlas_holdout.py
backend/src/curator/db/__init__.py
backend/src/curator/db/_entities.py
backend/src/curator/db/jobs.py
backend/src/curator/db/schema.py
backend/src/curator/db/sources.py
backend/src/curator/retrieval/chunking.py
backend/src/curator/retrieval/embedding.py
backend/src/curator/retrieval/engine.py
backend/src/curator/retrieval/evaluation.py
backend/src/curator/retrieval/fusion.py
backend/src/curator/retrieval/lexical.py
```

The whole `db/` package is pinned now (it was a single `db.py` when D2 first
ran; `db2_package_decomposition_rearm` split it and re-pinned all four
resulting files, and a later `db2_slice2_jobs_sources_rearm` added
`db/jobs.py` + `db/sources.py` when those were carved out too — both are
recorded, additive, "ranking-path unaffected" rearms already in the file, so
this is an established pattern in this repo, not a one-off exception). This
matters directly: it means I cannot add a new helper function to
`db/_entities.py` (e.g. a clean `db.list_span_neighbours(...)`) without
touching a frozen file and needing a rearm entry to justify it.

**Not frozen**, and specifically the files this proposal touches or reads:
`retrieval/evidence.py`, `retrieval/orchestrator.py`, `retrieval/router.py`,
`retrieval/models.py`, `retrieval/materializer.py`, `context_service.py`,
`search.py`, `pipeline/compile.py`, `pipeline/source_spans.py`.

Given that, the three candidate insertion points from the brief:

- **After fusion** (inside `fusion.rrf_fuse`, `retrieval/fusion.py:36`) —
  frozen. Rejected outright regardless of merit.
- **After rerank** (inside `HybridEngine.search`, `retrieval/engine.py:261`,
  or `HybridEngine._rerank`, `engine.py:172`) — frozen. Also architecturally
  wrong: the engine's job is to rank `search_documents` rows (which span
  five different `record_type`s per the 00_problem.md table — spans, atoms,
  relations, entities, reports); it has no business deciding that one
  particular `record_type` needs its text widened. That decision belongs
  where record-type-specific shaping already happens.
- **In evidence assembly** (`retrieval/evidence.py::build_evidence`,
  `evidence.py:417`) — not frozen, and this is already where record-type-
  specific shaping happens: `_span_items` (`evidence.py:284`) already
  re-hydrates full span text via `pipeline.compile.hydrate_spans`;
  `_report_items` (`evidence.py:350`) already reshapes community reports;
  `_apply_policy_scope` (`evidence.py:93`) already runs a per-item filter
  pass over `pack.items` before `build_evidence` returns. Adding one more
  per-item pass in the same place, before the same return, is the smallest
  possible extension of an existing, already-non-frozen contract.

**I recommend implementing entirely inside `evidence.py`**, as a new function
called from the end of `build_evidence()` (after the route-specific item
lists are assembled, before `_apply_policy_scope`, so an item whose neighbour
turns out to be policy-out-of-scope gets correctly dropped as a whole by the
scope filter that already exists — see §1.4). This keeps everything inside
the single `build_evidence()` call for a given query, which matters for a
constraint I found while reading `SEARCH_ENGINE_SCHEMA.md` §12.1 that
00_problem.md did not mention:

> "Plan F MUST NOT initiate a second `build_evidence` call to enrich the
> pack. Progressive expansion handles and client budgeting added by Plan F
> are stored alongside (not replacing) the Plan-A fields."

There is already a mechanism called "expansion" in this codebase
(`context_service.py:974`, `context_expand`) that pulls budget-*omitted*
items back into a pack on a client's explicit follow-up call, using
`expansion_handle` (`context_service.py:187`) — a client-driven, second-call,
whole-*item* operation. My proposal is server-side, single-call, sub-item
*text*-splicing. They do not conflict, but §12.1's literal text says
`pack.items` "MUST NOT be replaced" — a rule aimed at Plan F's client not
re-running retrieval, not obviously aimed at a same-call, in-place text
mutation performed once inside the one `build_evidence()` call before any
client ever sees the pack. I read this as compliant (nothing calls
`build_evidence` a second time; `pack.items` as a list is never swapped for
an unrelated set, only individual items' `.text`/`.source_span_ids` are
extended). **I am flagging this reading rather than asserting it silently** —
a stricter reading of "MUST NOT be replaced" as "no item's `.text` may
change after construction" would push this mechanism instead into
`context_service.context_fetch()`, between `build_evidence(...)`
(`context_service.py:777`) and `_apply_budget(...)` (`context_service.py:778`).
That alternative location is equally non-frozen and would work with almost
identical code — the only real difference is that `context_service.py` has
direct access to the caller's actual `limit_tokens`, so the budget cap in
§1.3 would be exact instead of assumed. Whoever synthesizes the Master Plan
should pick one of the two readings explicitly rather than let an
implementer guess.

### 1.2 What is a "neighbour": measured ordering, not assumed ordering

I queried the live DB directly rather than trusting the "ALL NULL" framing
in the brief at face value, because it is only half right:

```
$ sqlite3 state.sqlite "SELECT COUNT(*) total, SUM(start_char IS NULL),
  SUM(end_char IS NULL), SUM(page_number IS NULL), SUM(section_title IS NULL),
  SUM(toc_id IS NULL) FROM source_spans;"
11774|11774|11774|0|0|0
```

`start_char`/`end_char` are **100% NULL** (11,774/11,774) — confirmed, and
this is because `pipeline/source_spans.py::SpanRecord` never carries an
offset field at all (`source_spans.py:148-165`); `_block_spans`
(`source_spans.py:172`) computes exact regex match offsets for code/equation
blocks via `m.start()`/`m.end()` and even tracks a `cursor` through the
prose, but discards all of it before constructing `SpanRecord`. The columns
exist in the schema (`db/schema.py:391-392`) and are wired through
`upsert_source_span`'s signature (`db/_entities.py:122-123`) — nothing
downstream of `SpanRecord` is missing; the offsets are simply never computed.
This is a real, independently fixable gap, but fixing it is Family-A-adjacent
(it touches `pipeline/source_spans.py`, which the 00_problem.md brief lists
under Family A) and is **not required** for this proposal — see the "what
this does not solve" callout in §2.

`page_number`, `section_title`, `toc_id` are **0% NULL** — every span has
them. But they do not disambiguate order within a section: they are the
*grouping* key, not an *ordinal*. I measured the actual collision rate:

```sql
SELECT COUNT(*) FROM (
  SELECT source_id, page_number, section_title, toc_id
  FROM source_spans GROUP BY 1,2,3,4
);
-- 1176 distinct groups over 11774 spans
```

11,774 spans collapse into 1,176 distinct `(source_id, page_number,
section_title, toc_id)` groups — average group size ~10, with real outliers
up to **289 tied spans** in one Bibliography section of source 45. This is
mechanically guaranteed by `_block_spans` (`source_spans.py:172-186`): every
paragraph produced by splitting *one* section's text on blank lines
(`re.split(r"\n\s*\n", chunk)`, `source_spans.py:191`) carries the *same*
`page`, `title`, `toc_id` — they are the section's, passed down unchanged,
not the paragraph's own. For markdown sources specifically, `page_number` is
further collapsed to a single value for the *entire document* — I confirmed
this too:

```
source_id | file_type | span_count | distinct_pages
45        | pdf       | 8692       | 390
18        | md        | 205        | 1
12        | md        | 159        | 1
```

So "order spans without offsets" is not one question, it is two, and they
have different answers:

- **Which document/section does a span belong to** — answered reliably by
  `(source_id, page_number, section_title, toc_id)`. This is not ambiguous;
  it is exactly the section a human reading the source would recognize.
- **Which order do spans within that section appear in** — `source_spans`
  stores no explicit ordinal for this. The best available signal is
  SQLite's implicit `rowid`: `source_spans` is a normal rowid table (`id
  TEXT PRIMARY KEY` creates a unique index, not a `WITHOUT ROWID` table or an
  integer-alias rowid), and `store_source_spans` (`source_spans.py:242`)
  calls `upsert_source_span` once per span **in extraction order**
  (`source_spans.py:255-266`, confirmed the loop is a plain `for span in
  spans:` with no reordering). Under normal operation `rowid` therefore
  equals insertion order equals document order, for spans within one
  section. `list_source_spans` (`db/_entities.py:165-172`) already orders by
  `page_number IS NULL, page_number, start_char IS NULL, start_char` — since
  `start_char` is always NULL, that ORDER BY degrades to whatever tiebreak
  SQLite uses for fully-tied keys, which in practice is a table-scan in
  rowid order (not a documented SQL guarantee, but the query plan for a
  full scan with no other index hint does not need to reorder ties).

**The algorithm I propose**: resolve a matched span's neighbours by first
looking up its `(source_id, page_number, section_title, toc_id)` group, then
ordering that group by `rowid`, then taking a window of `±N` around the
matched span's position in that ordered list.

```sql
-- Step 1: resolve the grouping key for the matched span.
SELECT source_id, page_number, section_title, toc_id
FROM source_spans WHERE id = :span_id;

-- Step 2: fetch the full ordered sibling group (NULL-safe equality: use IS,
-- not =, since page_number/section_title/toc_id can each be NULL and `=
-- NULL` is never true in SQL).
SELECT id FROM source_spans
WHERE source_id IS :source_id AND page_number IS :page_number
  AND section_title IS :section_title AND toc_id IS :toc_id
ORDER BY rowid;
```

Then in Python: find the matched span's index in that ordered id list, take
`[idx - N : idx] + [idx + 1 : idx + N + 1]`, splitting into "before" and
"after" so the spliced text can be reassembled in reading order rather than
match-then-neighbours order.

**What happens when the ordering is ambiguous** — i.e. inside a tied group
where rowid is the *only* signal (a 90-span or 289-span group): I do not try
to resolve it further. The window is still taken from the rowid-ordered
list, so in the worst case a ±1 window picks a paragraph that is not
literally the true previous/next sentence but *is* guaranteed to be another
paragraph from the exact same section, on the exact same page, of the exact
same source. For the failure mode this Arena exists to fix — "a claim's
supporting sentence lands in a neighbouring span" (00_problem.md line 36-38)
— a same-section near-miss is a substantially better outcome than today's
zero neighbours, even when it is not the literally-adjacent sentence. I am
not claiming this is exact; I am claiming it is bounded and always
topically coherent, which is a testable, weaker, honest claim (see §1.6).

**Known fragility of the rowid fallback, stated plainly**: `rowid` is stable
across normal reads and re-inserts (idempotent upsert on `(source_id,
content_hash)`, `db/_entities.py:132-136`, means a re-parse that produces
identical text reuses the same row and rowid), but SQLite's `VACUUM` *can*
renumber rowids for a table with no declared `INTEGER PRIMARY KEY` alias.
I found no call to `VACUUM` anywhere in `wiki sync`, `wiki reindex`, or
`db/schema.py` today, so this is a latent risk, not a live one — but it
should be recorded as a constraint: **do not add a `VACUUM` step to this
table without re-deriving the neighbour ordering**, or the fallback silently
breaks. A more durable fix (backfilling `start_char`/`end_char`, which
`_block_spans` already computes and discards) is available and cheap
precisely because it does not touch `search_chunks`/embeddings — text
content is unchanged, only new metadata — but I am scoping it out of this
proposal (see §2) since the brief's Family split puts `pipeline/
source_spans.py` changes under Family A, and rowid ordering is sufficient to
ship Family B today without waiting on that decision.

### 1.3 Budget interaction: does expansion crowd out the number of hits?

**No, not the engine's ranked hit list** — that list is fixed by the frozen
`HybridEngine.search()` (`engine.py:261-463`) before evidence.py ever runs;
`limit=8` (the `build_evidence` default, `evidence.py:423`) hits come back
from `search.query()` and this proposal never changes their count, order, or
which `record_type`s were selected. **Yes, the token budget available to
other, lower-ranked evidence-pack items** — this is real and I am not
downplaying it. Concretely:

`_apply_budget` (`context_service.py:195-220`) uses `limit_tokens=16000`
(`context_service.py:21`, `_DEFAULT_BUDGET_LIMIT`), reserves `min(1000,
limit//4) = 1000` (`context_service.py:22`, `_DEFAULT_RESERVED_TOKENS`), so
`available = 15000`. Its cost function, `_estimate_tokens`
(`context_service.py:181-184`), computes `max(char_estimate=(len+3)//4,
byte_estimate=(len_utf8+2)//3)`; for ASCII text `byte_estimate ≈ len/3`
dominates, so **roughly `chars / 3` tokens** — deliberately conservative
(over-counts vs. a real ~4-char/token tokenizer, to leave headroom).

Using the 00_problem.md measured average — `source_span` avg 160 chars —
one neighbour ≈ 160/3 ≈ **53 tokens**. A `±1` window (previous + next) adds
at most 2 neighbours ≈ **106 tokens per widened item**, in the case both
neighbours exist and are not already claimed elsewhere (§1.4).

*Search-hit-only case* (the `local`/`explore`/`source-section` routes' capped
`_search_hits` items, `evidence.py:210-248`, `limit=8`): worst case all 8
hits are widenable `source_span` records → `8 × 106 = 848` extra tokens,
**~5.7% of the 15,000-token available budget**. Small.

*Entity-backed span case* (`_span_items`, `evidence.py:284-317`, called from
the `local`/`explore` routes with an **unbounded** count — up to `limit=5`
entities per seed term (`db.find_graph_entities(..., limit=5)`,
`evidence.py:268`) times up to 8 seed terms (`seed_terms(...,limit=8)`,
`evidence.py:191-207`), each entity potentially citing several spans): a
pathological pack with, say, 50 span items, all widened, is `50 × 106 =
5,300` extra tokens — **~35% of the available budget**, and in the *current*
`local`-route item ordering (`ent_items` then `_span_items` then
`_add_search_hits`, `evidence.py:520-524`) this would run *before*
`_apply_budget` reaches the search hits at all, potentially starving them.

This is the real crowding risk, and I am proposing a **hard valve**, not a
soft preference, to bound it: an absolute cap on how many neighbour-tokens
the whole widening pass may spend in one `build_evidence()` call, expressed
as a fraction of the same `available` budget context_service computes (a new
config key, `search.span_neighbour_budget_fraction`, default `0.20` — see
§1.8). Once the running neighbour-token counter would exceed `available ×
0.20 = 3,000` tokens, widening stops for every remaining item — those items
keep their original, un-widened text; nothing already spliced is undone.
With the 50-span pathological case above, the valve caps total neighbour
spend at 3,000 tokens (~28 of the 50 items get widened before the cap trips)
**instead of 5,300**, guaranteeing at least 80% of the available budget is
always still reachable by whatever the search hits and other items need.
This is a real, quantified, reviewable number — not "expansion is bounded"
asserted without arithmetic.

I additionally gate widening on the item's *own* text already being short —
only widen when `len(item.text) < 240` chars (a new config key,
`search.span_neighbour_max_anchor_chars`, default `240`, chosen just above
the corpus median of 182 so it catches the majority of the measured
fragments without touching items that are not part of the problem this
Arena exists to fix). This does not change the worst-case arithmetic above
(the pathological 50-span case assumed all 50 already qualify), but it means
a typical, non-pathological pack spends far less than the worst case,
because most packs mix long and short items.

### 1.4 Deduplication: an inlined neighbour that is also its own hit

This is a real failure mode I want to be explicit about rather than assume
away. A neighbour span `S4` of a matched span `S3` can independently be its
*own* separate hit — e.g. `S3` ranks 3rd on a lexical match, `S4` ranks 7th
on a different lexical or vector match, and both survive into `pack.items`
as distinct `EvidenceItem`s. Without a guard: `S4`'s text would appear
**twice** in the rendered evidence block (once inline inside `S3`'s widened
text, once as its own standalone item), and would be **double-charged**
against the token budget by `_apply_budget`, which has no idea `S4`'s text
is already present elsewhere.

**Fix**: a single `claimed: set[str]` threaded through one pass over
`pack.items`, seeded with every span id that already has its own standalone
item in the pack *before* any widening happens:

```python
claimed = {
    it.source_span_ids[0]
    for it in pack.items
    if len(it.source_span_ids) == 1
    and (it.kind == "source_span"
         or (it.kind == "search_hit" and it.record_type == "source_span"))
}
```

Then, iterating `pack.items` in existing list order (which already
approximates rank order — route-assembled entity/span items first, then
search hits, per `evidence.py:520-524`), for each eligible item: compute its
neighbour window, **drop any candidate neighbour id already in `claimed`**
(it has its own item elsewhere in the pack — do not duplicate it), splice
the survivors, and **add every spliced neighbour id to `claimed`** before
moving to the next item. This closes both duplication paths in one
mechanism: a neighbour that is *already* a standalone item is never inlined
anywhere (avoids inline-vs-standalone duplication), and a neighbour that
*two different* matched items would both want to inline (e.g. `S3` and `S5`
both border `S4`) is inlined into whichever item is processed first and
skipped for the second (avoids inline-vs-inline duplication). The trade-off
of "first item wins" is that it is order-dependent — acceptable here because
list order already reflects the pack's own priority ordering, so the
higher-priority item keeps the shared neighbour.

**Citation-list consequence**: when a neighbour is spliced into an item,
that neighbour's id is added to the item's `source_span_ids` (not just its
text) — `it.source_span_ids = sorted({*it.source_span_ids, *added_ids})`.
This matters for two things downstream that I checked rather than assumed:
`_apply_policy_scope` (`evidence.py:93-131`) drops an item entirely if *any*
backing span is out of a workspace's `curate.yml` source scope — so a
neighbour that pulls in out-of-scope content correctly kills the whole
(now-widened) item, with no extra code, because that filter already runs
after the widening pass and already treats `source_span_ids` as the
authority. And `pack.source_span_ids` (the citation-validity set threaded
into the LLM prompt's `valid_span_ids_block`, `orchestrator.py:110-124`)
already de-duplicates via `sorted(set(...))` at the pack level
(`evidence.py:127`, `context_service._selected_refs`,
`context_service.py:223-251`) — so a neighbour id appearing in two items'
`source_span_ids` lists (which cannot happen after the `claimed` guard
above, but would be harmless even if it did) collapses to one entry there
regardless.

### 1.5 Does this need a reindex? No — say plainly what that saves

**No.** This proposal changes zero rows in `search_chunks`, zero rows in
`search_embeddings`, and zero rows in `source_spans` or `knowledge_units`.
It reads spans that are already stored, via SQL executed directly from
`evidence.py` (through the existing, unmodified `db.connect()` — calling an
existing frozen function is not the same as editing one) and via the
existing `pipeline.compile.hydrate_spans` (`pipeline/compile.py:264`,
already used by `_span_items`, not frozen), which re-parses the *registered
source file* to recover exact span text by content-hash match — this
already happens today for every entity-backed span item; this proposal only
widens the *set* of span ids handed to the same, already-paid-for call
(neighbour ids get folded into the *same* `hydrate_spans(...)` batch call
that the anchor's own item already makes, since `hydrate_spans` groups by
`relpath` and re-parses each source file exactly once regardless of how many
of its spans are requested — `pipeline/compile.py:288-293` — so adding
neighbour ids from the *same* source costs one dict lookup, not one more
file re-parse).

What this saves, concretely: the 00_problem.md brief states a reindex would
re-embed **25,778 chunks / 4.7M chars** — that is the `search_chunks`
population across all five record types (source_span 11,774 + knowledge_unit
8,618 + graph_relation 2,540 + graph_entity 2,442 + community_report 404).
This proposal re-embeds **zero** of them. There is no provider call, no
`wiki reindex --embed` run, no window where search degrades to FTS5-only
while re-embedding is in flight, and no `VACUUM`/schema migration to roll
back if something goes wrong — rollback for this proposal is "revert the
`evidence.py`/`context_service.py`/`config.py` diff," a normal code revert,
not a data migration.

### 1.6 How is this measured — can `failure_atlas_holdout.py` score it?

**No, and I can say precisely why, not just assert it.** I read
`backend/scripts/failure_atlas_holdout.py` in full and its
`_seed_authoritative_corpus` (lines 39-74) plus the actual frozen
`docs/specs/failure_atlas/fixture_corpus.yml` it consumes. Every document in
that fixture is `record_type: knowledge_unit` with **exactly one**
`source_span_ids` entry each (`fixture_corpus.yml:17,24,31,...` — I checked
ten consecutive documents, all `[SPAN-fc0000NN]`, singular). The seeding code
inserts **one `source_spans` row per document**, with `text_preview` set to
the *entire* document body (`failure_atlas_holdout.py:56-61`). There is no
document in the frozen fixture with more than one span, so there is no
document with a *neighbour* — the fixture structurally cannot exercise a
neighbour-lookup, because neighbours do not exist in it. This is true
independent of any code change: even a hypothetical unfrozen copy of the
holdout script, run against this fixture, would find zero eligible
`source_span`-kind items to widen, because the fixture's spans are already
whole-document knowledge_unit citations, not the blank-line-split
`source_span` fragments `pipeline/source_spans.py` actually produces. This
also confirms, independently, that Family A's premise ("merge short spans
into neighbours") is equally untestable against this fixture, for the same
structural reason.

Separately, and just as decisively: `evaluate_rankings`
(`retrieval/evaluation.py`, frozen) is called by `failure_atlas_holdout.py`
directly on `EngineHit`-shaped dicts produced by `HybridEngine.search()`
(`failure_atlas_holdout.py:77-90`) — it never touches `evidence.py` at all.
This proposal's entire surface (`evidence.py`, `context_service.py`,
`models.py`, `config.py`) sits **outside the D2 call graph** by construction,
because those files were never part of it. Re-running the frozen holdout
after this change would (a) violate the repo's "refusing to rerun consumed
holdout" guard (`failure_atlas_holdout.py:98-99`) without an
`--audit-correction` justification, and (b) prove nothing about this
proposal even if run, since the code path it measures cannot reach the code
this proposal adds.

**What I propose instead — new, runnable, not one-shot**: this repo already
has exactly the right pattern for this, and I did not need to invent one.
`docs/specs/failure_atlas/FAILURE_ATLAS.md` defines a **Failure Atlas** case
methodology (`cases/F01.yml`…`F13.yml`, reproduced in
`backend/tests/test_failure_atlas_repro.py`) with a `baseline` test (asserts
today's defective behavior, passes by construction) and an `oracle` test
(`xfail(strict=True)`, asserts the desired contract, XPASSes — and thereby
fails the suite, forcing a deliberate status update — once the fix lands). I
found that **case F10** ("Searchable span evidence is capped at a
200-character preview", `docs/specs/failure_atlas/cases/F10.yml`) is the
closest existing case to this problem, `status: assigned` (not retired), and
its two tests (`test_f10_baseline_span_evidence_capped_at_preview` /
`test_f10_oracle_full_span_text_retrievable`,
`test_failure_atlas_repro.py:593-631`) exercise `build_evidence(...,
mode="source-section")` only — never `_search_hits`/the `local` route. I
traced why that gap exists and it is real: `materializer.py:371` sets
`search_documents.body = row.get("text_preview")` (capped at 200 chars,
`source_spans.py:_PREVIEW_CHARS = 200`) for **every** `record_type ==
"source_span"` row, unconditionally — `_span_items` (`evidence.py:284`)
works around this by re-hydrating full text itself, but `_search_hits`
(`evidence.py:210`) does not; it uses `hit.full_content` verbatim
(`evidence.py:229`), which traces straight back to that 200-char
`materializer.py:371` body. **This means every `source_span`-record search
hit reaching the `local`/`explore` routes today is silently capped at 200
characters, independent of this proposal, and untested.** I am reporting
this as a found, adjacent, pre-existing gap — not fixing it here, and not
folding it into this proposal's scope (see §2, "what this does not solve"):
fixing it is a `_search_hits`-only, one-function change with its own oracle
test, and CLAUDE.md's Surgical Changes rule says touch only what the task
requires.

For **this** proposal, I would add new deterministic (`execution_mode:
deterministic`, no LLM, no embedder needed) tests to
`test_failure_atlas_repro.py`, using the exact existing helper pattern
(`_store_section_spans`, `test_failure_atlas_repro.py:132-136`, which already
calls `l1.spans_from_sections` on a single multi-paragraph section — i.e.
already produces exactly the tied-group structure measured in §1.2):

```python
def test_span_neighbour_inlining_recovers_split_context(vault) -> None:
    paths = vault
    # Two paragraphs in ONE section => two source_spans sharing the same
    # (source_id, page_number, section_title, toc_id) group (source_spans.py
    # _block_spans), exactly the measured real-corpus shape.
    text = (
        "The vector confidence floor is 0.35.\n\n"
        "This floor gates whether Tier-2 query expansion runs as a recovery "
        "path, per SEARCH_ENGINE_SCHEMA search.expansion_vector_confidence_floor."
    )
    spans = _store_section_spans(paths, text, title="Recovery gating")
    assert len(spans) == 2
    pack = evidence_mod.build_evidence(
        paths,
        QueryRequest(question="what is the vector confidence floor",
                     mode="source-section", source_key="1"),
        "source-section",
    )
    item = next(it for it in pack.items if spans[0] in it.source_span_ids)
    # Oracle: the paragraph that explains what the number MEANS is reachable
    # from the item that matched the number itself.
    assert "Tier-2 query expansion" in item.text
    assert spans[1] in item.source_span_ids
```

plus a companion budget/dedup test asserting: (a) an item whose own text is
already over `span_neighbour_max_anchor_chars` is left untouched; (b) when a
neighbour is independently also a standalone hit, it is rendered exactly
once across `pack.items`, verified by counting substring occurrences of a
unique marker string across the joined `evidence_block()` output, not just
checking item count; (c) a synthetic pack with N widenable items and a small
`limit_tokens` proves the hard valve trips — the sum of `_estimate_tokens`
across all items' spliced-in neighbour text never exceeds `available ×
span_neighbour_budget_fraction`, checked by arithmetic, not just "did not
crash." All three are re-runnable by any reviewer with:

```bash
scripts/backend-check pytest backend/tests/test_failure_atlas_repro.py -k neighbour -v
```

no provider, no embedder, no testbed vault, deterministic every run — unlike
D2's one-shot, now-twice-invalidated holdout. I would also add a `wiki
testbed init <scenario>` smoke pass per CLAUDE.md's Testbed-Driven
Development mandate: run the same real question against the active testbed
scenario before/after, and read the rendered evidence block by hand to
confirm a previously-orphaned short span now arrives with its neighbour —
this is a qualitative check, explicitly labeled as such, not a substitute
for the pytest oracle above.

### 1.7 Naming: three different things are already called "expansion" here

I want this on the record because I nearly used the word myself and it would
have been a real hazard for the Master Plan reader:

1. `retrieval/expansion.py` (`expansion_mod.expand`, used by
   `engine.py:278,322`) — **query** expansion: turning one question into
   lexical/vector/HyDE variants before retrieval runs. Not frozen itself,
   but tightly coupled to the frozen engine.
2. `context_service.py:187,974` (`_expansion_handle`, `context_expand`) —
   **client-driven, second-call, whole-item** pull of budget-omitted items
   back into an already-served pack, gated by an opaque handle.
3. This proposal — **server-side, single-call, sub-item text splicing** of a
   matched span's document-order neighbours.

I am calling mine **"span-neighbour inlining"** throughout this document and
recommend the Master Plan keep that name (or another name that does not
contain the bare word "expansion") specifically so implementers, code
reviewers, and future search of this codebase do not conflate three
unrelated mechanisms under one term. This alone is a good reason to record
the naming decision explicitly rather than let it fall out implicitly from
whichever function name an implementer picks first.

### 1.8 Proposed config surface

Consistent with the existing `search:` config block (`config.py:242-264`,
documented in `SEARCH_ENGINE_SCHEMA.md` §1) — new keys, all additive, all
defaulted so existing configs need no migration:

```yaml
search:
  span_neighbour_inline: true            # feature flag; false = today's behavior
  span_neighbour_window: 1               # ±N sibling spans per matched item
  span_neighbour_max_anchor_chars: 240   # only widen items shorter than this
  span_neighbour_budget_fraction: 0.20   # hard valve: max share of the
                                          # available token budget neighbour
                                          # text may consume in one pack
```

`build_evidence()` gains one new optional parameter,
`limit_tokens: int | None = None` (defaulting to the same
`context_service._DEFAULT_BUDGET_LIMIT=16000` when unset, so existing test
call sites — I checked all nine production/test call sites via `grep -rn
"build_evidence("`, only `context_service.py:777` is the production caller —
keep working unchanged). `context_service.context_fetch` passes its own
`limit_tokens` through explicitly, so the valve in §1.3 is computed against
the *real* budget for that call, not an assumed default.

---

## 2. Pros & Cons

### Pros

- **Zero reindex.** No `search_chunks`/`search_embeddings` row changes, no
  provider calls, no downtime window, no rollback beyond a normal code
  revert. Directly answers the ROADMAP E2 entry's stated assumption
  ("Approved by the user on the understanding that fixing it re-embeds the
  corpus") by showing that assumption does not hold for this family.
- **Zero frozen-file edits**, verified against the *current*, wider pin set
  (§1.1), not the brief's summary of it — including the now-fully-pinned
  `db/` package, which the brief did not call out.
- **Reversible in isolation.** `span_neighbour_inline: false` is a complete,
  single-flag rollback with no data implications, unlike Family A where
  rollback means restoring a prior embedding generation.
- **Composes with existing machinery for free.** Policy-scope filtering
  (§1.4), citation-set de-duplication (§1.4), and the token-budget mechanism
  (§1.3) all already exist and already do the right thing once
  `source_span_ids`/`.text` are extended — none of them needed to change.
- **Found and reported one real, adjacent, pre-existing gap** (the
  `_search_hits` 200-char cap, §1.6) that F10's own oracle does not cover,
  without folding a fix for it into this change's scope.

### Cons / what this does NOT solve

- **Does not fix the stored data.** Every future direct read of
  `search_chunks`/`source_spans` (a different caller, a future export, a
  different retrieval path that does not go through `evidence.py`) still
  sees the same 56-char fragments. This proposal is a retrieval-time
  patch over a storage-time problem; if a new consumer of `source_spans`
  is added later that does not route through `build_evidence`, it inherits
  the original fragmentation with no warning.
- **Ordering is a documented best-effort proxy, not a schema-backed
  guarantee** (§1.2). It is correct at the section level and only
  approximate within a large tied group, and it depends on an SQLite
  implementation behavior (rowid-order tie resolution on a full scan) that
  is not part of the SQL standard, plus a live (if currently unexercised)
  fragility to a future `VACUUM`. A reviewer who wants a hard guarantee
  instead of a well-evidenced proxy should treat the `start_char`/`end_char`
  backfill mentioned in §1.2 as a prerequisite, not this proposal alone.
- **Budget crowding is bounded, not eliminated** (§1.3). In the pathological
  `local`-route case with many entity-backed span items, up to ~20% of the
  available context-pack budget can go to neighbour text before the valve
  trips, which is real budget that would otherwise have gone to other
  (possibly higher-relevance) items further down `pack.items`. The 20%
  figure is a proposed default, not a measured optimum — it has not been
  tuned against real query traffic.
- **Cannot be scored by the existing frozen evaluation harness at all**
  (§1.6) — favorable and unfavorable both: favorable because nothing this
  proposal does can accidentally perturb the D2 record; unfavorable because
  there is no existing, trusted, end-to-end retrieval-quality number this
  change can be checked against. The new tests in §1.6 check the mechanism
  in isolation (splicing happens, is bounded, de-dupes) — they do not
  measure whether answer quality on real questions actually improves. That
  would need a new held-out query set built the way `fixture_corpus.yml`/
  `qrels.yml` were, deliberately including multi-span documents this time —
  out of scope for this proposal, but worth naming as the real gap in
  Family B's evidence base if the user wants a quality number rather than a
  mechanism-correctness number.
- **Does not address community-report chunking**, the one record type the
  00_problem.md brief notes the *chunker* actually acts on (avg 811 chars).
  Out of scope by construction — this proposal is span-specific.
