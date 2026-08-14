# RELAY — Active Hotfix: Popover Chat Grounding Relaxation

## Active Goal (Hotfix)
Relax the strict grounding constraints in the Quick Query popover chat. When a user asks about content not present on the current page or context, the assistant should gracefully fall back to its parametric knowledge and offer a general explanation, rather than strictly refusing to answer. 

Additionally, the popover chat must be expanded to search and utilize the sidechat's pinned sources (purple pins, PDFs, MD files) as background context.

## Plan Reference
- Brief/Draft: `.agents/drafts/11_popover_chat_grounding.md`
- Master Plan: [Not yet created]

## Progress Status
- [x] Triage and queue the user's report into `.agents/ROADMAP.md` (Item 11).
- [x] Author problem brief (`.agents/drafts/11_popover_chat_grounding.md`).
- [ ] Run Arena debate and synthesize `PLAN_TEMPLATE.md`.
- [ ] Implement changes via TDD.

## Critical Context/Blockers (Hotfix)
- Changes to `boundaryConstraints` and `contextPriorityInstruction` may impact the main sidechat surface as well. Ensure any prompt tuning generalizes safely or is scoped explicitly to `POPOVER_PROFILE`.
- Architectural decision needed: How to inject sidechat pinned sources without breaking `local-only` security boundary.

## Immediate Next Action
**[EXECUTORS]**: Read `.agents/drafts/11_popover_chat_grounding.md`. Run the Arena debate to synthesize the implementation plan in `.agents/plans/` using the PLAN_TEMPLATE.md. Do not implement code until the plan is approved by the user.

---

# ⏸️ Pending / Paused Goal (Resume after Hotfix)

**Target:** ROADMAP item 10 (`pdfFullDocumentIndex` consumers)

## Critical context carried forward
- **`pdfFullDocumentIndex` has zero consumers.** The "Background page indexing"
  toggle writes a value nothing reads, so `search_pdf_anchor` is still limited
  to already-rendered pages. `fetch_pdf_page` reads any page the model can name,
  but cannot search unread pages without first knowing their page number.
- Venvs live at the repo root: `.venv` runtime, `.venv-dev` checks. Never
  `backend/.venv`, `backend/uv.lock`, or backend-local caches.
- Two time-dependent tests expired mid-session. Use far-future sentinels
  (2099-01-01), never a plausible near date.
- ROADMAP item 1 (formula recovery) is blocked on three prerequisites
  (acceptance gate, `validator_trace_id` producer, crop geometry) and has an
  Arena record in `.agents/plans/formula_recovery_arena/`.

## Suspended Action
ROADMAP item 10: implement `pdfFullDocumentIndex` consumers so the chat can
search unrendered PDF pages. Arena record exists at
`.agents/plans/pdf_background_index_arena/`, master plan at
`.agents/plans/04_pdf_background_index.md`. Needs Executor to proceed — read the
plan, fix the quadratic `upsertPage` first, then wire the consumers.

---

### Update (2026-08-14, Claude Code)

**v0.54.0 reading-assistant plan is executing. P0 and P2 are landed/open.**

Plan: `.agents/plans/05_pdf_reading_assistant.md` (Arena record under
`.agents/plans/pdf_reading_assistant_arena/`).

Shipped:
- **#152 → v0.53.3** — removed the three prompt sites that *instructed* the
  model to narrate its own retrieval state.
- **#153 → v0.54.0 (P0)** — the system prompt now opens with the assistant's
  three duties (read alongside, remind of prior notes, find new value) instead
  of a list of prohibitions. Duty 3 previously had zero instructions anywhere.
- **#154 → v0.55.0 (P2), OPEN** — `read_pdf_page_image(page_number)`: renders
  any page off-screen and reads the pixels, so a rasterized equation answers
  without the user snipping it. Model-invoked, not heuristic — see below.

Two master-level defects found and fixed by fast-forward while doing this:
- `chore(backend)` 67876a7 — hatchling 1.30 rejects `readme = "../docs/README.md"`
  and the redundant `force-include` block. Backend CI had gone red with no
  commit causing it, blocking every branch.
- `chore(ci)` dfdc6fc — **the version-consistency gate had never run on a pull
  request.** Its condition tested `github.ref` against `refs/heads/*`, but on a
  pull_request event that value is `refs/pull/<n>/merge`. `feat/**` was also
  missing from the push allowlist, so on those branches it ran zero times from
  either trigger. This is how v0.53.2 shipped with pyproject at 0.53.1 and the
  plugin manifests at 0.53.2. Condition removed; verified running on #154.

## Critical context for whoever picks this up

**`isScannedLike` cannot route pixel reads, and no threshold tuning changes
that.** It is a whole-page aggregate. Measured on "3D Line Mapping Revisited"
p.11 via pdf.js `getOperatorList()`: 14 image draw ops and 4,193 text chars,
against a prose control page's 5 ops. The page holding the rasterized equation
is text-dense by every page-level measure. Only the model answering the
question knows the answer is missing from the text it got — hence a
model-invoked tool.

**Unverified leg**: the vision transcription in #154 could not be exercised
end-to-end. Antigravity returns 429 capacity-exhausted for `gemini-3.6-flash`
and no local vision model is installed. The off-screen render *is* verified on
the real file. Re-run `wiki plugin pdf transcribe --image-file <page.png>`
once capacity returns.

## Immediate next action

Remaining plan phases, in order: **P1** (PLUGIN_SCHEMA contract for the
three-duty role — P2 already landed the §13.7 tool-set half), **P3** (`[8]`
citation resolution, depth 1), **P4** (provenance surfaced from tool results),
**P5** (vault coverage — 36 sources ingested against 137 markdown files on
disk), **P6** (live acceptance test).
