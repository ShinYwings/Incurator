# Briefing v2: formula recovery is finished, disconnected, and still blocked

Date: 2026-08-20 | Author: main agent (re-measured against current code)

Supersedes the framing in the original `00_problem.md` on one point: fixing the
acceptance gate is **not** one change, and the roadmap's implied fix does not
get there on its own.

## 1. Where this actually stands

`pipeline/formula_recovery.py` exists, exports `recover_formula`,
`classify_formula_loss`, `invalidate_formula_recoveries`, and has 6 passing
tests. `pipeline/compile.py` imports all three **only to re-export them**.
`recover_formula(` has **0 production call sites**.

The visibility half shipped in v0.49.0/.1 and works: 130 unreadable regions
across 4 sources are named, and the assistant says which region it could not
read. It still recovers nothing.

## 2. Blocker 1 re-measured — and it is two problems, not one

The gate that decides whether a recovered transcription may be trusted:

```python
# formula_recovery.py:135
structurally_matches_claim = recovered_tokens in claim_formulas    # tuple equality
```

versus what `validate_claim_support` uses for the same question:

```python
# claim_support.py:147
def _is_formula_subsequence(claim_tokens, span_tokens) -> bool:    # contiguous span
```

Ran eight faithful transcriptions of one claim formula — the kind of variation a
vision model actually produces — through both gates:

| variant | equality | subsequence |
|---|---|---|
| identical | accept | accept |
| `^\top` vs `^{T}` | REJECT | **REJECT** |
| `\boldsymbol` vs `\mathbf` | REJECT | **REJECT** |
| trailing `\tag{26}` | REJECT | accept |
| extra spacing macros | accept | accept |
| `\displaystyle` wrapper | REJECT | accept |
| `\left(...\right)` sizing | REJECT | **REJECT** |
| surrounded by prose | REJECT | accept |
| | **2/8** | **5/8** |

**The roadmap's "6 of 8 reject" is confirmed for the equality gate.** What it
does not say is that swapping to subsequence — the obvious fix, and the one the
item implies — reaches only 5/8.

The three that still fail differ in **tokens**, not in span:
`\top`≢`T`, `\boldsymbol`≢`\mathbf`, and sizing wrappers inject `\left`/`\right`
into the sequence. Subsequence matching is the wrong axis for those; they need
token-level normalisation of notational equivalents.

So blocker 1 is:

- **1a** span: equality → subsequence. Small, and `_is_formula_subsequence`
  already exists.
- **1b** notation: `\top`/`T`, `\boldsymbol`/`\mathbf`/`\mathbb`, sizing
  wrappers, and whatever else measurement turns up. This is a normalisation
  table, and every entry is a judgement about what counts as the same formula —
  which is a contract question, not a tidy-up.

Doing 1a alone and calling the gate fixed would leave a third of faithful
transcriptions rejected, and the failure would look like the model being bad at
transcription rather than the gate being wrong.

## 3. Blocker 2 stands, and the roadmap said otherwise until today

`validator_trace_id` has no producer. Every occurrence in the backend is a
parameter, a pass-through, or a column read; `formula_recovery.py:226` is
`validator_trace_id=validator_trace_id` handed to `upsert_claim_support`. The
only non-`None` values in the repository are test fixtures (`PTR-test`,
`PTR-reviewed`). The `reviewed` state is therefore unreachable and every
candidate would sit at `candidate` forever.

The roadmap's header claimed this producer "exists too, at
`formula_recovery.py:226`", contradicting its own blocker list four paragraphs
below. Corrected 2026-08-20.

## 4. Blocker 3 stands

`recover_formula` requires a `crop_hash` (`:81`). Placeholder spans carry
`metadata = None` and the only geometry that survives is `[width x height]` in
the placeholder text. `page_number` is a section index, not a physical page
(max 23 on a 27-page PDF), so the region cannot be located, let alone cropped.

## 5. What this means for sequencing

The item is **first by how much finished work sits unused and last by
readiness**. Wiring it today yields the Arena's estimated 0–2 of ~48 regions: a
third no-op, after v0.48.1 and after the visibility work.

The three blockers are the milestone. They are also not equally hard:

- 1a is small; 1b is a contract question.
- 2 is a design question — what mints a validator trace, and when does a
  candidate become reviewed.
- 3 is the largest: it needs page coordinates that the ingest path currently
  discards, which reaches back into parsing, not just recovery.

## 5a. Measured 2026-08-20 — there is no "recover what we can locate" subset

Question 2 below asked how many of the ~48 regions have usable geometry today,
because that number sizes the milestone. Measured against the live vault:

```
spans carrying a loss record  : 1135
verdicts                      : {'image_only': 1135}
region key-sets seen          : {('height', 'width'): 1135}
regions with page COORDINATES : 0
distinct sources affected     : 3
```

**Every one of them carries `{width, height}` and nothing else.** Zero have page
coordinates. So `recover_formula`, which requires a `crop_hash`, could crop
nothing at all — wiring it today recovers **0** regions, not the Arena's
estimated 0–2. There is no shippable subset to carve out.

Note the roadmap's own figures are stale: it says "130 unreadable regions across
4 sources"; the database says **1,135 across 3**. Neither number was re-derived
until now.

