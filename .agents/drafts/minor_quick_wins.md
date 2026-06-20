# Minor Quick Wins Plan

## Context
These are small improvement items independent of the major backend overhauls (Knowledge Sync Bridge, RAG Stabilization). They can be processed quickly as they mainly involve plugin-only work or research/validation tasks.

## Implementation Skeleton

### Diff Viewer UI/UX — MOVED
- The Diff Viewer UI/UX work, plus the `ai-agent-edit` SEARCH-match failures,
  edit-scope bug, immediate-diff rendering, hunk navigation, and the
  `00_System/Agent Diffs/` cleanup, grew substantial and were promoted to a
  dedicated milestone: `.agents/drafts/diff_viewer_plugin.md`.

### Convert-to-LaTeX Fast/Light Model Option — ✅ SHIPPED v0.21.0
- Added the **Convert-to-LaTeX model (fast/light)** setting (`latexModel`,
  placeholder `qwen2.5:0.5b`). `LLMClient.complete()` gained an optional
  `opts.model`; the call site overrides only for Ollama, else falls back to the
  main model. See CHANGELOG v0.21.0.

### `[[wikilink]]` Architecture Validation — FIX/VALIDATION MOVED TO ROADMAP ITEM 5
- **Current Status**: Core entities in the backend pipeline documents are not explicitly marked with `[[wikilink]]`.
- **Uncertainty**: It's possible that `[[wikilink]]` was intentionally removed in the past DB structure for the convenience of parsing backlinks using `()` or standard markdown links.
- **Execution Plan**:
  - `backend/src/curator/page_writer.py` and `sync.py`: Check if the existing `()` backlink parsing logic conflicts with the `[[wikilink]]` syntax.
  - Decide whether to introduce it based on validation results. Keep coding to a minimum.
  - This should be handled before the remaining feature-like quick wins.

### Web Search Feature Review
- **Current Status**: Need to design web search integration when using local models (Ollama, Deepseek, etc.).
- **Execution Plan**:
  - Design discussion needed: Which web search API (Brave, SerpAPI, etc.) to integrate with.
  - Review `backend/src/curator/llm.py` or a new `web_search.py` module.

### Zotero Profile/Item Checkbox Ordering — ✅ SHIPPED v0.21.0
- Items were already recent-first via `prioritizeZoteroItems`. Added
  `ZoteroImportProfile.lastUsedAt` + `sortProfilesByRecency`; the wizard now
  auto-loads the most-recently-used profile and orders the Import Profile
  dropdown recent-first. See CHANGELOG v0.21.0.
