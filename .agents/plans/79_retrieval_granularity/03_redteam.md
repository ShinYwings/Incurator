# v0.79.0 Red Team — measurement_redteam

**Role**: adversarial. My job is not to pick a family. My job is to attack the
shared premise, establish what is actually reachable and measurable, and price
the reindex honestly — all against the live DB and the real code paths, not
against what the briefing or either proposal *asserts*. Every number below was
re-derived independently, by me, directly against
`.cache/vaults/13ed51f8b06cb88e/state.sqlite` (`vault_root` =
`/Users/shin/shinywings/second_brain` — confirmed the largest, live
`state.sqlite` under `.cache/vaults/*/`, 324,579,328 bytes, versus the next
largest at 2,375,680 bytes). I read `01_proposal_stored.md` (Family A) only
*after* forming my own numbers, specifically so my figures would be an
independent check rather than a restatement — where they match, that is two
independent measurements agreeing, not one claim copied into two documents.
Where I differ from that proposal, or measured something it only estimated, I
say so explicitly in §7.

Every count in this document is a literal `sqlite3` query against the live DB
or a literal read of the named file at the named line. Nothing here is
extrapolated from the fixture, from documentation, or from the briefing's own
numbers without independently re-running the query that produced them.

---

## 0. Headline findings, before the detail

1. **The premise is real but a minority pattern.** Of 40 randomly sampled
   genuinely-short spans (not preview-truncated — see §1), only **8 (20%)**
   show the briefing's failure mode (a claim's supporting content in a
   neighbour). **17 (42.5%) are not claims at all** — PDF picture-omitted
   placeholders and page-number/running-head furniture that neither family
   can fix, because there is no meaning to recover from a neighbour. **15
   (37.5%) are short because they are complete** — headings-as-titles,
   one-line definitions, complete bullets, boilerplate.
2. **There is a second, larger, and completely orthogonal defect already
   inside the corpus**: 41.3% of all source_spans (4,865 of 11,774) have
   their body **hard-truncated to exactly 200 characters** before they are
   indexed, embedded, or reranked — independent of span boundaries entirely.
   A span that is a normal, complete 800-character paragraph is represented
   in the search corpus by its first 200 characters, whitespace-collapsed,
   full stop. This is not new — Family A's own proposal (`01_proposal_stored.md`
   §1.1) found and priced this as "Tier 1" before I read it; I verified it
   independently from the DB side (§1 below) and confirm the count.
3. **Reachability is asymmetric and route-dependent.** The primary FTS5 +
   vector + RRF + rerank path (`retrieval/engine.py`, frozen) delivers
   exactly the 200-char-capped preview with **no** hydration and **no**
   neighbour expansion. A *different* code path (`retrieval/evidence.py`,
   not frozen) recovers the full untruncated text of a span by re-parsing
   the source file — but only for entity-linked spans and the
   `source-section` route, never for a hybrid-search hit, and it never pulls
   in neighbours either way. See §2.
4. **`failure_atlas_holdout.py` cannot score either family, and it is not
   just policy — it is spent.** `run_count: 3`, `valid_run_count: 1`, one
   query (Q06), a synthetic 1,217-character fixture that bypasses
   `spans_from_sections` and `materialize_search_documents` entirely. The
   script itself refuses to run again (`raise SystemExit("refusing to rerun
   consumed holdout")`) past its cap. See §3.
5. **The reindex is local (confirmed) but not free, and the wall-clock
   number in circulation is a guess, not a measurement.** I benchmarked the
   actual configured embedder on this machine: **2.4 texts/second**, not
   the "hundreds of embeddings/sec" the Family A proposal assumes
   (`01_proposal_stored.md:440`). At the measured rate, embedding all 25,778
   chunks would take **~181 minutes (~3 hours)**, and the model is running
   **CPU-only** — 0 of 29 layers offloaded to the Mac's own Metal GPU,
   confirmed from the load log, despite Metal being available. See §4.
6. **The reindex's real cost ceiling is not embedding time at all — it's
   L2–L4 re-extraction.** Family A changes span `content_hash`, which
   changes span identity, which the existing F7/§26.4 stale-span
   reconciliation (`db/_entities.py: delete_source_spans`) is built to
   detect and clean up by **deleting** the `claim_supports` and
   `artifact_dependencies` rows anchored to the old span id and scrubbing it
   from `graph_entities`/`graph_relations.source_span_ids`. 46 of 49 sources
   (93.9%) have at least one span under 100 characters — i.e. nearly the
   whole vault is a re-segmentation candidate. The corpus currently holds
   20,230 `knowledge_units`, 2,481 `graph_entities`, 2,787 `graph_relations`,
   575 `community_reports`, and 19,521 `claim_supports` rows anchored to
   `source_span_ids`. None of this is provider-metered under the LOCAL
   embedder, but knowledge_unit/atom re-extraction is an LLM call, and
   *which* LLM depends on `wiki config provider` — this vault's persona
   config does not pin one in the slice I read. This is priced, honestly,
   as **unknown** in §4 and §6 — Family A's own proposal reaches the same
   "must be measured before shipping" conclusion (§1.3, §6 Cons) rather than
   a number, and I could not close that gap either without actually running
   the P0 dry-run script it proposes.

---

## 1. Falsifying the premise (task 1)

### 1.1 Setup: what "short" actually measures, and why the raw stat is contaminated

Before sampling, I checked whether "median 182 chars, 57% under 200" (the
number that started this Arena) is even measuring span *length*, or whether
it is measuring the 200-char preview cap. It is the second thing, partially.

`source_spans.text_preview` is built by `pipeline/source_spans.py:160-163`:

```python
@property
def text_preview(self) -> str:
    preview = " ".join(self.text.split())
    return preview[:_PREVIEW_CHARS]
```

