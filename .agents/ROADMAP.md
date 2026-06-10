# Incurator Master Roadmap & Todo List

This is the master roadmap for major architectural overhauls and future updates.
This document provides key guidelines on how agents should plan and execute future milestones.

## 🚨 Update Classification & Planning Rule

Before starting work, all agents MUST use `.agents/USER_REPORT.md` as the Single Source of Truth to identify unresolved items (To-Do).
Depending on the scale of the update, you MUST follow these planning rules:

- **Major and Minor Updates** (Architecture/feature changes where X or Y increases in version `v.X.Y.Z`):
  - **NEVER write code immediately.**
  - Based on the items in `USER_REPORT.md`, you MUST write a milestone specification and detailed plan in strict compliance with the `.agents/PLAN_TEMPLATE.md` template before starting implementation.
  - The written plan must be merged and managed under the corresponding milestone item in this document (`ROADMAP.md`) to prevent fragmentation.
- **Hotfix and Simple Bug Fix (Fix)** (Bug fixes on a scale where Z increases in version `v.X.Y.Z`):
  - These are exempted from the heavy template writing procedure, and you can immediately analyze the cause and apply the fix.

---

## 📥 Triage & Queuing (To-Do Queue)

This is the holding area where user requests received from `.agents/USER_REPORT.md` wait before being planned/incorporated into actual milestones. Writing a PLAN_TEMPLATE is mandatory when proceeding.

### 🚀 Unresolved Items to be Addressed in the Future (To-Do)

> Last triage: 2026-06-11 (bulk inbox triage from `USER_REPORT.md`).
> #1 Installation & Version Management Unification — ✅ shipped in v0.4.4 (PR #16, merged 2026-06-11).
> Agent Edit & Diff Viewer Reliability — ✅ shipped in v0.5.0 (branch `feature/agent-edit-diff-reliability`, PR pending).

1. **[Minor Update] Sidechat Selection & LaTeX Robustness** 🟢 ACTIVE
   - MathJax SVG→text stale read drops formulas in the Ask AI popover on drag; keyboard (Shift+Arrow) selection doesn't trigger Ask AI; partial-selection LaTeX copy (KaTeX swap or transparent overlay, low priority). #1/#2 are hotfix-class.
   - Detailed analysis: `.agents/drafts/sidechat_selection_latex.md`
   - Active plan: `.agents/plans/01_sidechat_selection_latex.md` (Arena: `.agents/plans/sidechat_selection_arena/`)

2. **[Minor Update] Sidechat Local Git History (drop `gh` dependency)**
   - Audit why `gh` is required; use local `git log`/`git show` for vault file-history reference ("how did I write this before?", recovery). Remove the hard `gh` requirement where local git suffices.
   - Detailed analysis: `.agents/drafts/sidechat_git_history.md`

3. **[Major Update] RAG & Knowledge Quality Stabilization**
   - Deep analysis and supplementation of the search engine (Qwen3 + FTS5), introduction of hybrid extraction to resolve missing math formulas, integrated logic for entity deduplication filtering and prevention, providing visibility for Vault Quota management. Now also owns the shared light/fast-model config plumbing (consumed by the Convert-to-LaTeX quick win).
   - Detailed analysis: `.agents/drafts/stabilization.md`

4. **[Minor Update] Chat Session Context Compaction**
   - Confirm/ensure full-session history usage; add a Claude-Code-style circular token-usage meter under the query box and a click-to-compact action for the session.
   - Detailed analysis: `.agents/drafts/chat_context_compaction.md`

5. **[Minor Update] Minor Quick Wins**
   - Web search integration review, `[[wikilink]]` conflict validation, Convert-to-LaTeX fast/light model option (`qwen2.5:0.5b`).
   - Detailed analysis: `.agents/drafts/minor_quick_wins.md`

6. **[Major Update] Native PDF Annotation & Asset System**
   - Remove external Zotero dependency, build a native annotation (highlight/memo) synchronization system utilizing Obsidian's built-in PDF Viewer. Expanded scope (2026-06-11): PDF/Zotero asset-location management (frontmatter-driven asset folder, external-image fallback to `05_Assets`), fix reload relativepath bug, add-source button → "Added" state, and in-PDF full-text search (with strict-spelling mode).
   - Detailed analysis: `.agents/drafts/pdf_annotation_system.md`

### 🧊 Blocked / Icebox (Pending Items)
- Items that cannot be resolved immediately due to external dependencies (library updates, etc.) are stored here.
- (Note: Items in this section are treated as exceptions to the agent's top-priority resolution duty.)

---

## 📌 Current Focus & Active Milestone

The specific To-Do list for the roadmap is migrated from the user's Inbox (`.agents/USER_REPORT.md`) to the `Triage & Queuing` section of this document for integrated management.

### 🟢 Currently Ongoing Work (Current Active Milestone)
- **Agent Edit & Diff Viewer Reliability** — ✅ shipped v0.5.0 (PR #17, merged 2026-06-11).
- **Sidechat Selection & LaTeX Robustness** (To-Do #1) — 🟢 PLAN AUTHORED, awaiting user approval before coding.
  - Master Plan: `.agents/plans/01_sidechat_selection_latex.md` · Arena: `.agents/plans/sidechat_selection_arena/`
