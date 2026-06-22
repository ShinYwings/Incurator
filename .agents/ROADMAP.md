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

1. **[Bugfix / Architecture] Popover Tool Execution & Sandbox Scope Violation**
   - The popover feature currently injects global MCP tools, leading to unexpected file-system traversal.
   - Refactor `quickQueryContext.ts` to share `systemPrompt.ts` rules and implement a `disableTools` flag in `llmClient.ts`.
   - Detailed analysis: `.agents/drafts/popover_tool_scope.md`

2. **[Major Update] Prompt Architecture Overhaul & Refactoring**
   - Centralized prompt registry, componentized generation, and dynamic anchoring.
   - Detailed analysis: `.agents/drafts/prompt_architecture_refactoring.md`

3. **[Major Update] Diff Viewer UI/UX**
   - UI/UX work including `ai-agent-edit` SEARCH-match failures, edit-scope bug, immediate-diff rendering, and hunk navigation.
   - Cleanup of `00_System/Agent Diffs/`.
   - Detailed analysis: `.agents/drafts/diff_viewer_plugin.md`

4. **[Validation] `[[wikilink]]` Architecture Validation**
   - Core entities in the backend pipeline documents are not explicitly marked with `[[wikilink]]`.
   - Validate `backend/src/curator/page_writer.py` and `sync.py` backlink parsing logic against `[[wikilink]]` syntax.
   - Detailed analysis: `.agents/drafts/minor_quick_wins.md` (Wikilink section)

5. **[Minor Update] Chat Session Context Compaction**
   - Confirm full-session history behavior.
   - Add a Claude-Code-style circular token usage meter under the query box and a click-to-compact action.
   - Detailed analysis: `.agents/drafts/chat_context_compaction.md`

6. **[Minor Update] Vault Storage Governance & Quota Visibility**
   - Separate authoritative, derived, cache, and external storage accounting.
   - Add capacity guidance, safe admission control, and CLI/plugin visibility.
   - Detailed analysis: `.agents/drafts/vault_storage_governance.md`

7. **[Major Update] Native PDF Annotation & Asset System**
   - Native annotation highlight/memo synchronization using Obsidian's built-in PDF viewer.
   - In-PDF full-text search and strict-spelling mode remain here.
   - Detailed analysis: `.agents/drafts/pdf_annotation_system.md`

8. **[Minor Update] Web Search Integration**
   - Design and integrate web search capabilities for local models (Ollama, Deepseek, etc.).
   - Investigate API options (Brave, SerpAPI) and implement `web_search.py`.
   - Detailed analysis: `.agents/drafts/minor_quick_wins.md` (Web Search Section)

---

## ✅ Completed Milestones

- **v0.23.0 — CLI Provider Tool-Scope Sandbox** (shipped 2026-06-22): closed the
  CLI-native-tool escape the v0.19.0 MCP isolation left open. `toolPolicy` now reaches
  the CLI command builder — popover runs tool-free, sidechat scopes tools to the
  allowed roots (vault + Zotero); dropped `agy --dangerously-skip-permissions`. agy's
  own `--sandbox` proved ineffective (P0 created files), so every CLI subprocess is
  wrapped in an OS sandbox (macOS `sandbox-exec`, Linux `bwrap`; Windows out of scope).
- **v0.22.0 — PDF Vision Extraction + Chat Decay & Quick Wins** (shipped 2026-06-21,
  one combined release on `feature/chat-decay-quick-wins`): dedicated PDF-extraction
  vision models (`llm.vision_model` always-on `add source` page-VLM → LaTeX L1,
  `latex_extract_model` light slot; CLI-subscription cloud vision, no API keys;
  Dashboard rows); plus localized-question edit-affordance suppression (`Cmd+Shift+L`)
  and Zotero import-profile recent-first ordering. (The unreleased v0.21.0 `latexModel`
  was reshaped into the vision slots — never shipped standalone.)

*(All previous milestones up to v0.20.0 have been successfully shipped and archived in the Git history. No active follow-ups remain.)*

---

## 🧊 Blocked / Icebox

No blocked items currently tracked.

---

## 📌 Current Focus & Active Milestone

- **Roadmap state**: v0.23.0 (Popover/CLI tool-scope sandbox) implemented on `feature/popover-tool-scope`; PR pending.
- **Active Milestone**: none (v0.23.0 shipped to PR; awaiting merge).
- **Next actionable item**: Prompt Architecture Overhaul & Refactoring after merge.
- **Priority order**: Prompt Architecture Overhaul, then Web Search Integration.
