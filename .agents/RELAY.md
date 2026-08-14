# RELAY — Active Goal: PDF Reading Assistant (plan 05)

## Active Goal

Make the sidechat and popover actually do the three jobs the user named: help
read PDFs/papers/books, remind them of notes they already wrote, and help them
find new value in both. The v0.53.x line fixed *symptoms* of a prompt stack that
had been built as a scope-limiter; plan 05 rebuilds it around the role.

## Plan Reference

- Master plan: `.agents/plans/05_pdf_reading_assistant.md`
- Arena record: `.agents/plans/pdf_reading_assistant_arena/`
  (`00_problem.md`, `A_prompt_role_audit.md`, `02_critique_redteam.md`)

## Analysis & Reasoning

The prompt audit is the reason this plan exists. Sentences in the stack,
classified by which duty they served:

| duty | enabling | limiting |
|---|---|---|
| 1 read/explain the document | 32 | 13 |
| 2 remind me of my own notes | 6 | 3 |
| 3 find new value | **4** | 0 |

Duty 3's four hits were MCP *tool descriptions* — no sentence anywhere said
that finding new value is the job. Both duty-2 sentences cancelled themselves
mid-clause ("…connect it to the user's existing notes, **but avoid**…"), while
three unhedged prohibitions said answer ONLY about the selection. The model
complied with the prohibitions. That is exactly what the user complained about.

## Progress Status

- [x] **P0 — Prompt re-pose** → v0.54.0 (#153). Three duties stated up front;
      general-knowledge narration mandate deleted; prohibitions rewritten as
      descriptions. Gated by `promptRoleBudget.test.ts` (≤17,000 chars,
      ≤23 negatives, all three duties present).
- [ ] **P1 — Contract.** PLUGIN_SCHEMA §13.7 gains the three-duty role and the
      provenance-from-results rule. *P2 already landed the tool-set half and the
      per-region pixel rule, so P1 is now the role + provenance remainder.*
- [x] **P2 — Per-region pixel routing** → v0.55.0 (#154).
      `read_pdf_page_image` renders any page off-screen and reads the pixels.
- [ ] **P3 — Citation resolution (depth 1).** Bibliography parse, `[8]` → paper,
      resolved pre-turn. Collision cases (`[^8]`, `[text][8]`, code indices)
      must drop.
- [ ] **P4 — Provenance surface.** Assemble from resolution results. No output
      regex.
- [ ] **P5 — Vault coverage.** ~101 markdown files are unindexed (36 sources
      ingested against 137 on disk), so duty 2 is not yet true.
- [ ] **P6 — Live acceptance.** The definition-of-done question, end to end.

Out-of-plan work that shipped alongside: v0.53.3 (#152) narration removal and
v0.54.1 (#155) the backend `ANTIGRAVITY_*` scrub.

## Critical Context / Blockers

**`isScannedLike` cannot route pixel reads, and no threshold changes that.** It
is a whole-page aggregate. Measured on "3D Line Mapping Revisited" p.11 via
pdf.js `getOperatorList()`: 14 image draw ops against 4,193 text chars, versus a
prose control page's 5 ops. The page holding the rasterized equation is
text-dense by every page-level measure. Only the model answering the question
knows the answer is missing — hence a model-invoked tool.

**Naming a tool in the prompt is not the same as making it reachable, and the
reverse can regress a known bug.** v0.55.0 first shipped with three prompt sites
steering *away* from the new tool, then with wording ("a tool for reading a page
as an image") that a CLI-routed model — which receives no local tools at all,
while agy holds a persistent `read_file()` grant — could satisfy with its own
file reader, re-opening the v0.48.4 `no output produced` failure. Every site now
names `read_pdf_page_image` literally. **Prompt assembly is still not
provider-aware; that is the open follow-up.**

**`buildRecencyAnchor` is the easiest site to forget.** It is emitted last, at
the recency position, and duplicates the pointer rule. It has now been missed
twice by two different changes. Any edit to the pointer instruction must touch
it too — `pageImageReachability.test.ts` covers it now.

**Unverified leg**: the vision transcription in v0.55.0 has never run end to
end. Antigravity returns 429 capacity-exhausted for `gemini-3.6-flash` and no
local vision model is installed. The off-screen render *is* verified on the real
file. Re-run when capacity returns:
`wiki plugin pdf transcribe --image-file <page.png>`

**Environment**: venvs at the repo root — `.venv` runtime, `.venv-dev` checks.
Never `backend/.venv`, `backend/uv.lock`, or backend-local caches. Plugin tests
need `plugin/src/generated/buildManifest.json`; CI stubs it, so stub it locally
too. Use far-future test sentinels (2099-01-01) — two tests expired mid-session
on a plausible near date.

## Immediate Next Action

**P3 — citation resolution (depth 1)**, or P1 if the contract should be settled
first. P3 is the user's stated item 1 (`[8]` references answered), and P5 is
what makes duty 2 true at all. P1 is docs-only and cheap.

Note the plan's own version line ("Minor → v0.54.0") is now stale: P0 shipped as
v0.54.0 and P2 as v0.55.0. Later phases version themselves on their own merits.

---

# ⏸️ Paused Goal (unchanged)

**ROADMAP item 10 — `pdfFullDocumentIndex` consumers.**

The "Background page indexing" toggle writes a value **nothing reads**, so
`search_pdf_anchor` is still limited to already-rendered pages. `fetch_pdf_page`
reads any page the model can *name*, but nothing can *locate* one in an unread
page.

Arena: `.agents/plans/pdf_background_index_arena/`
Plan: `.agents/plans/04_pdf_background_index.md`
Evidence: `.agents/plans/04_pdf_background_index_evidence.md`

Fix the quadratic `upsertPage` first — measured at **26,881 ms** for a 673-page
book against 81 ms for the bulk path (331x). The evidence ledger also records an
unanticipated finding: `search()` alone costs 59.7 ms on a full book index.

ROADMAP item 1 (formula recovery) remains blocked on three prerequisites, with
an Arena record at `.agents/plans/formula_recovery_arena/`.
