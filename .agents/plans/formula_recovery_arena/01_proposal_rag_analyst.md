# RAG Pipeline Proposal: Close The Adjacency Gap — The `uncertain` Units ARE The Image-Only Loss, Displaced By One Span

Date: 2026-08-07 | Agent Persona: RAG / DAG Analyst

## 1. Core Logic & Implementation

### 1.0 Headline finding (new measurement, changes the briefing's framing)

The briefing's §2.2 table concludes there are **two disjoint formula-loss
populations**, and that Route A therefore requires "creating a unit from a span
that has no extractable claim." I re-measured the same DB
(`.cache/vaults/13ed51f8b06cb88e/state.sqlite`, 2026-08-07) and reproduced every
number in §2.2 exactly — 643 spans on source 37, 95 placeholder-only, 130
vault-wide, 480 `uncertain`, 171 on source 37, **0** units citing a placeholder
span. All confirmed.

Then I ran the test the briefing did not run: **document-order adjacency**
instead of exact citation.

```sql
-- rowid is insertion order = document order (store_source_spans is sequential,
-- and upsert reuses the original row on re-parse, so rowid is stable).
WITH ordered AS (
  SELECT rowid AS rn, id, source_id,
         (text_preview LIKE '%intentionally omitted%') AS is_ph
  FROM source_spans
),
neighbors AS (
  SELECT a.id AS span_id FROM ordered a JOIN ordered b
    ON b.source_id = a.source_id
   AND b.rn BETWEEN a.rn - 1 AND a.rn + 1
   AND b.is_ph = 1
  WHERE a.is_ph = 0
)
SELECT COUNT(DISTINCT ku.id) FROM knowledge_units ku
JOIN neighbors n ON ku.source_span_ids LIKE '%' || n.span_id || '%'
WHERE ku.formula_status = 'uncertain';
```

| population | count |
|---|---|
| `uncertain` units citing a span **immediately adjacent** to a placeholder span, vault-wide | **159 / 480 (33%)** |
| same, source 37 only | **99 / 171 (58%)** |

**The populations are not disjoint. They are the two halves of one split.** The
equation region and the sentence that explains it were one continuous piece of
the page; the span splitter cut them apart; Phase A extracted the claim from the
prose half and could not extract anything from the image half. `formula_status =
'uncertain'` is not a *different* defect from image-only loss — on source 37 it
is predominantly the *downstream signature* of it, mis-anchored by exactly one
span position.

This matters enormously for the Arena, because it means **Route A does not need
a fictional unit.** The owning claim already exists. What `recover_formula()` is
missing is not a `unit_id` — it is a correct `span_id`. Today the unit cites the
`where` clause; the loss lives in the placeholder span next door; the API
requires `span_id ∈ unit.source_span_ids` (`formula_recovery.py:110-112`) and
that requirement is the whole blockage. **The fix is a locator, not a fiction.**

---

### 1.1 Exact trace of a rasterized equation, today (file:line)

**Step 1 — the placeholder is emitted by the vendored library, not by Incurator.**

`.venv/lib/python3.10/site-packages/pymupdf4llm/helpers/document_layout.py:735`

```python
if btype in ("picture", "formula", "table-fallback"):
    if isinstance(box.image, str):   ... # write image file ref
    elif isinstance(box.image, bytes): ... # embed base64
    else:
        md_string += f"**==> picture [{clip.width} x {clip.height}] intentionally omitted <==**\n\n"
```

Note `btype` includes the layout model's own `"formula"` class. pymupdf4llm has
**already identified the region as a formula** and then discarded it, because
Incurator does not ask it to write image files or embed base64. The trailing
`"\n\n"` is load-bearing — see step 3.

**Step 2 — Incurator's PDF parser passes it through verbatim.**

`backend/src/curator/parsers/pdf.py:151-153` calls
`pymupdf4llm.to_markdown(str(path), page_chunks=True, use_ocr=False)`; line 181
does `normalize_text(_merge_raw_text_fallback(markdown_text, raw_text))`.

`_merge_raw_text_fallback` (pdf.py:111-131) is genuinely math-aware — it keeps
short lines that contain `=+{}()[]\` (the `mathish` set at pdf.py:118). But it
recovers only from `doc[page].get_text("text")`, the PDF **text layer**. A
rasterized equation has no text layer, so there is nothing to merge. The
placeholder survives untouched into `parsed.text` and into
`parsed.metadata["pdf_pages"][i]["text"]`.

**Step 3 — the splitter turns it into a standalone content-free `paragraph` span.**

`ingest_raw.py:1470-1475` → `_extract_structural_sections(parsed)` →
`source_spans.spans_from_sections(sections)`.

In `pipeline/source_spans.py:46-79`, `_block_spans` recognizes exactly two
special block types:

```python
_CODE_BLOCK     = re.compile(r"```.*?```", re.DOTALL)      # line 20
_EQUATION_BLOCK = re.compile(r"\$\$.*?\$\$", re.DOTALL)    # line 21
```

The placeholder has no `$$`, so it is **not** classified as an `equation` span.
It falls to `_emit_prose`, which splits on `re.split(r"\n\s*\n", chunk)`
(line 63) — and pymupdf4llm appended exactly `\n\n`. So the placeholder becomes
its own `paragraph` span with 51-53 characters of parser apology and zero
content.

Measured confirmation: **all 130 placeholder spans vault-wide are
`span_type='paragraph'`. Zero are `equation`, zero are `figure_caption`.**

**Step 4 — it lands verbatim in `source_spans.text_preview`.**

`SpanRecord.text_preview` (`source_spans.py:36-39`):

```python
@property
def text_preview(self) -> str:
    preview = " ".join(self.text.split())
    return preview[:_PREVIEW_CHARS]     # 200
