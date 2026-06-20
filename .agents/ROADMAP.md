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

1. **[Minor] RAG Post-Stabilization Hardening — re-scoped to systemic group**
   - Grounding (2026-06-20) found the `batch_1_to_3_audit` drafts were written
     against a pre-stabilization tree: **6 of 10 findings already shipped** and are
     pinned by regression tests, so they are settled, NOT pending:
     - 04 locator false-truth → `orphaned_support` (FIXED);
     - 05 budget thrashing → `budget_exhausted` signal (FIXED);
     - 07 trace mutation → intentional & tested (`selected_items` + `synthesis_status`);
     - 08 CJK-safe token estimation → byte-aware estimator (FIXED);
     - 09 rank order preservation (FIXED);
     - 10 expansion state-machine hardening (FIXED).
   - Active scope = the genuinely unimplemented **systemic** items only:
     - 06 explore-route ContextService unification (concrete; first);
     - 03 pipeline healing + soft-snapshot auto-rebase;
     - 02 graph fragmentation / soft-link proposal + giant-component quarantine;
     - 01 real-world oracle sampling + noisy fixture coverage.
   - Plan: `.agents/plans/01_rag_systemic_hardening.md` (Arena debate concluded,
     **awaiting user approval**). Inputs: `.agents/drafts/batch_1_to_3_audit/`.

2. **[Minor Update] Chat Session Context Compaction**
   - Confirm full-session history behavior.
   - Add a Claude-Code-style circular token usage meter under the query box and a
     click-to-compact action.
   - Detailed analysis: `.agents/drafts/chat_context_compaction.md`

3. **[Minor Update] Minor Quick Wins**
   - Web search integration review.
   - Convert-to-LaTeX fast/light model option (`qwen2.5:0.5b`).
   - Zotero import profile/item checkbox lists sorted by most recently accessed
     or imported items.
   - Detailed analysis: `.agents/drafts/minor_quick_wins.md`

4. **[Minor Update] Vault Storage Governance & Quota Visibility**
   - Separate authoritative, derived, cache, and external storage accounting.
   - Add capacity guidance, safe admission control, and CLI/plugin visibility.
   - Detailed analysis: `.agents/drafts/vault_storage_governance.md`

5. **[Major Update] Native PDF Annotation & Asset System**
   - Native annotation highlight/memo synchronization using Obsidian's built-in
     PDF viewer.
   - In-PDF full-text search and strict-spelling mode remain here.
   - Detailed analysis: `.agents/drafts/pdf_annotation_system.md`

---

## ✅ Completed Milestones

- **Obsidian Agent UI/UX & Context Architecture Overhaul** — shipped in v0.19.0.
- **Curator Wikilink Native Resolution & External-Source Links** — shipped in v0.17.0 and v0.18.0.
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

- **Roadmap state**: Previous milestone shipped as v0.19.0.
- **Active Milestone**: Item 1 (RAG Post-Stabilization Hardening, re-scoped to systemic group).
- **Next actionable item**: Human approval of `.agents/plans/01_rag_systemic_hardening.md`; then executors run P0 (measured baseline) → P1 (docs-first specs). The bug-batch (04,05,07,08,09,10) is already shipped — do not re-plan it.
- **Priority order**: RAG hardening systemic group (item 1), then Chat Session Context Compaction (item 2).
