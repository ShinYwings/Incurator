# Reading Pipeline Proposal: One Resolution Step, Not N Resolvers

Date: 2026-08-31 | Agent Persona: reading_modes_analyst

## 0. Method note — actions, not needs, and why the axis matters here

The first pass at this proposal was organized as a needs table: one row per
"question class" per document kind, each row answering "does the pipeline
deliver what this question needs." The user corrected that framing directly
mid-Arena:

> 어떤걸 필요로 하겠어가 아니라 내가 어떤 행동을 하겠어가 맞겠다. 그로 인해
> 어떻게 프로세스를 만들어야할지. 저 위에 계속 반례가 생기니 말하는거야

Not "what would I need," but "what would I DO" — and the process built from
that. The correction is not stylistic. A needs-list is structurally a list:
one entry per kind of thing a reader might point at, and the codebase already
shows what a list architecture produces — a bibliography case
(`citationResolver.ts`), a cross-reference case (`crossReferenceResolver.ts`),
each hand-written, each independently threading (or failing to thread) the
same inputs. The bug that opened this release — the popover concluding it
needed a URL-fetch tool when the answer was already in the PDF's own last
pages (`.agents/plans/77_popover_fetch/00_problem.md`) — is exactly what a
missing list entry looks like from the outside.

So this proposal is organized around the six reader **actions** named in the
brief, each checked against all three document kinds (paper / book / note) as
a **generalization test**, not as the organizing axis. Where an action fails
to generalize, that failure is itself evidence for or against a unified
design — a real difference in what a paper, a book, and a note ARE (pages vs.
no pages, citations vs. wikilinks) is a legitimate reason for the code to
branch; a difference that exists only because nobody wired the fix through
is not.

## 1. Core Logic & Implementation

### 1.1 The six actions

1. **Select a passage and ask about it.**
2. **Type a question naming something, without selecting it.**
3. **Follow a pointer the text makes** — `[12]`, "see Fig. 4", "Section 3.2",
   "Eq. (7)", "p. 214", `[[a wikilink]]`.
4. **Ask where something was defined earlier** — the answer may be 200 pages
   back.
5. **Ask what I already concluded** — my own notes, not the document.
6. **Compare two documents.**

Actions 3 and 4 are two faces of the same mechanism (detect a pointer, locate
its target) and are analyzed together below. Action 2 is analyzed together
with 3 because the code's actual bug boundary sits exactly on the
selection/question distinction, not on the pointer-kind distinction.

### 1.2 Action-by-action architecture check

Table columns: **Action** | **Generalizes across paper/book/note?** (the
document-kind check) | **Current mechanism(s)** | **Shape: one step or N?**
| **Works today?** | **Evidence (file:line)**.

