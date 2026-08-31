# Retrieval-pipeline coverage audit: fix list

Date: 2026-08-31 | Agent Persona: retrieval_engineer

Method: read the pre-turn gathering path in both surfaces end to end
(`quickQueryPopover.ts`, `ChatSidebarView.ts`), traced every function each
calls into (`quickQueryContext.ts`, `chatContextPriority.ts`,
`providerContextPolicy.ts`, `pdfReferenceContext.ts`,
`crossReferenceResolver.ts`, `citationContext.ts`, `citationResolver.ts`,
`wikilinkResolver.ts`, `noteWindow.ts`, `providerContextFormat.ts`), and
checked the backend surface it all bottoms out on
(`backend/src/curator/plugin_api/pdf.py`, `backend/src/curator/context_service.py`,
`backend/src/curator/retrieval/*`). This is a coverage audit, not a redesign —
every entry below names an EXISTING feature or code path that is wired
incorrectly, wired to only one surface, or not wired at all. None of the four
already-fixed items (wikilink following for notes, bibliography tail-scan
depth, outline windowing, long-note windowing as a *mechanism*) are
re-proposed. Where a "fixed" item turns out to be fixed on only one surface,
that is reported as a coverage gap, not a re-proposal of the mechanism.

A sibling document, `11_proposal_reading_modes.md`, covers the architectural
question (one resolution step vs. N per-kind resolvers) and independently
found the core shape of finding #2 below from the "action" axis. This
document is organized by severity and cell coverage instead, per this task's
brief, and adds several findings that proposal's cross-reference-kind framing
did not surface (the sidebar's bibliography-list fallback being dead, the
tail-truncation direction bug, the `[[#Heading]]` self-link gap, and the
long-note-windowing coverage gap).

## Fix list, ordered by severity

### 1. System-prompt truncation cuts from the tail, discarding exactly the material the sidebar's own code says matters most — worst at book scale

**File:line:** `plugin/src/ui/chat/ChatSidebarView.ts:2154-2162` (`truncateContext`,
which calls `truncateToLength` at `plugin/src/utils/textUtils.ts:132-135` —
`content.slice(0, maxLength)`, i.e. keep the head, drop the tail), applied to
the WHOLE assembled system prompt at `ChatSidebarView.ts:1566`.

**What happens:** `buildLLMMessages` (`ChatSidebarView.ts:1404-1661`) builds
`systemText` by appending, in this order: base prompt → cursor-style rules →
provider-shared context → `context_priority` → `editable_selection` →
`obsidian_incurator_context` (vault evidence pack, resolved cross-references,
workspace notes, PDF window, document outline, PDF RAG hits, source status —
everything `buildIncuratorProviderContext`, `:1775-2086`, produces) → open-tab
list + tab content + `markdown_outlines` (`:1472-1514`) → the **wikilinks
block** (`:1516-1534`, this release's own new feature) → "Currently active
file" / "viewing PDF page N" (`:1536-1543`) → `edit_review_loop`
(`:1545-1564`), whose own comment says it is placed LAST "so it sits at the
position of strongest LLM attention." The whole string is then pushed as the
system message wrapped in `this.truncateContext(systemText)` (`:1566`), which
truncates from the **end**.

Under length pressure — a book PDF's page window (`formatPdfWindow` at 3000
chars/page × up to 8 pages × up to 3 open PDF tabs), a large vault-evidence
pack (up to 16000 tokens via `packLimit`, `:2038-2041`), and several open
markdown tabs (8000 chars each) all stacking in the SAME system prompt — this
is realistic exactly in the scenario the brief cares about: a reader with a
book open plus other tabs, especially on a smaller-context-window model
(the CLAUDE.md-documented Ollama/local path). When the budget is exceeded,
truncation removes, IN THIS ORDER: `edit_review_loop` first, then the
"active file" pointer, then the **wikilinks block**, then open-tab
content/outlines — i.e., exactly backwards from what the code's own comments
say should survive, and it can silently swallow this release's own wikilink
fix under the load conditions most likely to trigger it.

