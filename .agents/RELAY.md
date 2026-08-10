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