| # | Action | Paper / Book / Note check | Current mechanism | One step or N? | Works? | Evidence |
|---|---|---|---|---|---|---|
| 1 | Select a passage, ask about it | Works uniformly for all three — the selection is wrapped as `<primary_focus_selection>` regardless of source | `buildPrimarySelectionBlock` | One | Yes | `plugin/src/context/quickQueryContext.ts:61-63`; `plugin/src/ui/chat/ChatSidebarView.ts:1566-1567` (`isPrimaryUserContext(ref)` wraps the same way) |
| 2 | Type a question naming something, no selection | **Fails for papers/books, works for notes-via-sidebar** — the sidebar treats the typed message as the pointer-bearing text; the popover does not | See 1.3 below — this is the core asymmetry | **Currently N** (citation kind gets it, 8 cross-ref kinds do not, and the two surfaces differ) | Partly | `plugin/src/context/citationContext.ts:71-79` (question read) vs. `plugin/src/context/pdfReferenceContext.ts:270-296` (`resolveSelectionReferencesAsync` has no `question` parameter at all) |
| 3 | Follow `[N]` / "Fig. 4" / "§3.2" / "Eq. (7)" / "p.214" | Papers and books share one PDF-shaped resolver; notes have **zero** equivalent for `[[wikilink]]` | `crossReferenceResolver.ts` `PATTERNS` (8 kinds) for papers/books; nothing for notes | Papers/books: already mostly one dispatch table. Notes: **N=0**, not even attempted | Papers/books: yes for kinds with a matching pattern. Notes: **no** | `crossReferenceResolver.ts:132-206` (no wikilink pattern); `getFirstLinkpathDest` used nowhere in reading-context code, only `plugin/src/zotero/templateRenderer.ts:94` |
| 3b | Follow `[12]` specifically (citation) | Papers/books share one bibliography scanner; notes have no citations, N/A | `citationResolver.ts` + `citationContext.ts`, entirely separate module from #3's resolver | **N** — parallel module, own cache, own document-wide scan strategy (scan backward from end) instead of reusing the equation path's `locatePages`/BM25 | Yes, as of v0.77.0 (question-aware) | `citationContext.ts:1-19` (module doc admits it is a second discovery strategy); `citationResolver.ts:218` (`BRACKET_GROUP`, independent of `crossReferenceResolver.ts`'s `PATTERNS`) |
| 4 | Where was this defined earlier (200 pages back) | Papers: rarely triggers (papers are short). Books: this is the headline case. Notes: only via indirect vault search, never a direct link-follow | Equation kind gets a bounded backend-wide `locatePages` search; section/chapter/appendix/theorem/definition kinds get only outline-range expansion, capped at 12-24 pages, and only when the ToC has a matching entry | **N** — one kind (`equation`) got the document-wide fix, the rest did not | Equations: yes (bounded). Sections/theorems/definitions far from the ToC granularity: no | `pdfReferenceContext.ts:159-165` (`needsAdjacentEquationExpansion`, equation-only gate) and `:428-451` (`if (locatePages && latest.some(needsAdjacentEquationExpansion))` — the ONLY call site of `locatePages`) vs. `:453-472` (generic outline fallback, no backend search, for every other unresolved kind) |
| 5 | What did I already conclude (own notes) | Ingested notes (DAG) reachable on both surfaces; **un-ingested workspace notes reachable on the sidebar only** | `client.fetchContext` (both surfaces) + `searchWorkspaceNotes`/`buildWorkspaceNotesBlock` (sidebar only) | **N** — two parallel retrieval systems for the same action, and one is missing a caller | Sidebar: yes (both). Popover: partly (DAG only) | `plugin/src/context/workspaceNotes.ts:1-24` (module doc: "137 markdown files, 36 ingested, 75 of the gap are research notes inside one workspace"); import sites confirmed by `grep -rln workspaceNotesFor` = `ChatSidebarView.ts` + the module's own definition only — `quickQueryPopover.ts` and `quickQueryContext.ts` do not appear |
| 6 | Compare two documents | Sidebar reads every open tab (markdown outlines + up to 8000 chars of non-active markdown tabs, up to 3 PDF tabs with their own resolved-reference/RAG passes); **popover reads only the single active document and ignores everything else that is open** | `ActiveContext.openTabs` populated by `main.ts:refreshActiveContext` for both surfaces; consumed only by `ChatSidebarView.ts` | **N** — the type carries multi-document data on both paths, only one path reads it | Sidebar: yes. Popover: no | `grep -n openTabs plugin/src/context/quickQueryContext.ts plugin/src/ui/quickQueryPopover.ts` → zero matches; `ChatSidebarView.ts:1467-1509` (`nonActiveMdTabs`, `markdownOutlines`), `:1761-1780` (`pdfTabs.slice(0, 3)`) |

Two rows are explicitly **working and generalizing today**, worth naming so
this proposal does not read as "everything is broken": the outline/ToC block
(`buildMarkdownOutline` for notes, PDF bookmark `outline` for papers/books)
is built the same way and injected the same way on both surfaces
(`quickQueryContext.ts:65-79,126-130`; `ChatSidebarView.ts:1496-1509`), so
"what's the structure of this document" already generalizes cleanly across
all three kinds without a special case. Likewise action 1 (select-and-ask)
is uniform. The gaps cluster tightly around actions 2 through 6 — precisely
the ones that require the pipeline to go get something the reader did not
hand it directly.

### 1.3 The central asymmetry (action 2), stated precisely

`crossReferenceResolver.extractReferences(selectedText)` is called from
exactly two production call sites:

- `pdfReferenceContext.ts:214` — synchronous path
- `pdfReferenceContext.ts:288-289` — async path (`resolveSelectionReferencesAsync`)

