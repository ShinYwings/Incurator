# Architecture Proposal: Anchor Image-Only Loss At Acceptance Time, Not Before — `recover_formula` Verifies Its Own Adjacency, Never Trusts A Cached One
Date: 2026-08-08 | Agent Persona: Lead Architect

## 0. Where I stand relative to the RAG analyst

`01_proposal_rag_analyst.md` made one finding that changes the whole debate: on
source 37, **99 of 171 `uncertain` units (58%) cite a span rowid-adjacent to an
image-only placeholder**, vault-wide 159/480 (33%). I re-ran a scoped version of
that query myself against the same DB
(`.cache/vaults/13ed51f8b06cb88e/state.sqlite`, live, today) and it holds:

```
$ sqlite3 .cache/.../state.sqlite "SELECT rowid,id,page_number,
    (text_preview LIKE '%intentionally omitted%'),substr(text_preview,1,60)
    FROM source_spans WHERE source_id=37 AND page_number=11 ORDER BY rowid;"
...
10731  SPAN-6df340cb  11  0  This is a quadratic equation in λ1 and λ2, and can thus be writt...
10732  SPAN-2a02b227  11  1  **==> picture [158 x 12] intentionally omitted <==**
10733  SPAN-3e733dc3  11  0  Note that there is no constant term since det(p0,p0...
```

`KNU-63af4c5c` (`source_span_ids = ["SPAN-6df340cb","SPAN-3e733dc3","SPAN-3ba9d089"]`,
`formula_status='uncertain'`) states: *"The 2D collinearity condition can be
expressed as a quadratic equation `$\lambda^T Q \lambda + q^T \lambda = 0$`
without a constant term because..."* — and `KNU-a9c4e5c5`
(`source_span_ids=["SPAN-3e733dc3"]`) states the Lagrangian combining it with a
linear constraint, `$L(\boldsymbol{\lambda},\mu) = \boldsymbol{\lambda}^T A
\boldsymbol{\lambda}...$`. **This is the user's own question** — *"A,b Q,q
정의가 불명확하고 quadratic form과 linear form 두개가 왜 있는것인지"* — not a
representative sample, the actual claim cluster, sitting one rowid from
`SPAN-2a02b227`. I did not have to guess whether the adjacency finding applies
to the reported case; I checked. It does. This proposal is built to fix exactly
this pair, not a statistical abstraction of it.

So I do not dispute Route A's viability — I dispute **how the RAG analyst
proposes to wire it**. Their §1.3/§1.5 `anchor_loss_span` mutates
`knowledge_units.source_span_ids` for all 99 matched units **up front**, before
any recovery is attempted or accepted, via a plain `UPDATE`. I read this as
architecturally wrong for three independently-sufficient reasons, and I build
an alternative around fixing them:

1. **Zero existing precedent.** I grepped the entire backend for any write to
   `knowledge_units.source_span_ids` after row creation. There is none — the
   only tables whose `source_span_ids` are ever additively grown post-creation
   are `graph_entities` and `entity_aliases`
   (`backend/src/curator/db/sources.py:270,278`,
   `backend/src/curator/db/_entities.py:340,870,960` — Plan C entity-resolution
   merges, a *different* table with a documented growth contract). Introducing
   the **first-ever** mutation of `knowledge_units.source_span_ids` deserves a
   narrower, more defensible trigger than "the locator's confidence is high
   enough," applied to 99 rows unconditionally.
2. **The schema's own words treat it as fixed, not grown.** SCHEMA.md §20.2:
   *"a `knowledge_units` row's `source_span_ids` array remains the citation
   surface"* (of the LLM extraction, §26.1: *"Extraction... must declare, per
   claim, the minimal span set"*). §20.5's audit rule for a `formula` support
   row requires *"the support's `source_span_id` must still be in the unit's
   **declared** `source_span_ids`"* and states *"Recovery always attaches to a
   cited span, so a valid link is never dropped"* — written as if citation
   always **precedes** recovery, never the reverse. §22.5, a different
   subsystem, states the blanket principle even more plainly: *"`source_span_ids`
   is never mutated."* Amending it for 99 units, before any recovery succeeds
   or even runs, treats a stated invariant as negotiable by convenience.