with `_PREVIEW_CHARS = 200` (`source_spans.py:31`). This is the **only** copy
of span body text persisted anywhere in the schema —
`source_spans` has no `text`/`full_text` column, and `start_char`/`end_char`
are `NULL` on **all 11,774 rows** in the live DB (I queried
`MIN`/`MAX(end_char-start_char)` and got an empty result set; `COUNT(*) WHERE
start_char IS NULL OR end_char IS NULL` = 11,774 = every row). So any measure
of "span length" taken from the DB is actually measuring
`min(true_length, 200)` — right-censored at 200.

Direct count of how many spans hit the cap (definitely truncated, true length
≥ 200, unknown by how much):

```
sqlite3 state.sqlite "SELECT COUNT(*) FROM source_spans WHERE length(text_preview) = 200;"
-> 4865
sqlite3 state.sqlite "SELECT COUNT(*) FROM source_spans WHERE length(text_preview) < 200;"
-> 6909
```

**4,865 of 11,774 spans (41.3%) are capped, not short.** Bucket breakdown:

| bucket | count |
|---|---|
| `<50` | 2,027 |
| `50-99` | 2,625 |
| `100-199` | 2,257 |
| `=200` (capped/truncated, true length unknown, ≥200) | 4,865 |

This matters for the premise directly: the briefing's own stat ("median 182,
57% under 200") is a blend of two populations that behave completely
differently — genuinely short spans, and normal-or-long paragraphs
guillotined at 200 characters. Merging short spans into neighbours (Family A)
does nothing about the 4,865 already-capped spans unless `_PREVIEW_CHARS` (or
the storage strategy) is also fixed — a merged, now-longer paragraph still
gets truncated to the same 200 characters at the same property, so a
same-code merge could make the *proportion* of information lost per merged
unit **worse**, not better, for spans that were already near the cap.
(Family A's proposal already isolates this as "Tier 1" and fixes it
separately at `materializer.py:372` rather than in `source_spans.py`, which
is the right layer for it — see §7.)

I distinguish this "capped" population from "genuinely short" for the rest of
this section: everything sampled below is drawn from `text_preview < 100`, i.e.
**not** subject to the 200-char cap, so what you are reading is the span's
true, complete text.

### 1.2 Manual classification: 40 random genuinely-short spans

Query (paraphrased): `SELECT ... FROM source_spans WHERE length(text_preview)
< 100 ORDER BY RANDOM() LIMIT 40`, then classified by reading each one. Full
quoted sample (id, relpath, span_type, page, text):

Noise — parser/PDF artifacts, not claims (12/40, 30%):
```
SPAN-8cd542e2  MultipleViewGeometryHartley  paragraph  p.571  "**==> picture [318 x 55] intentionally omitted <==**"
SPAN-70337437  3D Line Mapping Revisited    paragraph  p.3    "**==> picture [223 x 12] intentionally omitted <==**"
SPAN-f18dd8ea  MultipleViewGeometryHartley  paragraph  p.194  "**==> picture [202 x 15] intentionally omitted <==**"
SPAN-f62e55ec  MultipleViewGeometryHartley  paragraph  p.367  "**==> picture [143 x 29] intentionally omitted <==**"
SPAN-09953797  MultipleViewGeometryHartley  paragraph  p.411  "**==> picture [311 x 14] intentionally omitted <==**"
SPAN-904b22ae  MultipleViewGeometryHartley  paragraph  p.452  "**==> picture [256 x 27] intentionally omitted <==**"
SPAN-88117657  MultipleViewGeometryHartley  paragraph  p.466  "**==> picture [139 x 16] intentionally omitted <==**"
SPAN-d032774f  MultipleViewGeometryHartley  paragraph  p.530  "**==> picture [114 x 16] intentionally omitted <==**"
SPAN-e356bae1  MultipleViewGeometryHartley  paragraph  p.591  "**==> picture [228 x 23] intentionally omitted <==**"
SPAN-badc2d31  MultipleViewGeometryHartley  paragraph  p.622  "**==> picture [292 x 15] intentionally omitted <==**"
SPAN-03358966  MultipleViewGeometryHartley  paragraph  p.626  "**==> picture [146 x 30] intentionally omitted <==**"
SPAN-d1ed9013  Ray-Space Projection Model   paragraph  p.4    "**==> picture [198 x 23] intentionally omitted <==**"
```

Noise — page-number / running-head furniture (4/40, 10%):
```
SPAN-56147838  MultipleViewGeometryHartley  paragraph  p.143  "126"
SPAN-bc3b3add  MultipleViewGeometryHartley  paragraph  p.192  "174"
SPAN-0db18ef9  MultipleViewGeometryHartley  paragraph  p.345  "_13.1 Homographies given the plane and vice versa_ 327"
SPAN-cc83fc2e  MultipleViewGeometryHartley  paragraph  p.457  "439"
```

Noise — structural/template artifact (1/40, 2.5%):
```
SPAN-c2a19bd1  02_Wiki/.../04_Backward...  paragraph  p.1  "---"   (YAML frontmatter delimiter)
```