Neither function has a `question` parameter. Compare
`resolveSelectionCitations` (`citationContext.ts:63-101`), which explicitly
takes `question` and builds `searchText = [selectedText, question]
.filter(Boolean).join("\n")` at line 78 specifically because, per its own
comment at lines 71-76, "until v0.77.0 only `selectedText` was read here, so
someone who typed 'reference 12의 제목이 뭐야?' without re-selecting the
bracket resolved nothing." That comment describes exactly the bug this
proposal is about — and the fix for it was applied to ONE of the ten
reference kinds (`citation`) and never propagated to the other eight
(`page`, `section`, `chapter`, `appendix`, `figure`, `table`, `equation`,
`theorem`).

Concretely, today: a reader who drags a paragraph and then types "이 문단이
언급하는 Figure 4는 뭘 보여줘?" — the word "Figure 4" lives in the QUESTION,
not in the drag-selected paragraph — gets no cross-reference resolution at
all, because `extractReferences` never sees the question. The same reader
asking "reference 12가 뭐야?" under the same drag DOES get resolution,
because citations got the fix and cross-references did not. This is not a
hypothetical; it is the same shape of bug already fixed once, still present
everywhere the fix wasn't copied — which is the structural argument for
folding these into one pass rather than patching call site by call site.

The chat sidebar is a partial exception worth noting precisely:
`ChatSidebarView.ts:1849` calls `resolveSelectionReferencesBlockAsync(query,
{...})` — passing the **typed chat message** as the first (`selectedText`)
argument, not an actual selection. That happens to make action 2 work for
cross-references on the sidebar, but only because the sidebar's calling
convention conflates "the text to scan for pointers" with "the drag
selection," which is a coincidence of that call site, not a designed
behavior — the popover's equivalent call (`quickQueryPopover.ts:537-569`)
correctly keeps `this.capturedSelection` as the selection and passes
`question` separately into `resolveSelectionContextAsync`, which then drops
it on the floor for everything except citations (`pdfReferenceContext.ts
:540-556`).

### 1.4 The central question, answered

**Is the right shape one resolution step, replacing N per-kind resolvers?**

**Mostly yes, with one honest exception the evidence does not support
merging.** The codebase already has the correct shape for 8 of the 10
pointer kinds: `crossReferenceResolver.ts`'s `PATTERNS: PatternSpec[]`
(`:132-206`) is a single kind-polymorphic detection table, and
`resolveOne`/`resolveReferences` (`:535-692`) is a single kind-dispatching
resolution loop that already produces one shared output type
(`ResolvedReference`) rendered by one shared formatter
(`buildResolvedReferencesBlock`, `:742-782`), with one shared
resolved/unresolved degradation contract (the `UNRESOLVED_NOTE`,
`:716-725`). The "N resolvers" problem is not that this table has 8 rows —
having 8 regexes for 8 genuinely different citation syntaxes is unavoidable
and not the disease. The disease is that **two more pointer kinds
(citation, wikilink) live entirely outside this table**, each reinventing
detection, question-handling, and (for citations) document-wide search from
scratch, and that **the fetch/expansion policy branches by kind instead of
by need** (only `equation` gets the document-wide backend search that every
distant, unresolved pointer actually needs).

So the design is: **one detection pass, one question+selection merge, one
resolved/unresolved contract, one "try harder when it's still unresolved"
escalation ladder that applies uniformly by need — with locate/fetch
strategies that are legitimately allowed to differ by kind**, because a
citation's target lives in a differently-structured place (a bibliography,
found by heading + entry-number parsing) than a section's target (an
outline entry) than a wikilink's target (a different vault file, found by
Obsidian's own link resolver). Collapsing locate strategies into one
function would be dishonest; collapsing detection, threading, and
degradation into one path is not just possible, it is what 8/10 kinds
already do, and it's exactly where the still-open bugs are.

#### 1.4.1 Detection: extend the existing table, not a new one

Add two entries to `crossReferenceResolver.ts`'s `PatternSpec` union
(`:124-127`, `:132-206`):

```ts
export type ReferenceKind =
  | "page" | "section" | "chapter" | "appendix"
  | "figure" | "table" | "equation" | "theorem"
  | "citation" | "wikilink";   // NEW

interface PatternSpec {
  kind: ReferenceKind;
  re: RegExp;
  build: (m: RegExpExecArray) => Partial<ReferenceQuery> & { label: string };
  /** NEW — context-sensitive accept/reject, for matches a bare regex can't
   *  disambiguate (citation vs. array index vs. footnote marker). Absent
   *  means "always accept," so the 8 existing kinds are untouched. */
  accept?: (fullText: string, m: RegExpExecArray) => boolean;
}
```

