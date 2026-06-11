# Relay State — IDLE (2026-06-11)

## Status
On clean `master` @ 50e07bf (post PR #21). No active milestone.

## Last action
Investigated ROADMAP Icebox item "Partial-selection LaTeX copy in the note view"
(Cmd+C/Cmd+X). **Concluded NOT feasible** for Reading View: Obsidian's bundled
**MathJax v3** makes rendered math non-selectable by design, so a drag-selection
can't cross a formula (live test: "skips at the formula"; web research: MathJax
#2240/#3508; the leading copy-as-latex plugin only uses `editor.getSelection()`).
Live Preview / Source already preserve LaTeX natively. Only a full renderer swap
(KaTeX, or force MathJax v4 — whose selectability is just the accessibility explorer,
not region drag-copy) could change this; all far-future. WIP preserved on branch
`feature/editor-latex-copy` (commit `be6ae32`, NOT merged). Icebox entry updated with
the full finding + the MathJax-v4 revisit trigger.

## Worktree note
Pre-existing uncommitted changes on `master` (USER_REPORT.md, build_manifest.json,
.agents/image-*.png deletions) are NOT from this session and were left untouched.

## Next candidate
Finish the current Claude/user worktree first. Then handle ROADMAP urgent items
#1-#3 unless explicitly overridden. To-Do #4 **RAG & Knowledge Quality
Stabilization** now has a full Arena plan and still requires user approval before
implementation.

### Update (2026-06-11, Codex)

- Planning-only side task completed while preserving the active
  `feature/editor-latex-copy` worktree and all Claude/user implementation changes.
- Triaged every remaining `USER_REPORT.md` item into ROADMAP-linked scope drafts.
  Urgent queue is now Zotero reload/navigation hotfix, dashboard runtime refresh,
  and external-PDF `resolveDoc` identity bug.
- Authored the full Arena/domain/master plan for **RAG & Knowledge Quality
  Stabilization**:
  `.agents/plans/03_rag_knowledge_quality_stabilization.md`.
- The plan is split into three independent releases: A) retrieval/provenance and
  working evidence links, B) math-preserving extraction/distillation, C) graph
  resolution/hierarchical communities/quota.
- No RAG implementation, branch switch, specs, tests, version bump, or release
  work was started. The plan remains DRAFT pending user approval after the current
  Claude work is finished.

### Update (2026-06-11, Codex — RAG plan reframing)

- The user clarified the core objective: agents must use the notes vault like a
  codebase by reusing meaningful note-derived prior knowledge through a trusted
  RAG + DAG hybrid.
- Rejected the earlier component-oriented split
  (`retrieval/provenance` → `math` → `graph/community/quota`) because compiler and
  graph changes would invalidate earlier retrieval baselines.
- Reframed the work into three independent programs:
  1. **Truth Contract & Quality Observatory**
  2. **Evidence Compiler Integrity**
  3. **Agentic Query Serving & Sensemaking**
- Completed a planning-only current-system failure analysis, external
  primary-source research matrix, and unified external/Obsidian agent context
  service contract. The active umbrella program plan is
  `.agents/plans/03_rag_knowledge_quality_stabilization.md`; its six component
  plans (`A-F`) each receive a dedicated Arena and root Master Plan.
- Program 1 now explicitly requires deep diagnosis, comparative research,
  measured experiments, and an approved detailed specification package before
  production implementation. The six plans are grouped into three ordered
  execution batches. Quota UI and unrelated provider UI are separate milestones.
- No RAG implementation, branch switch, production spec/guide update, tests,
  version bump, or release work was started. The plan remains DRAFT, and the
  current Claude/user worktree was preserved.

### Update (2026-06-11, Claude — note-view LaTeX copy SHIPPED)

- Finished my own (not CODEX's) note-view LaTeX copy/cut work and shipped it as
  **v0.5.4, PR #22** (`feature/editor-latex-copy`). **All CI green** (Backend +
  Plugin Tests + Version Consistency). Patch on the 0.5 spec line (specs unchanged
  at v0.5.0) — NOT 0.6.0; a minor bump would fail `test_spec_sync` unless all spec
  headers + ACTIVE_VERSION rev to 0.6, which a plugin feature doesn't warrant.
- The earlier "not feasible (MathJax v3)" abandonment (commit `be6ae32`) was
  refuted by a live chat test: a selection visually skips a non-selectable formula
  but the math node is still in `cloneContents()`, so the source copies fine.
  Solution = Markdown post-processor stamps `data-tex` (exact-count guarded) +
  capture-phase copy/cut handler gated to `.markdown-reading-view` + math.