3. **It commits the citation before knowing the recovery is any good.** The
   RAG analyst's `anchor_loss_span` runs *before* `recover_formula`, for every
   matched unit, regardless of whether the eventual VLM crop clears the 0.80
   threshold. A wrong crop, a timeout, a `candidate`-status rejection — the
   citation is already permanent. That is not fatal (their §1.3 monotonicity
   proof is correct: it cannot manufacture `failed`), but it is an unforced,
   irreversible write for work that has not yet been shown to succeed.

**My fix: move the same write to the one moment that already exists in
`recover_formula` for exactly this purpose — the `reviewed` gate — and make
the eligibility check re-verify adjacency live against current DB state at
that moment, instead of trusting a precomputed batch amendment.** No new
table, no new metadata field, no schema migration, and the touched function
already carries the acceptance machinery I need.

## 1. Core Logic & Implementation

### 1.1 Route decision

**Staged A (inner) + C, B deferred by explicit, priced choice — same top-level
shape as the RAG analyst, different P2 wiring.** I adopt without re-derivation:

- **P0/P0b (credit: RAG analyst §1.5)** — deterministic, no-LLM span
  classification (`omitted_region: {width, height, kind}` on
  `source_spans.metadata`, via `pipeline/source_spans.py`) plus a one-shot
  backfill migration for the 130 already-ingested placeholder spans. I checked
  their central claim independently — `text_preview` is 51–84 chars for every
  placeholder span I sampled (page 4, page 11 above), all under the 200-char
  cap — so the backfill is pure SQL/JSON over stored data, zero re-parse, zero
  LLM, zero span-id churn. I have no argument with this piece; it is the
  correct foundation and Route C needs it regardless of what P2 does.
- **P1 (credit: RAG analyst §1.5)** — stop stripping the loss at
  `ingest_raw.py:1094`, add a `wiki lint` check, add a Source Guide summary
  line. Required for honest reporting of the ~72 non-adjacent `uncertain`
  units on source 37 and any truly-orphaned placeholder span with no nearby
  claim at all — Route A recovers a majority slice, not everything, and the
  remainder must be *reported*, never silently dropped or invented.
- **P2 (mine — §1.4 below)** — the wiring that lets `recover_formula` accept
  an `image_only` span it was not originally cited by, gated on a live
  adjacency check performed inside the acceptance path itself.
- **P3 (credit: RAG analyst §1.3/§1.5)** — I independently traced the same
  five consumers (search body, chunking, evidence hydration, L1 page, claim
  re-validation) and confirm their finding: recovered LaTeX today reaches
  **none** of them except the in-memory re-validation call. Without making
  `retrieval/materializer.py`'s span-doc `body` and
  `pipeline/compile.hydrate_span_text` read `metadata.formula_recovery`, P2 is
  invisible. I adopt their re-entry design as stated; it does not depend on
  which citation-growth mechanism P2 uses.
- **P4/P5** — a targeted `wiki sources recover-formulas` driver, region-scoped
  by construction (only pages named by the locator), and `vision_model`'s
  `_resolve_vision_client(_vcfg, None)` discoverability gap named but **not**
  silently fixed here — same conclusion as the RAG analyst, for the same
  reason: fixing it would turn on full-page VLM ingest for every vision-capable
  main-model user, an unannounced cost change that needs its own decision.

### 1.2 Confronting the briefing's central objection directly

Briefing §2.2/§3: does Route A require "creating a unit from a span that has
no extractable claim"? **No — for the 99/171 (58% on source 37) adjacent
population, the unit already exists and its statement already contains the
correct formula** (`KNU-63af4c5c`'s `$\lambda^T Q \lambda + q^T \lambda = 0$`
was extracted from the surrounding prose — the model inferred the equation's
shape from its own defining sentence, exactly as SYSTEM_TEMPLATE instructs).
What is missing is not a claim; it is **evidence for a claim that already
states the right formula, structurally absent from the span it was forced to
cite** (`validate_claim_support` at `claim_support.py:379-384` calls this out
explicitly in its own comment: *"could be parse loss"*). Recovering that
evidence and binding it to the *existing* unit is not fiction — it is
completing a citation the extractor could not make because the evidence lived
one span away, in a region pymupdf4llm discarded before the extractor ever saw
readable content there.