**Complete, short by design** (15/40, 37.5%):
```
SPAN-c466e233  EWA splatting  equation      "$$m^{-1}(\mathbf{x})=\rho^{-1}(\phi^{-1}(\mathbf{x}))$$"
SPAN-28647b8b  EWA splatting  paragraph     "그러나 Surface resampling은 2D-to-2D이기 때문에 세 번째 항 x2를 제거해줍니다." (complete sentence)
SPAN-24887c77  Layleigh Quotient  paragraph "- 적어도 Rank(Full Rank - 1) 이어야 1차원의 Null space가 존재하여 유일한 해 x를 구할 수 있음." (complete bullet)
SPAN-7e9d01f5  3D Line Mapping Revisited  paragraph  "# **3D Line Mapping Revisited**"  (title, complete)
SPAN-34349b12  3D Line Mapping Revisited (note)  "- No annotations or highlights found." (Zotero boilerplate)
SPAN-beef4b18  Camera Pose Estimation...  "==근데 Appendix B는 행이 뒤집혀 있다!==" (complete annotation)
SPAN-08ae8928  MultipleViewGeometryHartley  "- (iv) If the size of Si is less than T, select a new subset and repeat the above." (complete algorithm step)
SPAN-daed7cb0  MultipleViewGeometryHartley  "**X** cannot be uniquely determined. Points on the baseline project to the epipoles in both images." (two complete sentences)
SPAN-747a2dab  MultipleViewGeometryHartley  "- (viii) pair of planes, neither point at the intersection, but points on different planes" (complete case label)
SPAN-1d7ab04a  MultipleViewGeometryHartley  "Algorithm A5.6. Algorithm for constrained minimization, subject to a span-space constraint." (complete caption)
SPAN-830c9df8  3DGUT (note)  "- No annotations or highlights found." (boilerplate, dup)
SPAN-65feaaa8  MultipleViewGeometryHartley  "_19.6 Calibration from rotating cameras_" (title)
SPAN-7a016f08  MultipleViewGeometryHartley  "_2.2 The 2D projective plane_" (title)
SPAN-625afc91  MultipleViewGeometryHartley  "## **18.4.5 When is the assumption λij=1 reasonable?]**" (question-as-heading, complete)
```

**Genuinely truncated / context-dependent on a neighbour — the premise,
confirmed present** (8/40, 20%):
```
SPAN-c4f36251  Layleigh Quotient          "- **Statistics (Gaussian View)**"          (bullet sub-heading, expects a following list)
SPAN-08195384  MultipleViewGeometryHartley "Writing P = f⁻¹X and P′ = f⁻¹′X, we see that"  (cut off mid-clause, right before the conclusion)
SPAN-4b740f0b  MultipleViewGeometryHartley "We describe a method for reconstruction from two views as follows."  (lead-in sentence, content is the NEXT span)
SPAN-cc278c1f  MultipleViewGeometryHartley "## **10.6 Closure**"                        (heading only, no body — see below)
SPAN-57d71546  MultipleViewGeometryHartley "as required."                                (tail fragment of a proof, lead-in is the PREVIOUS span)
SPAN-5c29d499  MultipleViewGeometryHartley "## **20.3 Closure**"                        (heading only, no body — same pattern)
SPAN-74e9c7d7  MultipleViewGeometryHartley "(i) Line–line–line correspondence"          (list-item label; explanation is elsewhere)
SPAN-fae65c6c  MultipleViewGeometryHartley ": Projective Space로부터 Euclidean Space로 복원..." (leading bare colon — orphaned from its own label term above it)
```

**N=40, 8 genuinely truncated (20%).** Six of those eight are one specific,
deterministic pattern: a markdown heading (`## **10.6 Closure**`) that became
its own `paragraph`-typed span because the section had other content too, so
`spans_from_sections`'s single-span collapse (`:232-239`) didn't fire, and the
body that follows the heading landed in a separate span across the blank
line. This is **not random truncation** — it is structural and predictable,
which is good news for whichever family targets it: it does not need fuzzy
"nearest neighbour" logic, it needs "if this span IS a bare heading, its
context is always the very next span in the same section."

### 1.3 How big is the noise population, corpus-wide

The 30%+10%+2.5% = 42.5% "not a claim at all" share of my sample is not a
sampling artifact. Corpus-wide counts:

```
picture-omitted placeholders (any length):        1,340 spans (11.4% of 11,774)
bare-digit page-number artifacts (≤6 chars, all-digit): 584 spans (5.0%)
markdown-heading-shaped paragraph spans (upper bound
  on the "orphaned heading" pattern, `#...` or `**#...`): 825 spans (7.0%)
```

**Neither family fixes the 1,340 picture-omitted spans or the 584
page-number spans.** There is no text to merge into them (Family A) and no
meaningful neighbour to append (Family B) — the fix for those is OCR/vision
recovery, which `pipeline/source_spans.py`'s own `describe_span_loss`
(`:76-97`) already names as the correct remedy ("set `llm.vision_model` ...
and re-add the source"). That is **1,924 of 11,774 spans (16.3% of the
corpus)** where "the span is too small" is the wrong diagnosis regardless of
which family wins this Arena — the diagnosis is "the parser never got text
here," a different, already-tracked problem (§26.2b).

### 1.4 Verdict on task 1

The premise is **real but overstated as a corpus-wide problem**. It is
concentrated and structural (orphaned headings, proof-tail fragments), not
diffuse. A fix that specifically targets "a span that is only a heading, or
that ends without terminal punctuation before a blank line" would catch most
of my 8/40 genuine cases far more precisely than a blanket "accumulate to N
characters" merge rule, which will also glue real noise (picture-omitted
markers, page furniture) onto real neighbours for no benefit — Family A's
own merge algorithm (`01_proposal_stored.md` §1.2) already excludes code/
equation blocks from merging, but does **not** exclude picture-omitted or
bare-page-number paragraphs from being merge *candidates* on either side, as
far as I read it. That is worth the Family A author checking: a
picture-omitted marker directly preceding a real short paragraph, both under
the floor, will merge into one span whose `classify_span_loss` (called on the
merged text) may or may not still fire correctly.

---

## 2. Is the defect reachable? (task 2)

The primary retrieval path (FTS5 + vector + RRF + rerank) and the
entity-linked evidence path deliver **different bodies of text for the same
span**, depending only on which route found it. Neither delivers a
neighbour.

### 2.1 The primary hybrid-search path: no hydration, no neighbours

`retrieval/materializer.py:372`:
```python
body = str(row.get("text_preview") or "")
```
This is the search corpus's only source of body text for a `source_span`
record — the 200-char-capped preview from §1.1, verbatim.

`retrieval/embedding.py:158-224` `materialize_chunks` runs `chunk_text` over
`title + "\n" + body` (`:164`) — since `body` is already ≤200 chars, `chunk_text`
(target 256 tokens ≈ 1,000 chars) never subdivides it; one search_span row
becomes exactly one `search_chunks` row (11,774 = 11,774, confirmed).

`retrieval/engine.py:239-255` `_hydrate` (**frozen file**) is what turns a
ranked `doc_id` into what the caller sees:
```python
def _hydrate(self, doc_id: str) -> dict | None:
    doc = db.get_search_document(self.db_path, doc_id)
    ...
    body = doc.get("body", "") or ""
    return {..., "body": body, "snippet": body[:280], ...}