```

No filtering. `store_source_spans` (line 108-129) passes it straight to
`db.upsert_source_span(..., text_preview=span.text_preview)`.

**Measured: `MIN(length(text_preview))=51, MAX=53` across all 130.** Every
placeholder span's `text_preview` is **the complete span text**, not a truncation.
This is a critical operational property — see §1.5: any retro-fix over the 130
existing spans needs no re-parse, no source file, no Zotero resolution, and no
LLM. The DB already holds 100% of the evidence.

**Step 5 — the L1 projection deletes the only human-visible trace.**

`ingest_raw.py:1094`, inside `_section_preview`:

```python
cleaned = re.sub(r"\*\*==>.*?intentionally omitted.*?<==\*\*", " ", cleaned)
```

`_section_preview` feeds both the `Source Guide` previews
(`_build_structural_source_guide`, ingest_raw.py:1174-1179) and the Atom
Candidates block (`_structural_atom_candidates`, ingest_raw.py:1061).

Measured: `second_brain/.curator/Collections/01_Contexts/CTX-f3a44022.md`
contains **0 occurrences** of `intentionally omitted` while the DB holds 95 for
that source. Source 37 also took the large-source branch
(`_should_inline_source_sections`, ingest_raw.py:1124-1128 → False), so every
`Source Sections` body is replaced by "Raw source text is not duplicated in this
L1 page because the source is large" + a `_section_preview` — placeholder
stripped again.

**`ingest_raw.py:1094` is the single line that makes the loss silent in the
human-facing L1 page.** The DB records the loss; the projection erases it. The
briefing's §2.4 ("nothing tells the user any of this") has a precise address.

**Step 6 — Phase A sees the placeholder and correctly produces nothing.**

`pipeline/compile.py:327-342` is Phase A's real entry (`ingest_llm.py:520-521`
labels it): `spans_from_sections` → `store_source_spans` → `span_inputs` →
`knowledge_units.extract_knowledge_units`.

`pipeline/knowledge_units.py:49-54`:

```python
def _spans_block(spans: list[dict]) -> str:
    lines = []
    for s in spans:
        title = s.get("section_title") or ""
        lines.append(f'{s["id"]} [{title}]: {s["text"]}')
    return "\n\n".join(lines)
```

The placeholder span **is** presented to the extractor, in-band, as
`SPAN-34ee94f2 [3.1.3 Point-guided Line Triangulation]: **==> picture [221 x 18]
intentionally omitted <==**`. The contract
(`prompting/families/knowledge_units.py`, SYSTEM_TEMPLATE) says:

> - Every unit MUST cite at least one source_span_id from the allowed list.
> - No span, no unit. Never invent a span id that is not in the allowed list.

There is no fact in 51 characters of parser apology. The model emits no unit for
it. **Measured: 0 units cite any placeholder span, vault-wide.** This is correct
behavior, not a bug. The bug is upstream (the region was discarded) and
downstream (nobody reports it).

---

### 1.2 Why the asymmetry exists, in pipeline terms — with the real rows

Page 4 of source 37, in document order (`ORDER BY rowid`):

```
SPAN-4d629b1c  paragraph  "**M1. Multiple Points** . For each matched line segment we generate…"
SPAN-34ee94f2  paragraph  "**==> picture [221 x 18] intentionally omitted <==**"      ← equation
SPAN-b3135200  paragraph  "Due to the low-dimensionality of the problem, a closed-form…"
SPAN-4e3a5b8b  paragraph  "**==> picture [198 x 13] intentionally omitted <==**"      ← equation
SPAN-16bedfdc  paragraph  "where _**v** 2_ R[3] is the VP. Using the constraint, we then solve for _**λ**_…"
...
SPAN-03d42a77  paragraph  "**==> picture [182 x 24] intentionally omitted <==**"      ← equation
SPAN-da0316a9  paragraph  "where _NI_ is the set of neighboring images of _I_ . The best 3D line candidate…"
```

The `where …` spans are **dangling definition clauses**. Their antecedent — the
equation being defined — is the placeholder span immediately above them.

Now the units that cite `SPAN-16bedfdc` / `SPAN-da0316a9` (measured):

| unit | formula_status | support_status | statement (truncated) |
|---|---|---|---|
| `KNU-7dd60672` | **uncertain** | unchecked | "The overall consistency score for a candidate 3D line `$L_k^j$` is computed by summing the maximum normalized pairwise distance score obtained from each neighboring image `$J \in N_I$`" |
| `KNU-18b2ad87` | **uncertain** | unchecked | "The overall consistency score `$sc(L_i)$` … summing the maximum pairwise line score across proposals from each neighboring image `$J \in N_I$`" |
| `KNU-140b28cc` | **uncertain** | unchecked | "The best 3D line candidate … selected as `$L = \text{argmax}_{L_i} sc(L_i)$` …" |
| `KNU-07f4771e` | **uncertain** | unchecked | "Method M3 solves for ray depths `$\lambda = (\lambda_1,\lambda_2)$` by minimizing residual errors … using the linear constraint from the vanishing point `$v \in …$`" |
| `KNU-df06be8b` | **uncertain** | unchecked | "The best 3D line candidate `$L^*$` … maximizes the consistency score `$sc(L_i)$`" |

The causal chain is now fully traceable:

1. The extractor is told (SYSTEM_TEMPLATE): *"Preserve equations exactly (with
   `$$...$$` / `$...$` delimiters) in equation units."* It reads the `where`
   clause, infers the equation's shape from its variable definitions, and writes
   `$...$` LaTeX into the statement.
2. It cites the only span it legitimately can: the prose span.
3. `validate_claim_support` (`pipeline/claim_support.py:379-384`) then runs:

```python
elif has_formula and not formula_ok:
    # Right topic, but the formula is absent/altered in the span: route to
    # P5 selective recovery rather than hard-fail (could be parse loss).
    verdict = "uncertain"
    reason = "central formula not structurally present in the cited span (possible parse loss or alteration)"
    formula_status = "uncertain"