For the remaining ~42% (source 37) / 67% (vault-wide) of `uncertain` units, and
for any placeholder span with no nearby claim at all, I take the briefing's
warning seriously: **no unit is invented.** They stay `uncertain`/undetected,
surfaced by P1, never routed through P2.

### 1.3 What P2 must NOT do, restated precisely

Locating a candidate pair `(unit_id, span_id)` is cheap and safe — it is a
read. **Persisting that pair into `knowledge_units.source_span_ids` is the
expensive, irreversible, precedent-setting act**, and it is the one thing that
needs a narrower trigger than "the locator found a match." §1.0's three
objections all target that one write. Everything below is designed around
deferring it to the latest safe moment and re-deriving its precondition from
live state rather than caching it.

### 1.4 P2: the citation-growth boundary, inside `recover_formula`

I read `backend/src/curator/pipeline/formula_recovery.py` in full (309 lines).
Current precondition (lines 96–116):

```python
with db.connect(db_path) as conn:
    span = conn.execute(
        "SELECT content_hash, text_preview, metadata FROM source_spans WHERE id = ?",
        (span_id,),
    ).fetchone()
    unit = conn.execute(
        "SELECT statement, source_span_ids, formula_status "
        "FROM knowledge_units WHERE id = ?",
        (unit_id,),
    ).fetchone()
if span is None:
    raise ValueError(f"unknown source span: {span_id}")
if unit is None:
    raise ValueError(f"unknown knowledge unit: {unit_id}")
cited_span_ids = json.loads(unit["source_span_ids"] or "[]")
if span_id not in cited_span_ids:
    raise ValueError(f"knowledge unit {unit_id} does not cite source span {span_id}")
if unit["formula_status"] != "uncertain":
    raise ValueError(...)
```

**Change 1 — widen the hard gate, keeping it hard for every case it already
covers.** Add `source_id` to the span `SELECT` (needed for the adjacency
query) and replace the single `raise` with a narrow, verified exception:

```python
with db.connect(db_path) as conn:
    span = conn.execute(
        "SELECT content_hash, text_preview, metadata, source_id "
        "FROM source_spans WHERE id = ?",
        (span_id,),
    ).fetchone()
    unit = conn.execute(
        "SELECT statement, source_span_ids, formula_status "
        "FROM knowledge_units WHERE id = ?",
        (unit_id,),
    ).fetchone()
    if span is None:
        raise ValueError(f"unknown source span: {span_id}")
    if unit is None:
        raise ValueError(f"unknown knowledge unit: {unit_id}")

    cited_span_ids = json.loads(unit["source_span_ids"] or "[]")
    newly_anchored = span_id not in cited_span_ids
    if newly_anchored:
        if loss_verdict != "image_only":
            raise ValueError(
                f"source span {span_id} is not cited by knowledge unit "
                f"{unit_id}; only an 'image_only' loss may recover via "
                f"live adjacency, not '{loss_verdict}'"
            )
        neighbors = _adjacent_image_loss_span_ids(
            conn, source_id=span["source_id"], around=cited_span_ids
        )
        if span_id not in neighbors:
            raise ValueError(
                f"source span {span_id} is not rowid-adjacent to any span "
                f"knowledge unit {unit_id} already cites; refusing to "
                f"recover an unanchored span"
            )
        cited_span_ids = [*cited_span_ids, span_id]  # in-memory only here

    if unit["formula_status"] != "uncertain":
        raise ValueError(
            f"formula recovery requires formula_status='uncertain': {unit_id}"
        )
```

`_adjacent_image_loss_span_ids` — new, small, pure-SQL, **same shape as the RAG
analyst's proven locator query**, but scoped to one call and re-run against
**live** rowids every time, not a stored fact:

