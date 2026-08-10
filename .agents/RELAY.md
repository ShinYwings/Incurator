# RELAY — IDLE at v0.53.2

No active goal. Master is at **v0.53.2**, working tree clean, no open PRs.

## Shipped this run (v0.53.1 → v0.53.2)

- **v0.53.1** — agy permission-rule fixed (`$read_file$()` was pruned on every
  run; correct form is `read_file()`). Solved the original "jetski: no output
  produced" root cause.
- **v0.53.2** — chat sidebar `fetchPageText` now falls back to the PDF.js viewer
  when the backend is unavailable or returns nothing. Closes the remaining jetski
  path for Zotero cloud PDFs and any untracked document.

## Critical context carried forward

- **`pdfFullDocumentIndex` has zero consumers.** The "Background page indexing"
  toggle writes a value nothing reads, so `search_pdf_anchor` is still limited
  to already-rendered pages. `fetch_pdf_page` reads any page the model can name,
  but cannot search unread pages without first knowing their page number.
  **This is the next planned item (ROADMAP item 10, v0.54.0 target).**
- Venvs live at the repo root: `.venv` runtime, `.venv-dev` checks. Never
  `backend/.venv`, `backend/uv.lock`, or backend-local caches.
- Two time-dependent tests expired mid-session. Use far-future sentinels
  (2099-01-01), never a plausible near date.
- ROADMAP item 1 (formula recovery) is blocked on three prerequisites
  (acceptance gate, `validator_trace_id` producer, crop geometry) and has an
  Arena record in `.agents/plans/formula_recovery_arena/`.

## Immediate next action

ROADMAP item 10: implement `pdfFullDocumentIndex` consumers so the chat can
search unrendered PDF pages. Arena record exists at
`.agents/plans/pdf_background_index_arena/`, master plan at
`.agents/plans/04_pdf_background_index.md`. Needs Executor to proceed — read the
plan, fix the quadratic `upsertPage` first, then wire the consumers.
