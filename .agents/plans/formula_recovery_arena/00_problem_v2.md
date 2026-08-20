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