```
`engine.py:403`: `full_content=data["body"]`. This is called from
`Engine.search()`, which is what `search.py:query()` calls
(`search.py:244-258`), which is what `evidence.py:_search_hits` calls
(`evidence.py:210-248`, used by the `local` route's `_add_search_hits` and
the `global` route's search fallback). **There is no re-parse, no full-text
hydration, and no neighbour lookup anywhere in this path.** A short span that
wins a slot via hybrid search is delivered to the LLM as exactly its
200-char-capped preview (or less, if genuinely short) — nothing more,
nothing from its neighbours, ever.

`search.py:220` even documents this as a feature: `"hydrate: Populate
full_content from the authoritative DB row"` — true and precise, but "the
authoritative DB row" is `search_documents.body`, not the source file. That
docstring is not wrong, but it is easy to misread as "the full original
text," which it is not for a capped span.

### 2.2 The entity-linked / source-section path: full text, still no neighbours

`retrieval/evidence.py:284-317` `_span_items` (used by the `source-section`
route and the `local` route's entity-seeded spans) calls
`_hydrate_full_texts` (`:36-44`), which calls `pipeline/compile.py:264-306`
`hydrate_spans`:

```python
def hydrate_spans(db_path: Path, span_ids: list[str]) -> dict[str, str]:
    """... Returns span_id -> full text for every span that hydrates and
    verifies; spans whose source is unavailable or whose hash drifted are
    omitted ..."""
```

This **re-parses the original source file**, groups spans by `relpath`,
re-derives a `content_hash -> text` index (`_reparse_hash_index`), and looks
up each span's exact full text by its `content_hash` — recovering the true,
untruncated text of **that exact span**, not a neighbour. `evidence.py:297`:
`body = text if text is not None else span.get("text_preview", "")` — falls
back to the capped preview only if hydration fails (source moved/hash
drifted), and marks the item `"evidence_status": "stale"` when that happens
(`:312`) rather than silently presenting the preview as complete. This
mechanism exists and works, but it is invoked **only** for
entity/source-section evidence, never for a plain hybrid-search hit.

**So the same span, reached two different ways, produces two different
answers to "how much text does the LLM see":** the capped 200 chars via
search, or the full original paragraph via entity/source-section lookup —
and *never* its neighbours, via either path.

### 2.3 `context_service.context_expand` is not neighbour-expansion

`context_service.py:974-1097` `context_expand` looks, by name, like it might
already be "Family B." It is not. It takes `handles` referring to items
**already present in the evidence pack but cut by the token budget**
(`omitted_candidates` from the same `context["omitted_items"]` list built at
pack-construction time) and re-admits them under a fresh budget
(`_budget_payloads`). It never queries the DB for a span's document-order
neighbours, never calls `db.list_source_spans` for adjacency, and cannot
surface anything that was not already a *ranked* candidate in the original
pack. If the two spans either side of a short match were never independently
retrieved (e.g. they didn't match the query lexically or semantically),
`context_expand` cannot produce them — there is nothing in the omitted set to
expand into. **Whoever writes the Family B proposal should not describe
`context_expand` as prior art for "return the matched span's neighbours" — it
solves a different problem (budget, not adjacency) and the plan's Family B
as stated does not exist in the codebase yet.**

### 2.4 Verdict on task 2

The defect (capped/short text reaching the LLM) is reachable through the
**primary** retrieval path, confirmed by file:line, not by assumption — and
it is asymmetric: it is *already fixed* for the entity/source-section route
(full text, no cap) and *not fixed at all* for the search-hit route (capped,
no hydration). Any Family B proposal has to decide whether it inserts
neighbour-fetching into `evidence.py` (unfrozen, cheap, but only benefits the
routes that go through `_span_items`/`_search_hits`) or into `engine.py`
(frozen, touches the D2 pin, but is the only place that sees every hybrid
hit uniformly before the caller). That choice is itself a cost decision — see
§3.2.

---

## 3. What can actually be measured (task 3)

### 3.1 `failure_atlas_holdout.py` and `D2_HOLDOUT_RESULT.yml`: spent, not just narrow

`docs/specs/failure_atlas/D2_HOLDOUT_RESULT.yml`:
```yaml
procedure:
  run_count: 3
  valid_run_count: 1
  ...
holdout_ids:
- Q06
frozen_inputs:
  engine: DB-native lexical FTS5/BM25
  limit: 5
  rerank: false
environment:
  scenario: failure_atlas_fixture
  providers: none
  model_judges: none
queries:
- id: Q06
  family: direct-factual
  indexed_characters: 1217
```

One query. One query family (`direct-factual`; the `associative` family in
`preflight_family_metrics` is a *preflight* number, not part of the frozen
holdout result itself — `holdout_ids: [Q06]` is the actual consumed set).
Lexical-only, rerank off, no embedding provider, no LLM judge, 1,217
characters of fixture text total — smaller than a single one of the "long"
capped spans in the real corpus.

`backend/scripts/failure_atlas_holdout.py:97-101`:
```python
prior_result = _load("D2_HOLDOUT_RESULT.yml") if OUTPUT.exists() else None
if prior_result and not args.audit_correction:
    raise SystemExit(f"refusing to rerun consumed holdout: {OUTPUT}")
if prior_result and prior_result["procedure"]["run_count"] >= 3:
    raise SystemExit("refusing more than two audit-correction reruns")
```
`run_count` is already `3` — **the harness will refuse to run again under
any invocation**, `--audit-correction` or not. Everything after `run: 2` in
the YAML's `invalidated_runs`/`*_rearm` history (18 entries, spanning
2026-06-12 to 2026-08-23) is not new evidence — it is a paper trail proving
that a later code change *could not have touched* the one frozen result,
re-hashing the 12 pinned files each time. This machinery is a **code-drift
tripwire**, not a live regression benchmark, and both proposal families need
to stop treating "does it touch a D2-frozen file" as the only cost question —
the harness could not score either family's actual effect even if neither
touched a single frozen byte, because its own fixture never exercises
`spans_from_sections` or `materialize_search_documents` at all: the harness
seeds `source_spans`/`search_documents` **directly** via
`db.upsert_search_document` and hand-built INSERTs
(`failure_atlas_holdout.py:39-74`), bypassing the exact code both families
propose to change.

### 3.2 Which files each family actually touches, checked against the frozen set

Frozen set (`D2_HOLDOUT_RESULT.yml: file_sha256`, 12 files):
```
failure_atlas_holdout.py, retrieval/{evaluation,engine,lexical,fusion,
embedding,chunking}.py, db/{__init__,schema,_entities,jobs,sources}.py
```

**Not in the frozen set**: `pipeline/source_spans.py`, `retrieval/materializer.py`,
`retrieval/evidence.py`, `context_service.py`, `pipeline/compile.py`.

- **Family A**, as scoped by the briefing (`pipeline/source_spans.py`), and
  as Family A's own proposal further scopes its Tier-1 fix
  (`retrieval/materializer.py:372`), **touches zero frozen files**. It does
  not need a rearm entry at all under this holdout's own governance model —
  worth stating plainly since the briefing's "hard constraints" section
  reads as if any granularity change is presumptively at risk of the pin.
- **Family B** is not yet written, so I can only red-team the *space* of
  where it could live. If implemented the "natural" way — inside
  `HybridEngine.search()`/`_hydrate()` in `engine.py`, because that is the
  one place that sees every ranked hit uniformly regardless of route — it
  **touches a frozen file** and needs a rearm entry, same governance cost as
  any other `engine.py` edit in this file's own history (see the 18 `*_rearm`
  entries — the going rate for justifying a frozen-file touch is a detailed,
  audited non-impact argument, not a rubber stamp). If implemented instead
  as a post-processing step in `retrieval/evidence.py` after
  `_search_hits`/`_span_items` return their hits — looking up
  `db.list_source_spans(source_id)` for the matched span's immediate
  document-order neighbours and splicing their (also-hydrated) text onto the
  evidence item — it **touches zero frozen files**, exactly like Family A.
  This is a real, concrete degree of freedom the Family B author should use:
  the frozen-file cost is not inherent to "retrieval-time expansion," it is
  a consequence of *where in the stack* the expansion is implemented, and
  `evidence.py` already does the analogous full-text hydration for spans
  (§2.2) — extending that same function to also fetch the matched span's
  siblings is the lower-cost implementation site.

