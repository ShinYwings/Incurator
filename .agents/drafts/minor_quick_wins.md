# Minor Quick Wins Plan

## Context
These are small improvement items independent of the major backend overhauls (Knowledge Sync Bridge, RAG Stabilization). They can be processed quickly as they mainly involve plugin-only work or research/validation tasks.

## Implementation Skeleton

### Diff Viewer UI/UX — MOVED
- The Diff Viewer UI/UX work, plus the `ai-agent-edit` SEARCH-match failures,
  edit-scope bug, immediate-diff rendering, hunk navigation, and the
  `00_System/Agent Diffs/` cleanup, grew substantial and were promoted to a
  dedicated milestone: `.agents/drafts/diff_viewer_plugin.md`.

### Convert-to-LaTeX Fast/Light Model Option (triaged 2026-06-11)
- **Current Status**: The right-click "Convert to LaTeX" PDF feature reuses the
  main model. Simple conversion doesn't need the heavy model.
- **Requirements**: Add a settings option to pick a separate "Fast/Light model"
  for LaTeX conversion. Recommended Ollama default `qwen2.5:0.5b`; investigate
  whether an even smaller usable model exists.
- **Note**: Architecturally this is a "task-specialized light model" setting.
  Implement the config plumbing once and reuse it for other fast/cheap model
  surfaces; this entry is the quick plugin-settings surface for it.

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

### Zotero Profile/Item Checkbox Ordering
- **Current Status**: Zotero import/search UI has recent-item support in the
  plugin settings model, but the user-facing checkbox/list ordering must be
  verified and fixed where needed.
- **Requirement**: When listing Zotero profiles or importable Zotero items with
  checkboxes, sort the list by most recently accessed/imported first so the
  user's current working papers appear at the top.
- **Execution Plan**:
  - Inspect `plugin/src/ui/zoteroWizardModal.ts` and related tests for
    `recentZoteroItems` / profile ordering behavior.
  - Ensure empty-query suggestions and checkbox lists preserve recent-first
    ordering without dropping non-recent results.
  - Add or update plugin tests for recent-first checkbox/list rendering.