```

The claim carries a formula; the *cited* span does not; verdict `uncertain`. The
comment on line 380-381 literally says "route to P5 selective recovery … could
be parse loss." **It was right. The parse loss is one span away, and nothing
walks that one step.**

**Therefore the fix must live in three distinct places, and conflating them is
what produced two no-op hotfixes:**

| concern | correct layer | why not elsewhere |
|---|---|---|
| **Detecting and recording that a region was image-only** | **L1 extraction** (`source_spans.spans_from_sections`) — deterministic, no LLM, no provider | Only L1 sees the parser output. By L2 the information is a 51-char string nobody parses. Detecting it at query time is guessing. |
| **Anchoring the loss to the claim it broke** | **L2, post-validation** (a new locator step after `validate_claim_support`) | The claim does not exist until Phase A runs. The span does not know which claim it broke. Only the pair (uncertain unit, adjacent typed loss span) identifies the anchor, and only after both exist. |
| **Recovering the content** | either **upstream §26.2a** (`vision_model`, pre-L1) or **downstream §26.2** (`recover_formula`, post-anchor) | Not at retrieval time. A query-time VLM call has no `page_hash` lifecycle, no acceptance gate, and would re-run per query. |

Route C (surface the loss) is **not a third option** — it is the L1 row of that
table, which A and B both require. It ships first because it is the enabling
primitive, not because it is a consolation prize.

---

### 1.3 How recovered content re-enters the DAG — and the gap that makes recovery a no-op today

This is the question the briefing did not ask and the one that determines whether
any recovery route produces a user-visible result.

**Today, recovered LaTeX re-enters at exactly ONE place**, and it is not a place
a reader can see. `recover_formula` (`pipeline/formula_recovery.py:182-208`)
builds `augmented_span_texts` in memory and passes it to
`validate_claim_support`:

```python
augmented_span_texts[cited_id] = f"{augmented_span_texts[cited_id]}\n${rec['latex']}$"
verdict = validate_claim_support(db_path, unit_id, span_texts=augmented_span_texts)
```

That is a **transient, in-process** augmentation. On success it writes a
`claim_supports` row and sets `formula_status='linked_evidence'`
(formula_recovery.py:219-228). The LaTeX itself is persisted only in
`source_spans.metadata.formula_recovery[]`, per SCHEMA §20.4.

Now trace every downstream reader of span content:

| consumer | file:line | reads `metadata.formula_recovery`? |
|---|---|---|
| Search index body for a span doc | `retrieval/materializer.py:372` — `body = str(row.get("text_preview") or "")` | **No** |
| Chunking / embedding | `retrieval/embedding.py` over `search_documents.body` | **No** (inherits the above) |
| Evidence-pack full text | `retrieval/evidence.py:33-41` → `pipeline/compile.hydrate_spans` | **No** — `hydrate_span_text` (compile.py:200-226) *re-parses the source file* and returns the text whose `content_hash` matches. For a placeholder span that is the placeholder string. |
| L1 CTX page | `ingest_raw.py:1094` | **No** — actively strips it |
| Claim re-validation | `formula_recovery.py:182-208` | **Yes** (in-memory only) |

**Conclusion: even a perfectly executed §26.2 recovery, today, flips two status
columns and shows the user nothing.** The LaTeX never reaches the FTS index, the
vector index, the evidence pack, or the L1 page. Any plan that stops at "call
`recover_formula()`" is the **third** no-op, for a reason the briefing has not
yet named.

**The re-entry mechanism I propose — additive, never mutating raw text
(constraint 2 / SCHEMA §20.4 "raw parser/source span text is immutable"):**

- **NOT a new span.** A new span would need a new `content_hash`, would not
  correspond to any region of the re-parsed source, and would therefore fail
  `hydrate_span_text`'s hash verification forever (compile.py:221-225). It would
  also break `reconcile_source`'s `existing - current` stale-span deletion
  (claim_support.py:713-715), which would delete it on every subsequent compile.
  **Rejected.**
- **NOT a new atom.** There is no new claim. The claim already exists and is
  `uncertain`. Minting a unit whose statement is a bare equation duplicates the
  owning claim's formula and creates a reconciliation candidate collision on
  `semantic_hash`. This is the "fiction invented to satisfy an API" the briefing
  warns about, and it is unnecessary given §1.0. **Rejected.**
- **YES: amend the existing unit's citation, then attach as `linked_evidence`.**
  Two additive writes, no new rows in `source_spans` or `knowledge_units`:
  1. `knowledge_units.source_span_ids` gains the adjacent loss span, with
     `support_roles[span] = 'formula'`.
  2. `recover_formula(unit_id=<existing uncertain unit>, span_id=<loss span>, …)`
     then works unmodified, writing `metadata.formula_recovery` and, on
     acceptance, a `support_role='formula'` verified row +
     `formula_status='linked_evidence'`.
- **PLUS one new read, which is the missing link**: `materializer.py` must
  append `reviewed` recovery LaTeX to a span doc's `body`, and
  `compile.hydrate_span_text` must append it to hydrated evidence text. Without
  this the recovery is invisible (table above).

**Safety proof that step 1 cannot demote a unit.** Adding a span to
`source_span_ids` re-runs `validate_claim_support`, so the verdict must be
monotone non-worsening. Inspect claim_support.py:334-354:

- `max_cov = max(max_cov, cov)` (line 336) — a max over spans. Adding a span can
  only raise it. The `failed` branches at lines 371 and 357 key on `max_cov <
  _SUPPORT_FAIL` and `not spans`; neither can newly trigger.
- `span_formulas.update(...)` (line 338) — a set union. `formula_ok` (line
  351-354) is `all(... in union ...)`; the union only grows, so `formula_ok`
  is monotone non-decreasing.
- `best_id` can only change to the new span if its score `(0, 0.0)` strictly
  exceeds the incumbent (line 348), which is impossible for a non-empty
  incumbent.

**Verdict transitions are therefore one-way: `uncertain → uncertain` before
recovery, `uncertain → verified` only after accepted recovered evidence.** No
unit can be pushed to `failed` — which matters because `failed` is the one
status `materializer.py:273` still excludes from the index. This is the single
most important safety property of the whole proposal and it is provable from the
existing code without a schema change.

**What re-runs, and what it costs.**

| stage | re-runs? | cost on the measured vault |
|---|---|---|
| L1 parse | **No** for the retro-fix. `text_preview` is the complete text for all 130 spans (51-53 chars, measured), so typing/classification is pure SQL over the DB. | 0 LLM calls, 0 file reads, 0 Zotero resolutions |
| Phase A (`extract_knowledge_units`) | **No.** Citation amendment and `recover_formula` are `UPDATE`s on existing units. No re-extraction. | 0 LLM calls |
| Recovery VLM | **Yes**, selectively. Measured surface: **25 distinct `(source_id, page_number)` pairs vault-wide**; source 37 contributes **17 of its 27 pages**. Only 4 sources have any placeholder spans at all (37: 95, 34: 15, 35: 11, 32: 9). | ≤ 25 page renders + crops. Cached by `(page_hash, model)` via `db.vision_cache_get/put` (ingest_raw.py:1591, 1621). |
| `validate_claim_support` re-run | Yes, per amended unit — **deterministic, no provider** (claim_support.py:290). | ~159 units vault-wide, milliseconds |
| `materialize_search_documents` | Yes, once. `dependency_parts` includes `source_span_ids` (materializer.py:406), so amended units re-materialize automatically. | one full pass, ~5,445 docs, no LLM |
| Embeddings | Only for changed chunks — `input_hash` gate at materializer.py:187-198 | ~a few hundred re-embeds |
| **Phase B (concepts) / Phase C (synthesis)** | **NO — and this is a deliberate design constraint of my proposal.** | 0 |

The Phase B/C answer deserves its own justification, because "does it re-run
B and C" is where the cost explodes. Measured:

```
reports_citing_placeholder    = 0
synthesis_citing_placeholder  = 0
entities_citing_placeholder   = 0
relations_citing_placeholder  = 0
```

No L3 or L4 artifact cites a placeholder span, so **no L3/L4 artifact is
invalidated by amending a span's metadata or a unit's citation list.** The
`materializer` liveness filters at lines 344-365 gate reports and syntheses on
`source_span_ids ⊆ live_span_ids` — and since we add spans rather than delete
them, `live_span_ids` only grows. **Nothing is evicted.** Concept and synthesis
regeneration is a follow-up milestone, explicitly out of scope; the recovered
formula reaches the reader through the L2 atom and the L1 span doc, which is
enough for the measured question.

**Contrast: what the §26.2a `vision_model` route costs.** `_apply_vlm_pdf_extraction`
(ingest_raw.py:1623-1634) does `page["text"] = chosen; parsed.text =
"\n\n".join(new_texts)`. Every page's text changes → every span's
`content_hash` changes → `spans_from_sections` yields an entirely new span set →
`reconcile_source` (claim_support.py:672, 705-708) computes `spans_unchanged =
all(sid in current for sid in cited)` = False for **every** prior unit → **every
unit is retired**, and line 713-715 deletes every old span. Source 37 alone loses
all 171+ units and pays a full Phase A LLM pass; Phase B community detection and
Phase C synthesis then genuinely do have to rebuild, because their upstream
entities/relations are rebuilt from the new units. That is the honest price of
Route B on already-ingested sources, and the briefing's constraint 5 demands it
be stated. It is roughly two orders of magnitude more expensive than the
adjacency route for the same 4 sources.

---

### 1.4 What retrieval needs for "수식 26 설명좀" to be answerable

Walk the actual query path.

1. `retrieval/engine.py:261 search()` → lexical (`search_documents_fts`,
   `search_documents_fts_tri`) + vector (`search_chunks`/`search_embeddings`) →
   RRF fusion → `_rerank` → `_demote_unsupported` (engine.py:208-237).
2. `_hydrate` (engine.py:239-255) returns `body` from `search_documents`.
3. `retrieval/evidence.py:33-41` hydrates full span text via
   `pipeline.compile.hydrate_spans`.
4. `retrieval/orchestrator.py:106-119` constrains the answer prompt to
   `context_pack["source_span_ids"]`.

**Fact 1: the span layer IS indexed, with no admission gate.**
`materializer.py:221-228` selects **every** `source_span` row — no
`support_status` analog, no filter. `materializer.py:369-393` builds one doc per
span with `body = text_preview`. Measured: `record_type='source_span'` →
**2,363 of 5,445 docs**, and **130 of them have a body that is nothing but the
placeholder**, all 130 chunked and all 130 embedded.

So the index is not missing a gate — **the index is faithfully serving 130
documents whose entire content is a parser apology.** They occupy FTS rows,
chunk rows, and embedding rows, and they can win RRF slots on a nearest-neighbor
query about equations (they are lexically about "picture", semantically about
nothing). This is measurable index pollution, not a hypothetical.

**Fact 2: v0.47.0's `support_status <> 'failed'` change is the right precedent
and it already covers the L2 half.** The comment block at materializer.py:229-265
is explicit that support became a *ranking and labelling* signal
(`_demote_unsupported`, engine.py:208) rather than an admission gate. The
`uncertain` units of §1.2 are therefore **already reachable** by the query — they
are `unchecked`, not `failed`. The user's question does not fail because the
claims are hidden. It fails because the claims describe the equation and do not
contain it, and their cited evidence is a `where` clause.

**Fact 3: the query key itself was rasterized.** Measured on source 37:

```
spans containing "(1)":1   "(2)":9   "(3)":3   "(4)":4   "(5)":3   "(20)":1
spans containing "(24)":0  "(25)":0  "(26)":0
```

Equation *references* survive in prose ("minimizing the two residuals of (2)").
Equation *numbers* live inside the images, because the `\tag{26}` is typeset
inside the rasterized region. **So "equation 26" has no lexical anchor anywhere
in the corpus** — which is precisely why v0.48.1's widened page search for the
label was a no-op, and why v0.48.4 correctly reports it cannot retrieve it.

**Therefore, what retrieval actually requires, in order:**

- **A span-level lookup is NOT enough.** There is no span to look up: `wiki
  plugin pdf search --source-id 37 --query "(26)"` → 0 hits is not a search bug,
  it is an absent-document result, correctly reported.
- **The FTS index is the binding requirement.** The user typed a label. Labels
  are matched lexically. Recovered LaTeX must land in
  `search_documents.body` (and hence in `search_documents_fts` /
  `search_documents_fts_tri`, materializer.py:166-184) or it is unreachable by
  the query as phrased. This is the change identified in §1.3: `body` must become
  `text_preview` + reviewed recovery LaTeX.
- **The chunk vector index follows for free** — `embedding.materialize_chunks`
  reads the same `body` (materializer.py:519), so one change fixes both layers.
- **Additionally, an equation-label index is needed**, because LaTeX alone may
  not carry "(26)". A recovered candidate's `locator` (SCHEMA §20.4:
  `{"source_id": 3, "page": 7, "region": [...]}`) plus any `\tag{...}`/trailing
  `(N)` the VLM transcribes should be surfaced in the span doc's **title**
  (materializer.py:371 currently `section_title or relpath`) as e.g.
  `"3.1.3 Point-guided Line Triangulation — equation (26), p.4"`. The title is
  indexed as a separate FTS column, so this makes the label directly matchable.
- **`_demote_unsupported` needs no change.** A span doc has no
  `support_status` in provenance (materializer.py:387-392), so factor 1.0
  applies; an unrecovered image-only span should instead be *labelled*, per the
  §1.5 P0 change, not demoted — otherwise the honest "this is an image on p.4"
  answer becomes unrankable too.

**Definition of done, measurable on source 37, in two tiers:**

- **Tier 1 (honest answer, no provider required):** asking about equation 26
  returns *"Source 37 page N contains an equation region that was not extracted
  (image-only, 182×24 at p.4). 95 such regions exist across 17 pages of this
  source. Recovery is available via …"* — i.e. `wiki lint` emits it, `wiki add`
  prints it, and the chat can cite it because the span doc says so.
- **Tier 2 (content answer):** `SELECT body FROM search_documents WHERE record_id
  = '<loss span>'` contains LaTeX; `KNU-7dd60672.formula_status =
  'linked_evidence'`; `wiki query "explain equation 26"` returns the equation
  with a `SPAN-` citation.

---

### 1.5 Concrete implementation (phased, DAG-scoped)

**P0 — L1: type the loss instead of losing it. Deterministic, no LLM, no
provider, no schema migration.**

`pipeline/source_spans.py` — recognize the region and record what is already
known about it:

```python
# pipeline/source_spans.py
_PICTURE_OMITTED = re.compile(
    r"^\*\*==>\s*picture\s*\[(\d+)\s*x\s*(\d+)\]\s*intentionally omitted\s*<==\*\*$"
)

