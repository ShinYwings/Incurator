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

1. **[Minor Update] Dedicated PDF-extraction (VLM) models** — Master Plan authored, awaiting approval
   - TWO Dashboard-selectable models decoupled from the main LLM: `vision_model` (heavy, full-page ingest) + `latex_extract_model` (light region OCR for snip/Convert; empty → falls back to `vision_model` → main vision).
   - Always-on PDF ingest → page-VLM → LaTeX L1; Cmd+Shift+X + Convert-to-LaTeX use the light model; reshapes the unreleased v0.21.0 `latexModel` in place.
   - Plan: `.agents/plans/01_pdf_vlm_extraction.md`. Same branch `feature/chat-decay-quick-wins`, one combined `v0.22.0` (no merge-first). P1 (§26 spec) STOPs for approval.

2. **[Major Update] Prompt Architecture Overhaul & Refactoring**
   - Centralized prompt registry, componentized generation, and dynamic anchoring.
   - Detailed analysis: `.agents/drafts/prompt_architecture_refactoring.md`

2. **[Minor Update] Web Search Integration**
   - Design and integrate web search capabilities for local models (Ollama, Deepseek, etc.).
   - Investigate API options (Brave, SerpAPI) and implement `web_search.py`.
   - Detailed analysis: `.agents/drafts/minor_quick_wins.md` (Web Search Section)

3. **[Minor Update] Chat Session Context Compaction**
   - Confirm full-session history behavior.
   - Add a Claude-Code-style circular token usage meter under the query box and a click-to-compact action.
   - Detailed analysis: `.agents/drafts/chat_context_compaction.md`

4. **[Minor Update] Vault Storage Governance & Quota Visibility**
   - Separate authoritative, derived, cache, and external storage accounting.
   - Add capacity guidance, safe admission control, and CLI/plugin visibility.
   - Detailed analysis: `.agents/drafts/vault_storage_governance.md`

5. **[Major Update] Native PDF Annotation & Asset System**
   - Native annotation highlight/memo synchronization using Obsidian's built-in PDF viewer.
   - In-PDF full-text search and strict-spelling mode remain here.
   - Detailed analysis: `.agents/drafts/pdf_annotation_system.md`

---

## ✅ Completed Milestones

- **v0.21.0 — Chat Context Decay & Minor Quick Wins** (shipped 2026-06-21):
  localized-question edit-affordance suppression (`Cmd+Shift+L`), Convert-to-LaTeX
  fast/light model setting, Zotero import-profile recent-first ordering.

*(All previous milestones up to v0.20.0 have been successfully shipped and archived in the Git history. No active follow-ups remain.)*

---

## 🧊 Blocked / Icebox

No blocked items currently tracked.

---

## 📌 Current Focus & Active Milestone

- **Roadmap state**: v0.21.0 in review (PR #45). PDF VLM extraction Master Plan authored, awaiting approval.
- **Active Milestone**: **Dedicated PDF-extraction (VLM) model** (target `v0.22.0`) — plan-approval gate.
- **Next actionable item**: Approve `.agents/plans/01_pdf_vlm_extraction.md`; merge PR #45; then branch + implement.
- **Priority order**: PDF VLM extraction, then Prompt Architecture Overhaul.