```python
def _adjacent_image_loss_span_ids(
    conn: sqlite3.Connection, *, source_id: int, around: list[str]
) -> set[str]:
    """Rowid +/-1 neighbors of `around` typed `equation_band` by the P0
    classifier. Recomputed from current DB state on every call — this
    function is the ONLY place that decides adjacency; nothing upstream
    persists an anchor that could go stale relative to a later re-ingest."""
    if not around:
        return set()
    placeholders = ",".join("?" for _ in around)
    rows = conn.execute(
        f"""
        WITH ordered AS (
            SELECT rowid AS rn, id, metadata FROM source_spans WHERE source_id = ?
        )
        SELECT b.id, b.metadata FROM ordered a
        JOIN ordered b ON b.rn BETWEEN a.rn - 1 AND a.rn + 1 AND b.rn != a.rn
        WHERE a.id IN ({placeholders})
        """,
        (source_id, *around),
    ).fetchall()
    return {
        r["id"]
        for r in rows
        if json.loads(r["metadata"] or "{}").get("omitted_region", {}).get("kind")
        == "equation_band"
    }
```

This is a code-level guard the P4 driver's `locate_image_only_loss()` (P1's
read-only discovery pass, unmodified from the RAG analyst's version) cannot
bypass by construction: even if the driver's cached candidate list is stale —
spans re-ingested, rowids shifted between "locate" and "recover" — `recover_formula`
re-derives the pairing itself and **fails closed** rather than trusting a
precomputed anchor. This directly answers the RAG analyst's own Con #1 ("`rowid`
as document order is an implementation detail... I would not defend it"): I
don't need to defend a cached fact, because nothing caches one.

**Change 2 — the hydrated-text hash check (existing lines 117–131) needs no
edit.** It already iterates `cited_span_ids`, which by this point in the
function is the extended local list when `newly_anchored`. The caller (P4
driver) must now additionally pass `raw_span_texts[span_id] = <the loss
span's own hydrated placeholder text>` for a first-time anchor — trivial,
since P0b already established that text is the complete `text_preview` for
every placeholder span, no re-parse needed. Reusing the SAME `"missing
hydrated source span for revalidation"` error (line 124) for an omitted entry
means zero new error paths.

**Change 3 — persist the citation only at acceptance, in the existing
metadata block's neighborhood.** Current code (lines 133–180, unchanged
through the metadata append) computes:

```python
reviewed = (
    confidence >= acceptance_confidence
    and bool(validator_trace_id)
    and structurally_matches_claim
    and raw_span_texts is not None
)
status = "reviewed" if reviewed else "candidate"
candidate = {...}
# ... existing read-modify-write of source_spans.metadata.formula_recovery ...
```

Immediately after that block (still before `if not reviewed: ... return
candidate`), add the one new `UPDATE` — the entire P2 write surface:

```python
if reviewed and newly_anchored:
    with db.connect(db_path) as conn:
        conn.execute(
            "UPDATE knowledge_units SET source_span_ids = ? WHERE id = ?",
            (json.dumps(cited_span_ids, ensure_ascii=False), unit_id),
        )
```

Everything downstream — the existing `if not reviewed: ...`, the existing
`augmented_span_texts` construction loop (lines 190–208, unmodified, now
naturally walks `span_id` too since it is in `cited_span_ids`), the existing
`validate_claim_support(db_path, unit_id, span_texts=augmented_span_texts)`
call, the existing `upsert_claim_support`/`set_unit_formula_status` success
path — **runs completely unmodified**. `validate_claim_support` re-reads
`unit["source_span_ids"]` fresh from the DB (`claim_support.py:310,315`
`_load_unit`), so it sees the just-persisted extension and correctly includes
`span_id`'s (now formula-bearing) text in its `_load_spans` pass
(`claim_support.py:221`, `for sid in declared`) — I verified this by reading
`_load_unit`/`_load_spans` line-by-line; there is no other path by which a
non-declared span's text would ever reach the validator, which is exactly why
the write has to happen before this call and cannot be deferred further, and
exactly why it cannot happen any earlier than the `reviewed` gate without
reintroducing the RAG analyst's up-front-commitment problem.

**A `candidate`-status (unreviewed) attempt on a newly-anchored span never
writes to `knowledge_units` at all** — it returns at the pre-existing `if not
reviewed: ... return candidate` line having only appended to
`source_spans.metadata.formula_recovery` (already-additive, already
lifecycle-gated, unchanged). A low-confidence crop, a missing validator trace,
or a non-matching LaTeX leaves the unit's citation surface exactly as the
extractor declared it. Only a candidate that already cleared 0.80 confidence,
carries a validator trace, and structurally matches the owning claim's own
formula gets to touch `source_span_ids` — and even then, only that one
candidate's own span_id, never a batch.