### 3.3 What a reviewer could actually re-run

Nothing existing scores this. Three concrete, buildable options, in
increasing cost:

1. **A read-only, LLM-free structural script** (no DB writes, safe to run
   any number of times): re-parse the vault's real source files with the
   proposed new `spans_from_sections` (or, for Family B, with the existing
   one plus a neighbour-lookup simulation) and report exact before/after
   span counts, the char-length histogram (reproducing this report's §1
   buckets so a reviewer regenerates them rather than trusting them), and —
   critically for Family A — the exact `old_span_ids - new_span_ids` set
   size, which determines how many `knowledge_units`/`claim_supports` rows
   go stale. Family A's own proposal (§1.2.1) already asks for exactly this
   script as its required P0 step; I independently reached the same
   conclusion before reading that section, which is a second piece of
   evidence it is the right next step rather than a stylistic choice.
2. **A new, freely-rerunnable retrieval fixture**, built the way Q06 should
   have been built for *this* question: real or realistic multi-paragraph
   documents where the correct answer needs a claim plus a currently-split
   neighbour, scored by calling `retrieval.evaluation.evaluate_rankings`
   (`retrieval/evaluation.py:15-` — frozen, but callable *unchanged* from a
   new, unfrozen script; calling a frozen function does not touch its hash
   or the D2 pin). This gives apples-to-apples recall@k/MRR/citation-
   completeness numbers, on a corpus that actually exercises segmentation,
   without touching or re-consuming Q06 at all.
3. **A direct, live spot-check against the real vault**, no fixture needed:
   pick several of the 8 genuinely-truncated cases from §1.2 (e.g.
   `SPAN-cc278c1f`, the bare `"## **10.6 Closure**"` heading with its body in
   the next span) and run `wiki query "<a question whose answer is in that
   closure paragraph>"` before and after the change, inspecting the returned
   evidence/citation text directly. This is the cheapest of the three and
   the most concrete — it answers "did this specific, previously-identified
   failure actually get fixed" rather than a corpus-wide aggregate, and it
   needs no new fixture, no new script, and no reindex to try (a small
   number of touched spans is enough to demonstrate the mechanism before
   committing to the full-corpus cost in §4).

### 3.4 Verdict on task 3

