# v0.49.0 Image-Only Formula Loss — Make It Visible, Not Silent

Date: 2026-08-08
Status: **AWAITING USER APPROVAL** — Arena debate concluded. No code until approved.

Arena record: `.agents/plans/formula_recovery_arena/` — 4 proposals, 1 red-team
critique, 2 convener amendments, every load-bearing claim re-verified against
the live vault DB and the code by the convener.

## 1. Objective

When a source's central equations exist only as rasterized images, the system
must **say so, precisely and everywhere the user looks** — instead of silently
deleting them and answering as though nothing was missing.

**Definition of done**, measurable on the reported case (source 37,
`KNU-63af4c5c`, the "Q, q quadratic vs linear form" claim on page 11):

1. The CTX projection the plugin reads contains a visible marker where the
   equation image was, instead of a blank. Today: `intentionally omitted`
   appears **0** times in `CTX-f3a44022.md`.
2. `wiki lint` names the affected sources with counts and pages.
3. `wiki add` reports the loss at ingest time, only when a source actually lost
   something.
4. Asking the reported question yields an answer that names *what* could not be
   read and *why*, and points at the remedy — without asserting a verified
   absence the code never established.
5. `wiki db import` no longer silently drops a `source_spans.metadata` write.

## 2. Explicit Non-Goals

- **No formula recovery.** This milestone does not transcribe a single
  equation. §5 explains why that is currently impossible, not merely deferred.
- **No blanket page-VLM.** §26.2 forbids it as a recovery action, and nothing
  here escalates to it.
- **No auto-enabling `vision_model`.** Not even via the `main-if-vision`
  fallback — see Locked Decision D3.
- **No re-ingest of the 130 existing placeholder spans** as part of shipping.
  See D5 and the `--force` trap in §5.4.
- **No `ALTER TABLE`.** See D4.

## 3. Strict Quality Conditions & Release Gates

- Every claim in this plan that begins "measured" must be reproducible by
  re-running the query recorded beside it.
- No user-facing string may assert that content is *absent from the document*.
  Only that it *could not be read*. (Regression test required.)
- The ingest warning must not fire on a PDF that lost nothing — verified
  against a text-layer PDF in the testbed.
- Local gates: `scripts/backend-check pytest|ruff|mypy` + plugin Vitest + `tsc`.
- Spec + both guides (EN first, then `_KR`) updated in the same commit.

## 4. Locked Design Decisions (Arena Consensus)

- **D1 — The loss record lives on the SPAN, not the claim.** `formula_status`
  is claim-level and has no value meaning "no claim exists." Image-only loss is
  a property of a span. Store it as a `metadata.loss` JSON key on
  `source_spans`, reusing the existing `LOSS_VERDICTS` enum. (Schema Guardian
  §1.0; Red Team concurs.)
- **D2 — Do not mutate `knowledge_units.source_span_ids`.** The RAG analyst's
  bulk 99-row write is rejected. The span is the source of truth; unit linkage
  stays re-derivable. Red Team additionally proved the RAG analyst's
  `len(cands) != 1` guard would have **skipped the user's own claim** —
  `KNU-63af4c5c` has placeholder neighbours on *both* sides.
- **D3 — `main-if-vision` must NOT auto-fire at ingest.** Antigravity, Claude
  and Codex are all vision-capable, so the fallback would make full-page VLM
  ingest effectively always-on, unattended, up to 300 pages, with no consent
  moment. `_resolve_vision_client(_vcfg, None)` stays as it is; the fix is to
  *tell* the user the slot exists, not to spend their money for them.
- **D4 — Zero DDL.** There are **0** `ALTER TABLE` statements in the entire
  backend (capability removed in `f8b40be`); editing `SCHEMA_SQL` never reaches
  an existing vault. Reopening it for this is rejected. The sync-clock defect
  is fixed without a new column — see D6.
- **D5 — Ordering must not rely on `rowid`.** Measured on source 37: the final
  four spans are `rowid` 11106–11109 carrying pages 2,2,3,3 *after* page 23.
  Any adjacency logic must sort explicitly and tolerate a broken tail.
- **D6 — Fix the cross-device sync clock without DDL.** `source_spans` has no
  `updated_at`; `db_sync.py:87` uses immutable `created_at` as the LWW clock,
  so the `metadata` mutation that shipped `recover_formula()` already performs
  is silently dropped by a peer on import. Fix inside the existing column set
  (D6 detail in P2), not with a new column + trigger.

## 5. Why Recovery Cannot Ship In This Milestone

This is the section that prevents no-op #3. Three independent blockers, each
verified in code by the convener, not inferred:

### 5.1 The acceptance gate rejects faithful transcriptions

`formula_recovery.py:135`:

```python
structurally_matches_claim = recovered_tokens in claim_formulas   # tuple EQUALITY
```

`validate_claim_support` uses a *subsequence* test for the same job
(`claim_support.py:343`, `_is_formula_subsequence`). Recovery is strictly
stricter than validation. The Red Team ran `_formula_tokens` against
`KNU-63af4c5c`'s own formula: **6 of 8 plausible faithful transcriptions
reject** (`^\top` vs `^{T}`, `\boldsymbol{\lambda}` vs `\lambda`, a `\tag{26}`,
a trailing comma). The neighbouring spans show bold λ and equation numbering,
so a *faithful* VLM transcription is exactly what gets rejected; only one that
happens to match the LLM's earlier paraphrase passes.

