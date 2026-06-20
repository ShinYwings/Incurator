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

1. **[Minor Update] Chat Context Decay & Minor Quick Wins**
   - Chat context decay: Fix `Cmd+Shift+L` attention failure and recency anchoring.
   - Minor Quick Wins: LaTeX fast model (`qwen2.5:0.5b`), Zotero profile checkbox sorting.
   - Detailed analysis: `.agents/drafts/chat_context_decay.md`, `.agents/drafts/minor_quick_wins.md`

2. **[Major Update] Prompt Architecture Overhaul & Refactoring**
   - Centralized prompt registry, componentized generation, and dynamic anchoring.
   - Detailed analysis: `.agents/drafts/prompt_architecture_refactoring.md`

3. **[Minor Update] Web Search Integration**
   - Design and integrate web search capabilities for local models (Ollama, Deepseek, etc.).
   - Investigate API options (Brave, SerpAPI) and implement `web_search.py`.
   - Detailed analysis: `.agents/drafts/minor_quick_wins.md` (Web Search Section)

4. **[Minor Update] Chat Session Context Compaction**
   - Confirm full-session history behavior.
   - Add a Claude-Code-style circular token usage meter under the query box and a click-to-compact action.
   - Detailed analysis: `.agents/drafts/chat_context_compaction.md`

5. **[Minor Update] Vault Storage Governance & Quota Visibility**
   - Separate authoritative, derived, cache, and external storage accounting.
   - Add capacity guidance, safe admission control, and CLI/plugin visibility.
   - Detailed analysis: `.agents/drafts/vault_storage_governance.md`

6. **[Major Update] Native PDF Annotation & Asset System**
   - Native annotation highlight/memo synchronization using Obsidian's built-in PDF viewer.
   - In-PDF full-text search and strict-spelling mode remain here.
   - Detailed analysis: `.agents/drafts/pdf_annotation_system.md`

---

## ✅ Completed Milestones

*(All previous milestones up to v0.20.0 have been successfully shipped and archived in the Git history. No active follow-ups remain.)*

---

## 🧊 Blocked / Icebox

No blocked items currently tracked.

---

## 📌 Current Focus & Active Milestone

- **Roadmap state**: Chat Context Decay & Minor Quick Wins — Master Plan authored.
- **Active Milestone**: **Chat Context Decay & Minor Quick Wins** (target `v0.21.0`).
- **Next actionable item**: AWAITING human approval of `.agents/plans/01_chat_decay_quick_wins.md`, then TDD implementation (P0→P5).
- **Priority order**: Chat Context Decay & Minor Quick Wins, then Prompt Architecture Overhaul.