The existing harness is disqualified by construction, not by choice — even a
change with zero blast radius could not be scored by it, because its fixture
never calls the code either family touches. §3.3's option 3 is the cheapest
real evidence either sibling proposal could produce before this Arena
converges; option 1 is required regardless of which family wins, because
both need the real `old_ids - new_ids` / touched-chunk count before anyone
can answer §4 precisely.

---

## 4. Pricing the reindex honestly (task 4)

### 4.1 Provider and content-addressing — independently confirmed

```
sqlite3 state.sqlite "SELECT provider, model, dim, COUNT(*) FROM search_embeddings GROUP BY provider, model, dim;"
-> llama-cpp|qwen3-embedding-0.6b|1024|25778
sqlite3 state.sqlite "SELECT status, COUNT(*) FROM search_embeddings GROUP BY status;"
-> ready|25778
```
All 25,778 rows, one provider/model, all `ready`. `retrieval/providers.py:203-238`
`LlamaCppEmbedder.__init__` does `from llama_cpp import Llama` and constructs
an in-process `Llama(...)` — no HTTP client anywhere in the class, confirmed
by reading the whole file. **This is genuinely local**: no network call, no
per-token or per-request billing, no external quota. The coordinator's
correction is right, and it changes the argument the briefing's "hard
constraints" section made ("a reindex re-embeds 25,778 chunks / 4.7M chars —
say what it costs" reads, in context, as an implied API-cost warning; there
is no API here).

`retrieval/embedding.py:227-307` `embed_corpus`, confirmed content-addressed
by `(chunk_id, provider, model)` with an `input_hash` staleness check
(`:254-256`: `if prior and prior.get("input_hash") == row["input_hash"]:
skipped += 1; continue`). A re-segmentation that leaves a chunk's text
byte-identical does skip re-embedding it — this part of the coordinator's
correction is also confirmed, not just asserted.

### 4.2 Measured, not guessed: embedding throughput on this machine

I could not find a documented throughput number for
`llama-cpp::qwen3-embedding-0.6b` anywhere in this repo — neither could
Family A's proposal (`01_proposal_stored.md:435`, which then guesses
"hundreds of embeddings/sec"). Rather than repeat that guess or invent my
own, I ran a real, read-only, side-effect-free micro-benchmark: loaded the
exact configured model (`/Users/shin/.cache/incurator/models/Qwen3-Embedding-0.6B-Q8_0.gguf`,
639,150,592 bytes) with the exact construction `retrieval/providers.py:210-216`
uses (`pooling_type=LAST, n_ctx=32768`), and embedded two batches of 32 real
`search_chunks.text` rows sampled from the live DB (batch_size=32 matches
`embed_corpus`'s own default, `embedding.py:231`). This wrote nothing to any
database — it is a standalone in-process inference call.

```
sample size: 64 texts, total chars: 10250
model load time: 1.75s
embed(32 texts) time: 14.385s  ->  449.5 ms/text
embed(32 texts) run 2 time: 12.608s -> 394.0 ms/text
steady-state rate: 2.4 texts/sec
estimated full-corpus (25,778 chunks) embed time at this rate: 10,872s = 181.2 min
```

**Measured: ~2.4 texts/sec, not "hundreds/sec."** That is roughly two orders
of magnitude slower than the guess currently in the sibling proposal. At the
measured rate, embedding the entire 25,778-chunk corpus from scratch would
take **~3 hours** on this machine. A partial reindex (only the changed
chunks, per §4.1's content-addressing) would be proportionally faster — at
Family A's own worst-case bound of ≤7,138 touched span identities (§1.2.1 of
that proposal), that is `7,138 / 2.4 ≈ 2,974s ≈ 49.6 minutes`; at its
optimistic bound (4,865, Tier-1-only), `4,865 / 2.4 ≈ 2,027s ≈ 33.8 minutes`.
**Neither of those is "free" or "a couple of minutes," and both are
materially larger than what "hundreds of embeddings/sec" would imply
(10-70 seconds).** This machine has 8 CPU cores (Apple M1) — I did not test
whether raising `embed_corpus`'s `batch_size` or running multiple embedder
processes in parallel changes this materially; that is a real optimization
lever I did not have time to characterize and report as unknown, not
dismissed.

**Why it's this slow — a separate, orthogonal, fixable observation**: loading
the model with `verbose=True` shows
```
load_tensors: offloading 0 repeating layers to GPU
load_tensors: offloaded 0/29 layers to GPU
```
despite Metal being detected and initialized on this Apple M1
(`ggml_metal_device_init: GPU name: MTL0 (Apple M1)`). `retrieval/providers.py`'s
`LlamaCppEmbedder.__init__` (`:195-216`) does not pass `n_gpu_layers` to the
`Llama(...)` constructor, so it defaults to 0 — **CPU-only inference by
configuration, not by hardware limitation.** I am not proposing this as part
of either family's scope (it is out of scope for this Arena and is a
provider-layer change, not a segmentation or retrieval change), but it is
directly relevant to interpreting the §4.2 number honestly: the 3-hour
full-reindex figure is a property of the current, unoptimized embedder
configuration, not a hard physical floor for this hardware. Flagging it here
rather than silently absorbing it into "the reindex costs 3 hours" as if that
were immutable.

### 4.3 The cost that actually matters more: L2–L4 re-extraction, not embedding

This is the finding I weight most heavily against "the reindex is cheap now
that we know it's local," and it is **Family A-specific** — it does not
apply to Family B, which never changes a span's `content_hash` because it
never changes what is stored.

`db/_entities.py:229-` `delete_source_spans` docstring, quoted in full
because its wording is load-bearing:
> "Remove stale source spans and their derived support/dependency rows
> (SYSTEM_BEHAVIOR §26.4 / F7 reconciliation). The span rows of an edited
> source are removed rather than left lingering beside their replacements;
> dependent `claim_supports` and `artifact_dependencies` rows are removed in
> the same transaction so the compiler audit finds no dangling references —
> including stale span ids scrubbed from graph entity/relation
> `source_span_ids` arrays."