def _classify_omitted_region(text: str) -> dict | None:
    """Return image-region metadata for a pymupdf4llm omission, else None.

    Purely deterministic: the placeholder carries its own pixel dimensions,
    which are enough to separate a display-equation band from a figure or a
    decorative glyph without any provider call.
    """
    m = _PICTURE_OMITTED.match(text.strip())
    if not m:
        return None
    w, h = int(m.group(1)), int(m.group(2))
    if w * h < 2000:
        kind = "glyph"           # inline symbol / logo / rule
    elif w >= 3 * h:
        kind = "equation_band"   # wide-and-short: display equation
    else:
        kind = "figure"
    return {"omitted_region": {"width": w, "height": h, "kind": kind}}
```

Wired into `SpanRecord` (add `metadata: dict | None = None`) and
`store_source_spans` (pass `metadata=span.metadata` — `db.upsert_source_span`
already accepts it, `db/_entities.py:125`). **`content_hash` is unchanged** —
it hashes `text`, not `span_type` or `metadata` — so **span ids stay stable and
no unit citation dangles.**

Measured triage over the existing 130 (SQL over `text_preview`, no re-parse):

| band | count | dimension range |
|---|---|---|
| `equation_band` (w ≥ 3h) | **48** | 152×10 … 504×104 |
| `figure` | 54 | 29×40 … 510×600 |
| `glyph` (< 2000 px²) | 28 | 14×7 … 219×59 |

48 equation-band regions vault-wide is the honest size of the recovery target —
not 158, not 130. That is a §26.2-compliant *selective* surface by construction.

**P0b — retro-fix for the 130 already-ingested spans. One-shot backfill, no
re-ingest.** `db.upsert_source_span` is insert-or-return-existing
(`db/_entities.py:130-136`): it will **not** update `metadata` on an existing
row. So a migration is required — and it is trivial, because
`text_preview` is the full text for all 130 (measured 51-53 chars, §1.1 step 4):

```python
# one-shot, in db/schema.py migrations
for row in conn.execute(
    "SELECT id, text_preview, metadata FROM source_spans "
    "WHERE text_preview LIKE '%intentionally omitted%'"
):
    meta = json.loads(row["metadata"] or "{}")
    classified = _classify_omitted_region(row["text_preview"])
    if classified and "omitted_region" not in meta:
        meta.update(classified)
        conn.execute("UPDATE source_spans SET metadata = ? WHERE id = ?",
                     (json.dumps(meta, sort_keys=True), row["id"]))
