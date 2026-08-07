# Critique on `01_proposal_rag_analyst.md`, `01_proposal_architect.md`, `01_proposal_schema_guardian.md`, `01_proposal_product_honesty.md`
Date: 2026-08-08 | Agent Persona: Red Teamer

Every claim below was re-derived against the live DB
(`.cache/vaults/13ed51f8b06cb88e/state.sqlite`) and the checked-in source at this
commit. Where a proposal states a fact I could not reproduce, I give the
`file:line` that contradicts it.

**Bottom line up front.** Three of four proposals converge on a route whose
terminal gate is `formula_recovery.py:135` — **full token-tuple equality**
between a VLM's verbatim transcription and a formula the extractor *paraphrased
out of surrounding prose*. Measured against the actual claim: 6 of 8 plausible
transcriptions are rejected, and the 2 that pass are the ones spelling the
equation exactly the way the LLM guessed. Failed candidates sit at
`status='candidate'` forever, and both re-entry designs read only
`status == 'reviewed'`. **That is no-op #3, fully assembled, with a VLM bill
attached** — and all three technical proposals freeze that gate and list
freezing it as a virtue.

---

## 1. Vulnerabilities & Flaws

S1–S2 are ship-blockers for the recovery route; S3–S7 are correctness failures
inside the chosen mechanism; S8–S11 are cost/contract failures; S12–S15 are
precision problems in individual proposals.

---

### S1 — FATAL. The acceptance gate is strictly stronger than the validation gate it protects, and is unreachable in practice. This is how it ships as the third no-op.

`recover_formula` (`backend/src/curator/pipeline/formula_recovery.py:133-141`):

```python
claim_formulas = [_formula_tokens(v) for v in _extract_latex(unit["statement"])]
recovered_tokens = _formula_tokens(latex)
structurally_matches_claim = recovered_tokens in claim_formulas   # ← EXACT tuple equality
```