`citation`'s pattern is `BRACKET_GROUP` (`citationResolver.ts:218`) moved
here verbatim, with its collision rules (footnote `[^8]`, code span,
preceding-char class — currently `extractCitationNumbers`,
`citationResolver.ts:226-253`) becoming its `accept` hook instead of a
second, separately-invoked extraction function. `wikilink`'s pattern is new:
`\[\[([^\]|#]+)(#[^\]|]+)?(?:\|[^\]]+)?\]\]`, kind `"wikilink"`, label = the
link text (heading anchor kept separately for the locate step).

This is the concrete meaning of "without a per-kind regex zoo": today there
are three detection call sites (`extractReferences` for 8 kinds,
`extractCitationNumbers` for citations, nothing for wikilinks), each with
its own overlap-resolution and its own caller-side wiring. After this
change there is **one** call to `extractReferences`, over **one** merged
input (see 1.4.2), producing **one** sorted, de-overlapped list
(`extractReferences`'s existing overlap logic at `:226-238` already handles
this across kinds — citation and wikilink brackets need to be added to the
"more specific wins" tie-break, since `[12]` and `[[Note]]` can overlap
adjacent character ranges).

#### 1.4.2 One question+selection merge, at one place

Change `resolveSelectionReferences`/`resolveSelectionReferencesAsync`
(`pdfReferenceContext.ts:209-244`, `:270-296`) to accept an optional
`question` parameter and build the scan text the same way
`citationContext.ts:78` already does:

```ts
const searchText = [selectedText, question].filter(Boolean).join("\n");
const refs = extractReferences(searchText);
```

Then `resolveSelectionContextAsync` (`:517-556`) passes `question` into
**both** branches of its `Promise.all`, not just `resolveSelectionCitations`.
Once citations move into the same `extractReferences` table (1.4.1), this
collapses to a single call:

```ts
const resolved = await resolveSelectionReferencesAsync(
  selectedText, source, fetchPageText, locatePages, question
);
```

This is the fix for the action-2 asymmetry (1.3), applied once, upstream of
every kind, rather than per call site. Both callers
(`quickQueryPopover.ts:537-569` and `ChatSidebarView.ts:1849`) need a
one-line change to actually pass `question`/`query` through (the popover
already has `question` in scope and currently drops it before this call;
the sidebar already passes it as `selectedText`, which stops being
necessary/confusing once the real parameter exists).

#### 1.4.3 Locate strategies: shared escalation ladder, per-kind lookup

The existing ladder in `resolveSelectionReferencesAsync`
(`pdfReferenceContext.ts:270-487`) already has the right shape: try direct
target fetch → try adjacent-page probe (equation-only today) → try
document-wide `locatePages` (equation-only today) → try outline-range
expansion (all kinds) → fail closed. The fix is to **widen the
document-wide escalation gate from "is this an equation" to "is this still
unresolved after everything cheaper failed"**:

```ts
// today, :159-165:
function needsAdjacentEquationExpansion(ref: ResolvedReference): boolean {
  return ref.query.kind === "equation" && /^\d+$/.test(...) && ref.method !== "caption-index";
}

// proposed: generalize the DOCUMENT-WIDE gate (the :428-451 block) away from
// this equation-only predicate to:
function needsDocumentWideLocate(ref: ResolvedReference): boolean {
  return ref.method === "unresolved" || isWeakCurrentPageHit(ref, currentPage);
  // i.e. reuse needsOutlineExpansion's own condition (:152-157), so ANY
  // kind that survives outline-range expansion still unresolved gets one
  // backend search attempt before failing closed — not just equations.
}
```

This directly closes the action-4 gap (row 4 in 1.2): a reader 200 pages
into a book asking about "Definition 2.1," first seen on page 40 while they
are on page 260, currently gets only a bounded outline-range fetch (12-24
pages, and only if the ToC has an entry matching "2" or "2.1" — many books'
ToC does not go that deep) and then fails closed. With the gate widened,
it gets the same `client.getPdfRagHits`-backed whole-document search
equations already have (`ChatSidebarView.ts:1899-1911`, the existing
`locatePages` implementation) — and this is *lower risk* for
section/theorem/definition labels than it is for equations, because those
labels are descriptive text ("Definition 2.1", "Theorem 5.3") that BM25
handles well, whereas today's only user of this path searches on a bare
digit (`ref.label || objectNumber`, `pdfReferenceContext.ts:435`), which is
the noisier query of the two.