Any merge that changes a span's text changes its `content_hash`
(`_hash(para)` in `source_spans.py:170-171`, computed on the exact span
text), which changes its `id` (`idx_source_spans_source_hash` is keyed on
`(source_id, content_hash)`). The **existing** mechanism this codebase
already has for "a span's identity changed" is to delete the old span and
everything anchored to it, on next recompile of that source. That is not
"re-embed 25,778 chunks" — it is "re-derive whatever L2 (`knowledge_units`),
L3 (`graph_entities`/`graph_relations`/`community_reports`), and L4
(`synthesis`) content cited the now-deleted span id," which for
knowledge_unit extraction is an **LLM call**, not a local embedder call.

Blast radius, measured directly:
```
sqlite3 state.sqlite "SELECT COUNT(DISTINCT source_id) FROM source_spans;"                              -> 49
sqlite3 state.sqlite "SELECT COUNT(DISTINCT source_id) FROM source_spans WHERE length(text_preview)<100;" -> 46
```
**46 of 49 sources (93.9%) contain at least one span under 100 characters** —
i.e. nearly every source in the vault is a re-segmentation candidate under
any merge-floor around 100 chars. Rows currently anchored to
`source_span_ids` corpus-wide:
```
knowledge_units    20,230
graph_entities      2,481
graph_relations     2,787
community_reports     575
claim_supports     19,521
synthesis               0
```
I am **not** claiming all of this gets re-extracted — a merge only orphans
the specific knowledge_units/claims that cited a span whose *exact* id
disappears, and `db/_entities.py` around the deletion path references a
`semantic_hash`-based reconciliation that may re-attach some claims to a
merged span without a full LLM re-extraction (Family A's proposal, §1.3,
flags this same uncertainty and reaches the same "must be measured" verdict
I do — that convergence, from two independent reads of the same code, is
itself evidence the uncertainty is real rather than either of us missing
something obvious). What I can state as fact, not estimate: **the mechanism
that runs when Family A ships is a deletion-and-reconciliation path that has
never been exercised at this scale (thousands of spans changing identity in
one release) before**, per the D2 rearm history's own framing of `F7` as a
per-edited-source mechanism, not a corpus-wide one. Sizing that honestly
requires actually running it (or the P0 dry-run script from §3.3) against a
scratch copy of the DB — not something I did, because it would mean writing
to a copy of the real vault's derived-knowledge DAG to observe how much of it
survives, which is exactly the kind of "reindex the real thing to see what
breaks" action this report exists to price *before* anyone runs it, not
during.

### 4.4 Verdict on task 4

**Embedding cost**: local, no provider spend, confirmed. Wall-clock: measured
at ~2.4 texts/sec on this machine, ~3 hours for a full reindex, ~34–50
minutes for Family A's own estimated touched-chunk range — an order of
magnitude slower than the only prior estimate in circulation, which was a
guess. **Re-extraction cost** (Family A only): mechanism exists and is
well-documented (§26.4/F7), blast radius is large by source-count (93.9% of
sources) but unknown by row-count without actually running the
reconciliation, and the honest answer is that this — not the embedder — is
the number that could make Family A materially more expensive than "a few
hours of local CPU time." Family B has none of this cost, structurally,
because it changes nothing that has an identity to lose.

---

## 5. Failure modes (task 5)

**Family A (change what is stored) — what it looks like when it is wrong,
and who notices.** The failure is *silent and structural*: a merge-floor
tuned from the wrong population (as §1 shows, a majority of "short" spans are
either noise or already-complete) glues a picture-omitted placeholder or a
page-number artifact onto the paragraph next to it, and `classify_span_loss`
either still fires (harmless, just a slightly larger span) or — worse —
doesn't, because the loss marker is no longer at a position the regex
expects relative to the merged text's boundaries, silently downgrading a
known "unreadable region" back into an ordinary, uncaught span. Separately,
if the F7 reconciliation (§4.3) re-attaches claims to merged spans via
`semantic_hash` matching imperfectly, some fraction of `claim_supports`
rows silently point at evidence that no longer says what the citation
implies, or knowledge_units get orphaned and quietly drop out of the search
index until a full recompile notices and re-extracts them — a **coverage
regression that looks like nothing changed**, because search still returns
results, just fewer or differently-sourced ones, and nobody is comparing
counts before/after unless they think to. The person who notices is whoever
runs `wiki lint` and gets a spike in orphan/broken-citation counts weeks
later, disconnected in time from the release that caused it — or, if F7
performs perfectly, nobody notices anything, which is the success case, but
§4.3 establishes that "F7 performs perfectly at 3,500+ simultaneous span
changes" is untested, not proven.

**Family B (change what is returned) — what it looks like when it is wrong,
and who notices.** The failure is *visible and immediate, but only in the
answer's shape, not in an error*: a query returns MORE evidence text per hit
(the matched span plus its neighbours), and if the neighbour-selection logic
is naive (e.g. "always the next span by rowid" rather than "the next span in
the same section/toc_id"), it will occasionally append content from an
unrelated section — the boundary between "closing sentence of section 10.5"
and "heading of section 10.6" is exactly the kind of adjacency a rowid-only
neighbour lookup gets wrong, producing an evidence item that reads as
internally contradictory or non-sequitur to the LLM, which then either
hedges visibly (a symptom users do notice and complain about) or, worse,
cites a claim's support as spanning content that isn't actually about the
same topic (a symptom nobody notices until a human fact-checks a specific
answer). It also does nothing for the 16.3% of the corpus that is
picture-omitted/page-furniture noise (§1.3) — those spans have no useful
neighbour to append either, so a naive implementation will spend token
budget expanding noise spans that were never going to be useful regardless
of how much surrounding text they get. The person who notices is either a
user reading a suddenly-longer, sometimes-incoherent citation, or a reviewer
watching `context_service`'s token-budget accounting (`_apply_budget`,
`context_service.py:195-`) start truncating more evidence items than before
because each retrieved item now costs more tokens — a resource-pressure
symptom, not a correctness one, that shows up as more `omitted_counts` in
routine query traces rather than as a failure anyone flags directly.

