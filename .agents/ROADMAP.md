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

1. ✅ **[Minor Update] Sidechat Edit Loop — Enforced & Observable State Machine**
   — SHIPPED in v0.14.0.
   - Prompt contract + runtime validator hard-gate + visible UI phases + wider
     triggers shipped. Plan artifacts deleted (see Git history); see CHANGELOG
     `[0.14.0]`.

2. ✅ **[Fix] Diff Viewer Plugin Overhaul & Sync Fixes** — Tier A SHIPPED and
   merged in v0.14.1.
   - P0 triage: 2 FIXED (nav, premature-write), 2 LIVE (Accept-All cursor, hover),
     7 PARTIAL. Tier A fixes shipped: cursor restore, toolbar anchor, review
     race guard, path fallback, derived pill status, "proposed not applied".
   - **Deferred to item 6**: unified-view CSS polish (#5), cross-model output
     determinism (#8), token-truncation hard guard (#10). Existing
     `warnIfLargeReplacement` warning remains for #10.

3. ✅ **[Fix/Minor Update] Persistent Quick Query Popover** — SHIPPED and
   merged in v0.15.0 / PR #37.
   - Upgrade the inline copilot popover to be immune to outside clicks, freely
     draggable, minimizable, and usable as a persistent reference window.
   - Code-review findings addressed: teardown order,
     text-node click crash, fixed palette scroll behavior, dynamic title ref,
     drag state, and minimize state.
   - PR #37 follow-up review fixes addressed: trigger scroll listeners detach
     when the persistent popover remains open, global Escape handling is scoped
     to popover focus, and active spec headers/tests are synchronized to v0.15.0.
   - Plan/draft artifacts deleted on ship; use Git history for details.
   - Keep separate from `.agents/drafts/popover_tool_scope.md` unless planning
     the broader UI/UX architecture overhaul.

4. ✅ **[Fix/Chore] Purge Legacy Search Binary References** — SHIPPED in
   v0.16.0.
   - Removed stale retired-search-binary references from active runtime, build,
     plugin status, docs/specs, and guard-tested source surfaces.
   - Backend/MCP/plugin status now expose DB-native `search_*` readiness only.
   - Obsolete search parity benchmark artifacts were deleted; use DB-native
     reindex/status/testbed smoke as the active validation path.
   - Plan/draft artifacts deleted on ship; use Git history for details.

5. **[Fix/Validation] `[[wikilink]]` Architecture Validation**
   - Validate whether current backend link parsing intentionally avoids
     `[[wikilink]]` syntax or whether missing wikilinks are a real conflict.
   - Keep coding minimal unless validation proves a concrete parser/sync bug.
   - Detailed analysis: `.agents/drafts/minor_quick_wins.md`

6. **[Minor Update] Obsidian Agent UI/UX & Context Architecture Overhaul**
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

7. **[Major/Minor Follow-Up] RAG Post-Stabilization Hardening**
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

8. **[Minor Update] Chat Session Context Compaction**
   - Confirm full-session history behavior.
   - Add a Claude-Code-style circular token usage meter under the query box and a
     click-to-compact action.
   - Detailed analysis: `.agents/drafts/chat_context_compaction.md`

9. **[Minor Update] Minor Quick Wins**
   - Web search integration review.
   - Convert-to-LaTeX fast/light model option (`qwen2.5:0.5b`).
   - Zotero import profile/item checkbox lists sorted by most recently accessed
     or imported items.
   - Detailed analysis: `.agents/drafts/minor_quick_wins.md`

10. **[Minor Update] Vault Storage Governance & Quota Visibility**
   - Separate authoritative, derived, cache, and external storage accounting.
   - Add capacity guidance, safe admission control, and CLI/plugin visibility.
   - Detailed analysis: `.agents/drafts/vault_storage_governance.md`

11. **[Major Update] Native PDF Annotation & Asset System**
   - Native annotation highlight/memo synchronization using Obsidian's built-in
     PDF viewer.
   - In-PDF full-text search and strict-spelling mode remain here.
   - Detailed analysis: `.agents/drafts/pdf_annotation_system.md`

---

## ✅ Completed Milestones

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

- **Roadmap state**: None (System IDLE).
- **Next actionable item**: item 5, `[[wikilink]]` Architecture Validation.
- **Priority order**: item 5, then RAG hardening and remaining feature work.