Citation's locate strategy (`loadBibliography`/`scanForBibliography`,
`citationContext.ts:111-157`, including the just-landed proportional
tail-scan-depth fix for books at `citationContext.ts:29-45`) is
**legitimately kept separate** — a bibliography entry is not findable by
BM25-searching the number "12"; it requires structural parsing (heading
detection, entry-number continuity across pages). The unification here is
narrower and still real: citation resolution becomes one more `case` inside
`resolveOne`'s kind switch (`:535-632`), sharing the same `ResolvedReference`
output shape, the same cache-or-fetch plumbing, and the same
resolved/unresolved formatter, instead of living in a separate module with
its own `Promise.all` branch and its own block tag
(`buildCitationsBlock`, `citationContext.ts:160-170`, producing
`<resolved_citations>` instead of `<resolved_cross_references>`). Keeping a
**separate block tag** for citations is correct and should stay — a cited
work's bibliography entry and a section's target content are semantically
different things the model should treat differently
(`chatContextPriority.ts:97`, the prompt already says so) — but the engine
underneath producing that tag's contents should be the shared one.

#### 1.4.4 Wikilinks: a new environment adapter, same detection/format contract

Wikilink resolution cannot live inside `crossReferenceResolver.ts`'s
`ResolveContext` (`:67-93`) as-is — that context is PDF-shaped
(`searchPages` over a BM25 page index, `getPageText` by page number,
`outline` as `PdfOutlineItem[]`). A markdown note has no pages. This is the
one place document kind legitimately forces a branch, and
`pdfReferenceContext.ts` already establishes the right pattern for it: it
is explicitly a *bridge* between the pure resolver and one environment (its
own file header, `:1-10`, says exactly this — "Bridges the pure
`crossReferenceResolver` with the in-memory PDF index"). The proposal is to
add a sibling bridge, `noteReferenceContext.ts`, for the vault environment:

```ts
export interface NoteReferenceSource {
  resolveLink: (linktext: string, sourcePath: string) => TFile | null; // app.metadataCache.getFirstLinkpathDest
  readFile: (file: TFile) => Promise<string>;                          // app.vault.cachedRead
  resolveHeading?: (content: string, heading: string) => string | undefined;
}

export async function resolveWikilinkReferences(
  refs: ReferenceQuery[],   // pre-filtered to kind === "wikilink" from the SAME extractReferences() call
  source: NoteReferenceSource,
  sourcePath: string
): Promise<ResolvedReference[]> { ... }
```

The output is still a `ResolvedReference[]`, rendered through the same
`buildResolvedReferencesBlock` — a wikilink that resolves becomes a
`<resolved_cross_references>` entry exactly like a resolved "Section 3.2,"
and an unresolved one (dead link, ambiguous link, note outside the vault)
gets the same `UNRESOLVED_NOTE` treatment. What's new is the locate/fetch
implementation, not the contract, and — critically — the SAME detection
pass and the SAME question+selection merge from 1.4.1/1.4.2 feed it, since
`extractReferences` already returns `wikilink`-kind entries alongside every
other kind from one call. This directly closes action-3's note gap (row 3
in 1.2): `[[관련 노트]]` in a selection or a typed question currently
produces zero special handling anywhere in the pipeline (confirmed:
`getFirstLinkpathDest` has exactly one caller in the whole plugin,
`templateRenderer.ts:94`, unrelated to reading context).

Both call sites need this new source wired in: `quickQueryContext.ts`
(new `resolvedWikilinksBlock` argument alongside the existing
`resolvedReferencesBlock`) and `ChatSidebarView.ts`'s per-turn resolution
(`:1849` and the per-pinned-ref path at `:1571`).

#### 1.4.5 Action 5 (own notes): one popover call, mirroring the sidebar exactly

No new architecture needed — the sidebar already does this correctly
(`ChatSidebarView.ts:4068-4087`, `workspaceNotesFor`). The fix is
mechanical: `quickQueryPopover.ts`'s `vaultEvidenceFor` (`:711-763`)
currently calls only `client.fetchContext` (the ingested-DAG path). Add the
same `searchWorkspaceNotes`/`buildWorkspaceNotesBlock` call
(`workspaceNotes.ts:124-150,186-202`) the sidebar makes, scoped to the
active file's workspace exactly as `ChatSidebarView.ts:4069-4071` resolves
it (`workspaceRelpathForFile(activeRelpath)`), and concatenate the result
into `vaultEvidenceBlock` before it's passed to
`buildQuickQueryContextMessages`. This is not a new resolution concept — it
is finishing the wiring for a mechanism that was already built generally
(`workspaceNotes.ts`'s own doc comment, `:1-24`, describes the gap in
vault-wide terms — "137 markdown files on disk, 36 ingested" — not in
sidebar-specific terms) and only ever connected to one surface.

