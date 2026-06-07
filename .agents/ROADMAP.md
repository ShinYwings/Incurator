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

1. **[Minor Update] Minor Quick Wins**
   - Review web search feature integration, validate potential `[[wikilink]]` conflicts and introduction of explicit Obsidian backlinks, Diff Viewer UI/UX improvements, etc.
   - Detailed analysis: `.agents/drafts/minor_quick_wins.md`

2. **[Major Update] RAG & Knowledge Quality Stabilization**
   - Deep analysis and supplementation of the search engine (Qwen3 + FTS5), introduction of hybrid extraction to resolve missing math formulas, integrated logic for entity deduplication filtering and prevention, providing visibility for Vault Quota management.
   - Detailed analysis: `.agents/drafts/stabilization.md`

3. **[Major Update] Native PDF Annotation System**
   - Remove external Zotero dependency, build a native annotation (highlight/memo) synchronization system utilizing Obsidian's built-in PDF Viewer.
   - Detailed analysis: `.agents/drafts/pdf_annotation_system.md`

### 🧊 Blocked / Icebox (Pending Items)
- Items that cannot be resolved immediately due to external dependencies (library updates, etc.) are stored here.
- (Note: Items in this section are treated as exceptions to the agent's top-priority resolution duty.)

---

## 📌 Current Focus & Active Milestone

The specific To-Do list for the roadmap is migrated from the user's Inbox (`.agents/USER_REPORT.md`) to the `Triage & Queuing` section of this document for integrated management.

### 🟢 Currently Ongoing Work (Current Active Milestone)
- No active milestone is currently designated. (Please select the next task from the To-Do list above)
