# Proposal — prompt_economist: is the prompt better, or merely bigger?

## Method note

Every number below came from calling the real production functions
(`buildQuickQueryMessages`, `buildResolvedReferencesBlock`, `buildCitationsBlock`,
`buildWikilinksBlock`, `formatCuratorContextPack`) with realistic synthetic
inputs, in a throwaway `plugin/src/context/__measure_tmp.test.ts` run under
`vitest`, then deleted — not a reimplementation. The gate's own
`promptProse()`/`NEGATIVE` regex was re-run verbatim in a standalone Node
script against the current file contents. Both scripts and their raw output
are reproduced inline below so the numbers are checkable, not asserted.

This file was written while `wikilinkResolver.ts`, `ChatSidebarView.ts`, and
`quickQueryPopover.ts` were under concurrent edit by another Arena agent. The
`buildWikilinksBlock` note text and its `MAX_LINKS`/`MAX_LINK_CHARS` constants
— the only parts of that file this report depends on — were unchanged across
that edit; the diff was wiring (a `self` parameter for `[[#Heading]]`
self-links), not prompt text. Numbers below are current as of that snapshot.

---

## 1. Instruction chars vs document chars, per document kind — measured

`buildQuickQueryMessages` output split into: **instruction** = the system
message (`systemText`) + the `<critical_invariants>`/`<context_priority>`
tagged spans inside the user turn (these are the only tags that carry
model-facing instruction rather than document content); **document** =
everything else in the user turn (primary selection, background PDF/markdown
text, resolved references/citations/wikilinks bodies, vault evidence, pinned
sources, follow-up Q&A, the question itself).