#### 1.4.6 Action 6 (compare two documents): thread `openTabs` into the popover

Also mechanical, not a new mechanism. `buildActiveBackgroundContext`
(`quickQueryContext.ts:81-134`) takes `ActiveContext` and reads
`.viewType`/`.fileContent`/`.pdfPage` — never `.openTabs`, even though
`ActiveContext.openTabs` (`types.ts:480`) is populated by the same
`refreshActiveContext()` call the popover already makes
(`quickQueryPopover.ts` calls `this.plugin.refreshActiveContext()` at the
top of `runQuery`). The sidebar's pattern
(`ChatSidebarView.ts:1467-1509` for markdown tabs,
`:1761-1780`/`getPromptIncludedTabs` for PDF tabs) should be mirrored at a
popover-appropriate budget — smaller than the sidebar's 8000-chars-per-tab
/ 3-PDF-tab budget, since the popover's whole background block is already
capped at `DEFAULT_BACKGROUND_LIMIT = 12000` total
(`quickQueryContext.ts:57`). A reasonable popover version: outlines for
every open markdown/PDF tab (cheap, high signal) plus a much smaller
per-tab content excerpt (e.g. 1500 chars) for at most 2 non-active tabs,
folded into the existing `maxBackgroundLength` budget rather than added on
top of it.

### 1.5 Ranked gaps and the smallest change set

Ranked by how often an actual reader hits the gap, given the vault holds
papers, books, and the reader's own notes side by side:

1. **Action 2/3 asymmetry (question not threaded into cross-reference
   detection).** Highest frequency — this is the literal shape of the bug
   that opened this release, and it recurs every time a popover follow-up
   question names a pointer instead of re-selecting it. **Fix: 1.4.2**,
   ~15 lines across `pdfReferenceContext.ts` and the two call sites.
2. **Wikilink following (action 3, note case).** A personal Zettelkasten
   vault's primary navigation structure — `[[links]]` — has zero
   resolution support in the reading assistant, on either surface. **Fix:
   1.4.1 (wikilink pattern) + 1.4.4 (new adapter)**, the largest single
   piece of new code in this proposal but still additive, not a rewrite.