Compare `validate_claim_support`
(`backend/src/curator/pipeline/claim_support.py:343`), which uses
`_is_formula_subsequence(...)` — a *contiguous subsequence* test, deliberately
tolerant of surrounding tokens. **The gate that decides `reviewed` is strictly
tighter than the gate that decides `verified`**, and because `if not reviewed:
... return candidate` (line 178-180) short-circuits, a transcription that
*would* have produced a `verified` verdict never reaches the validator at all.
Nobody in the Arena noticed this asymmetry; all three technical proposals
declare the acceptance contract untouchable (RAG §1.5 P2 "zero relaxation of
constraint 2"; architect §1.9; guardian §1.7).

Measured on the exact claim the convener identified. `KNU-63af4c5c.statement`
contains `$\lambda^T Q \lambda + q^T \lambda = 0$`, which tokenizes to
`('\lambda','^','T','Q','\lambda','+','q','^','T','\lambda','=','0')`. I ran
`_formula_tokens` verbatim over eight plausible verbatim transcriptions of that
displayed equation:

| candidate transcription | result |
|---|---|
| `\lambda^T Q \lambda + q^T \lambda = 0` | **MATCH** |
| `\lambda^TQ\lambda+q^T\lambda=0` | **MATCH** |
| `\lambda^{T} Q \lambda + q^{T} \lambda = 0` | REJECT (`^ { T }`) |
| `\lambda^\top Q \lambda + q^\top \lambda = 0` | REJECT (`\top`) |
| `\boldsymbol{\lambda}^T Q \boldsymbol{\lambda} + q^T \boldsymbol{\lambda} = 0` | REJECT |
| `\mathbf{\lambda}^\top Q \mathbf{\lambda} + \mathbf{q}^\top \mathbf{\lambda} = 0` | REJECT |
| `\lambda^T Q \lambda + q^T \lambda = 0 \tag{26}` | REJECT |
| `\lambda^T Q \lambda + q^T \lambda = 0,` | REJECT (trailing comma) |

Now weight those priors against the source. Neighbouring spans render λ as
**bold** (`SPAN-e45fbd35`: "the ray depths of the two endpoints _**λ**_ = ( _λ_
1 _, λ_ 2)"), so the typeset equation is a bold-vector equation and a faithful
VLM emits `\boldsymbol{\lambda}`/`\mathbf{\lambda}`. The paper numbers its
equations ("From (27) we get…", "Then inserting into (28)" on the same page), so
a faithful VLM emits a tag. **Every high-fidelity transcription is rejected;
only a low-fidelity one that coincidentally matches the LLM's own paraphrase
passes.**

Realistic acceptance rate over the 48 `equation_band` regions the RAG analyst
targets: **0–5, most likely 0–2.** Anything with a bold vector, `\top`, a
brace-wrapped superscript, a tag, `\begin{aligned}`, or trailing punctuation is
out by construction. This is not a code accident — SCHEMA §20.4 mandates it
("the recovered ordered token sequence must exactly match a formula in the
owning claim") — so it cannot be quietly relaxed during implementation.

**Compounding blocker, same severity: `validator_trace_id` has no producer.**
`reviewed` also requires `bool(validator_trace_id)` (line 138). Outside
`formula_recovery.py` the identifier appears only as a `claim_supports` column
and a passthrough parameter (`db/_entities.py:489,508,515,519`;
`claim_support.py:585-587`; `db/schema.py:365`). **No production code produces
one**, and §20.4 defines it as recording "a deterministic gold check or recorded
human review" — an *independent* validator, not the extraction call. Passing the
VLM's own `PTR-` id is self-certification, exactly what "parseable LaTeX alone
verifies nothing" forbids. No proposal says what the validator is. **Without
S1's two fixes, every line of P2/P3/P4 in every proposal is dead code.**

---

### S2 — FATAL. The proposed loss record cannot address a region, so the only implementable recovery action is a whole-page VLM call — which §26.2 bans as recovery. Three proposals claim compliance they cannot deliver.

SCHEMA §20.4 freezes the locator shape:

```json
"locator": {"source_id": 3, "page": 7, "region": [120, 410, 580, 470]}
```

— a **four-element bounding box**, plus a `crop_hash` of "the cropped region
image." The existing test suite uses exactly that shape
(`backend/tests/test_plan_b_formula_recovery.py:105`).

The RAG analyst's classifier emits `omitted_region: {width, height, kind}` and
its locator emits `"region": [region["width"], region["height"]]` (§1.5 P2) — a
**size, not a position**. The guardian re-namespaces the same two numbers under
`loss.region` (§1.2) and does not add coordinates. The architect adopts the RAG
locator verbatim. **None of them can compute a crop.** pymupdf4llm has the
`clip` rect at `document_layout.py:735` and prints only `clip.width` /
`clip.height`; the coordinates are discarded before Incurator ever sees the
string, and `parsers/pdf.py` never asks for them.

So the P4 driver's stated behaviour — "renders only the pages named by the
locator, **crops the region**" (RAG §1.5 P4; architect §1.1 P4) — is not
implementable from the data these proposals store. All you can do with
`{page, width, height}` is render the whole page and hand it to the VLM. That is
precisely constraint 1: *"the selective-recovery mechanism MUST NOT escalate to
blanket page-VLM; it recovers only measured-loss regions"* (§26.2). **Both P4
designs violate §26.2 in substance while claiming compliance** (RAG Pro #4: "it
cannot escalate to blanket page-VLM … by construction"). It escalates by
necessity — and page 11 of source 37 carries **ten** placeholder spans, so
"whole-page render + find the matching equation" puts the region selection
inside the model, which is the exact thing §26.2 rejects.

---

### S3 — CRITICAL. `rowid` is not document order. Not "an unpinned invariant" — demonstrably violated on the very source under discussion, and the briefing's "3 inversions" undercounts it.

The RAG analyst calls this Con #1 and says "I would not defend it." The
architect claims his live re-verification makes staleness "fail closed"
(§1.4/Pro #3). Both are arguing about a property that is **already false today**:

```
rowid  span            page  text
11104  SPAN-398fff4d   23    27
11105  SPAN-539a1e51   23    descriptor for line matching. Pattern Recognition,
11106  SPAN-3ca04707    2    **==> picture [65 x 99] intentionally omitted <==**
11107  SPAN-58f5e4d7    2    **==> picture [65 x 214] intentionally omitted <==**
11108  SPAN-ba7590ce    3    **==> picture [29 x 256] intentionally omitted <==**
11109  SPAN-74d68f67    3    **==> picture [29 x 59] intentionally omitted <==**
```

Four page-2/page-3 image spans sit at the **end** of source 37's rowid range,
after the page-23 bibliography — so a bibliography span (`SPAN-539a1e51`) is
"rowid-adjacent" to a page-2 figure under both locators. The mechanism is
structural: `upsert_source_span` (`db/_entities.py:130-136`) returns the existing
id or **appends at the tail**, and `compile_source_l2` re-runs
`spans_from_sections` + `store_source_spans` on every L2 pass
(`compile.py:327-328`). **Any span a later parse produces that the first did not
is permanently filed at the end of the rowid range.** The order does not degrade
gracefully; it gets a hole punched in it on every re-ingest that changes
anything.

The architect's "re-verify live" re-verifies against the same corrupt order. His
Con #3 frames the failure mode as "degrades to recovers nothing (safe)" — it
degrades to *recovers a rowid-adjacent span from a different page*, the unsafe
direction he claims to have bought out of.

**Blast radius when adjacency is wrong:** the wrong span lands in
`knowledge_units.source_span_ids`, a `verified` `support_role='formula'` row is
created against it, the unit flips to `linked_evidence`, and the claim then
asserts — with a clickable citation — that its equation lives on a page it does
not. S1's exact-match gate is currently the only thing preventing that, which is
an argument for fixing S3, not for keeping S1.

---

### S4 — CRITICAL. The RAG analyst's locator refuses to recover the user's reported claim. The architect's accepts three candidates and disambiguates none.

The `KNU-63af4c5c` neighbourhood, from the live DB:

```
10729  SPAN-c1bf9cb9  11  Let p1 and p2 be the 2D points (after applying R and removing...
10730  SPAN-a23f9d4e  11  **==> picture [178 x 11] intentionally omitted <==**     ← equation
10731  SPAN-6df340cb  11  This is a quadratic equation in λ1 and λ2, and can thus be written as
10732  SPAN-2a02b227  11  **==> picture [158 x 12] intentionally omitted <==**     ← equation
10733  SPAN-3e733dc3  11  Note that there is no constant term since det(p0, p0) = 0. Com...
10734  SPAN-d21861c1  11  **==> picture [223 x 13] intentionally omitted <==**     ← equation
```

`KNU-63af4c5c.source_span_ids = ["SPAN-6df340cb","SPAN-3e733dc3","SPAN-3ba9d089"]`.

- **RAG analyst.** `locate_image_only_loss` collects `±1` neighbours over *all*
  cited spans, then `if len(cands) != 1: continue`. Cited span 10731 contributes
  {10730, 10732}; cited span 10733 contributes {10732, 10734}. `cands` has
  length 4. **The unit is skipped.** The proposal that discovered the adjacency
  population produces **zero recovery for the exact claim the user asked about**
  — and its §1.4 "Definition of done, Tier 2" names that outcome as success.
  This is a self-inflicted no-op, independent of S1.
- **Architect.** `_adjacent_image_loss_span_ids` returns a *set* and accepts any
  member. All three placeholders classify `equation_band` under the `w >= 3h`
  rule (178≥33, 158≥36, 223≥39). So the gate performs **no disambiguation at
  all** for this case; whichever span the driver happens to propose is admitted.
  His Pro #2 ("the smallest defensible trigger") is a trigger that admits every
  candidate and delegates the real decision to S1's gate, which never fires.

The disambiguating evidence is sitting in the prose and neither proposal reads
it: "…and can thus be **written as**" means the equation *follows*; a span
beginning "where …" / "Note that …" means the equation *precedes*. See A4.

---

### S5 — CRITICAL. `recompile_source` silently reverts `linked_evidence` to `uncertain`. The architect asserts the opposite and says he checked it.

Architect §1.5: *"`recompile_source` (compile.py:933-1024) needs zero changes,
and I checked this specifically because it is the one place a naive version of
this idea breaks."*

`compile.py:986-987`, on the slow path:

```python
for uid in unit_ids:
    validate_claim_support(db_path, uid, conn=conn)     # ← span_texts=None
```

With `span_texts=None`, `_load_spans` (`claim_support.py:228`) falls back to
`row["text_preview"]` — the raw placeholder. `formula_ok` is False, the verdict
is `uncertain`, and `db.set_unit_formula_status(..., "uncertain")` (line 430)
**overwrites `linked_evidence`.** Meanwhile
`_clear_claim_supports(preserve_formula=True, ...)` (325-328) *keeps* the
`verified` `support_role='formula'` row. That resulting state — a verified
formula support row on a unit that is no longer `linked_evidence` — is **not
detected** by the audit: `run_compiler_audit` checks only the forward direction
(`claim_support.py:531`), never the converse.

The architect's defence is that the fast path (954-961) keys on
`_source_content_hash`, which a citation edit does not move. True and
irrelevant: the fast path *also* requires
`prior["prompt_contract_version"] == PROMPT_CONTRACT_VERSION`
(`compile.py:957`), currently `"curator.knowledge_unit_extract@v3"`
(`compile.py:66`) — a string that changes whenever the extraction prompt does.
**One prompt-contract bump walks every source through the slow path and erases
every recovery in the vault, silently, with no lint signal.** No-op #4,
pre-loaded.

---

### S6 — CRITICAL. The schema guardian is right that reconciliation is a durability hole and wrong about which branch causes it. The branch they named is unreachable; the branch they missed retires the recovered unit outright.

Guardian §1.4 predicts: *"a semantic-hash match reused onto the stable id — the
candidate's own `source_span_ids` overwrite the stable row's."* That path is
`_reuse_verified_candidate`, and it is gated at `claim_support.py:655` on
`unit["support_status"] == "verified"`. A freshly-extracted candidate for one of
these formula claims is `uncertain` by construction (its formula is in the image
next door) — **it can never be `verified`, so it can never enter `candidates`,
so branch (a) never fires for this population.**

The branch that *does* fire is `claim_support.py:690` → `707`:

```python
if spans_unchanged and not any(sid in candidate_spans for sid in cited):
    ...  # carry forward
    continue
db.retire_knowledge_unit(db_path, unit_id, conn=conn)      # ← line 707
```

On the next `compile_source_l2`, any fresh *verified* candidate citing one of the
recovered unit's prose spans (e.g. a plain-prose claim from `SPAN-3e733dc3`) puts
that span into `candidate_spans` → the guard fails → **the recovered unit is
retired.** `retire_knowledge_unit` deletes its `claim_supports`
(`db/_entities.py:590-594`), so the formula link vanishes, while the `reviewed`
candidate stays in `metadata.formula_recovery` pointing at a retired
`knowledge_unit_id` — which a later `invalidate_formula_recoveries` will then
call `set_unit_formula_status` on.

So the guardian's *conclusion* (citation mutation is not durable; needs
idempotent re-application after reconcile) is correct and important; their
*mechanism* is wrong and their preferred remedy (b) is worse — see S7.

---

### S7 — CRITICAL. The architect's central architectural objection is factually false, and the guardian's preferred remedy (b) makes Tier 2 unreachable by construction.

**Architect objection #1** (§0): *"I grepped the entire backend for any write to
`knowledge_units.source_span_ids` after row creation. There is none…
Introducing the **first-ever** mutation…"*

`backend/src/curator/pipeline/claim_support.py:564-574`:

```python
fields = (
    "unit_type", "canonical_name", "statement", "source_span_ids",   # ← here
    "source_id", "confidence", "truth_status", "prompt_run_id",
    "semantic_hash", "support_status", "support_reason",
    "formula_status", "generation_id",
)
assignments = ", ".join(f"{field} = ?" for field in fields)
c.execute(
    f"UPDATE knowledge_units SET {assignments}, updated_at = ? WHERE id = ?", ...
)
```

`_reuse_verified_candidate` **overwrites `knowledge_units.source_span_ids` on an
existing stable unit id**, on every reconciliation reuse, and has done so since
Plan B. A literal grep cannot find it because the SQL is assembled from the
`fields` tuple — which is exactly why the architect's grep came back empty. The
precedent exists, in the same file he cites for his monotonicity argument.

**Objection #2** rests on three quotations, two over-read:
- SCHEMA §20.2 (line 1731) — *"…remains the citation surface, while
  `claim_supports` carries the verified minimal subset"* is a
  **declared-vs-verified distinction**, not an immutability rule; it is the
  sentence that *permits* declaring more spans than are verified.
- SCHEMA §22.5 (line 2409) — *"`source_span_ids` is never mutated; items dropped
  by scope are counted in `omitted_counts["policy_excluded"]`"* is the
  **evidence-pack curation read path**: it forbids *trimming* span ids when
  filtering by workspace scope. Quoting it as "the blanket principle even more
  plainly" applies a read-path rule to a compiler write path.
- SCHEMA §20.5 is the only relevant one, and it checks against the unit's
  **declared** `source_span_ids` — consistent with the declared set growing.

So his *placement* is right and every stated *reason* is wrong — which matters,
because §1.8 asks for three spec edits to legalize an exception to an invariant
that does not exist as stated.

**Guardian's remedy (b)** — "drop the citation amendment; the span is
independently searchable" — is materially wrong about its cost.
`validate_claim_support` reads `declared = unit["source_span_ids"]`
(`claim_support.py:315`) and loads only those spans (`_load_spans`, 220-230).
**No path exists by which a non-declared span's text reaches the validator.**
Remedy (b) therefore means: never call `recover_formula`, never reach
`linked_evidence`, never re-validate. It is Route C wearing Route A's name — a
defensible *decision*, but it must be stated as "we are not doing recovery."

---

### S8 — HIGH. The `wiki add --force` trap is real, and product-honesty under-priced it by 9×. It is a full-vault LLM rebuild, not four sources.

`backend/src/curator/commands/core.py:680-704`, with `force=True`:

```python
candidate_rows = conn.execute(
    "SELECT id, relpath, content_hash, context_id, l1_status FROM sources "
    "WHERE status IN ('pending', 'force_pending', 'curated', 'error') ORDER BY id ASC"
).fetchall()
...
conn.execute("UPDATE sources SET status = 'force_pending', ... "
             "l1_status='pending', l2_status='pending', "
             "l3_status='pending', l4_status='pending', ... "
             f"WHERE id IN ({placeholders})", ids)
```

There is **no per-file scoping**: every source in that status set is flagged.
Measured live: `SELECT status, COUNT(*) FROM sources GROUP BY status` →
`curated | 36`, total 36. **`wiki add --force` resets all 36 sources to
`l2/l3/l4='pending'`**, and `build()`'s default selection (`core.py:806-812`)
then re-extracts **the entire vault** on the next plain `wiki build` — including
one the user runs for an unrelated new source. Product honesty found the door and
mis-measured the room behind it ("the 4 already-ingested sources"). Largest
unpriced cost in the Arena, and a latent hazard independent of this plan.

---

### S9 — HIGH. The guardian's clock finding is the best diagnosis in the Arena. Their prescription breaks in three concrete places.

The diagnosis is correct and I reproduce it: `_UPDATED_AT_COL["source_spans"] =
"created_at"` (`db_sync.py:87`); `created_at` is written once at INSERT
(`db/_entities.py:159`); `upsert_source_span` never updates an existing row
(`db/_entities.py:130-136`); `_lw_upsert` compares with strict `>` and returns
`"skipped"` on equal timestamps (`db_sync.py:1364-1370`); `_local_max_ts` takes
`MAX(col)` per table (`db_sync.py:1649-1654`). **Every `metadata` write on
`source_spans` is invisible to cross-device sync today.** That is real, shipped,
and must be fixed before anything writes production data into that column.

The prescription (§1.6) has three defects:

1. **`SCHEMA_VERSION` 13 → 14 is a hard sync outage, not a graceful fail-safe.**
   Guardian Step 4 reasons about `_lw_upsert` receiving `None` for the new
   column. That code never runs: `import_knowledge` checks the header first and
   raises `schema_version mismatch` (`db_sync.py:812-815`), and the auto
   peer-import path logs and *silently skips* (`db_sync.py:1551-1554`). A
   mixed-version pair does not degrade — it **stops syncing, quietly.** Any
   v14→v13 payload that got past the header would then raise `Table
   'source_spans' has unknown columns` (`db_sync.py:863-866`). "Needs no
   special-case code" is the opposite of what the code does.
2. **The trigger inverts the codebase's guard and eats their own backfill's
   timestamp.** Both shipped triggers use `WHEN NEW.updated_at = OLD.updated_at`
   (`db/schema.py:843,861`) — *fire only when the caller did not set the clock*.
   The guardian's `WHEN NEW.metadata IS NOT OLD.metadata` fires **whenever
   metadata changes, including when the caller set the clock explicitly**, so
   their Step-5 backfill's carefully-justified `metadata_updated_at = now` is
   immediately overwritten by the trigger's own `strftime('now')`. Harmless
   here; fatal for any caller or test needing a deterministic clock. §1.6 claims
   the trigger "mirrors `compiler_generations_touch_updated_at` **verbatim**" —
   it inverts its condition.
3. **The DDL is unnecessary.** A11 obtains the same LWW correctness with zero
   `ALTER TABLE`, zero `SCHEMA_VERSION` bump, and therefore zero sync outage.
   Reopening the door `f8b40be` closed (5 `ALTER TABLE` statements removed as
   policy) is not required by this problem.

---

### S10 — HIGH. `classify_formula_loss` returns `fragmented`, not `image_only`, on this exact input. The architect's new gate hard-requires `image_only`, so the sanctioned classifier and the sanctioned driver disagree.

`formula_recovery.py:64-65`:

```python
if rendered_formula_present:
    return "fragmented" if extracted_text.strip() else "image_only"
```

The image-only span's `extracted_text` is the 51-char placeholder — **non-empty**
→ `"fragmented"`. To obtain `image_only`, a driver must pass `extracted_text=""`,
i.e. must decide the answer before asking the classifier. §26.2 requires a
*measured* loss verdict; hand-setting `loss_verdict="image_only"` is not a
measurement. The architect's Change 1 then raises `ValueError` for any verdict
other than `image_only` (§1.4), so the only way through his own gate is to feed
the classifier a lie or to bypass it. Neither proposal mentions this.

---

### S11 — HIGH. `source_spans.page_number` is a section index, not a physical PDF page, and identical placeholders are deduplicated across the document. Any page-keyed render is aimed at the wrong page for 26% of source 37.

I extracted every span on source 37 whose entire text is a short number — the
printed page footers — and compared to the stored `page_number`:

```
page_number 5  → printed footers "5" AND "6"
page_number 18 → printed footers "18" AND "19"
page_number 23 → printed footers "23","24","25","26","27"
```

`MAX(page_number) = 23`, 21 distinct values, for a 27-page paper. **Physical
pages 24–27 are all filed under `page_number = 23`** (146 spans). A driver that
renders `locator.page = span.page_number` renders the wrong physical page for 7
of 27 pages, and for `page_number=23` it has a 1-in-5 chance.

Second mechanism: **`upsert_source_span` deduplicates by `(source_id,
content_hash)`** (`db/_entities.py:128-136`), and the placeholder's entire text
is `**==> picture [W x H] intentionally omitted <==**`. **Any two discarded
images anywhere in the source with identical pixel dimensions collapse into one
row, which keeps the *first* occurrence's `page_number`.** The briefing's own
numbers show it: **158** discarded picture blocks, **95** rows. ~63 images have
no row at all, and 95 rows may carry a page number belonging to a different
image on a different page. Inline glyphs (`[17 x 30]`, `[36 x 16]`, `[39 x 25]`)
are the likeliest colliders, but nothing prevents two display equations from
colliding.

Every proposal treats "130 placeholder spans" as the complete inventory. It is
the *deduplicated* inventory; the real count is 158+ vault-wide. Product
honesty's Surface-1 wording ("95 equation-like regions on 17 pages") therefore
under-reports the loss by ~40% while claiming precision — a self-inflicted
honesty defect in the honesty proposal.

---

### S12 — MEDIUM. The `w >= 3h` triage filters nothing on the reported case, and its 48/54/28 split is the one number nobody re-derived.

All three flanking placeholders around `KNU-63af4c5c` classify `equation_band`,
including `SPAN-a23f9d4e` (178×11), the display equation for the *preceding*
claim. The heuristic cannot separate "this claim's equation" from "the previous
paragraph's equation" — its only job in the architect's gate. Separately, the
48/54/28 split is the only figure the convener did not reproduce and the
guardian explicitly declined to check (their Con #3); a two-line
`\begin{aligned}` block is squarer than 3:1 and lands in `figure`, a wide
caption strip lands in `equation_band`. Every cost estimate ("25 pages, 48
regions") inherits it.

---

### S13 — MEDIUM. P3 breaks `hydrate_span_text`'s contract in a way that circularly disables `recover_formula`.

RAG §1.5 P3 (adopted verbatim by the architect, §1.1 P3): *"Mirror the same
append in `pipeline/compile.hydrate_span_text` … but the `content_hash`
verification must still run against the raw text."* One function cannot both
return augmented text and be the source of raw text whose `sha256[:16]` equals
`content_hash` — and `recover_formula` requires exactly the latter
(`formula_recovery.py:127-131`, pinned by
`test_plan_b_formula_recovery.py:208-224`). **A driver that builds
`raw_span_texts` from a P3-augmented `hydrate_spans` can never reach
`reviewed`.** `hydrate_span_text` is a *verification* primitive
(SEARCH_ENGINE_SCHEMA §10.2 / F10, `compile.py:200-208`); augmentation belongs
in a separate `hydrate_span_evidence()`.

One fear I can retire for both: Phase A reads `spans[i].text` directly
(`compile.py:329-332`), **not** hydration, so P3 creates no extraction feedback
loop. The hash circle is the real defect.

---

### S14 — MEDIUM. 159/480 and 99/171 are upper bounds of unknown tightness; every proposal quotes them as coverage floors.

The query joins on `rowid ± 1`. Per S3 that order is broken at every re-ingest
boundary; per S11 placeholder rows are deduplicated to first occurrence. Both
distortions manufacture *spurious* adjacency (a page-2 image beside a page-23
reference) as readily as they destroy real adjacency. The number is
reproducible — I do not dispute the reproduction — but it measures "claims whose
citation is one *insertion-order position* from a deduplicated placeholder row,"
not "claims whose equation is one span away." Until A3 lands, no percentage
built on it belongs in a plan.

---

### S15 — MEDIUM. Definition-of-done drift: success is defined on `KNU-63af4c5c`, the user asked about "수식 26", and nobody established the two are the same deliverable.

I accept the convener's content mapping. But the user typed an equation
*number*; spans containing "(26)" number **0**; the page-11 prose references
"(27)" and "(28)". Both the RAG analyst (Con #4) and the architect (§1.7) concede
"수식 26" may stay lexically unmatchable even after a *successful* recovery.
That concession quietly redefines done: a plan whose Tier 2 is
`KNU-63af4c5c.formula_status == 'linked_evidence'` can be fully green while the
user's question still fails. Resolve before coding, not in a Con list. See A12.

---

## 2. Suggested Alternatives

Ordered so that each is independently shippable and each earlier item unblocks
the later ones. **A1, A2 and A10 are mandatory; without A1+A2 nothing else in
the recovery route can produce a user-visible result.**

### A1 — Fix the acceptance gate before writing one line of driver code. (Blocks S1.)

Two edits in `pipeline/formula_recovery.py`, plus a spec change.

```python
# new, pure, table-driven; ~30 lines, no provider
_TRANSCRIPTION_ALIASES = {r"\top": "T", r"\intercal": "T", r"\mathsf{T}": "T"}
_WRAPPERS = (r"\boldsymbol", r"\mathbf", r"\bm", r"\vec", r"\mathrm")

def canonical_formula_tokens(latex: str) -> tuple[str, ...]:
    """Token sequence with transcription-only variation removed.

    Strips \\tag{...}/\\label{...}, unwraps single-argument style macros
    (\\boldsymbol{\\lambda} -> \\lambda), unwraps single-token brace groups
    (^{T} -> ^T), maps transpose spellings to a canonical token, and drops
    trailing punctuation. Operator order, grouping, and direction are NOT
    touched -- a^b != b^a still holds.
    """
```

Then:

```python
claim_formulas = [canonical_formula_tokens(v) for v in _extract_latex(unit["statement"])]
recovered = canonical_formula_tokens(latex)
structurally_matches_claim = any(
    _is_formula_subsequence(f, recovered) or _is_formula_subsequence(recovered, f)
    for f in claim_formulas
)
```

This aligns the acceptance gate with the *same* predicate
`validate_claim_support` already trusts (`claim_support.py:343`), removing the
S1 asymmetry. Spec work is a hard prerequisite: SCHEMA §20.4's "must exactly
match" and §26.2's "does not exactly match" both become "must canonically match
(transcription-normalized, ordered, direction-preserving)."

**Acceptance test, written first, from the S1 table:** all 8 variants accept;
`\lambda^T Q \lambda - q^T \lambda = 0` (sign flipped), `q^T Q \lambda +
\lambda^T \lambda = 0` (operands swapped), and `… = 1` reject. If that table does
not pass, the recovery route does not ship.

### A2 — Give `validator_trace_id` a producer: independent second-pass agreement. (Blocks S1.)

Add a third sanctioned validator form to §20.4 alongside "deterministic gold
check" and "recorded human review": **two independent transcriptions of the same
crop must canonically agree.** The driver calls the extract client twice
(different provider where configured, else same model with a distinct prompt at
`temperature=0`), records the second call via `db.record_prompt_run`
(`db/_entities.py:2687`), and passes that `PTR-` id as `validator_trace_id` only
when `canonical_formula_tokens(a) == canonical_formula_tokens(b)`. Cost: 2× over
≤48 regions. This satisfies "parseable LaTeX alone verifies nothing" without
inventing a human in the loop, and it is the only mechanism proposed anywhere
that makes `reviewed` reachable without weakening evidence.

### A3 — Delete rowid adjacency. Populate `start_char`/`end_char`, which already exist and are always NULL. (Fixes S3, S14.)

`_block_spans` (`pipeline/source_spans.py:44-78`) already knows every span's
offsets (`m.start()`/`m.end()` for blocks, the `cursor`/`re.split` walk for
prose). Thread a running per-section offset into `SpanRecord`, pass it through
`store_source_spans` → `upsert_source_span` (parameters already exist,
`db/_entities.py:120-121`), and define document order as `(page_number,
start_char)`. `list_source_spans` (`db/_entities.py:161-166`) **already** orders
by exactly that and is currently sorting on all-NULL columns — this makes an
existing intent true rather than inventing one. `content_hash` hashes `text`
only, so **no span id changes and no citation dangles.** Backfill for the 4
affected sources: re-parse, match by `content_hash`, `UPDATE ... SET
start_char=?, end_char=?`. ~25 lines. Until this lands, no adjacency-derived
number belongs in a plan.

### A4 — Disambiguate the ±1 window with the cue the prose already carries; make ambiguity reported, not silently skipped. (Fixes S4, mitigates S12.)

```python
_EQUATION_FOLLOWS = re.compile(
    r"(written as|given by|expressed as|as follows|becomes|reads|we (?:get|have|obtain))"
    r"\s*[:,]?\s*$", re.I)
_EQUATION_PRECEDES = re.compile(r"^\s*(where|with|here|note that|in which)\b", re.I)
```

Pair the loss span *after* a cited span matching `_EQUATION_FOLLOWS`, *before*
one matching `_EQUATION_PRECEDES`. On `KNU-63af4c5c`, `SPAN-6df340cb` ends with
"…can thus be **written as**" ⇒ take the *following* span
(`SPAN-2a02b227`) — a determined pairing where RAG skips and the architect
coin-flips. When no cue fires, emit a `wiki lint` entry naming *both* candidates
with their pages and dimensions, and recover nothing. Table-driven, one test row
per regex; the false-positive cost is bounded by A1's match gate.

### A5 — Stop deduplicating discarded-image spans. (Fixes S11's second mechanism.)

In `spans_from_sections`, for spans matching the placeholder regex only, hash a
position-qualified string: `_hash(f"{toc_id}|{ordinal}|{text}")`. Discarded-image
spans are cited by **0** knowledge units vault-wide (measured, and re-confirmed
by me), so the id churn dangles nothing — this is the one place in the schema
where an id change is provably free. Result: one row per discarded image (158+,
not 95), each with its own true page and position. Ship this together with A3
and a single backfill pass over the 4 sources; both are pure L1 re-derivation
with no LLM and no unit mutation.

### A6 — Capture the real bounding box, or stop calling it selective recovery. (Fixes S2.)

Do not patch vendored pymupdf4llm. In `parsers/pdf.py`, after
`pymupdf4llm.to_markdown(..., page_chunks=True)`, run a second `fitz` pass per
page collecting image/drawing rects, match each `[W x H]` placeholder to the rect
with those dimensions on that page, and carry `[x0,y0,x1,y1]` into
`SpanRecord.metadata.loss.region` — **the four-element shape SCHEMA §20.4 and
`test_plan_b_formula_recovery.py:105` already require.** Where two same-size
rects share a page, record `region: null` and mark the span non-recoverable.
Then `crop_hash` is computable and §26.2's "recovers only measured-loss regions"
is true rather than asserted. **If the Arena declines A6 it must delete P4 and
say plainly that region recovery is not being built** — a page-level VLM recovery
action is out of contract regardless of locator vocabulary.

### A7 — Make recovery durable, or declare it explicitly ephemeral. (Fixes S5, S6.)

1. `compile.py:986-987` — `recompile_source` must not re-validate a recovered
   unit against bare previews: pass augmented span texts (mirroring
   `formula_recovery.py:190-208`), or skip re-validation for units whose only
   outstanding formula evidence is a `reviewed` recovery.
2. `claim_support.py:690` — extend the carry-forward guard so a unit holding a
   recovery-created `verified` `formula` support row is carried forward rather
   than retired at line 707, **or** re-apply the anchor idempotently after
   `reconcile_source` in the same transaction (guardian's option (a)).
3. `run_compiler_audit` — add the missing converse of assertion 5: a `verified`
   `formula` support row on a unit that is not `linked_evidence` is an
   inconsistency. `claim_support.py:531` checks one direction only, which is
   exactly why S5 is silent.

### A8 — Ruling on the three-way linkage disagreement.

**Adopt the architect's placement, on the guardian's reasoning, with the RAG
analyst's locator deleted and replaced by A3+A4+A5.**

- **Reject the RAG analyst's bulk up-front `UPDATE` of 99 rows.** Its safety
  proof concerns *verdict monotonicity*, which is correct and beside the point:
  it does not justify permanently editing the citation surface of 99 published
  claims for work that, per S1, succeeds for roughly 0–2 of them. The 97+
  failures leave an unexplained extra citation behind.
- **Adopt the architect's placement** — one span, one unit, inside the existing
  `reviewed` gate, immediately before the existing `validate_claim_support`
  call. Correct, for a reason he did not give: `validate_claim_support` reads
  `declared` fresh from the DB (`claim_support.py:310-316`), so the write can
  land neither later nor earlier. **Strike his §1.8 spec edits as written** —
  they legalize an exception to an invariant that does not exist (S7). Replace
  with one §20.2 sentence naming `_reuse_verified_candidate`
  (`claim_support.py:564-574`) and accepted `image_only` recovery as the **two**
  sanctioned post-creation writers of `source_span_ids`.
- **Adopt the guardian's durability requirement, reject remedy (b)** — (b) is
  not "optional linkage," it is "no recovery" (S7). Take remedy (a): re-derive
  and re-apply the anchor idempotently after every reconcile/publish, in the
  same transaction (A7.2).
- **Delete the duplicated predicate** the architect's own Con #2 flags:
  `locate_image_only_loss` and `_adjacent_image_loss_span_ids` must be one
  shared function.

### A9 — Build the narrow L1 refresh, and scope `--force`. (Fixes S8.)

Product honesty deferred the (a)/(b) choice; take (a). Add
`wiki sources refresh-l1 [--source-id N]`: re-run `_section_dicts` +
`_build_structural_source_guide` + the CTX `page_writer` write, touching **no**
`l*_status` column and no DB row. ~30 lines, no LLM. Independently, fix
`commands/core.py:680-704` so `--force` scopes to the sources named or discovered
in the current invocation, instead of arming a full-vault LLM rebuild that any
user can trigger by accident.

### A10 — Ship Route C first, alone, and correct its numbers. (The only work here that cannot no-op.)

Product honesty items 1–2 (`ingest_raw.py:1094` marker; `UNRESOLVED_NOTE`
tightening) are string edits with no dependency on anything above, and I verified
their key structural claim: `_section_preview` feeds the CTX body, which
`_durable_l1_projection` (`plugin_api/pdf.py:62-95`) parses and serves as the
plugin's PDF chat context. The marker fix repairs the exact surface the bug
occurred on and does **not** touch `source_spans`, so `content_hash` and every
span id are unaffected. Two corrections before it ships: user-facing counts must
not be "95 regions" (S11 — that is the deduplicated count; ship A5 first or say
"at least N"), and any "page N" must be labelled a document section index until
A6/S11 are resolved. By product honesty's own §1.2 standard — "specificity is
strictly more honest *when it is true*" — "page 22" is currently not true.

### A11 — Fix the sync clock with zero DDL, zero `SCHEMA_VERSION` bump, zero mixed-peer outage. (Replaces guardian §1.6 Steps 1–4; keeps Step 5.)

Every writer of `source_spans.metadata` already does a read-modify-write of a
JSON object (`formula_recovery.py:161-176`, `:280-284`, plus the backfill). Have
them also set a top-level scalar `metadata["revision"] = _now_iso()`. Then:

```python
# db_sync.py
_UPDATED_AT_COL["source_spans"] = "created_at"   # unchanged, no DDL
_REMOTE_TS_FN["source_spans"] = lambda row: (
    _json_get(row.get("metadata"), "revision") or row.get("created_at") or ""
)
_LOCAL_TS_FN["source_spans"] = ...               # new, symmetric to the above
# _local_max_ts: per-table expression instead of a bare column
"source_spans": "MAX(COALESCE(json_extract(metadata,'$.revision'), created_at))"
```

`_REMOTE_TS_FN` already exists for exactly this purpose (`db_sync.py:114-116`,
consumed at `:1245-1250` and `:1363`); the only new pieces are its local-side
twin and a per-table expression in `_local_max_ts` (`db_sync.py:1649-1654`).
**No `ALTER TABLE`, no trigger, no `SCHEMA_VERSION` bump — so no import
rejection at `db_sync.py:812-815`, no silent peer skip at `:1551-1554`, and
`f8b40be`'s policy stays closed.** ~20 lines against the guardian's column +
trigger + version bump + one-way-door caveat. Keep their Step-5 backfill; under
this design writing `metadata.revision` *is* the clock.

### A12 — Settle the definition of done against the user's actual question before coding. (Fixes S15.)

Two acceptable answers; the plan must pick one in writing:

- **(i) Content.** `wiki query "equation 26 … Q, q, quadratic vs linear"` returns
  the recovered LaTeX with a `SPAN-` citation. Requires A1+A2+A6 plus a truthful
  section-index → physical-page mapping (S11).
- **(ii) Honest location.** *"Equation (26) is on <physical page>; this source
  stores it as an image and its content was never extracted. 158 such regions
  exist in this document."* Requires only A5+A10 — no provider, no VLM, one
  small PR.

Sequencing: **ship (ii) now** (A10+A5+A9+A11, no LLM anywhere in that set) and
gate (i) behind a *measured* acceptance-rate experiment — run A1's canonicalizer
plus A2's double transcription over 10 of the 48 candidate regions and report how
many clear the gate. **If fewer than 3 of 10 clear it, do not build P4.** That
number, not an architecture argument, decides whether Route A is real.

---

## Which proposal survives contact

- **`01_proposal_product_honesty.md` — survives; the only proposal whose core
  deliverable cannot become a no-op.** Its Surface-3 trace is correct (verified
  independently) and it found the highest-blast-radius latent bug in the Arena
  (S8), under-priced by 9×. Its counts need the S11 correction before they reach
  a user.
- **`01_proposal_schema_guardian.md` — survives in diagnosis, fails in
  prescription.** §1.0 is the single most valuable finding here and must be fixed
  before anything writes to `metadata`; §1.3's rejection of a synthetic unit is
  airtight and should be adopted verbatim. §1.6's migration is wrong on three
  counts (S9) and unnecessary (A11); §1.4's mechanism is wrong (S6) and remedy
  (b) is Route C mislabelled (S7).
- **`01_proposal_architect.md` — right placement, wrong reasons, one false "I
  checked this" (S5).** Adopt its P2 wiring; discard every argument offered for
  it (S7). Its live-adjacency gate filters nothing on the reported case (S4).
- **`01_proposal_rag_analyst.md` — best forensics, worst deliverable.** §1.1's
  six-step trace and §1.3's "recovered LaTeX reaches no reader" table are the most
  useful pages written here. But its locator **skips the user's own claim** (S4),
  its up-front batch write is unjustifiable at S1's acceptance rate, its
  `region: [w,h]` breaks the §20.4 locator contract and makes cropping impossible
  (S2), and its P3 creates a hash circle that disables `recover_formula` (S13).

**The hybrid that survives:** product honesty's four surfaces (A10) + the
guardian's §1.3 rejection and §1.5 metadata shape + A11's zero-DDL clock, shipped
first and alone as the honest-failure release; then A1+A2+A3+A4+A5+A6 as the
enabling work; then the architect's P2 placement (A8) with A7's durability edits,
and only if A12's 10-region acceptance experiment clears its bar.

Ship the recovery route without A1 and A2 and it is the third no-op, on the
record, for the third time.