- PR is **scoped to feature files only**. CODEX's `.agents` RAG-stabilization
  planning (03_rag_*, A–F, arena, ROADMAP/USER_REPORT triage) was left
  uncommitted and untouched, ready for the user's next RAG session.
- ROADMAP updated: Icebox item moved to ✅ shipped (LaTeX = v0.5.4, not 0.6.0).

### Update (2026-06-11, Claude — urgent bugfix batch SHIPPED, v0.5.5)

- Per user request, branched `fix/urgent-roadmap-bugfixes` off
  `feature/editor-latex-copy`, fixed the three urgent ROADMAP items, and
  fast-forward-merged back into `feature/editor-latex-copy` (pushed → PR #22 now
  carries v0.5.4 LaTeX + v0.5.5 bugfixes). Local fix branch deleted.
- Shipped (commit `e2a2b17`): #1 Zotero hotfix (shared `assetLocalization.ts`
  unifying reload+import → vault-relative `05_Assets`, legacy `imageFolder`
  migration, overwrite changed annotation regions; backend `resolve-pdf` parent
  item→child PDF attachment + effective `attachment_key`; annotation-jump via child
  key; `Cmd+Shift+R` reload note+PDF). #2 dashboard fresh-first `readRuntimeStatus`
  + explicit-unavailable version. #3 external-PDF path-preserving get/setState +
  cache retention (no load-time existsSync race).
- CI (local): plugin vitest 347, backend pytest 508 + zotero 14, ruff clean, tsc
  clean, no NEW mypy errors (84 pre-existing on master, untouched). Patch on the
  0.5 spec line (specs unchanged at v0.5.0).
- Deleted the three implemented bug-fix drafts from `.agents/drafts/`.
- CODEX's RAG planning in `.agents/` still untouched/uncommitted. **Urgent bug
  queue is now clear → RAG milestone is unblocked pending user approval.**

### Update (2026-06-11, Claude — PDF add-source plan DRAFTED, NOT implemented)

- User promoted **PDF Add-Source Asset Routing + "Added" State** to ROADMAP
  **To-Do #1 (TOP priority)**; RAG dropped to #2; Native-PDF item (#6) notes the
  split-out. Plan written: `.agents/plans/04_pdf_add_source_assets.md` (+ arena).
- **PLANNING ONLY — no code written. User said "계획까지가 끝" (stop at the plan).**
  Do NOT implement until the user explicitly says go.
- Verified behavior (for the plan): add-source ingests **L1 immediately + queues
  L2/L3** (`source import` → `source register --build`); PDF images hard-dumped to
  `05_Assets/<slug>/` (`ingest_raw.py::_save_pdf_images`); badge has no "added"
  state (falls to "Check source"); PDF parser = pymupdf4llm (math-weak → VLM is RAG
  plan B, OUT of scope here).
- Locked user decisions: (A) plugin passes `--asset-dir` (05_Assets fallback);
  (B) tracked/built (`l1_ready…l4_ready/ready`) → non-clickable "Added" badge.
- **Branch decision + BLOCKER**: user chose a fresh `fix/pdf-add-source-assets` off
  `master`. BUT `master` is still v0.5.3 — it lacks v0.5.5's
  `assetLocalization.ts::resolveProfileAssetSpec` (which the plan reuses) and the
  add-source files (`chatSidebar.ts`/`incuratorClient.ts`) were changed in PR #22,
  so branching off master now risks conflicts. **Recommended: merge PR #22 to master
  FIRST, then branch off the updated master → v0.5.6.** (User merges PRs, not the
  agent.) When implementation is greenlit, start at P0 in the plan.

### Update (2026-06-11, Codex — RAG planning completed, implementation blocked)

- Completed planning-only RAG stabilization structure:
  one umbrella plan (`03`) plus six independent Master Plans (`A-F`), each with
  its own Arena.
- The three ordered execution batches are:
  `D1 → E → D2` (diagnosis/research/final observatory), `B → C` (compiler integrity), and
  `A → F` (retrieval substrate/ContextService).
- Removed the main overlap: Plan A owns retrieval, provenance continuity,
  authoritative retrieval transaction, and locator resolution; Plan F owns
  ContextService, progressive packs, public adapters, external/Obsidian parity,
  and feedback lineage.
- Preserved Vault quota/storage requirements as the separate
  `.agents/drafts/vault_storage_governance.md` milestone.
- This work is planning only. Do not begin RAG implementation until PR #22 is
  merged and the relevant component plan is explicitly approved. The separate
  PDF add-source plan remains ROADMAP priority #1.