```

**No file access, no Zotero resolution, no LLM, no re-parse, no span-id churn,
no unit retirement.** This directly answers briefing §5's "what happens to the
130 already-ingested placeholder spans": they are typed in place, in
milliseconds, and become queryable.

**P1 — L1 projection + lint: stop erasing the loss.**

- `ingest_raw.py:1094` — instead of `re.sub(..., " ", cleaned)`, substitute a
  compact marker: `"[image-only region 221x18]"`. The preview stays readable and
  the CTX page stops lying by omission.
- `_build_structural_source_guide` — add a per-source line: *"17 pages contain
  95 image-only regions (48 equation-band); their content is not in this vault."*
- New `lint.py` check with an existing-shaped `LintIssue` (lint.py:65-75):

```python
def check_image_only_regions(paths) -> list[LintIssue]:
    """INFO/WARNING: source regions the parser discarded (image-only)."""
    # group source_spans by (source_id, page_number) where
    # json_extract(metadata,'$.omitted_region.kind') = 'equation_band'
    # → one issue per source, severity WARNING when equation_band > 0
    #   page="01_Contexts/<CTX>.md", context={"pages":[...], "counts":{...}}
```

On the measured vault this fires for 4 sources / 25 pages / 48 equation bands.
Category: reuse `CheckId.COMPILER_INTEGRITY` (lint.py:61) — it is already the
§26.5 audit bucket — or add `SOURCE_FIDELITY`. Non-release-blocking (it is a
source property, not a DAG break).

**P2 — L2: the adjacency locator. This is the piece that unblocks
`recover_formula`.**

New `pipeline/formula_recovery.py` function — **it produces no unit, invents
nothing, and only ever adds a citation**:

```python
def locate_image_only_loss(db_path: Path, source_id: int) -> list[dict]:
    """Pair each `uncertain` unit with the adjacent image-only span that caused it.

    Returns [{"unit_id", "span_id", "loss_verdict": "image_only", "locator": {...}}].
    Deterministic; no provider call. This is the missing `span_id` argument of
    `recover_formula`, not a synthetic knowledge unit.
    """
    with db.connect(db_path) as conn:
        spans = conn.execute(
            "SELECT rowid AS rn, id, page_number, metadata FROM source_spans "
            "WHERE source_id = ? ORDER BY rowid", (source_id,)
        ).fetchall()
    loss = {r["rn"]: r for r in spans
            if (json.loads(r["metadata"] or "{}")
                 .get("omitted_region", {}).get("kind") == "equation_band")}
    by_span = {r["id"]: r["rn"] for r in spans}

    out = []
    for unit in db.list_units_with_formula_status(db_path, source_id, "uncertain"):
        cited = json.loads(unit["source_span_ids"] or "[]")
        # nearest equation-band loss span within ±1 of any cited span
        cands = [loss[rn] for sid in cited if sid in by_span
                 for rn in (by_span[sid] - 1, by_span[sid] + 1) if rn in loss]
        if len(cands) != 1:
            continue   # ambiguous or none → do NOT guess; report, don't recover
        span = cands[0]
        region = json.loads(span["metadata"])["omitted_region"]
        out.append({
            "unit_id": unit["id"],
            "span_id": span["id"],
            "loss_verdict": "image_only",
            "locator": {"source_id": source_id, "page": span["page_number"],
                        "region": [region["width"], region["height"]]},
        })
    return out