The popover has no equivalent risk: every block `buildQuickQueryMessages`
(`quickQueryContext.ts:208-278`) assembles is pre-bounded individually
(`DEFAULT_BACKGROUND_LIMIT=12000`, `PINNED_SOURCE_LIMIT=6000`,
`QUICK_QUERY_VAULT_EVIDENCE_TOKENS=2500`, `FOLLOWUP_TEXT_LIMIT=4000`) and
nothing does a final blanket cut over the assembled turn — so this is a
genuine surface divergence as well as a book-scale and ordering issue.

**Cells repaired:** book-sidebar (most acutely — largest windows/outlines/
evidence), paper-sidebar and note-sidebar in heavy multi-tab sessions.

**Concrete change:** stop doing one blanket tail-cut of the fully assembled
system prompt. Either (a) keep every section pre-bounded the way the popover
already does — the pattern already exists everywhere else in this codebase —
so there is nothing left needing a final safety net, or (b) if an overall cap
must remain as a last resort, cut from a point that preserves the
deliberately-late sections (e.g. reserve their combined length and truncate
only the material before them). This is a judgment call about how prompt
assembly should degrade under pressure, not a one-line fix — flagging
precisely rather than picking for the user.

---

### 2. The sidebar never gets the "ask about the bibliography with no `[N]`" fallback — the exact bug shape this release opened with, recurring on the other surface

**File:line:** `plugin/src/context/pdfReferenceContext.ts:498-506`
(`resolveSelectionReferencesBlockAsync` — signature is `(selectedText, source,
fetchPageText, locatePages)`, no `question` parameter, and it calls
`resolveSelectionContextAsync(selectedText, source, fetchPageText,
locatePages)` at line 504 with the 5th `question` argument simply omitted);
called this way at `plugin/src/ui/chat/ChatSidebarView.ts:1873-1941`.

