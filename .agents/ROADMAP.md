# Incurator Master Roadmap & Todo List

This is the master roadmap for major architectural overhauls and future updates.
It tracks only live priorities and active follow-up references. Completed plan
artifacts are removed from `.agents/plans/`; use Git history for old plans.

## 🚨 Update Classification & Planning Rule

Before starting work, all agents MUST use `.agents/USER_REPORT.md` as the Single
Source of Truth to identify unresolved items.

- **Major and Minor Updates**: do not write code immediately. Write or update a
  milestone plan using `.agents/PLAN_TEMPLATE.md` first, then implement.
- **Hotfix and Simple Bug Fixes**: may skip heavy planning only when the change is
  small, isolated, and does not alter public contracts, schemas, or architecture.
- **Completed plans**: delete active `.agents/plans/` artifacts after shipping.
  The Git history is the archive.

---

## 📥 Triage & Queuing

`USER_REPORT.md` is currently empty. The following queue is the ordered roadmap.

### 🚀 Priority Order

1. **[Fix/Validation] `[[wikilink]]` Architecture Validation**
   - Validate whether current backend link parsing intentionally avoids
     `[[wikilink]]` syntax or whether missing wikilinks are a real conflict.
   - Keep coding minimal unless validation proves a concrete parser/sync bug.
   - Detailed analysis: `.agents/drafts/minor_quick_wins.md`

2. **[Minor Update] Obsidian Agent UI/UX & Context Architecture Overhaul**
   - Unified refactor for systemic agent attention failures, prompt duplication,
     and UI state desyncs.
   - **Deferred Diff Viewer polish (from v0.14.1 P0 triage)**: unified-view CSS
     gutter alignment (#5), cross-model `reviewInEditor` output determinism (#8),
     and a token-truncation hard-reject guard (#10). The original
     `diff_viewer_plugin.md` draft was deleted on ship; see Git history (v0.14.1)
     for the full bug list.
   - Component drafts:
     - `.agents/drafts/chat_context_decay.md`
     - `.agents/drafts/popover_tool_scope.md`
     - `.agents/drafts/prompt_architecture_refactoring.md`

3. **[Major/Minor Follow-Up] RAG Post-Stabilization Hardening**
   - RAG & Knowledge Quality Stabilization itself is complete, but the audit
     drafts identify follow-up hardening work that has **not** been implemented
     as a unified follow-up yet.
   - Inputs: `.agents/drafts/batch_1_to_3_audit/`
   - Main themes:
     - real-world oracle sampling and noisy fixture coverage;
     - graph fragmentation / soft-link proposal strategy;
     - pipeline healing for broken locators and orphaned spans;
     - explore-route ContextService unification as a measured research loop;
     - CJK-safe token estimation;
     - expansion state-machine hardening;
     - trace mutation / retrieval metric integrity.

4. **[Minor Update] Chat Session Context Compaction**
   - Confirm full-session history behavior.
   - Add a Claude-Code-style circular token usage meter under the query box and a
     click-to-compact action.
   - Detailed analysis: `.agents/drafts/chat_context_compaction.md`

5. **[Minor Update] Minor Quick Wins**
   - Web search integration review.
   - Convert-to-LaTeX fast/light model option (`qwen2.5:0.5b`).
   - Zotero import profile/item checkbox lists sorted by most recently accessed
     or imported items.
   - Detailed analysis: `.agents/drafts/minor_quick_wins.md`

6. **[Minor Update] Vault Storage Governance & Quota Visibility**
   - Separate authoritative, derived, cache, and external storage accounting.
   - Add capacity guidance, safe admission control, and CLI/plugin visibility.
   - Detailed analysis: `.agents/drafts/vault_storage_governance.md`

7. **[Major Update] Native PDF Annotation & Asset System**
   - Native annotation highlight/memo synchronization using Obsidian's built-in
     PDF viewer.
   - In-PDF full-text search and strict-spelling mode remain here.
   - Detailed analysis: `.agents/drafts/pdf_annotation_system.md`

---

## ✅ Completed Milestones

- **Purge Legacy Search Binary References** — shipped in v0.16.0.
- **Persistent Quick Query Popover** — shipped in v0.15.0.
- **Sidechat Edit Loop & Diff Viewer Tier A Fixes** — shipped in v0.14.0 and v0.14.1.
- **RAG & Knowledge Quality Stabilization** — complete through v0.13.0 / PR #34.
  - Batch 1: D1 v0.6.0, Plan E complete, D2 v0.7.0.
  - Batch 2: Plan B v0.8.0, Plan C v0.9.0.
  - Batch 3: Plan A v0.10.0, Plan F v0.13.0.
  - Active `.agents/plans/` artifacts should remain deleted; use Git history for
    plan details.
- **Diff Viewer Overhaul** — merged in v0.11.0, but follow-up fixes remain queued
  under item 2.
- **PDF Handling Unification & Simplification (Plan G)** — shipped in v0.12.0.
  - Unified PDF identity resolver for Reference Mode / add-source / agent↔PDF
    viewer and moved non-annotation asset routing into the shipped PDF flow.
  - Native annotation and in-PDF full-text search remain queued separately.

---

## 🧊 Blocked / Icebox

No blocked items currently tracked.

---

## 📌 Current Focus & Active Milestone

- **Roadmap state**: Item 1 active on `feature/wikilink-architecture-validation`.
- **Next actionable item**: Implement/Validate item 1 (`[[wikilink]]` Architecture Validation).
- **Priority order**: item 1, then UI/UX architecture overhaul and RAG hardening.