```

The `len(cands) != 1` guard is deliberate: an ambiguous pairing is reported by
P1's lint check and never recovered. Honest under-coverage beats a wrong anchor.

Then the amendment, which is the only mutation of an existing unit:

```python
def anchor_loss_span(db_path, *, unit_id: str, span_id: str) -> None:
    """Add the loss span to the unit's citation surface with role 'formula'.

    Additive only. Proven monotone-safe (see §1.3): `validate_claim_support`
    takes max() over span coverage and union() over span formulas, so adding a
    span can never worsen a verdict — in particular it can never produce
    `failed`, the one status excluded from the search index
    (materializer.py:273).
    """
    # UPDATE knowledge_units SET source_span_ids = json_insert(...) WHERE id = ?
    # then: validate_claim_support(db_path, unit_id, span_texts=hydrated)
```

With that done, **`recover_formula(...)` runs completely unmodified**: its
`span_id ∈ cited_span_ids` check (formula_recovery.py:110-112) passes, its
`formula_status == 'uncertain'` check (line 113-116) passes, and the whole
§26.2 lifecycle — 0.80 threshold, validator trace, exact ordered-token match
against the owning claim's formula, hydrated-hash revalidation of every cited
span, `page_hash` invalidation (`invalidate_formula_recoveries`) — applies
verbatim. **Zero new contract, zero relaxation of constraint 2, 3, or 4.**

The hydration requirement is satisfiable: the loss span's stored text IS its
full text, and `hydrate_span_text` (compile.py:200-226) re-derives it from the
source with a matching `content_hash`, so `raw_span_texts` is obtainable and the
SHA-256 check at formula_recovery.py:127-131 passes.

**P3 — retrieval re-entry. Without this everything above is invisible
(the gap proven in §1.3).**

```python
# retrieval/materializer.py, in the span loop (currently line 369-393)
body = str(row.get("text_preview") or "")
meta = json.loads(row.get("metadata") or "{}")
region = meta.get("omitted_region")
if region:
    # replace the parser apology with a labelled, searchable statement
    body = (f"Image-only {region['kind']} region "
            f"({region['width']}x{region['height']}) on page {row.get('page_number')}; "
            f"content not extracted by the text-layer parser.")
