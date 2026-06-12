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

1. **[Major Update] RAG & Knowledge Quality Stabilization**
   - Heart-of-system three-program initiative for using the notes vault like a
     codebase: first establish the truth contract, deep diagnosis, external
     research, and quality observatory; then make the note-to-L1-L4 evidence
     compiler faithful and incremental; finally serve the trusted prior knowledge
     to external and Obsidian agents through one bounded agentic context runtime.
     External techniques are benchmarked and adopted selectively, never wholesale.
   - Scope analysis: `.agents/drafts/stabilization.md`
   - Umbrella program plan:
     `.agents/plans/03_rag_knowledge_quality_stabilization.md`
   - Six component plans (`A-F`) each have their own Arena and Master Plan; they
     are executed in three ordered batches after the current PR merges.
   - Batch 1: `.agents/plans/D_current_system_failure_atlas.md` D1 →
     `.agents/plans/E_external_research_design_matrix.md` →
     `.agents/plans/D_current_system_failure_atlas.md` D2
   - Batch 2: `.agents/plans/B_math_extraction_distillation.md` →
     `.agents/plans/C_graph_quality.md`
   - Batch 3: `.agents/plans/A_rag_retrieval_provenance.md` →
     `.agents/plans/F_agent_context_service.md`

2. **[Minor Update] Vault Storage Governance & Quota Visibility**
   - Separate authoritative/derived/cache/external storage accounting, capacity
     guidance, safe admission control, and CLI/plugin visibility from RAG quality.
   - Detailed analysis: `.agents/drafts/vault_storage_governance.md`

3. **[Minor Update] Chat Session Context Compaction**
   - Confirm/ensure full-session history usage; add a Claude-Code-style circular token-usage meter under the query box and a click-to-compact action for the session.
   - Detailed analysis: `.agents/drafts/chat_context_compaction.md`

4. **[Minor Update] Minor Quick Wins**
   - Web search integration review, `[[wikilink]]` conflict validation, Convert-to-LaTeX fast/light model option (`qwen2.5:0.5b`), Zotero profile import sorted by recently accessed.
   - Detailed analysis: `.agents/drafts/minor_quick_wins.md`

5. **[Major Update] Native PDF Annotation & Asset System**
   - Remove external Zotero dependency, build a native annotation (highlight/memo) synchronization system utilizing Obsidian's built-in PDF Viewer. In-PDF full-text search (with strict-spelling mode) and native highlight/memo sync remain here.
   - **Split out (2026-06-11):** PDF add-source asset-location routing + "Added" button state → **shipped in v0.5.6** (2026-06-12); the Zotero reload relativepath bug was already fixed in v0.5.5. External-image-attachment-to-`.md` routing rides v0.5.6's `--asset-dir` mechanism as a follow-up.
   - Detailed analysis: `.agents/drafts/pdf_annotation_system.md`

### 🧊 Blocked / Icebox (Pending Items)
- Items that cannot be resolved immediately due to external dependencies (library updates, etc.) are stored here.
- (Note: Items in this section are treated as exceptions to the agent's top-priority resolution duty.)
---

## 📌 Current Focus & Active Milestone

The specific To-Do list for the roadmap is migrated from the user's Inbox (`.agents/USER_REPORT.md`) to the `Triage & Queuing` section of this document for integrated management.

### 🟢 Currently Ongoing Work (Current Active Milestone)
- **Active Milestone**: **PDF Add-Source Asset Routing + "Added" State (v0.5.6)**
  - **Status**: Asset-routing implementation complete on
    `feature/pdf-add-source-assets`; adaptive routing correction is implemented,
    locally verified, and passing PR #23 CI. User review/merge remains.
- **Next in Queue**: To-Do #1 **RAG & Knowledge Quality Stabilization**. Planning completed (`03_rag_knowledge_quality_stabilization.md` and `A-F` plans). Implementation remains blocked until the v0.5.6 PR merges and explicit approval is given.