### 5.2 `reviewed` is unreachable — `validator_trace_id` has no producer

The `reviewed` gate requires `bool(validator_trace_id)`. Every occurrence in
the backend is a parameter, a pass-through, or a column read. **Nothing mints
one.** Both re-entry designs read only `reviewed` rows. So every candidate
would sit at `candidate` forever.

### 5.3 The region cannot be cropped

`recover_formula` wants a `crop_hash` and a `locator`. Measured: placeholder
spans have `metadata = None` — no bbox, no coordinates, no physical page. The
only geometry that survives is `[width x height]` inside the placeholder text.
You cannot locate the image on the page, so you cannot crop it to send to a
vision model. `page_number` does not rescue this: on source 37 it maxes at
**23** for a **27-page** PDF with gaps at 6 and 19 — it is a section index, not
a physical page.

**Combined realistic yield of shipping recovery today: 0–2 regions out of ~48.**
That is the definition of the third no-op, and it is why this plan ships
visibility instead.

### 5.4 The retrofit trap

`wiki add --force` looks like a cheap way to rebuild existing CTX pages, but it
sets `l2_status='pending'`, which `wiki build`'s default selection later picks
up — silently triggering a full, expensive L2/L3 rebuild. Red Team measured the
blast radius as **all 36 sources**, not the 4 assumed. No retrofit rides in
this milestone.

## 6. Evidence Ledger

Reproduced by the convener against
`.cache/vaults/13ed51f8b06cb88e/state.sqlite` and the code, 2026-08-07/08:

| fact | value |
|---|---|
| source 37 spans / placeholder-only spans | 643 / 95 |
| placeholder occurrences across page text | 158 |
| placeholder spans vault-wide | 130 |
| units citing any placeholder span | **0** |
| `uncertain` units citing an *adjacent* span (vault / src 37) | 159 of 480 / 99 of 171 |
| `CTX-f3a44022.md` occurrences of `intentionally omitted` | **0** |
| `source_sections_inline` for source 37 | `false` |
| `ALTER TABLE` statements in backend | **0** |
| `source_spans` LWW clock (`db_sync.py:87`) | `created_at` (immutable) |
| placeholder span `metadata` | `None` |
| `page_number` max vs physical pages (src 37) | 23 vs 27 |
| `rowid` tail inversion (src 37) | 4 spans, pages 2–3 after page 23 |

**Red-team claim NOT confirmed:** "placeholders dedupe by `content_hash`
(158 → 95)". Measured: 95 placeholder rows with 95 distinct `content_hash` and
95 distinct `text_preview` — no dedupe collapse. The 158/95 gap is a
counting-basis difference (occurrences in page text, including inline ones,
versus spans that are *only* a placeholder). Do not build on the dedupe claim.

**Dirty worktree:** none at plan time; `formula_recovery_arena/` is untracked
and lands with this plan.

**Rollback:** every phase is additive and revertible by `git revert`. No
destructive DB operation. P2 touches sync bookkeeping only.

## 7. Execution Phases

- **P0 — Baseline.** Record current behaviour as tests: the CTX projection has
  no marker, `wiki lint` reports nothing, a `metadata` write is dropped on
  import. These must fail at P0 and pass at the end.
- **P1 — Contract Specification.** SYSTEM_BEHAVIOR §26.2b (span-level loss
  record + reporting duty) and SCHEMA `metadata.loss`. Guides EN then `_KR`.
  **STOP for approval** — this defines a stored contract.
- **P2 — Sync clock (D6).** Make a `source_spans.metadata` mutation survive
  `wiki db import`. Zero DDL. Verify with a two-vault import round-trip.
  Cross-referenced into milestone 03's B2 so it is not solved twice.
- **P3 — Classify at ingest.** Write `metadata.loss` when a span is a picture
  placeholder. Backfill the 130 existing spans with a one-shot Python pass
  (regex over `text_preview`, no LLM, no re-ingest).
- **P4 — Stop erasing the marker.** `_section_preview` (`ingest_raw.py:1094`)
  emits a compact marker instead of a blank, so the CTX body — and therefore
  `_durable_l1_projection` and the plugin's chat context — shows the gap.
- **P5 — Report it.** `wiki lint` check + `wiki add` summary, gated so a clean
  PDF never nags. Name counts and pages; point at `llm.vision_model`.
- **P6 — Chat wording.** Tighten `UNRESOLVED_NOTE` to name the mechanism when
  a `metadata.loss` record exists for the region, still never asserting the
  content is absent from the document.
- **P7 — Testbed smoke.** `VAULT_ROOT=testbed wiki add/lint` on a PDF with
  image equations and one without.

## 8. Scope Exclusions & Stop Conditions

**Exclusions (own milestone, blocked on §5):** formula recovery. Its three
prerequisites are now named and must be planned together — align the
recovery gate with `_is_formula_subsequence`, build a `validator_trace_id`
producer, and persist a real region locator (page + bbox) at parse time.
Without all three, recovery is unreachable regardless of provider quality.

**Stop conditions:**
- Stop if P2's round-trip still drops the write — that means the LWW model
  needs a design change, not a patch, and B2 owns it.
- Stop if P4's marker changes any existing L1 snapshot test in a way that
  implies CTX bodies are load-bearing beyond the projection.
- Stop if the backfill finds placeholder spans whose text yields no parsable
  dimensions — report the count instead of guessing.
