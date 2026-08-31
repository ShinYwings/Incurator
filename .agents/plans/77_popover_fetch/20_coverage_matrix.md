# Coverage audit — the actions a reader takes, in every cell

The user's framing, twice corrected and finally exact:

> 논문(pdf), 책(pdf), 노트 md 파일 이렇게만 들어오는 상황에서 사용자가 sidechat과
> popover에서 어떤 행동들을 취할까 고민해보고. 지금 있는 기능들을 모든 케이스에
> 문제 없이 돌아가도록 프로세스 점검 및 개선하라는 거였어

Three inputs, two surfaces, and the job is to make the features that ALREADY
EXIST work in every cell. Not new features, and not a redesign.

## Why the action is the axis

A needs-list is a list, so it always has a missing entry — and the pipeline is
built with one hand-written resolver per entry, so the missing entry is a silent
empty answer. This release opened by concluding the popover needed a URL fetch
tool; the answer was in the last pages of the PDF already open.

An action generalises where a need does not. The reader:

1. selects a passage and asks about it
2. types a question naming something, without selecting it
3. **follows a pointer the text makes**
4. asks where something was defined earlier
5. asks what they themselves already concluded
6. compares two documents

Action 3 is the one that broke, and it broke separately in each column because
each column has its own resolver.

## The matrix, as measured

`✓` works · `~` works but wrong for this document kind · `✗` absent

| Feature | paper | book | note | surfaces |
|---|---|---|---|---|
| selection → context | ✓ | ✓ | ✓ | both |
| typed question → pointer resolution | ✓ *(fixed)* | ✓ *(fixed)* | ✓ *(new)* | both |
| bibliography / citations | ✓ | ~ → ✓ *(fixed)* | n/a | both |
| cross-references (Fig / Sec / Eq / p.) | ✓ | ✓ | n/a | both |
| **wikilinks — the note's citation** | n/a | n/a | **✗ → ✓ *(new)*** | both |
| document outline | ✓ | **~ → ✓ *(fixed)*** | ✓ | both |
| active document text | ✓ | ✓ | **~ → ✓ *(fixed)*** | popover |
| vault evidence pack | ✓ | ✓ | ✓ | both |
| in-document search index | ✓ | ✓ | n/a | both |
| local page-fetch tool | API path only | API only | n/a | both |
| permission denial handling | ✓ *(fixed)* | ✓ | ✓ | both |

## What the audit found, and what it says about the code

Every finding has the same shape: **a constant or a code path that is correct for
one document kind and silently wrong for another.** None of them are missing
features. All of them are existing features that do not survive a change of
column.

1. **A note's `[[link]]` was never followed.** Papers got citation resolution in
   v0.56.0. Notes got nothing — the plugin only ever WROTE wikilinks, as output
   locators. The reader's action is identical; only the column differs.
   → `wikilinkResolver.ts`, wired into both surfaces.

2. **A book's bibliography is not six pages from the end.** The tail scan was a
   flat six, which is exactly right for a paper and unreachable past a book's
   twenty-to-thirty page index.
   → proportional depth, floored and ceilinged.

3. **A book reader got the outline of page 1.** `formatOutline` took the first 80
   entries. A paper never has 80, so the slice never fired and the code looked
   correct for years. A reader on page 400 was handed the contents of pages
   1–100.
   → top-level entries kept, remaining budget spent nearest the reader.

4. **A long note was cut at its opening.** The active note was truncated at 6,000
   chars from the head. On a short note that is the whole file; on a note the
   reader has kept for a year, everything after the opening is absent.
   → windowed on the selection and the question, with the elision marked.

Findings 3 and 4 are the same defect as 2, in different features: **truncating
from the head is wrong whenever the reader is not at the head.** That is the
generalisation the action-axis produces and the needs-list did not.

## Cells checked and found sound

- **Un-ingested PDFs.** The in-document BM25 index is built client-side from the
  open document, so pointer resolution and in-document search work with no `wiki
  add`. Vault evidence will not include the document, which is correct — it is
  not in the vault.
- **Outlines for notes.** Both surfaces already build one (`markdown_outline`,
  `markdown_outlines`). An earlier reading of mine that said otherwise was wrong.
- **Follow-up turns in the popover.** Bounded at 3 turns / 4,000 chars, same on
  every column.

## Not addressed here

- The local page-fetch tool still does not exist on the CLI path. v0.77.0 stops
  the prompt from promising it; giving the CLI an equivalent means exposing it as
  a second local MCP server, which is a new always-on subprocess and belongs in
  its own release.
- Action 6 (compare two documents) is served only by whatever the reader has open
  as tabs. Not measured in this pass.
- Author-year and parenthetical citation styles remain unmatched.


## Round two — the two Arena audits, and how each finding was resolved

Both audits were re-run after the first round (the originals died on a session
limit). Between them they raised sixteen items.

### Fixed

| # | Finding | Where |
|---|---|---|
| R1 | System-prompt truncation cut from the tail, discarding the material placed last for attention | `promptTruncation.ts` |
| R2 | Sidebar never got the bibliography-without-a-bracket fallback | `pdfReferenceContext.ts` |
| R3 | Popover resolved cross-references from the selection only, never the question | `pdfReferenceContext.ts` |
| R4 | A book's reference list was followed for only 5 pages past its heading | `citationContext.ts` |
| R5 | Long-note windowing was wired into the popover only | `ChatSidebarView.ts` |
| R6 | `[[#Heading]]` and `![[image]]` — found by opening the vault | `wikilinkResolver.ts` |
| R7 | Pinned passages resolved pointers by a sync path that cannot fetch | `ChatSidebarView.ts` |
| R8 | Popover's vault-evidence gate was a narrower copy of the sidebar's | `quickQueryPopover.ts` |
| B2 | The prose ceiling was measuring comments, and the trims it forced were wrong | `promptRoleBudget.test.ts` |
| B3 | PDF-only instruction on every markdown turn | `chatContextPriority.ts` |
| B4 | One fact told four times, in the invariants section | `promptRegistry.ts` |
| B5 | The reader's selection measured 0.19% of its own turn | `turnBudget.ts` |
| B6 | The budget policy existed only as prose | `turnBudgetPolicy.test.ts` |

### Judged, not changed

**R9 — vault-evidence budget: flat cap on the popover, proportional on the
sidebar.** The audit found it documented as intentional and found no evidence
against it. Left alone.

**R10 — `items.slice(0, 12)` on the evidence pack, and the 40-entry bibliography
cap.** The audit flagged these "for judgment, not asserting a defect", and said
plainly it could not establish from the code whether 12 was a token-budget
decision or a readability one. Two facts settle it: the backend already applies
its own token budget before these items are returned, and `fitTurnBudget` now
bounds the rendered block a second time. A third bound would be redundancy, not
correctness. **Not a defect.**

That is the whole list. Nothing was deferred silently.