### 1.5 Why this survives `invalidate_formula_recoveries` and `recompile_source` unmodified

- **`invalidate_formula_recoveries` (formula_recovery.py:232–309) needs zero
  changes.** A page-hash change flips the candidate to `rejected`, marks the
  `claim_supports` formula row `stale`, and sets `formula_status='uncertain'`
  — exactly as today. It does **not** remove `span_id` from
  `source_span_ids`, and per SCHEMA §20.5's own text (*"Recovery always
  attaches to a cited span, so a valid link is never dropped"*) it should not:
  the citation asserts *where the equation lives*, which a page edit does not
  change; only the *transcription's trust* goes stale, which the existing
  status flip already handles.
- **`recompile_source` (compile.py:933–1024) needs zero changes, and I checked
  this specifically because it is the one place a naive version of this idea
  breaks.** Its fast path (`_audit_content_hash(prior) == fingerprint`, line
  958) keys on `sources.content_hash` only (`_source_content_hash`,
  compile.py:765–770) — untouched by a `knowledge_units.source_span_ids`
  edit. A later `recompile_source` call on source 37 will still take the fast
  path and return the (now-extended) state as-is. That is correct, not a gap:
  `recover_formula` already ran `validate_claim_support` synchronously inside
  the same call that performed the extension, so `support_status`,
  `formula_status`, and `claim_supports` are already internally consistent by
  the time it returns — there is nothing left for a later `recompile_source`
  to re-validate. This is not a new risk category: `recover_formula` already
  mutates `claim_supports`/`formula_status` outside any `GEN-` generation
  transaction today (lines 219–228 of the current file); extending it to one
  more column under the same gate is consistent with, not an escalation of,
  that existing precedent.

### 1.6 What happens to the 130 already-ingested placeholder spans

Same answer as P0/P0b: typed in place by the backfill migration (SQL over
`text_preview`, no re-parse, no LLM, no Zotero round-trip). Of the resulting
`equation_band`-typed spans, P2 recovers the subset live-adjacent to an
`uncertain` unit's existing citation (measured 99/171 on source 37) when the
P4 driver runs a VLM crop that clears 0.80 confidence with a validator trace
and a structural match. The rest — non-adjacent `uncertain` units and
placeholder spans with no nearby claim — are typed and lint-reported (P1),
never fabricated a unit, never silently dropped.

### 1.7 Definition of done, source 37, in two tiers

**Tier 0 (P0+P0b+P1 only, no provider call):**
`SELECT metadata FROM source_spans WHERE id='SPAN-2a02b227'` contains
`omitted_region.kind='equation_band'`; `wiki lint` reports source 37 with its
image-only-region count and page list; asking about the disputed equation
returns an honest, page-located statement — *"page 11 of this source contains
an unrecovered equation image near the claim about the quadratic-form
collinearity condition (Q, q) and its Lagrangian combination with the linear
constraint (A)"* — instead of the current bare failure-to-retrieve.

**Tier 1 (P2+P3+P4, needs one vision call):**
`recover_formula(db_path, unit_id="KNU-63af4c5c", span_id="SPAN-2a02b227",
loss_verdict="image_only", ...)` returns `status="reviewed"`,
`KNU-63af4c5c.formula_status` flips to `linked_evidence`,
`claim_supports` gains a `verified` `support_role='formula'` row for
`(KNU-63af4c5c, SPAN-2a02b227)`, `search_documents.body` for
`SPAN-2a02b227` contains the recovered LaTeX (via P3), and
`wiki query "수식 26 설명좀... Q,q..."` returns prose grounded in the
recovered `$\lambda^T Q \lambda + q^T \lambda = 0$` and, once `KNU-a9c4e5c5`'s
own adjacent span is separately recovered (`SPAN-3e733dc3` is not itself
marked `equation_band` in my sample above — it is prose — so that unit's
formula may already be `preserved_in_text`; this needs the P0 backfill to
confirm, and I do not claim it here), a citation the user can verify against
page 11. I do not claim the literal digit "26" becomes lexically matchable —
the `\tag` lives inside the raster, same limitation the RAG analyst names in
their Con #4, unresolved by either proposal without the VLM transcribing the
tag itself.