for rec in meta.get("formula_recovery", []):
    if rec.get("status") == "reviewed" and rec.get("latex"):
        body += f"\n$${rec['latex']}$$"          # ← reaches FTS *and* the vector index
        label = _equation_label(rec["latex"])     # \tag{26} / trailing (26)
        if label:
            title = f"{title} — equation ({label}), p.{row.get('page_number')}"
# dependency_parts must gain the recovery fingerprint so a new candidate
# re-materializes the doc:
dependency_parts["formula_recovery_hash"] = _json_hash(meta.get("formula_recovery", []))
```

The `dependency_parts` addition is mandatory — without it the doc's
`dependency_hash` (materializer.py:97-99) is unchanged by a recovery and the
embedding layer's `input_hash` gate skips re-embedding.

Mirror the same append in `pipeline/compile.hydrate_span_text` (return
`text + "\n$$" + reviewed_latex + "$$"`) so evidence packs carry it too — but
**only for `reviewed` candidates**, and the `content_hash` verification must
still run against the *raw* text, not the augmented string, or F10's whole
guarantee collapses.

**P4 — the recovery driver itself.** A new `wiki sources recover-formulas
[--source-id N]` that: renders only the pages named by
`locate_image_only_loss`'s locators (25 pages vault-wide, measured), crops the
region, calls `_resolve_extract_client` (ingest_raw.py:1522-1544 — the *light*
region model, which is exactly what §26.2 selective recovery wants and which
today has no production caller), and feeds `recover_formula`. This is
region-scoped by construction and therefore **inside** constraint 1's
prohibition on "escalating to blanket page-VLM."

Reference Mode is already handled: `_resolve_reference_source` (ingest_raw.py:98-130)
resolves the `zotero:YACIRUKK` stub to the real PDF and `generate_l1_structural_context`
passes that `resolved_source` — not the stub — into `_apply_vlm_pdf_extraction`
(ingest_raw.py:1420-1431). The recovery driver must call the same resolver.
Constraint 6 is satisfied by reuse, not by new code.

**P5 — Route B remains available and unchanged, correctly priced.** Nothing
above touches `vision_model`. §1.3's table states its real cost on already-ingested
sources (full span-set churn → full unit retirement → full Phase A/B/C rebuild
for 4 sources). It stays the right choice for *newly added* math-heavy PDFs and
the wrong choice for retrofitting 130 spans. Two discoverability defects should
be fixed regardless, because both are cheap:

- `_resolve_vision_client(_vcfg, None)` at ingest_raw.py:1427 passes
  `main_client=None`, so the documented `vision_model → main-if-vision → None`
  chain (docstring at ingest_raw.py:1507, spec §26.2a) **collapses to
  `vision_model → None` on the ingest path**. Either the spec or the call site is
  wrong. I read this as a genuine defect: a user whose main model is
  vision-capable gets the documented behavior in the plugin snip path and not at
  ingest. But it is a *separate* defect and fixing it silently would turn on
  page-VLM for every PDF ingest for such users — a large unannounced cost change.
  It must be its own decision, not a side effect.
- P1's lint/add output should name `llm.vision_model` when it reports
  equation-band regions, which is the honest form of "configure this yourself."

---

## 2. Pros & Cons

### Pros

1. **It is anchored to a measurement the briefing did not have.** 159/480
   `uncertain` units vault-wide and 99/171 on source 37 sit one span from a
   placeholder. Route A stops being "invent a unit to satisfy an API" and becomes
   "supply the `span_id` the API always needed." The briefing's central
   objection to Route A dissolves under a different query, not under an argument.
2. **No fictional knowledge unit, no new span, no schema migration.** Everything
   rides existing structures: `source_spans.metadata` (SCHEMA §20.4 is already
   a free-form JSON column), `knowledge_units.source_span_ids`, `claim_supports`.
   `recover_formula` and `invalidate_formula_recoveries` are called
   **unmodified**, so constraints 2, 3, and 4 are satisfied by reuse.
3. **The 130 existing spans are fixed with pure SQL.** Because every placeholder's
   `text_preview` is 51-53 chars — below the 200-char cap — the DB already holds
   100% of the evidence. No re-parse, no Zotero round-trip, no LLM, no span-id
   churn, no unit retirement. This is the strongest available answer to
   constraint 5, and it is a measured property, not an assumption.
4. **The recovery surface is genuinely selective and small.** Deterministic
   dimension triage yields **48 equation-band regions across 25 (source, page)
   pairs in 4 sources**. That is a §26.2-compliant selective target by
   construction, not by promise — it cannot escalate to blanket page-VLM because
   the locator only ever emits regions with a recorded loss verdict.
5. **Provable monotone safety.** `max()` over coverage and `union()` over span
   formulas (claim_support.py:334-354) mean a citation amendment cannot produce
   `failed` — the one status still excluded from the index. No unit can be
   demoted out of retrieval by this change. This is checkable by reading 20 lines
   of existing code and is the property I would put a test on first.
6. **It names the re-entry gap that would have made a third no-op.** §1.3's table
   shows recovered LaTeX currently reaches **no** reader: not FTS, not the vector
   index, not evidence hydration, not the CTX page. Any plan without P3 ships a
   status-flag flip and calls it a fix. This is, in my view, the single most
   valuable thing this proposal contributes.
7. **Tier-1 honesty ships without any provider.** P0+P0b+P1 alone convert 130
   silent losses into a counted, page-located, lint-reported, *searchable* fact,
   with zero LLM cost and zero re-ingest. Route C stops being "the same silence
   with a label" because the label lands in `search_documents.body` and is
   therefore retrievable by the failing query.
8. **L3/L4 are provably untouched.** Measured: 0 reports, 0 syntheses, 0
   entities, 0 relations cite a placeholder span, and the materializer's
   liveness filters (materializer.py:344-365) gate on subset-of-live-spans, which
   only grows. Phase B and C do not re-run. The cost stays bounded.

### Cons & Limitations

1. **`rowid` as document order is an implementation detail, not a contract.**
   `store_source_spans` inserts sequentially and `upsert_source_span` returns the
   existing row on re-parse, so it holds today — but nothing enforces it, and a
   source re-ingested after an edit could interleave rowids. The honest fix is to
   populate `start_char`/`end_char` (columns exist in the schema, currently
   always `NULL` — `spans_from_sections` never sets them) and order by those.
   That is extra work this proposal creates, and until it is done the adjacency
   locator rests on an unpinned invariant. **A red-teamer should attack this
   first, and I would not defend it.**
2. **Adjacency is a heuristic and it under-covers by design.** 159 of 480
   `uncertain` units match; the other 321 are the genuine present-but-damaged
   population `recover_formula` was written for, plus ambiguous cases. The
   `len(cands) != 1` guard drops multi-equation neighborhoods entirely. Coverage
   on source 37 is 58%, not 100%. Some equations will stay unrecovered and must
   be reported as such.
3. **Amending `source_span_ids` mutates an authoritative artifact.** Even though
   the verdict is monotone-safe, the *citation surface* of a published unit
   changes outside a new `compiler_generation`. §26.3's generation model may
   require this to run as a staged generation with a publish gate rather than an
   in-place `UPDATE`. I have not resolved that; `schema_guardian` should rule on
   it, and if a generation is required the cost of P2 rises materially.
4. **The equation *number* may still be unrecoverable.** `(24)/(25)/(26)` appear
   in **0** spans, because the `\tag` is inside the raster. If the VLM does not
   transcribe the tag, the title-labelling in P3 has nothing to write and "수식
   26" remains lexically unmatchable even after successful LaTeX recovery — the
   user would get the right equation only via semantic match on the surrounding
   prose. A fallback (ordinal position of equation-band regions per source) is
   possible but is a guess and I would rather report the limitation.
5. **P3 weakens a clean invariant.** Today `search_documents.body` for a span is
   exactly `text_preview` — a pure, verifiable projection. Appending recovery
   LaTeX makes the indexed body a *derived* artifact that no longer round-trips
   to `content_hash`. That is defensible (it is gated on `status == 'reviewed'`),
   but it is a real loss of a nice property and the provenance JSON must record
   which part of the body is recovered so a citation cannot claim the source said
   something it did not.
6. **`kind` triage by pixel dimensions is crude.** `w >= 3h` catches 48 regions,
   but a two-line aligned equation (`\begin{aligned}`) is squarer and lands in
   `figure`; a wide figure caption strip lands in `equation_band`. It is cheap
   and deterministic, which is why I prefer it as a *pre-filter* — but it must
   not be treated as a loss verdict on its own. `classify_formula_loss` remains
   the authority; the dimension band only decides what is worth rendering.
7. **It does not fix newly added sources.** A new math-heavy PDF ingested
   tomorrow still loses its equations at L1; it just loses them *loudly* now. The
   real upstream fix is Route B (`vision_model`), which this proposal explicitly
   does not enable. I am proposing to make the loss visible and repairable, not
   to prevent it — and the Arena should be clear that those are different
   promises.
8. **The `_resolve_vision_client(_vcfg, None)` question stays open.** I flagged
   it as a probable defect but deliberately did not fold the fix into this
   proposal: silently satisfying `main-if-vision` at ingest would turn on
   full-page VLM for every PDF for users with a vision-capable main model — a
   large, unannounced cost and latency change that deserves its own decision.
9. **Explicitly NOT in scope:** regenerating L3 concepts or L4 syntheses;
   changing `_SUPPORT_VERIFY`/`_SUPPORT_FAIL` thresholds; touching the 498
   `failed` units with `formula_status='preserved_in_text'` that
   materializer.py:260-265 names as false negatives; enabling `vision_model`;
   any change to `recover_formula`'s acceptance contract; the `wiki plugin pdf
   context --file-path` encryption failure noted in briefing constraint 6 (a real
   but separate defect); and equation-number reconstruction beyond whatever tag
   the VLM happens to transcribe.
