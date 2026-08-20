# Arena conclusion: no build. A corrected item and one new filing.

Date: 2026-08-20 | Agent Persona: system_synthesizer

## What this Arena set out to do, and why it is not doing it

It opened to plan wiring `recover_formula` into the compile path. Five
measurements later, every premise it would have planned against is gone:

| premise | measured |
|---|---|
| "~48 unreadable regions" | **2,121** by the current parser (437 + 11 + 1,673) |
| "130 regions across 4 sources" (roadmap) | 1,135 stored, across **3** |
| "`validator_trace_id` producer exists at `:226`" | it is a pass-through; only test fixtures mint one |
| "swap equality → subsequence fixes the gate" | 2/8 → **5/8**; three faithful transcriptions still reject |
| "the parser discards coordinates" | it never had them; the marker carries only a size |
| "the coordinates can be re-associated" | size join **6/1,135**; per-page positional join **3/158** |
| "97% of regions are lost in the pipeline" | **wrong** — nothing is lost; the stored rows are an old parse |

A sixth thing was learned by accident: the survey the proposal wanted as P0
costs 90 seconds and has already run, above.

Writing an implementation plan on top of this would repeat the item's own
history — v0.48.1 shipped as a no-op, then a visibility release, then an Arena
estimating 0–2 recoveries against a count that was wrong by a factor of forty.

## The state, stated once

**Formula recovery cannot produce a single recovery today**, and not because the
acceptance gate is strict or the trace id is missing. It cannot locate a region.
0 of 2,121 carry coordinates, the marker `pymupdf4llm` emits carries only
`[width x height]`, and neither a size join nor a positional join re-associates
them — `get_image_info` reports vector drawings too, so page 2 of one paper has
5 markers against 36 image objects.

The association has to come from the parser itself, and whether `pymupdf4llm`
can expose it is an **experiment**, not a design decision. Its `to_markdown`
signature is `(*args, **kwargs)`.

## Two outputs

**1. ROADMAP 1 is corrected**, not re-planned. Its numbers were wrong, its
blocker ordering was wrong, and its header contradicted its own blocker list.
All three are now fixed in place with the measurements attached.

**2. A new item is filed: nothing re-derives a source whose parse improved.**

A source at `l2_status='done'` is never re-parsed. v0.49.0 taught the parser to
report unreadable regions on 2026-08-08; source 37 was added 08-04 and has never
seen it, which is why it stores 4 loss records against 437 the current parser
finds. Measured: 646 stored spans versus 2,050 computed today, for the same file.

This is larger than formula recovery and sits upstream of it. Every stored
measurement in the vault is a claim about whatever parser ran when that source
was last ingested, and nothing says so at the point of reading.

**Formula recovery should not move again until that is fixed.** Its blockers are
real, but they are measured against data that describes an older system.

## What would reopen this item

One experiment, cheap: does `pymupdf4llm` expose the association between an
omitted-picture marker and the image object it stands for? If yes, blocker 3
becomes tractable and this Arena reopens with a real design question. If no, the
next question is whether the pipeline should stop using `pymupdf4llm`'s markers
and walk the page with `fitz` itself — a much larger change that deserves its
own briefing rather than a phase inside this one.

Nobody should wire `recover_formula` before that experiment returns.