3. **Distant non-equation pointers (action 4, book case).** Named
   explicitly in the brief as the headline book scenario ("the answer is
   200 pages back") and currently only equations get the backend-search
   escalation. **Fix: 1.4.3**, a one-line gate widening plus reusing the
   existing `getPdfRagHits`-backed `locatePages` implementation that
   already exists for equations.
4. **Workspace notes missing from the popover (action 5).** The popover is
   the fast-lookup surface, so "did I already think about this" is a
   natural popover question, and it silently answers from the ingested DAG
   only. **Fix: 1.4.5**, mechanical, reuses an existing function.
5. **Multi-document compare missing from the popover (action 6).** Real,
   but the popover is inherently single-selection-triggered, so this is
   hit less often than 1-4 in practice — a reader doing serious
   document-to-document comparison is more likely to already be in the
   sidebar. **Fix: 1.4.6**, mechanical, budget-bounded mirror of existing
   sidebar logic.

Items 1, 4, and 5 are pure wiring fixes (no new resolution concept, reusing
code that already exists for the other surface). Items 2 and 3 are the
actual "one resolution step" architecture work — extending the existing
kind-dispatch table rather than adding an eleventh parallel module.

### 1.6 What stays N, on purpose (named honestly, not glossed over)

- **Citation locate strategy** (1.4.3) stays a distinct structural parser
  (heading + entry-number continuity), not a BM25/outline lookup, because a
  bibliography number is not semantically findable by keyword search the
  way a section title is. Only its detection, threading, and output
  contract move into the shared path.
- **Wikilink locate/fetch** (1.4.4) stays a distinct adapter file because
  its environment (Obsidian's own link graph and vault reads) shares
  nothing with the PDF environment's page/outline/BM25 shape. Forcing it
  into `ResolveContext` would mean stubbing our four PDF-shaped fields with
  meaningless values for every note question, which is worse than a second
  small adapter.
- **Distinct block tags** (`<resolved_cross_references>` vs.
  `<resolved_citations>`, and a new `<resolved_wikilinks>` or reuse of the
  cross-reference tag for notes) are kept because the model needs to know
  *what kind* of pointer it is looking at to answer correctly — a cited
  work's bibliography line is not the same thing to explain as the target
  section's own content — and `chatContextPriority.ts:97` already carries
  per-tag guidance the model relies on.

## 2. Pros & Cons

**Pros**

- Directly closes the exact bug shape that started this release
  (question-not-threaded), and closes it upstream in one place instead of
  patching each of the ten kinds' call sites separately, so the eleventh
  kind added later inherits the fix instead of needing its own.
- Every "N-resolver" fix proposed here is additive to an architecture that
  already exists and mostly works (`PATTERNS`/`resolveOne`/
  `buildResolvedReferencesBlock`) — this is not a rewrite, it is finishing
  a pattern the codebase already committed to for 8 of 10 kinds.
- Three of the five ranked fixes (1, 4, 5) require zero new resolution
  concepts — they reuse a function or a code path that already works
  correctly on the sidebar and was simply never wired into the popover.
  These are low-risk, testable in isolation, and each removable
  independently if review finds a problem.
- The document-wide locate widening (1.4.3) is evidence-backed as *lower*
  risk for its new kinds (descriptive labels) than for its existing kind
  (bare digits), not merely "probably fine."

**Cons — named explicitly, not solved by this proposal**

- **Equations/figures/tables drawn as images remain unanswerable on every
  CLI-routed provider** (`promptRegistry.ts:92-97` `surfaceToolReality`,
  `messageUtils.ts:56-73` `shouldInjectLocalTools`, `LLMClient.ts:1789-1792`
  `shouldUseCli` — local tool injection, including `read_pdf_page_image`,
  fires only for `ollama`/`deepseek`; every other provider routes through a
  CLI subprocess that gets no injected tools at all). This is a provider
  tool-injection problem, not a pointer-resolution problem: a perfect
  resolver still only returns text, and a rasterized equation has none.
  Nothing in this proposal changes that; it would need either a
  vision-capable emission on the CLI path or pre-rendering page images into
  context proactively (out of scope — no new always-on subprocess, and the
  brief's ground rules forbid a new external dependency).
- **Wikilink resolution adds new surface area** (a new adapter file, two
  new wiring points) rather than being pure deletion — this proposal
  reduces the number of *parallel systems* for existing actions but does
  add code for action 3's note case, since nothing existed to consolidate.
- **The document-wide locate widening (1.4.3) is unmeasured** against real
  book PDFs at the time of writing; the equation path's existing bound
  (`DOCUMENT_WIDE_EQUATION_PAGE_LIMIT = 3`, `pdfReferenceContext.ts:35`)
  should carry over as a starting cap for the new kinds, but the right
  bound for a 900-page book's theorem lookup vs. a 30-page paper's equation
  lookup may differ and needs a P0 measurement pass, not an assumption.
- **Multi-document compare in the popover (1.4.6) is deliberately
  under-scoped relative to the sidebar** (2 non-active tabs, 1500 chars
  each, vs. the sidebar's 3 PDFs / unlimited markdown tabs at 8000 chars)
  to respect the popover's tighter prompt budget and the brief's §"the
  prompt-budget gate is real." A reader doing heavy multi-document work in
  the popover will still hit a ceiling this proposal does not remove — the
  sidebar remains the right surface for that, by design.
- **Citation and wikilink detection sharing one `extractReferences` call
  means their overlap-resolution tie-breaks now interact** (a citation
  `[12]` and a markdown reference-style link `[text][12]` were already a
  known collision `citationResolver.ts:239-246`; adding wikilink brackets
  `[[...]]` into the same merged/sorted list needs its own overlap test,
  not assumed safe by analogy).
- This proposal does not address non-numbric/non-bracket pointers such as a
  reader asking about undefined notation with no explicit label at all
  (e.g., "이 σ가 뭐야?" with no "Definition N" anywhere in the selection) —
  that is a retrieval/vault-evidence question (action 5's territory, or
  general-knowledge fallback), not a pointer-following one, and is already
  as-covered as it will get by the existing `vaultEvidenceBlock` and the
  "answer from general knowledge" instruction
  (`promptRegistry.ts:132-136`).