**What happens:** `resolveSelectionCitations`
(`plugin/src/context/citationContext.ts:84-122`) computes
`asksForList = asksAboutBibliography(question ?? "")` (line 98) — this is
precisely the v0.77.0 fix ("bibliography-seeking question gets the reference
list even with no `[N]`") — and only takes the whole-list fallback path when
`asksForList` is true. Because `resolveSelectionReferencesBlockAsync` has no
way to pass `question` through, `resolveSelectionContextAsync`
(`pdfReferenceContext.ts:517-561`) always receives `question = undefined` on
the sidebar's call path, so `asksForList` is **always false** there,
regardless of what the reader typed. Contrast the popover, which calls the
question-carrying `resolveSelectionContextAsync` directly
(`quickQueryPopover.ts:564-596`, `question` as the 5th argument) — where the
fix genuinely works.

Concretely: a reader asks the popover "이 논문 참고문헌 목록 보여줘" (no
bracket) and gets the whole reference list. The identical question asked in
the chat sidebar, on the identical document, gets nothing — `matched.length
=== 0 && !asksForList` returns `[]` (`citationContext.ts:112`). This is the
mirror image of the bug that opened this release (a typed question about a
reference that resolved nothing because only the selection was read) —
fixed on the surface that reported it, not on the other one.

**Cells repaired:** book-sidebar and paper-sidebar (the sidebar's citation
fallback for a no-bracket reference-list question).

**Concrete change:** give `resolveSelectionReferencesBlockAsync` an optional
`question?: string` parameter and forward it into
`resolveSelectionContextAsync`'s 5th argument; at the sidebar's call site
(`ChatSidebarView.ts:1873`) pass `query` (already in scope in
`buildIncuratorProviderContext`) as that question. `query` is currently
consumed as the function's `selectedText` argument, which is what lets
cross-reference detection work here at all (see finding #3) — it should
additionally be passed as `question` once the parameter exists, not
instead of being `selectedText`.

---

### 3. The popover never resolves a cross-reference (Fig./Sec./Eq./Chapter/Table/Theorem/p.) that is only in the typed question — the mirror-image gap of #2

**File:line:** `plugin/src/ui/quickQueryPopover.ts:564-571` (calls
`resolveSelectionContextAsync(this.capturedSelection, {...}, fetchFn,
undefined, question)` — `this.capturedSelection` is the ONLY text that
reaches reference detection); `plugin/src/context/pdfReferenceContext.ts
:270-296` (`resolveSelectionReferencesAsync` — its signature has no
`question` parameter at all, ever); `pdfReferenceContext.ts:540-556`
(`resolveSelectionContextAsync` threads `question` into
`resolveSelectionCitations` at line 555 only — `resolveSelectionReferencesAsync`
at line 541 gets `selectedText` alone).

**What happens:** the citation fix (finding #2's mechanism, working correctly
on the popover) only widened `resolveSelectionCitations` to read `question`.
The cross-reference resolver — the SAME general mechanism, for the other
eight pointer kinds (`page`, `section`, `chapter`, `appendix`, `figure`,
`table`, `equation`, `theorem` — `crossReferenceResolver.ts:25-33`) — never
got the same widening. `extractReferences` (`crossReferenceResolver.ts
:209-239`) is only ever called on `this.capturedSelection` in the popover, so
a reader who drags an unrelated paragraph and then types "이 부분에서
언급하는 Figure 4는 뭘 보여줘?" — the label lives in the QUESTION, not the
drag — gets no cross-reference resolution for it at all.

The sidebar happens NOT to have this specific gap, but only by an accident
noted in finding #2: it passes the typed message itself as
`resolveSelectionReferencesBlockAsync`'s `selectedText` argument, so
`extractReferences` does see the question there. That accident is exactly
what breaks finding #2 (the true selection/question distinction citations
need is erased). Fixing #2 and #3 together with the same mechanism —
building `searchText = [selectedText, question].filter(Boolean).join("\n")`
once, upstream of both the cross-reference and citation calls, the way
`citationContext.ts:99` already does for citations alone — closes both gaps
without re-introducing either one. (This is the same fix `11_proposal_reading_modes.md`
§1.4.2 proposes from the architecture angle; independent corroboration.)

**Cells repaired:** paper-popover, book-popover (a typed reference/figure/
equation/section pointer with no matching text in the current selection).

**Concrete change:** add an optional `question?: string` parameter to
`resolveSelectionReferencesAsync` (and its sync sibling
`resolveSelectionReferences`), merge it with `selectedText` the same way
`citationContext.ts` already does, and have `resolveSelectionContextAsync`
pass `question` into both branches of its `Promise.all` (currently only the
citations branch). Then have `resolveSelectionReferencesBlockAsync` gain the
`question` parameter from finding #2 and forward it here too, so the sidebar
gets this fix "for free" once #2 and #3 share the same threading point.

---

### 4. A book's bibliography is still cut after 6 physical pages, even once the (already-fixed) tail scan finds the heading

**File:line:** `plugin/src/context/citationContext.ts:51`
(`const CONTINUATION_PAGES = 5;`), consumed at line 172
(`for (let next = start + 1; next <= Math.min(lastPage, start +
CONTINUATION_PAGES); next += 1)`), inside `scanForBibliography`
(`:151-178`).

**What happens:** this is a DIFFERENT constant from the one already fixed.
`tailScanDepth` (`:46-49`, already fixed to scale with page count) controls
how far back the scanner looks to FIND the References heading. Once found,
`scanForBibliography` still only reads the heading page plus
`CONTINUATION_PAGES = 5` more pages — 6 pages total — before calling
`collectBibliography(window)` and returning, no matter how long the actual
list is. The module's own doc comment gives the motivating measurement: a
110-entry paper's bibliography fits in 3 pages (`:9-14`). A book's
bibliography, or a long survey's reference list, routinely runs past 6
physical pages; every entry past page 6 is simply never read, and any
citation to it resolves to nothing — even on a document where the heading is
now found correctly.

`collectBibliography` itself (`citationResolver.ts:142-162`) already has the
right stopping condition — it stops at the first page that adds nothing new,
or whose numbering restarts — so the artificial `start + CONTINUATION_PAGES`
ceiling is what is cutting the scan short, not `collectBibliography`'s own
logic.

**Cells repaired:** book-popover, book-sidebar (any citation to an entry
past the 6th page of the reference list); also a long-survey-paper case.

**Concrete change:** let the continuation fetch keep following pages while
`collectBibliography` keeps finding new, climbing entry numbers, instead of
stopping at a flat `+5`. A proportional cap in the same spirit as
`tailScanDepth` (floor at the current 5, scale with `pageCount`, ceiling to
bound worst-case cost) is the minimal change; removing the cap entirely and
relying purely on `collectBibliography`'s natural stop condition is also
defensible since that stop condition is already the safety net.

---

### 5. Long-note windowing — already fixed, but wired into only one surface

**File:line:** `plugin/src/context/noteWindow.ts` (the fix, `selectNoteWindow`,
`:83-151`) is imported and called at exactly one place in the whole plugin:
`plugin/src/context/quickQueryContext.ts:9,119` (`buildActiveBackgroundContext`,
the popover's path). `plugin/src/ui/chat/ChatSidebarView.ts:2213-2319`
(`buildAutoContextRefs`, the sidebar's equivalent for the active markdown
note) still calls `this.truncateContext(tab.content)` at line 2226, which is
`truncateToLength` — pure `content.slice(0, maxLength)` head truncation
(`plugin/src/utils/textUtils.ts:132-135`) — exactly the failure mode
`noteWindow.ts`'s own doc comment (`:1-13`) describes as fixed: "a question
about the middle is answered from the top or not at all."

This is not a re-proposal of the windowing mechanism — it is a report that
the mechanism's rollout covers one of the two surfaces the brief asks about.
A reader who has kept a note for a year and asks about its middle gets a
windowed, relevant answer from the popover and a head-truncated, likely
irrelevant answer from the sidebar, for the identical note and the identical
question.

The same flat head-truncation pattern also governs two adjacent sidebar
paths that are lower-traffic but share the defect: non-active open markdown
tabs (`TAB_CONTENT_LIMIT = 8000`, `ChatSidebarView.ts:1487-1494`) and the
markdown edit-target dump (`TARGET_LIMIT = 50000`,
`buildOpenMarkdownEditTargetContext`, `:1698-1729`).

**Cells repaired:** note-sidebar (headline); secondarily any non-active
markdown tab or edit-target note on the sidebar.

**Concrete change:** route the active markdown tab's content in
`buildAutoContextRefs` through `selectNoteWindow` (passing the reader's
current selection/question, which are both already in scope where this
function is called from `buildLLMMessages`) instead of `truncateContext`'s
flat slice. Whether to extend the same treatment to non-active tabs and the
edit-target dump is a smaller follow-on judgment call, not required to close
the headline gap.

---

### 6. `[[#Heading]]` same-note wikilinks never resolve, on either surface — a capability that was built and never wired

**File:line:** `plugin/src/context/wikilinkResolver.ts:126-142`
(`resolveWikilinks`'s third, optional `self` parameter, built specifically
for `[[#Heading]]` — the function's own comment at lines 129-132 calls it
"an everyday Obsidian form"). Called with only 2 arguments — no `self` — at
both:
- `plugin/src/ui/quickQueryPopover.ts:552-556`
- `plugin/src/ui/chat/ChatSidebarView.ts:1528-1532`

**What happens:** `resolveWikilinks`'s branch for an empty `link.target`
(`wikilinkResolver.ts:138-142`) is `self ? { path: self.selfPath, text:
self.selfText } : undefined`. Since `self` is never passed by either caller,
this branch always evaluates to `undefined`, and the link is silently
dropped (`if (!found?.text?.trim()) continue;`, line 143) before it ever
reaches `buildWikilinksBlock`. `readVaultNote` (`main.ts:1859-1874`) is never
even consulted for this case, because `resolveWikilinks` only calls `read()`
when `link.target` is non-empty (line 138-139) — a same-note link never
reaches it at all. This is not a divergence between the surfaces (both are
equally broken) — it is the "computed and never reaches the prompt" shape
named in the task: the parameter, the type, and the doc comment explaining
why it exists were all written, and neither caller passes it.

**Cells repaired:** note-popover and note-sidebar identically.

**Concrete change:** both call sites already have what `self` needs in
scope (`activeContext.filePath`/`activeContext.fileContent` in the popover,
`activeCtx?.filePath`/`activeCtx.fileContent` in the sidebar, guarded the
same way the existing `activeContext?.viewType === "markdown"` /
`activeCtx?.viewType === "markdown"` checks already guard the call). Pass
`{ selfPath: <filePath>, selfText: <fileContent> }` as the third argument at
each site.

---

### 7. Sync vs. async cross-reference resolution split inside the sidebar itself, for the same reader action

**File:line:** `plugin/src/ui/chat/ChatSidebarView.ts:1595`
(`resolveSelectionReferencesBlock(ref.content, {...})` — the SYNC,
non-page-fetching function, `plugin/src/context/pdfReferenceContext.ts
:254-259`) vs. `ChatSidebarView.ts:1873`
(`resolveSelectionReferencesBlockAsync(query, {...})` — the ASYNC,
page-fetching function, `pdfReferenceContext.ts:498-506`).

**What happens:** the sidebar resolves pointers two different ways depending
on WHERE the pointer text lives, not on what kind of pointer it is. A
pointer typed into the chat message (or living in a PDF tab's own window)
gets the full async treatment — it can trigger a backend page fetch for a
distant target. A pointer inside a PINNED/cropped primary-focus context ref
(`isPrimaryUserContext(ref)`, line 1590) is resolved with the sync function,
which can only match against whatever pages are ALREADY in `ref.windowPages`
— it can never fetch a missing page. The popover has one path
(`resolveSelectionContextAsync`, always async) for the equivalent action, so
this is a within-sidebar inconsistency more than a cross-surface one, but it
means the SAME reader action — pin a passage, then ask about a pointer
inside it — behaves differently from asking the same thing in the message
box.

**Cells repaired:** paper-sidebar, book-sidebar (a pointer inside a pinned/
cropped selection whose target page is not already loaded).

**Concrete change:** lower priority than 1-6 above — flagging for the
record since it is squarely "the same reader action resolved differently,"
but the fix (giving the per-ref path a page-fetch callback and awaiting it)
is more involved than the others and I could not find evidence in the code
of how often a pinned ref's `windowPages` actually lacks the target in
practice, so I am not asserting this is high-impact — naming it precisely
rather than guessing at frequency.

---

### 8. Popover vault-evidence gate is narrower than the sidebar's, for the same "should I even fetch" decision

**File:line:** `plugin/src/ui/quickQueryPopover.ts:740`
(`if (isEditRequest(question)) return undefined;` — the popover's only gate)
vs. `plugin/src/context/providerContextPolicy.ts:121-144`
(`shouldRunCuratorDomainQuery` — the sidebar's gate, which additionally skips
short follow-ups via `SHORT_FOLLOW_UP_RE`, `providerContextPolicy.ts:4`, and
skips when a primary SELECTED context ref is being edited).

**What happens:** a bare "again" / "다시 해줘" follow-up in the popover still
triggers the up-to-4-second vault-evidence fetch path
(`QUICK_QUERY_VAULT_EVIDENCE_TIMEOUT_MS = 4000`, `quickQueryPopover.ts:138`)
that the sidebar would skip outright. This never produces a wrong or missing
answer — the popover's timeout means it degrades to "answer without vault
evidence" either way — so this is a minor latency/wasted-fetch divergence,
not a correctness bug. Noting it because item 1 asks for every divergence
for the same action, not only the ones that change the answer.

**Cells repaired:** none broken outright; minor latency difference on
paper/book/note-popover for short follow-up turns.

**Concrete change:** low priority. If addressed, reuse
`SHORT_FOLLOW_UP_RE`-equivalent logic in `vaultEvidenceFor`'s gate.

---

### 9. Vault-evidence budget: flat cap on the popover, proportional on the sidebar — documented as intentional, noted for completeness

**File:line:** `plugin/src/ui/quickQueryPopover.ts:126`
(`QUICK_QUERY_VAULT_EVIDENCE_TOKENS = 2500`, flat) vs.
`plugin/src/ui/chat/ChatSidebarView.ts:2038-2041` (`packLimit`, proportional
to `maxContextLength`, capped at 16000).

**What happens:** the popover's own comment
(`quickQueryPopover.ts:122-126`) explains this is deliberate — the popover
answers about a selection, and vault evidence is a bonus, not the main
event. Listed here only because item 1 asks for every place the two
surfaces diverge on the same input; this one is a documented design choice,
not a bug, and I am not proposing a change.

**Cells repaired:** none — informational.

---

### 10. Item 2 (book-scale constants), remaining entries not covered above

- **`plugin/src/context/providerContextFormat.ts:258`**
  (`for (const item of items.slice(0, 12))` inside `formatCuratorContextPack`)
  hard-caps rendered vault-evidence items at 12, regardless of how many the
  backend's own token-budget accounting (`_apply_budget`/`_budget_payloads`,
  `backend/src/curator/context_service.py:195-220,474-520`) already selected
  as fitting the requested `limit_tokens`. Shared identically by both
  surfaces (not a divergence), but is exactly the "top-k unrelated to how
  much actually fits" shape item 2 asks about. **Lower confidence this is
  wrong** — 12 items may be a deliberate prompt-readability choice
  independent of token budget, and I could not establish from the code
  which the original author intended. Flagging for judgment, not asserting
  a fix.
- **`plugin/src/context/citationContext.ts:82`**
  (`MAX_WHOLE_BIBLIOGRAPHY_ENTRIES = 40`) caps the whole-bibliography-dump
  fallback (finding #2's payload, once #2 is fixed) at 40 entries. For a
  paper this is generous; for a book bibliography this could still be a
  small fraction of the true list. Lower severity than finding #4 because a
  reader asking for "the reference list" in a popover/chat turn is
  plausibly well served by the 40 most numerous entries rather than the
  full list — flagging, not asserting it needs to change.
- **Backend (`backend/src/curator/plugin_api/pdf.py:206-389`, `pdf_context`):**
  the vault-wide evidence retrieval underneath `fetchContext` is
  token-budget-driven throughout (`_apply_budget`, `context_service.py`),
  which already scales correctly with corpus size — I found no flat,
  document-length-blind constant there worth flagging. The PDF-window
  fetch (`radius`/`max_pages`) is a per-request parameter supplied by the
  plugin (`pdfWindowRadius` default `1`, `pdfRagTopK` default `5`,
  `types.ts:194,197`), not a hardcoded constant, and a small fixed window
  around the current page is correct regardless of document length (a
  reader is always centered on a couple of pages, whatever the book's
  total size) — I did not find this to be a book-scale bug.

---

## Answers to the five audit questions, directly

**1. Divergence between the two surfaces.** Findings #2, #3, #5, #7-9 above
are the full list found. #2 and #3 are the same shape as the reported bug —
one surface reads the question for one purpose (citations vs.
cross-references) and not the other. #5 is a fix credited as complete in the
coverage matrix that is genuinely only complete on one surface. #7 is a
within-surface split for the same action. #8-9 are minor/by-design.

**2. Book-scale constants.** `CONTINUATION_PAGES = 5`
(`citationContext.ts:51`, finding #4) is the one that is clearly wrong at
book scale and not yet fixed. `items.slice(0, 12)`
(`providerContextFormat.ts:258`) and `MAX_WHOLE_BIBLIOGRAPHY_ENTRIES = 40`
(`citationContext.ts:82`) are flagged with lower confidence — see #10. I
looked specifically for a repeat of the outline bug's shape (flat head-N
that silently never fires on small documents) across `formatPdfWindow`,
`formatRagHits`, the PDF-window `radius`/`max_pages` path, and the backend's
budget system, and found none of comparable severity — those are either
per-page (scale-invariant) or already token-budget-driven.

**3. The vault-evidence path.** Answered in full in finding text above and
restated here directly: `vaultEvidenceFor`
(`quickQueryPopover.ts:739-791`) is silent in every failure mode. Backend
offline (`client.available === false`, line 744): returns `undefined`
immediately, no log, no UI signal. Fetch throws: caught, logged via
`logger.warn` to the console only (line 769) — never shown in the popover
UI. Fetch times out (>4000ms): logged via `logger.info` to the console only
(lines 784-787), the popover answers without evidence this turn while the
fetch keeps running in the background for the next question (documented,
intentional). In no failure mode does the popover's UI
(`provenance.ts:148-151`, `summarizeProvenance` — which covers only
cross-references and citations, never vault evidence) tell the reader
anything about whether their own notes were searched. Whether the OPEN
document is in the vault DB is orthogonal to this call: `fetchContext` is a
vault-WIDE query (not scoped to the open document), so an un-ingested PDF or
note simply will not itself appear among results — other vault content can
still surface normally, confirming what the coverage matrix already
concluded.

**4. Ordering.** Popover: `quickQueryContext.ts:255-272` — primary selection
→ resolved refs/citations → wikilinks → background (outline/PDF window) →
vault evidence → pinned sources → followups → **the question itself** →
recency anchor, all in ONE user-turn message, with the question and anchor
last. Sidebar: `buildLLMMessages`,`ChatSidebarView.ts:1404-1661` — nearly
all of the equivalent content (vault evidence, resolved refs, wikilinks, PDF
window/outline, "active file" pointer, edit-loop contract) lives in the
SYSTEM message, which precedes the entire conversation history, not just the
latest turn; only a short recency-anchor INSTRUCTION (not the evidentiary
content itself) is appended to the latest user message's own text
(`:1645-1650`). The two surfaces do not agree, and the sidebar's positioning
is further undermined by finding #1 (tail-truncation), which can strip
exactly the material placed latest in that system message. On the strict
question "is the most relevant material near the end, where attention is
strongest": yes for the popover, no for the sidebar's block-level content
(only its short anchor instruction sits at the true end).

**5. Computed but never reaches the prompt.** Finding #6
(`[[#Heading]]`/`self` — a full parameter and code path built and never
invoked with what it needs) is the clearest instance found, matching the
task's named precedent exactly. Lower-confidence secondary instances,
included for completeness: `pack.route_reason`, `pack.coverage`, and
`pack.evidence` (`types.ts:619-644`) are parsed by the client
(`incuratorClient.ts:1018-1034`) but `formatCuratorContextPack`
(`providerContextFormat.ts:193-291`) never reads `route_reason` or
`evidence`, and `coverage` reaches only the separate query-trace debug panel
(`incuratorQueryTrace.ts:200`), never the prompt. I could not establish from
the code whether these were intended as prompt content or are deliberately
diagnostic-only — flagging rather than asserting a bug, since (unlike the
v0.75.0 persona precedent) there is no comment or test suggesting these were
meant to reach the model.

## What I could not establish from the code

- **Frequency/impact of finding #7** (sync vs. async pointer resolution for
  pinned refs) — I have no measurement of how often a pinned ref's
  `windowPages` actually lacks the target page in practice, so I ranked it
  by mechanism-severity rather than measured impact.
  - **Whether `items.slice(0, 12)` and `MAX_WHOLE_BIBLIOGRAPHY_ENTRIES = 40`
    (finding #10) are bugs or deliberate prompt-length choices** — no comment
  or test in either file states the intent behind the specific numbers, only
  that a cap exists.
- **Whether `contextWindow` values feeding `truncateContext`
  (`ChatSidebarView.ts:2154-2162`) are expressed in characters or tokens**
  — I could not find where `ModelOption.contextWindow` values are actually
  populated (no literal `contextWindow:` assignment outside test files), so
  I cannot say how often finding #1's truncation actually fires in
  production versus only under unusual settings. The STRUCTURAL bug (tail-cut
  direction contradicting the code's own "attention" comments) holds
  regardless of how often it triggers, which is why it is still ranked #1.
