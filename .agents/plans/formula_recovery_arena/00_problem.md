# Briefing: Image-Only Formula Loss Is Silent And Unrecoverable

Date: 2026-08-07 | Author: main agent (Arena convener)

## 0. Why this briefing exists

Two hotfixes for this bug shipped **no-ops** because they were coded from the
symptom. v0.48.1 widened a page search for a label that was never ingested.
v0.48.4 fixed a real defect (the prompt said nothing when a reference failed)
but does not recover the equation. Anyone who plans from "wire up
`recover_formula()`" without reading §3 below will ship the third no-op.

Every number here was measured against the live `second_brain` vault DB
(`.cache/vaults/13ed51f8b06cb88e/state.sqlite`) on 2026-08-07, not inferred
from code or specs.

## 1. The user-visible failure

User adds a 27-page paper through Reference Mode ("add resource"). Ingest
succeeds — 643 spans, source id 37. User opens page 4, which visibly renders
equations (3) and (4), and asks:

> 수식 26 설명좀. A,b Q,q 정의가 불명확하고 quadratic form과 linear form 두개가
> 왜 있는것인지?

Before v0.48.4 the answer was the provider's own failure text
(`no output produced — ... auto-denied`). After v0.48.4 the assistant correctly
says it could not retrieve equation 26. **It still cannot answer the question.**

## 2. Measured ground truth

### 2.1 The equations were never ingested

- Every displayed equation in this paper is a **rasterized image**. The parser
  emits `**==> picture [W x H] intentionally omitted <==**`.
- **158** discarded picture blocks across all 27 pages (sampled every page).
- **95** of source 37's 643 spans are *nothing but* that placeholder.
- Spans containing `(24)`: **0**. `(25)`: **0**. `(26)`: **0**.
- Page 4, which renders equations (3) and (4), stores only the placeholder.
- `wiki plugin pdf search --source-id 37 --query "(26)"` → **0 hits**.

### 2.2 `recover_formula()` is structurally unreachable for this case

`recover_formula(db_path, *, unit_id, span_id, loss_verdict, locator,
page_hash, crop_hash, provider, model, confidence, latex, ...)` requires:

- a `knowledge_units` row whose `formula_status = 'uncertain'`, AND
- that unit to cite `span_id` in `source_span_ids`.

Measured:

| population | count |
|---|---|
| placeholder spans, vault-wide | 130 |
| units citing **any** placeholder span | **0** |
| units with `formula_status='uncertain'` | 480 |
| of those citing a placeholder-bearing span | **0** |
| source 37 `uncertain` units | 171 |

**There are two disjoint formula-loss populations.** The 480 `uncertain` units
are claims whose formula is present-but-damaged — `recover_formula` serves
those. Image-only equations produce **no unit at all**, because a span whose
entire content is a placeholder yields no claim to extract. The §26.2 pipeline
is anchored to a unit that never exists for this case.

> **AMENDMENT (2026-08-08) — the paragraph above is WRONG, and the correction
> changes the plan.** The RAG/DAG analyst tested *document-order adjacency*
> instead of exact citation, and the convener independently reproduced it:
>
> | population | count |
> |---|---|
> | non-placeholder spans immediately adjacent to a placeholder span | 139 |
> | `uncertain` units citing such a span, vault-wide | **159 / 480 (33%)** |
> | same, involving source 37 | **99 / 171 (58%)** |
>
> The populations are disjoint **by citation** but **adjacent by document
> order**. The equation region and the prose explaining it were one continuous
> piece of the page; the span splitter cut them apart; Phase A extracted a claim
> from the prose half and nothing from the image half. On source 37,
> `formula_status='uncertain'` is predominantly the *downstream signature* of
> image-only loss, mis-anchored by one span position.
>
> **Consequence: Route A does not require inventing a unit.** The owning claim
> already exists. What `recover_formula()` lacks is not a `unit_id` but a
> correct `span_id` — and its precondition `span_id ∈ unit.source_span_ids`
> (`formula_recovery.py:110-112`) is precisely the blockage. The fix is a
> locator, not a fiction.
>
> Caveat for proposals relying on this: `rowid` was used as document order.
> It holds here (3 page-number inversions across 2,363 spans) but is an
> assumption, not a guarantee — a proposal that depends on adjacency must say
> how it establishes ordering robustly.
>
> Proposals written before this amendment may still argue the disjoint framing;
> the red team should judge them against these numbers, not against the
> superseded paragraph.

`classify_formula_loss()` does return `image_only` — but only when handed
`expected_latex`, and its docstring is explicit: "recovery is never scheduled
from an expected formula alone." Nothing produces that expectation here.

Both functions have **0 production call sites** (14 test call sites). That is
true, and it is *not* the root cause of the reported bug.

### 2.3 The sanctioned upstream path exists and is switched off

SYSTEM_BEHAVIOR §26.2a defines `llm.vision_model` — a user-elected, opt-in
full-page vision extractor for `add source` PDF ingest, explicitly "distinct
from §26.2's downstream measured-loss recovery" and motivated by exactly this:
"pymupdf4llm text-layer extraction cannot reliably reconstruct LaTeX for math."

It is **fully implemented** (`ingest_raw.py:1422-1429`, `_apply_vlm_pdf_extraction`,
`_resolve_vision_client`) and **unset in the user's vault** — the slots do not
appear in `second_brain/.curator/settings.yml` at all.