### 1.8 Docs/spec changes this requires (P1 phase, before code, per CLAUDE.md)

- **SCHEMA.md §20.2**: add one sentence to the "citation surface" rule
  acknowledging the single narrow exception — *"An `image_only` recovery
  candidate accepted (`reviewed`, ≥0.80, validator trace, structural match)
  against a span rowid-adjacent to an already-cited span MAY append that span
  to `source_span_ids` at acceptance time; no other write path may mutate
  `source_span_ids` post-creation."*
- **SCHEMA.md §20.5**: annotate that the "declared `source_span_ids`" the
  audit checks against may include this one additive class of entry.
- **SYSTEM_BEHAVIOR §26.2**: document the live-adjacency precondition as part
  of the selective-recovery contract, and state explicitly that it is
  re-verified at call time, never cached, so a red-teamer or future reader
  does not have to infer that property from the code.
- **docs/guides/**: document `wiki lint`'s new image-only-region check and
  `wiki sources recover-formulas` (P4), English first then `_KR.md`.

### 1.9 What this proposal does NOT do

- Does not touch `classify_formula_loss`, the 0.80 threshold, the exact-match
  requirement, `invalidate_formula_recoveries`, or any existing test's
  assertions about the `fragmented`/`parser_omitted` path — those are
  unmodified by construction (§1.5).
- Does not recover the ~42% (source 37) / ~67% (vault-wide) of `uncertain`
  units with no adjacent image-only span, nor any placeholder span with no
  nearby claim at all — those stay `uncertain`/untyped-to-a-claim and rely
  entirely on P1's honest surfacing.
- Does not extend adjacency past rowid ±1 — a ±2 or semantic-proximity
  variant is a plausible follow-up but unmeasured; I would rather under-cover
  than guess a threshold with no evidence behind it.
- Does not fix `_resolve_vision_client(_vcfg, None)`'s `main-if-vision`
  collapse (ingest_raw.py:1427) or enable `vision_model` for any source. Both
  are named, priced, and deliberately deferred to a separate decision.
- Does not regenerate L3 concepts or L4 syntheses. Measured (trusting the RAG
  analyst's count, consistent with the materializer's liveness-filter logic I
  independently read at `materializer.py:344-365`): zero reports/syntheses
  cite a placeholder span, so nothing downstream needs invalidation.
- Does not fix the `wiki plugin pdf context --file-path` encryption failure
  named in briefing constraint 6 — real, separate, out of scope.
- Does not attempt equation-number/tag reconstruction beyond whatever the VLM
  transcribes; "수식 26" may remain matchable only by semantic proximity to
  the recovered formula's surrounding prose, not by literal label.

## 2. Pros & Cons

### Pros

1. **Verified against the exact reported case, not a statistical proxy.** I
   traced `KNU-63af4c5c`/`SPAN-2a02b227` on the live DB myself before writing
   this section; it is the user's own "A,b Q,q, quadratic vs linear form"
   question, one rowid from the image that would resolve it.
2. **The one genuinely new/risky write — extending
   `knowledge_units.source_span_ids` for the first time in this codebase's
   history — is minimized to the smallest defensible trigger:** one span, one
   unit, only after that specific candidate has already cleared every
   existing acceptance gate `recover_formula` enforces today. Ninety-nine
   units are never touched speculatively; only the ones whose recovery
   actually succeeds are touched, one at a time, as they succeed.
3. **No cached anchor to go stale.** Adjacency is re-derived from live rowids
   inside `recover_formula` itself at the moment it matters, so a re-ingest
   between "locate" and "recover" fails closed (a `ValueError`) rather than
   silently trusting a fact computed against a DB state that no longer
   exists. This is strictly safer than a locate-then-batch-amend design.
4. **Minimal code-review surface for a narrow, precise change.** One new
   9-line pure function, one restructured precondition block, one new
   3-line `UPDATE` gated on a boolean that already exists
   (`reviewed`). No new table, no new metadata key, no schema migration.
5. **Every existing safety property the RAG analyst proved still holds,
   because I did not touch the code that provides them.** Their §1.3
   monotonicity proof (`max()` over coverage, `union()` over span formulas —
   `claim_support.py:334-354`) applies unchanged: `validate_claim_support` is
   called with an unmodified body, only a different (correctly-persisted, not
   speculative) `declared` set feeding it.
6. **Consistent with, not a new exception to, `recover_formula`'s existing
   contract.** The function already mutates authoritative-generation state
   (`claim_supports`, `formula_status`) outside any `GEN-` transaction on
   every successful call today. Extending it to one more column under the
   exact same gate is the smallest possible generalization, not a new
   mechanism layered on top.

### Cons & Limitations

1. **This is a bigger diff inside a load-bearing, already-tested function**
   than the RAG analyst's "call a separate pre-step, touch `recover_formula`
   not at all" design. Their approach has a smaller blast radius on
   `formula_recovery.py`'s existing test suite; mine restructures the
   precondition block that those tests almost certainly assert against
   directly, and every one of those tests needs re-verification, not just the
   new adjacency path's own tests.
2. **`locate_image_only_loss` (P4's read-only discovery pass) and
   `_adjacent_image_loss_span_ids` (the enforcement check inside
   `recover_formula`) compute the same predicate twice, in two places.** I
   have deliberately not shared one implementation between "what should the
   driver attempt" and "what may `recover_formula` accept," because the
   driver's version can safely be a superset (over-propose, let
   `recover_formula` reject) — but this is a DRY violation a `peer_reviewer`
   should flag, and the Master Plan should require both call sites to import
   one shared predicate function rather than maintain two copies that could
   drift.
3. **Still inherits the RAG analyst's Con #1 at one remove.** Rowid-as-
   document-order is still an implementation detail, not a schema-enforced
   contract (`start_char`/`end_char` remain unpopulated). Re-verifying it live
   makes staleness fail closed instead of silently wrong, but it does not fix
   the underlying fragility; if `store_source_spans`/`upsert_source_span`'s
   insertion-order guarantee is ever weakened, this whole mechanism degrades
   to "recovers nothing" (safe) rather than "recovers the wrong span"
   (unsafe) — I believe that degradation direction is the right one to buy,
   but it is still a real dependency on an unpinned property.
4. **The spec edits in §1.8 are a real prerequisite, not paperwork.**
   SCHEMA.md §20.2/§20.5 currently read as if `source_span_ids` is immutable
   post-creation; shipping this code without first landing that spec
   clarification leaves the contract self-contradictory for the next reader
   who greps for "never mutated" and finds this code doing exactly that.
5. **Coverage ceiling is identical to the RAG analyst's proposal (58% on
   source 37) — this is not a coverage improvement, only a safer wiring
   mechanism for the same coverage.** A reviewer who cares primarily about
   maximizing recovered equations, not about the citation-mutation contract,
   will reasonably see this as solving a problem (premature/batch citation
   commitment) they did not think was the important one.
6. **`raw_span_texts` callers now carry an implicit new obligation** — supply
   the loss span's own hydrated text on a first-time anchor, or the hash-check
   loop raises `"missing hydrated source span for revalidation"` for a span
   the caller may not realize is now part of the cited set. The P4 driver
   must be written with this in mind from the start; it is easy to get right
   once documented, easy to get subtly wrong (a confusing runtime error) if
   the docstring for `raw_span_texts` is not updated to say so explicitly.
7. **Explicitly not resolved here (deferred to `schema_guardian` and the
   Master Plan):** whether a `compiler_generations` audit pass, run
   independently of `recover_formula` (e.g. a future `wiki lint --repair` or
   a scheduled integrity sweep), should re-verify that every `source_span_ids`
   entry beyond the original extraction-time set still satisfies the live
   adjacency predicate — today nothing re-checks this after the fact, so a
   theoretical future change to span ordering could leave a stale-but-never-
   re-audited citation in place indefinitely, differing from case to case
   only in whether `recover_formula` happens to be called again on that unit.
