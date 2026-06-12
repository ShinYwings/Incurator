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

1. **[Major Update] RAG & Knowledge Quality Stabilization** — *IN PROGRESS*
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
     - **D1 shipped as v0.6.0** (2026-06-12): Failure Atlas spec + case
       records F1–F13 (all reproduced & assigned), deterministic
       repro/oracle/contract/experiment/eval suites, frozen fixture corpus +
       qrels + baseline.
     - **Plan E COMPLETE (P0-P8)** (2026-06-12): PM approved the P7 decision
       package; P8 validated artifact completeness/link integrity and handed
       the accepted contracts off as "Plan E P7 Research Handoff" sections in
       the five downstream plan documents (D/B/C/A/F). PR #26 awaits final
       review/merge. P7 consumed the four research-spike
       holdout items (RUQ05/GQ07/HQ01/FR05) exactly once under frozen
       configurations, passed all five red teams (provenance, leakage,
       framework bias, cost, update/delete), and issued final scoped
       decisions: 4 `adopt-contract` (fine-grained diagnostics → Plan D2;
       query-relevant-global and progressive-context-disclosure → Program 3;
       formula-preserving-distillation → Program 2), 2 `reject-default`
       (unfiltered PPR, whole-corpus heavy recovery), rest `benchmark-later`.
       The Failure Atlas qrels holdout (Q06) remains reserved for D2. See
       `backend/research_spikes/reports/p7.md`. No decision authorizes
       production implementation.
       Earlier phases: P0/P1 established immutable multi-tier inputs and
       primary-source dossiers; P2 froze the evaluation protocol; Waves A-D
       (retrieval units, graph/hierarchy/global/expansion, serving policies,
       conditional formula recovery) all completed and were approved.
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

6. **[Minor Update] Purge Legacy QMD References**
   - The `qmd` binary has been retired since v0.3.2, but over 50 references still exist across the codebase (`cli.py`, `search.py`, `lint.py`, tests, etc.). These references must be completely purged to prevent hallucination or regressions before removing the tombstone warnings from the agent contracts.
   - Detailed analysis: `.agents/drafts/purge_qmd_legacy.md`

7. **[Hotfix] SQLite connection leak in `db.init_db`**
   - `init_db()` uses `with sqlite3.connect()` without explicitly closing the connection, leaving WAL sidecars and causing environment-dependent "database is locked" errors on Ubuntu.
   - Detailed analysis: `.agents/drafts/bug_sqlite_leak.md`

### 🧊 Blocked / Icebox (Pending Items)
- Items that cannot be resolved immediately due to external dependencies (library updates, etc.) are stored here.
- (Note: Items in this section are treated as exceptions to the agent's top-priority resolution duty.)
---

## 📌 Current Focus & Active Milestone

The specific To-Do list for the roadmap is migrated from the user's Inbox (`.agents/USER_REPORT.md`) to the `Triage & Queuing` section of this document for integrated management.

### 🟢 Currently Ongoing Work (Current Active Milestone)
- **Active Milestone**: **Plan E (External Research Design Matrix)** —
  **COMPLETE (P0-P8)**. Plan D1 (v0.6.0) shipped and merged. The P7 decision
  package was PM-approved; P8 validation and downstream handoff are done.
  PR #26 awaits final human review and merge. Side-task in flight: the
  `[Hotfix] SQLite connection leak in db.init_db` (To-Do item 7) on its own
  `hotfix/*` branch from `master`.
- **Next in Queue**: Plan D2 (following Plan E completion).
  Execution order: Batch 1 `D1 → E → D2`, Batch 2 `B → C`, Batch 3 `A → F`. Implementation starts only on explicit user approval.