Note for debate: ingest calls `_resolve_vision_client(_vcfg, None)` with
`main_client=None`, so the documented `vision_model → main-if-vision → None`
resolution collapses to `vision_model → None` on this path. Whether that is
intentional is an open question for the Arena.

### 2.3b AMENDMENT (2026-08-08) — the placeholder IS erased on the path the plugin reads

An earlier convener note called `ingest_raw.py:1094` "a preview helper, not the
main text path." That was wrong, and the correction matters for the plan.

`_section_preview` strips the placeholder (`ingest_raw.py:1094`). For a source
where `_should_inline_source_sections()` is false, the CTX **body** is built
from that preview (`ingest_raw.py:1355-1362`), and `_durable_l1_projection()`
(`plugin_api/pdf.py:62-95`) parses exactly that body and serves it as the
plugin's PDF chat context.

Measured on source 37 (`CTX-f3a44022.md`):

- frontmatter: `source_sections_inline: false`, `source_text_policy: on_demand`
- occurrences of `intentionally omitted` in the CTX file: **0**

So the loss is recorded in `source_spans.text_preview` (95 spans keep the
placeholder) and simultaneously **erased** from the durable L1 projection the
plugin actually reads. A reader of the CTX page — human or model — sees prose
with a silent gap where the equation was, with nothing marking it.

Proposals should treat this as a distinct, cheap, no-LLM repair opportunity
separate from any recovery: emitting a compact marker instead of a blank costs
nothing and makes the gap visible on the surface the user hits. Note it only
takes effect for future ingests unless a retrofit path is specified — and see
the `--force` cost trap flagged in the product-honesty proposal before assuming
re-ingest is cheap.

### 2.4 Nothing tells the user any of this

158 equation images were dropped and no surface reported it: not `wiki add`
output, not `wiki lint`, not the job indicator, not the chat. The spans record
the loss (placeholder text, page number, image dimensions) and nothing reads
it. The user's own framing: *"이거 add resource로 knowledge system에 입력한거임.
시스템이 제대로 동작 안한다는거지"* — it was added correctly, and the system
still does not work.

## 3. The question for the Arena

**Not** "how do we call `recover_formula()`." The question is:

> When a source's central equations exist only as images, what should the
> system do — at ingest, at lint, and at query time — and which of the three
> candidate routes actually fixes the measured case without violating §26.2's
> explicit prohibitions?

Candidate routes, to be argued and attacked, not assumed:

- **A — Downstream recovery (§26.2).** Make image-only loss produce the
  `uncertain` unit the pipeline needs, then call the existing classifier and
  recovery. Requires creating a unit from a span that has no extractable claim.
  Argue whether that is coherent or a fiction invented to satisfy an API.
- **B — Upstream vision extraction (§26.2a).** Treat this as a configuration
  and discoverability defect: detect the condition, tell the user, make
  `vision_model` reachable. Argue whether shipping "configure this yourself"
  is a fix or an abdication, and what happens to the 130 spans already ingested.
- **C — Surface the loss without recovering it.** Record and report that N
  equations on M pages are images; make `wiki lint` and the chat say so.
  Argue whether this is honest engineering or the same silence with a label.

These are not exclusive. The synthesis may take a staged combination — say so
explicitly and justify the ordering.

## 4. Hard constraints every proposal must respect

1. **§26.2 forbids blanket page-VLM as an automatic recovery action**: "the
   selective-recovery mechanism MUST NOT escalate to blanket page-VLM; it
   recovers only measured-loss regions." A proposal that VLMs every page as
   *recovery* is out of contract. §26.2a's user-elected extractor is a
   different, permitted thing — be precise about which you are proposing.
2. **Recovery output is additive and lifecycle-gated**
   (`candidate | reviewed | rejected`), stored in
   `source_spans.metadata.formula_recovery` (SCHEMA §20.4). Acceptance
   threshold 0.80, requires a validator trace and an exact match against an
   owning-claim formula. "Parseable LaTeX alone verifies nothing."
3. **No silent flip to verified.** `uncertain → verified` only against
   recovered evidence; otherwise `missing`.
4. **A changed page hash invalidates that page's candidates.**
   `invalidate_formula_recoveries()` already exists.
5. **Re-ingest cost is real.** 130 placeholder spans already exist across the
   vault; source 37 alone took a full LLM pass. Any plan that silently implies
   re-ingesting everything must say so and price it.
6. **Reference Mode**: the PDF lives outside the vault (`zotero:<key>`), the
   `relpath` is a markdown stub. Any page-image work must address the real PDF
   through the Zotero identity, not the stub. Note `wiki plugin pdf context
   --file-path <pdf>` fails with "Could not read PDF (encrypted or corrupt)"
   while `--zotero-attachment-key YACIRUKK` succeeds on the same file.
7. **Internals are English/Latin only.** Input/output prompts may carry other
   languages; nothing else.
8. **Docs mandate**: any behavior change updates `docs/specs/` and
   `docs/guides/` (English first, then `_KR.md`).

## 5. What a good proposal looks like

- Names which route (A/B/C or a staged combination) and why the measured
  evidence supports it.
- States what happens to the **130 already-ingested placeholder spans**.
- States the **definition of done** as something measurable on source 37 —
  e.g. "asking about equation 26 returns its content" vs "returns an honest
  statement naming the page and that it is an image."
- Gives concrete pseudocode / SQL / call sites, not architecture adjectives.
- Says explicitly what it does NOT do.