| Scenario | instruction chars | document chars | total | instruction share | doc : instr ratio |
|---|---:|---:|---:|---:|---:|
| **Paper** — selection cites `[12]` and points at "Section 3.2"; 3-page PDF window, 11-entry outline, 1 resolved section-ref, 1 resolved citation, 6-item vault evidence pack, 1 pinned note, 1 follow-up turn | 6,670 | 17,242 | 23,912 | 27.9% | 2.58 : 1 |
| **Book** — reader on p.412/620, asks where a term was first defined *and* for the whole bibliography (`asksForList` path, 40 entries — this is the realistic worst case for a book action per the coverage matrix's "answer is often 200 pages from where the reader is sitting") | 6,670 | 23,933 | 30,603 | 21.8% | 3.59 : 1 |
| **Note** — 15,000-char note accumulated over a year, question about the middle section, 2 followed wikilinks (1 whole-note, 1 heading-scoped), same vault evidence pack | 6,670 | 15,529 | 22,199 | 30.0% | 2.33 : 1 |

Instruction weight is **constant across all three** (6,670 chars) — it does not
vary with document kind or question, because `systemText` and
`contextPriorityInstruction(true)` are built unconditionally on every popover
turn regardless of what is actually being read (see §3). Document content is
what varies, and document content dominates every single-turn scenario by
2.3–3.6×. On its face this looks healthy: the prompt is not "mostly
instructions." The two findings below (§4, §5) are why that headline number
is not the whole story.

---

## 2. The prohibition ceiling — and why its number cannot be trusted as reported

`promptRoleBudget.test.ts` reports (re-run verbatim against current files):

```
systemPrompt.ts:            8,381 chars, 12 prohibitions
chatContextPriority.ts:     3,194 chars,  2 prohibitions
promptRegistry.ts:          2,602 chars,  5 prohibitions
crossReferenceResolver.ts:  2,616 chars,  1 prohibition
citationContext.ts:           156 chars,  0 prohibitions
─────────────────────────────────────────────────────────
TOTAL:                     16,954 / 17,000 chars  (46 chars of headroom — 99.7% full)
                               20 / 23 prohibitions (3 of headroom)
```

Read at face value, the char ceiling is nearly breached. **It is not — the
number is corrupted, and in a way that also hides a real bug.**

`promptProse()` extracts model-facing text with `/"(?:[^"\\]|\\.)*"/g` — a
regex that finds `"..."` spans in the *raw source text*, with no idea whether
a given quote character opens a JS string or sits inside a `/** JSDoc */`
comment. `crossReferenceResolver.ts:705` has this comment:

```
 * prompt for the tool permission it would need to open the file, so an implied
 * "go read it yourself" is answered by the runtime with an auto-denial and the
```

The two literal `"` characters around *go read it yourself* are inside a
comment, invisible to a real tokenizer, but the regex treats them as string
delimiters. That flips quote-parity for the rest of the file. I verified the
consequence directly — this is what `promptProse()` actually extracts for
`crossReferenceResolver.ts` (full text, not a summary):

```
/**
 * Instruction carried on the unresolved block.
 * The provider must be told not to go looking. A headless CLI provider cannot
 * prompt for the tool permission it would need to open the file, so an implied
 *  is answered by the runtime with an auto-denial and the user sees no answer
 * at all. It says . How hard the plugin actually looked varies by call site...
 * ...the wrong-context failure this block exists to avoid, relocated from the
 * snippet to the note.
 */
const UNRESOLVED_NOTE =
  ;
```

`const UNRESOLVED_NOTE = ;` — **the actual 630-char model-facing string is
erased to nothing.** Every character the gate attributes to this file
(2,616 of them) is JSDoc commentary the model never sees. Confirmed by direct
substring check: `total.includes("the answer describes the document, never
the context")` (the real note's closing sentence) → **false**.

Consequences, both directions:

- **The reported 99.7%-full ceiling is fiction.** Strip the 2,616 comment
  chars and add back the real 630-char `UNRESOLVED_NOTE`, and true prose is
  16,954 − 2,616 + 630 = **14,968 chars — 2,032 chars of real headroom**, not
  46.
- **The one prohibition the gate credits to this file is also fiction.** The
  file's "1 prohibition" is the word *avoid* from "...this block exists to
  **avoid**, relocated..." — a code comment. The real prohibition in
  `UNRESOLVED_NOTE` ("...describes the document, **never** the context or
  what it does or does not contain") is invisible to the gate — it was erased
  along with the rest of the string. **The gate is measuring a comment's word
  choice as a live model instruction while missing the actual one sitting
  three lines below it.**
- This is not a one-off: I found the same erasure mechanism (odd embedded
  `"` count before a template-literal note, from an escaping regex
  `.replace(/"/g, "&quot;")` a few lines above) zeroing out
  `wikilinkResolver.ts`'s note text when I first tried to extend the same
  measurement to that file — see §3.

Given that, "how close is the current text to the cap" cannot be answered
from the gate's own printed number. The honest answer: **the gate has ~2,000
chars of real headroom, but its accounting is unreliable in both directions
(a stray quoted phrase in a comment can either manufacture 2,000+ chars of
phantom "prose" or erase a real 630-char instruction to zero), so a future
change that looks safe by the gate's number is not verified safe.** §6
proposes the concrete fix.

**Load-bearing vs dilution, among the 20 (gate-counted) prohibition hits:**

Load-bearing — cutting these reintroduces a bug this release or an earlier
one already paid for:
- `promptRegistry.ts` filesystem/tool-boundary rules (3 `never`s,
  `boundaryConstraints`) — the file's own docstring: "security-critical rules
  ... can never silently diverge between the two surfaces again."
- `chatContextPriority.ts:97` "...describe the paper, **never** the
  retrieval" — directly protected by its own test
  (`promptRoleBudget.test.ts` §"no provenance narration is mandated"),
  guarding the exact bug the user reported this release.
- `promptRegistry.ts:214` "Answer **ONLY** about the
  `<primary_focus_selection>`" — the recency anchor this whole release's
  long-session-drift fix depends on.
- `promptRegistry.ts:235` "do **NOT** output any ai-agent-edit blocks" — the
  popover's `allowEdits: false` security boundary, stated in prose because the
  provider has no other way to know it.
- The edit-loop markers in `systemPrompt.ts` (do not translate marker tokens,
  do NOT claim edits are saved, do NOT emit markers on a non-edit turn) —
  each traces to a named, previously-shipped bug in the file's own comments.

Dilution candidates — safe to cut, with reasons:
- `crossReferenceResolver.ts:UNRESOLVED_NOTE`'s "**never** the context or
  what it does or does not contain" — this is real and load-bearing
  (prevents provenance narration on the unresolved path specifically), but
  because the gate cannot currently see it (see above), it is *effectively*
  unprotected. Not a cut candidate — a **measurement-gap candidate** (§6).
- `systemPrompt.ts` "do not mention Incurator setup or note-edit suggestions
  unless asked" — narrower value than the others; a soft UX preference bundled
  in among security/correctness rules. Safe to cut or fold into a positive
  instruction ("mention setup only when asked") without losing a guarantee
  anything else in this file depends on.
- `promptRegistry.ts:214`'s "**Do NOT** explain, summarize, or modify the
  whole document..." sits directly beside `chatContextPriority.ts:96`'s "You
  **MUST NOT** explain the entire document or current page when a primary
  focus selection is provided" — same prohibition, same trigger condition
  (a primary selection is present), stated in two different files that are
  *both* always injected together on every popover turn with a selection
  (which is every popover turn). One of these two is pure duplication, not
  two independent guarantees — see §4 for the fuller duplication picture,
  which makes this the smaller half of a much larger problem.

---

## 3. Instruction emitted where it cannot apply — yes, and it is the same shape v0.54.1 removed

`promptRegistry.ts:167–180` documents the precedent directly: a universal
rule naming "Active Document" and "[PDF Context]" metadata was removed because
it rode on every surface, including ones that never had that metadata —
"Negative instructions prime the behaviour they forbid, so a rule naming
[things that don't exist here] on a surface with neither was pure dilution."

The same shape survives, now keyed on **document kind rather than surface**.
`contextPriorityInstruction(true)` — called unconditionally,
`quickQueryContext.ts:252`, on every popover turn regardless of whether the
open document is a PDF or a markdown note — always appends the full
"POINTER SELECTIONS" paragraph (`chatContextPriority.ts:97`, 1,262 chars
across three PDF/citation-only clauses, measured below) and
`buildRecencyAnchor` (`promptRegistry.ts:207–239`, called unconditionally
whenever `hasPrimarySelection` — which `quickQueryContext.ts:266–269` always
sets `true` — appends a further 528 PDF/citation-only chars). Per the
coverage matrix this proposal's briefing already established:

```
bibliography / citations              | paper ✓ | book ✓  | note n/a
cross-references (Fig/Sec/Eq/p.)      | paper ✓ | book ✓  | note n/a
```

For a note-reading turn, `<resolved_citations>` can never be emitted (only
`resolveSelectionCitations`, PDF-page-fetch-backed, ever produces one) and
`<resolved_cross_references>`/`<unresolved_cross_references>` can never be
emitted for prose that has no page numbers, section numbers, or figure
numbers to point at (`extractReferences` only matches those patterns). Yet
every markdown-note popover turn is told, twice, in detail, how to use these
three block types and when to call `read_pdf_page_image`:

```
B (chatContextPriority.ts:97, always injected):
  pointer/cross-reference intro + resolved_cross_references handling: 711 chars
  "<resolved_citations> block ... answer about a cited paper..."      157 chars
  "<unresolved_cross_references> ... call read_pdf_page_image..."     394 chars
  = 1,262 chars

C (promptRegistry.ts:207–239, always injected when a selection exists):
  "...pointer/cross-reference, about its resolved target..."          111 chars
  "<resolved_citations> block ... answer about the cited work..."     131 chars
  "...call read_pdf_page_image ... rasterized equation..."            286 chars
  = 528 chars

TOTAL PDF-only dead weight on every note-reading turn: 1,790 chars
```

That is 1,790 of the note scenario's 6,670 instruction chars (26.8%) spent
telling the model how to use apparatus that is structurally absent from the
turn it is reading. This is not hypothetical — I confirmed by construction:
the "note" scenario in §1 has `resolvedReferencesBlock` and citations both
empty (correctly — nothing to resolve), yet `contextPriorityInstruction(true)`
and `buildRecencyAnchor` still emit the full PDF-pointer prose, because
neither is conditioned on document kind or on whether those blocks are
actually present this turn.

---

## 4. Overlapping blocks — yes, up to a fourfold restatement of the same instruction

Every block that carries followed/resolved content wraps it in a `note="..."`
attribute explaining how to use it — a reasonable, block-local, pay-only-if-
present design:

| Block | File:line | Note text | Chars |
|---|---|---|---:|
| `<resolved_citations>` | `citationContext.ts:187-189` | "The selection cites these works; each entry is the bibliography line it resolves to. Explain the cited work when the question is about it." | 138 |
| `<unresolved_cross_references>` | `crossReferenceResolver.ts:716` (`UNRESOLVED_NOTE`) | (630-char note, quoted in §2) | 630 |
| `<resolved_wikilinks>` | `wikilinkResolver.ts:170-171` | "Notes the reader's own text links to. Answer about a linked note from its content here rather than from its title." | 114 |
| `<workspace_notes>` | `workspaceNotes.ts:197-200` | "Notes the reader wrote themselves, in the project they are working in. Surface what they already concluded when it bears on the question, and attribute it to them — these are their working notes, not established fact." | 217 |

That is the intended, cheap design: the explanation travels with the block
and costs nothing when the block is absent. **But two of these — citations
and workspace-notes — are then explained a *second and third time*, in full,
in text that is injected unconditionally regardless of whether the block is
present:**

```
B — chatContextPriority.ts:97 (contextPriorityInstruction, ALWAYS in system prompt):
  citations clause:       "A `<resolved_citations>` block, when present, holds the
                            bibliography entries for works the selection cites —
                            answer about a cited paper from its entry there."        (157 chars)
  workspace_notes clause: "A `<workspace_notes>` block holds notes the reader wrote
                            themselves in the project they are working in; when they
                            bear on the question, surface what they already
                            concluded and attribute it to them rather than
                            presenting it as established fact."                      (244 chars)
                                                                          subtotal:    401 chars

C — promptRegistry.ts:207-239 (buildRecencyAnchor, ALWAYS appended when a
    selection exists — every popover turn):
  citations clause:       "A <resolved_citations> block, when present, holds the
                            papers the selection cites; answer about the cited
                            work from its entry there."                              (131 chars)
  workspace_notes clause: "A <workspace_notes> block holds notes the reader wrote
                            themselves in this project; when they bear on the
                            question, say what the reader already concluded and
                            attribute it to them."                                   (179 chars)
                                                                          subtotal:    310 chars
```

B and C are not two independent rules — they are the **same instruction,
written twice, in two different files, by (evidently) two different edits,
both always-on**. When a citations block and a workspace-notes block are
*both* present in one turn (a realistic case: the paper scenario in §1 has
exactly this), the model reads the "what a `<resolved_citations>` block is
and how to use it" instruction **three times** in one turn: B, C, and the
block's own `note=` attribute at `citationContext.ts:187`. Same for
workspace-notes when `<workspace_notes>` and `<resolved_wikilinks>` both fire
(a note-reading turn that also gets vault-evidence-adjacent workspace notes):
up to two restatements plus the block's own note, though not a fourth,
since `<workspace_notes>` itself has only the one dedicated note text.

**There is no de-duplication story.** B, C, and each block's own `note=`
were evidently each written to be self-sufficient in isolation, and nothing
enforces that only one of the three actually needs to survive. Combined
redundant chars from B+C's citations/workspace-notes clauses alone: **711
chars** (401 + 310), present on every popover turn that has a primary
selection — i.e., every popover turn, unconditionally, whether or not either
block is ever populated (see §3: the clauses fire even when the blocks are
structurally absent).

---

## 5. Do the caps crowd out the primary selection? Worst-case arithmetic

Every optional block has its own independent character cap
(`DEFAULT_BACKGROUND_LIMIT = 12,000` at `quickQueryContext.ts:67`,
`PINNED_SOURCE_LIMIT = 6,000` at `quickQueryContext.ts:170`,
`FOLLOWUP_TEXT_LIMIT = 4,000` at `quickQueryContext.ts:69`,
`MAX_WHOLE_BIBLIOGRAPHY_ENTRIES = 40` (uncapped per-entry length) at
`citationContext.ts:82`, and the backend evidence pack renders up to 12 items
at up to 1,600 chars of `detail` each
(`providerContextFormat.ts:258,281`) plus per-item structural lines — nothing
sums these caps against each other, and **nothing reserves any minimum share
for the primary selection**, which has neither a cap nor a floor.

I built the actual worst case — every optional argument present and at or
near its cap simultaneously — through `buildQuickQueryMessages` directly:

```
primary selection ("As shown in Section 3.2 [12], the result follows.")     102 chars
resolved_citations (40-entry whole bibliography)                         10,142 chars
quick_query_background (PDF window + 220-entry outline, windowed)         9,635 chars
incurator_evidence_pack (12 items × ~1,600-char detail + structure)      21,047 chars
pinned_sources (3 × ~2,000 chars, at PINNED_SOURCE_LIMIT)                 6,202 chars
quick_query_followups (3 turns, at FOLLOWUP_TEXT_LIMIT)                   4,064 chars
─────────────────────────────────────────────────────────────────────────────────
user-turn total                                                          53,032 chars
primary selection's share of the user turn                                 0.19%
```

A deictic selection ("이게 뭐야", "what does this mean") — the *common* case per
the briefing's own action-axis framing, since a popover question is usually
"deictic ... the topic lives in the SELECTION" (`quickQueryContext.ts:190`) —
is by construction short. The thing the reader actually pointed at can be
outweighed by **the vault evidence pack alone by ~206×**, by pinned sources
alone by ~60×, with zero mechanism connecting the two: nothing shrinks the
supporting blocks when the selection is small, and nothing grows the
selection's share when the supporting blocks are large. The recency anchor
(§4, block C) is positioned last specifically to fight attention decay over
a *long conversation* — its own docstring says so
(`promptRegistry.ts:198-201`, "Fixes long-session attention decay") — but it
was not designed against attention decay over a *long single turn*, which is
what stacking every optional block at cap produces. This is a structural risk
argument (no runtime eval data backs a specific accuracy claim here), but the
arithmetic is not speculative: the caps are real, independent, and additive,
and none of them is aware of the others.

---

## 6. Proposed budget policy — concrete enough to be a test

Four rules, each phrased so it could be dropped into
`promptRoleBudget.test.ts` or a sibling file as-is:

**(a) Fix the extraction before trusting the ceiling again.**
`promptProse()`'s regex must strip `/** ... */` and `// ...` comments from
each file's source *before* running the `"..."` scan — a two-line change
(`src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "")`) that turns
§2's silent erasure into either a clean extraction or a visible zero, never a
comment's prose standing in for a real string. Test: assert
`promptProse()`'s output, for `crossReferenceResolver.ts` specifically,
contains the literal substring `"never the context or what it does or does
not contain"` — this fails today and would pass once fixed. This is the
single highest-value change in this report: everything else here is a
judgment call about what to cut; this is a bug in the thing that would tell
you whether a cut was safe.

**(b) Widen `PROMPT_FILES` to match what actually ships in this release.**
Add `wikilinkResolver.ts` and `workspaceNotes.ts` — both new or newly-wired
this release, both carry a `note="..."` instructional attribute of the exact
shape the gate's own comment (`promptRoleBudget.test.ts:34-39`) already says
must be tracked ("Leaving it out would have let instruction text grow in a
file the ceiling does not see"). That reasoning was applied to
`citationContext.ts` in v0.56.0 and not yet re-applied to this release's two
new instructional files. Test: the existing ceiling test, unchanged, once
these two files are added to the array — it will still pass (their notes are
114 + 217 = 331 chars), which is the point: cheap to add, and it closes the
exact gap the comment warns about.

**(c) One explanation per block, enforced.** A block's usage instruction may
live in exactly one of two places: its own `note="..."` attribute (preferred
— zero-cost when absent) or a shared always-on instruction (`B`/`C`) — never
both. Concretely: `contextPriorityInstruction` and `buildRecencyAnchor` may
name a block (`<resolved_citations>`, `<workspace_notes>`) to say which one
takes priority when several are present, but must not restate what the block
*contains* — that sentence belongs solely to the block's own note. Test:
assert the *combined* char count spent explaining `<resolved_citations>`
usage, summed across `chatContextPriority.ts` + `promptRegistry.ts`, is
`<=` some small fixed margin (e.g. 60 chars, room for a bare cross-reference
like "see its entry in `<resolved_citations>`") — today that sum is 288
chars (157 + 131) and the rule would force it down to one sentence, living in
`citationContext.ts` alone. Same rule, same test shape, for
`<workspace_notes>` (currently 244 + 179 = 423 chars split across two
files). This removes the 711 measured redundant chars from §4 with no loss:
the information still reaches the model, once, attached to the block it
describes, present only when the block is.

**(d) Don't emit a block's usage instruction when the block cannot exist this
turn.** `contextPriorityInstruction` and `buildRecencyAnchor` are pure
functions of a boolean today (`hasPrimaryContext`, `hasPrimarySelection`).
Extend them to take (or infer from) which optional blocks the caller actually
built this turn, and drop the PDF-pointer/citations clauses when none of
`resolvedReferencesBlock`, citations, or PDF context were supplied — which
`buildQuickQueryMessages` already knows, since it is the function deciding
what to concatenate. Test: build a `QuickQueryMessageArgs` with
`activeContext.viewType === "markdown"` and no PDF-shaped args, assert the
system+user text does not contain `resolved_citations` or
`read_pdf_page_image`. This removes the 1,790 measured dead-weight chars
from §3 on every note-reading turn — the majority of this release's own
target document kind, per the briefing's three-way split.

**(e) A combined cap on the "supporting" blocks, independent of the
selection's own size.** Sum `vaultEvidenceBlock + pinnedBlock +
resolvedReferencesBlock(citations) + followups` and assert the total is
`<=` a fixed ceiling (proposal: 20,000 chars — roughly the sum of today's
*individual* caps for background + pinned + followups, deliberately
excluding the uncapped worst-case evidence-pack-plus-wholesale-bibliography
combination measured in §5 at 45,455 chars for those four blocks alone). Where
the combined content would exceed it, truncate the *lowest-priority* block
first (followups, then pinned, then wholesale citations, then vault
evidence — reader's own words outrank retrieved evidence, per this release's
own duty-2 framing) rather than truncating all of them proportionally, which
is invisible and unpredictable to reason about. This does not touch the
primary selection's cap-free status — deliberately: capping the one thing the
reader pointed at, to protect budget for optional retrieved material, would
be the wrong trade.

**Pros of adopting all five:**
- (a)+(b) restore a ceiling number that can actually be trusted, at close to
  zero cost — no prompt text changes, no behavior changes, ~20 lines of test
  code.
- (c)+(d) recover roughly **2,500 measured chars** (711 duplication + 1,790
  dead weight) of pure waste with no loss of capability — the same
  information still reaches the model exactly once, exactly when relevant.
- (e) puts a ceiling on the exact failure mode §5 demonstrates, without
  touching the thing (the primary selection) this whole release exists to
  keep central.

**Cons / what this does not fix:**
- (c) and (d) require function-signature changes to `contextPriorityInstruction`
  and `buildRecencyAnchor` (both currently pure boolean-in functions used by
  both surfaces) — a small refactor, not a text edit, so it is implementation
  work and not something this proposal (research/economics only, per the
  brief) should just do inline.
- (e) is a judgment call on the specific ceiling number (20,000) and the
  drop order; both are defensible but not derived from a hard constraint the
  way the character-cap-per-block numbers are.
- None of this addresses whether 6,670 instruction chars is itself the right
  budget for a *single* popover turn — only that, whatever it is, it should
  not be inflated by duplication, comment-noise, or document-kind-mismatched
  prose. A model-quality eval (does answer quality change with (c)/(d)
  applied) is out of scope for this file and would need real provider calls,
  not a char-count script.