**This reverses the sequencing.** Blocker 3 is not a prerequisite alongside the
other two — it IS the milestone. Fixing the acceptance gate (blocker 1) and
minting a validator trace (blocker 2) perfectly would still recover nothing,
because nothing can be located. And blocker 3 does not live in the recovery
code: the coordinates are discarded upstream, during parsing, so the work
touches a different part of the system than the item's name suggests.

Question 2 is therefore answered and withdrawn. The open question it becomes:
**can the parser retain page geometry for a dropped image region, and at what
cost to ingest?** That is the first thing to establish, and it is measurable
before anything is designed.

## 5b. Measured — the coordinates exist in the PDF; the JOIN is the problem

§5a asked whether the parser could retain page geometry. Re-framed after
reading the code: **the coordinates are never discarded, because the parser
never has them.** `pymupdf4llm` emits a marker string —
`**==> picture [185 x 12] intentionally omitted <==**` — and
`source_spans.py:72` parses width and height out of that text. Size is all the
marker carries.

So the question becomes: can the geometry be recovered from the PDF and matched
back to a placeholder? Both halves measured.

**The coordinates are there.** On source 37, `fitz.get_image_info(xrefs=True)`
returns **192 image objects, 192 with a usable bbox**. Nothing is lost at the
PDF level.

**Matching them by size does not work.** Joining each loss record's
`{width, height}` to a PDF image of the same rounded on-page size:

```
source  37:     4 loss spans -> unique    4 | ambiguous  0 | no match    0
source  45:  1120 loss spans -> unique    1 | ambiguous  2 | no match 1117
source  46:    11 loss spans -> unique    1 | ambiguous  0 | no match   10
TOTAL:       1135              unique    6 | ambiguous  2 | no match 1127
```

**6 of 1,135.** The 27-page paper joins perfectly (4/4) and the 673-page book
fails almost completely — which is the shape you would expect if the marker's
numbers are in different units, or rounded differently, or measured before a
transform that `get_image_info` reports after. Whatever the cause, a
size-keyed join is not the mechanism.

That kills the cheap version of blocker 3. The viable direction is to capture
the bbox **at parse time**, where the placeholder and the image object are the
same event, rather than trying to re-associate them afterwards from two
independently-derived descriptions. Whether `pymupdf4llm` exposes that
association, or whether the pipeline has to walk the page with `fitz` alongside
it, is the next thing to establish — and it is the real content of this
milestone.

## 5c. Measured at parse time — and a bigger finding underneath

§5b concluded the bbox must be captured where the placeholder and the image are
the same event. Measured what that would take, on source 37 (27 pages):

**The units are already the same.** A marker reading `[17 x 30]` sits on a page
whose `get_image_info` bbox measures `17.0 x 30.0`. So §5b's guess about
different units was wrong — the numbers agree.

**But the association still does not fall out.** Restricting the join to a
single page, then trying position (k-th marker ↔ k-th image object):

```
per-page size join : unique 13 | ambiguous 3 | no match 142
positional join    : match 3   | mismatch 155
```

Page 0 has 8 markers and 11 image objects; page 2 has 5 markers and **36**.
`get_image_info` reports vector drawings too (`xref=0`), so the two lists
describe overlapping-but-different populations. Neither size nor order
identifies which image a given marker stands for. Capturing the bbox "at parse
time" therefore is not a matter of reading it off — `pymupdf4llm` would have to
expose the association itself, and its `to_markdown` signature is
`(*args, **kwargs)`, so that has to be established against the library rather
than assumed.

**A "97% are lost" finding, and then its correction.** Source 37's parsed text
contains **158 markers** while the database holds **4** loss spans for it, which
looked like the pipeline dropping almost everything. Traced the stages instead
of concluding:

```
1. parsed.text markers            : 158
2. after structural sectioning    : 437   (62 sections)
3. after spans_from_sections      : 437   (2050 spans)
4. spans classify_span_loss flags : 437
```

**Nothing is lost — the count goes UP**, because sectioning repeats content
across overlapping sections, and every marker that survives is classified. Zero
spans carry more than one marker, so there is no merge swallowing them either.

The 4 in the database are a **stale parse**: 646 spans stored against 2,050
computed from the same PDF today, written between 2026-08-04 and 08-18, while
the source was first added 2026-08-04 — before v0.49.0 (2026-08-08) taught the
parser to report these regions at all, and before its 27 pages were
VLM-transcribed. The row is `l2_status=done`, so nothing will re-derive it.

So the real finding is smaller than it looked and different in kind: **the loss
records in this vault describe an older parse of these files.** The vault's
"1,135 regions" is not an undercount of a live measurement; it is a count of
whatever the parser said whenever each source was last actually re-derived.

**Sequencing consequence.** Any measurement of "how many regions exist" must
re-derive from the PDFs rather than query `source_spans`, and this milestone
cannot size itself from stored data. It also raises a question worth its own
item: a source whose parse improves does not get re-derived, so a shipped parser
fix reaches only sources ingested after it.

## 6. Questions for the Arena

1. Is 1b a normalisation table, or does the gate need a different comparison
   entirely (structural parse rather than token sequence)? The 3/8 that survive
   subsequence are the evidence either way.
2. ~~Is "recover what we can locate" a shippable subset?~~ **Answered by
   measurement (§5a): no. 0 of 1,135 regions carry coordinates.** The question
   becomes whether the parser can retain page geometry for a dropped image
   region, and what that costs at ingest.
3. What produces a `validator_trace_id`, and is `reviewed` a human action or an
   automated one? The answer decides whether this is a UI feature or a pipeline
   one.
