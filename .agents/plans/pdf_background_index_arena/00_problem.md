# Briefing: the chat cannot search a PDF page the user has not scrolled past

Date: 2026-08-09 | Convener: Claude Code | Status: OPEN for proposals

## 0. Where this came from

The user asked a direct question: *"when I use sidechat or the popover, is it
definitely searching my knowledge system + the currently open PDF (including
non-rendered pages) + information in my vault?"* — adding that this had been
"fixed several times and still doesn't work."

Two of the three channels were answered in v0.53.0: the MCP server was
unstartable by any client since v0.34.0, and the vault had no `mcpServers`
entry, so the knowledge system and vault channels were unreachable regardless of
how well the backend answered. Both now work.

**This briefing is about the third channel, which is still broken.**

## 1. The defect, stated precisely

`pdfFullDocumentIndex` — labelled in settings as *"Background page indexing —
Index all pages of open PDFs in the background for faster search"* — is a
**setting with zero consumers**. Measured:

```
pdfFullDocumentIndex : 0 consumers outside settings.ts
pdfRagTopK           : 4 consumers
pdfWindowRadius      : 1 consumer
pdfRagEnabled        : 1 consumer
```

It is `true` in the reporting vault. It has never done anything.

The consequence is a split capability in the chat's local PDF tools
(`plugin/src/agent/llm/localPdfTools.ts`):

| tool | reach | gate |
|---|---|---|
| `fetch_pdf_page` | **any** page `1..N`, on demand | offered whenever a PDF is active |
| `search_pdf_anchor` | **only pages already read** — its own description says so | offered only when `outlineState === "absent"` |

`PdfDocumentIndexService.search()` iterates `index.pages.values()`, and pages
enter that map only via `upsertPage`, called from `extractPageTextFromPdfJs` —
which runs on render (`ExternalPdfView.ts:1108`) or an explicit `fetchPage`.

So the model can **read** any page it can name, but can only **find** content on
pages the user already scrolled past. For a target that is not in the outline —
"the derivation in Supplementary B", "the lemma about degenerate configurations"
— it cannot locate the page, so it cannot fetch it.

## 2. Measured facts every proposal must respect

**Extraction cost (pdf.js 4.10, the plugin's own options `disableFontFace: true`,
measured on the user's real files):**

| document | pages | ms/page | full-document | index text |
|---|---|---|---|---|
| 3D Line Mapping Revisited | 27 | 12.9 | **0.3 s** | 118 KB |
| Multiple View Geometry (Hartley) | 673 | 11.8 | **7.9 s** | 1.4 MB |

Cost is roughly linear and page-size-independent. A paper is free. A textbook is
not free but is not prohibitive either — the question is *when* it is paid and
whether it blocks anything.

**The backend is NOT a substitute. This is the finding that constrains the
design most, and it kills the obvious "just ask the backend" answer:**

```
source  file          spans  MAX(page_number)   real pages
37      3D Line Map    645         23               27
34      QuadricSLAM    197          7                ?
32      2D GS ref       134         17               ?
35      Plücker          82          7                ?
```

- `source_spans.page_number` is a **section index, not a physical page** (23 on a
  27-page PDF; 7 on papers that are certainly longer). `curator_get_pdf_context`
  keyed by `page_num` therefore cannot answer "what is on the page the viewer is
  showing".
- Only **4 PDFs** are ingested at all. The 673-page MVG book is not among them —
  its source row was removed when a job was cancelled. **An open PDF may have no
  backend representation whatsoever**, which is the common case for a paper the
  user just opened.

**Existing machinery that a proposal should reuse rather than reinvent:**

- `ExternalPdfView.fetchPage(pageNum)` already loads and caches an arbitrary
  page via pdf.js, explicitly "Used by the cross-reference resolver to fetch
  pages the user hasn't yet scrolled to".
- `PdfDocumentIndexService` already maintains a BM25 index with
  `documentFrequency`, per-page `termFrequency`, and `upsertPage`.
- `pdfReferenceContext.ts` already drives batched multi-page fetching
  (`fetchPages`, `orderedUniquePages`) for cross-reference resolution.
- The plugin already has `pdfRagTopK`, `pdfWindowRadius`, `pdfRagEnabled` wired.

## 3. Constraints

- **`search_pdf_anchor` is currently gated on `outlineState === "absent"`.** Any
  proposal that makes the index whole-document must say whether that gate
  survives. An outline gives section titles, not body text, so a document *with*
  an outline still cannot be searched for a phrase today.
- **The renderer thread is the user's editor.** Obsidian is a single-window
  Electron app; a synchronous 7.9 s extraction loop would freeze it.
- **Do not add a second source of truth.** The backend owns ingested knowledge;
  this index is a transient, per-open-document retrieval aid and must not be
  persisted into `.curator/` or the DB.
- **`ExternalPdfView` already carries render-cancellation machinery**
  (`renderToken`, `cancelAllPageRenders`, `onClose`). Background work must
  participate in it, not race it.
- Every venv lives at the repo root; no backend-local artifacts.

## 4. The question for the Arena

Design the mechanism that makes `search_pdf_anchor` cover the whole open
document, such that a user asking about Supplementary Section B gets an answer
without having scrolled there — while keeping Obsidian responsive on a 673-page
book, and without persisting a second knowledge store.

Specifically, each proposal must answer:

1. **When is the work paid?** Eager on open, idle-time, on-first-search, or
   incremental? Justify against the 12 ms/page measurement, not intuition.
2. **What bounds it?** A 673-page book at 1.4 MB of text is fine; a 5,000-page
   scan is not. Name the limit and what happens at it.
3. **What does the model see while indexing is incomplete?** A tool that
   silently searches 12 of 673 pages and reports nothing is the failure mode
   this whole project keeps re-encountering. State the honesty contract.
4. **Does `outlineState === "absent"` survive?** If the index becomes whole-
   document, is anchor search still withheld from outlined documents, and why?
5. **Cancellation and lifecycle.** Tab close, document swap, popout window,
   Obsidian quit. What stops the work, and what happens to a half-built index?
6. **What is the test?** This project's rule is that a fix is not finished until
   a test is verified to fail without it. Name the tests.