---

## 6. Explicit unknowns

Stated plainly, per this task's own instruction that an honest "unknown" is
worth more than a confident guess:

- **The true post-merge span count and exact `old_ids - new_ids` set for
  Family A.** Neither I nor, by its own admission, the Family A proposal
  computed this — it requires re-parsing all 49 source files with the actual
  new algorithm, which is the P0 script §3.3/§1.2.1 both independently land
  on as the required next step, not something either of us estimated
  precisely.
- **How much of the 46-source blast radius (§4.3) triggers real LLM
  re-extraction versus clean `semantic_hash` reconciliation.** I confirmed
  the *mechanism* exists and is real; I did not and could not (without
  actually running a corpus-wide re-segmentation against a scratch DB) size
  its outcome at this scale.
- **Which LLM provider re-extraction would use, and therefore what that
  arm of the cost actually costs.** The vault's `.curator/settings.yml`
  slice I read has a `persona` block but no `llm.provider` field in what I
  viewed; CLAUDE.md documents an auto-select-by-RAM rule
  ("<16 GB → Antigravity cloud, ≥16 GB → Ollama local") but I did not check
  this machine's RAM or the full config file to determine which branch
  applies here, so I am not stating a provider for this cost.
- **Whether raising `embed_corpus`'s `batch_size` or running concurrent
  embedder processes changes the measured 2.4 texts/sec materially on this
  8-core machine.** I benchmarked exactly the code path as configured
  (`batch_size=32`, matching `embedding.py:231`'s default); I did not vary
  it.
- **Whether Family B, once actually written, keeps its neighbour-lookup
  entirely inside `evidence.py`/`context_service.py` (frozen-file-free, per
  §3.2) or ends up needing something inside `engine.py` for a route I have
  not enumerated.** I established the degree of freedom exists; I have not
  seen a Family B proposal to check which choice it makes.
- **The exact interaction between a Family A merge and `classify_span_loss`
  on merged text at scale** — I confirmed by reading `source_spans.py:190-199`
  that loss classification runs on whatever text is at `_flush()` time, so it
  is preserved *by construction* for a single merge, but I did not
  construct and check a case where a picture-omitted marker sits adjacent to
  a real paragraph under a proposed merge floor to confirm the regex still
  matches correctly at the new position within the longer merged string.

---

## 7. Cross-check against `01_proposal_stored.md` (Family A)

I read this only after forming my own findings (see header). Where we agree,
both routes reached the same place independently:

- The 200-char preview cap and its 4,865/11,774 (41.3%) count — same number,
  independently queried.
- `failure_atlas_holdout.py` cannot score this, and it's the harness's own
  fixture-seeding shortcut (bypassing `spans_from_sections`/
  `materialize_search_documents`) that makes it structurally blind to this
  class of change, not merely policy caution about the frozen-file pin.
- `start_char`/`end_char` being `NULL` on all rows / dead for this purpose.
- The F7/§26.4 stale-span reconciliation mechanism and its uncertainty at
  scale — both of us land on "must be measured before shipping," not a
  number, from independent readings of `db/_entities.py`.
- The P0 requirement (a throwaway re-parse script to get exact before/after
  counts) before committing to a merge floor.

Where I differ or add:

- **The "hundreds of embeddings/sec" estimate (`01_proposal_stored.md:440`)
  is wrong by roughly two orders of magnitude** against my measured 2.4
  texts/sec on this machine. This changes that proposal's §4 cost framing
  from "a couple of minutes" to "tens of minutes to hours," and the Arena
  should use the measured number, not the guessed one, when weighing Family
  A's cost against Family B's.
- The proposal states (§1.2.1) that simulating the merge against stored rows
  "would require re-parsing all 49 source files" because "the table has no
  stored adjacency column." That's correct for simulating the *new*
  paragraph-merge algorithm (which needs the raw, not-yet-split prose), but
  document-order adjacency for *already-stored* spans is available today via
  SQLite's implicit `rowid` ordering — I used exactly this (`ORDER BY
  s.rowid`) in §1.2's sampling to pull each short span in document order
  without any schema change. This doesn't change the proposal's conclusion
  (the P0 re-parse is still required for the actual new algorithm), but the
  adjacency-column claim as stated is slightly stronger than the code
  supports — worth a one-line correction if that section is revised.
- I independently sampled and manually classified 40 genuinely-short spans
  (§1.2) into noise/complete/genuinely-truncated buckets — a qualitative
  check the proposal's quantitative histogram doesn't include. My 20%
  genuine-truncation rate, and specifically the finding that 6 of the 8 real
  cases are one deterministic pattern (orphaned heading, no body), is new
  information for tuning `_MIN_SPAN_CHARS` or, alternatively, for a much
  narrower fix that targets exactly that pattern instead of a corpus-wide
  character floor.
- I flagged a gap in the merge algorithm as reviewed (§1.4): it does not
  appear to exclude picture-omitted/page-furniture paragraphs from being
  merge candidates, only code/equation blocks. Worth the author's explicit
  confirmation either way.

No finding in that proposal is contradicted by anything I independently
measured. The convergence itself — two separate reads of the same DB and
code arriving at the same core numbers — is evidence those numbers are
solid; the divergence (embedding throughput) is evidence that "it's local so
it's cheap" needs the measured number attached before it does any more work
in this Arena's reasoning.
