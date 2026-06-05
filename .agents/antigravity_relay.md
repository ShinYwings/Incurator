# Antigravity Junior Agent - State & Workflow Relay
Date: 2026-06-05

## 🚨 Antigravity Persona & Strict Workflow (MUST READ)
As the Junior Agent (Antigravity), you MUST adhere to the following workflow on every task. The user has explicitly criticized your tendency to jump to conclusions and make empty promises. Prove your rigor.
1. **Codebase-First**: Before acting or theorizing, trace the complete call stack (`grep_search`, `view_file`). Never guess.
2. **Self-Critical Chaining**: Challenge your own hypotheses constantly. Ask "Is this the real root cause?", "What am I missing?".
3. **Show, Don't Tell**: Do not say "I will keep this in mind." Document your analyses and decisions directly in this file. 

---

## Bug Fix Report (For Senior Review)
This section contains a summary of the out-of-band UX and UI bug fixes implemented by the Antigravity Junior agent. 

**1. Agentic PDF Navigation:**
- Implemented a new backend MCP tool `curator_get_pdf_toc` and updated system prompts (`mcp_server.py`, `systemPrompt.ts`) to allow the LLM to actively jump to PDF chapters and pages.
- Added image forwarding logic for selected regions in the chat UI (`chatSidebar.ts`).
- (See `.agents/plans/2026-06_agentic_pdf_navigation.md` for details).

**2. MCP / Local LLM Robustness:**
- **Native TypeScript MCP Loop**: Fully refactored `llmClient.ts` to execute MCP tool calls natively in TypeScript for Ollama and DeepSeek, removing the hard dependency on the python `codex` CLI for local models.
- **Empty Tool Roles**: Patched `OllamaAdapter` and `OpenAIAdapter` to pass `""` instead of `null` for tool roles to prevent 400 Bad Request / 500 errors. Added fallback `tool_call_id` generation for local models.

**3. Context & Pinning Fixes:**
- **UI Pin Suppression**: Fixed `chatSidebar.ts` so pinning explicit text selections or PDF crops no longer suppresses the background document's "eye" pin. Both background context and focused selections can now be seen simultaneously. (Resolved Bug 5).
- **PDF Context Prioritization**: Reordered `buildLLMMessages` so user-pinned contexts (`msg.contextRefs`) are pushed *after* the auto-generated background context. This ensures the LLM correctly prioritizes the user's explicit selection over the background page. (Resolved Bug 2).
- **Text Extraction Fallback & Hotkey Fix**: Fixed an issue where `Cmd+Shift+L` or dragging text from Markdown/PDFs failed to capture plain text. 
  - Added `text/plain` fallback in `handleDataTransferDrop` to support pure text drag and drop.
  - **CRITICAL**: The global `line-reference` command in `main.ts` was completely missing its default `hotkeys` array! This meant pressing `Cmd+Shift+L` while focused on a PDF or MD editor did nothing natively.
  - To work around this missing hotkey, users were clicking the chat input first, which caused the browser to lose the active text selection (`window.getSelection()`). This lost selection triggered `withVisionFallback` to improperly capture the entire PDF page as an image instead of text.
  - Fixed by registering the global `Cmd+Shift+L` hotkey in `main.ts` and refactoring `chatSidebar.ts` to defer execution to the global command, making text extraction rock-solid across all contexts.
- **Context Tag Priority Fix**: Fixed an issue where the LLM ignored explicit text chips (e.g., Markdown selections) when a PDF was open in the background. 
  - The system prompt instructs the LLM to prioritize text inside `<primary_focus_selection>` tags over `<background_reference_only>` tags.
  - However, explicit `msg.contextRefs` (user-created chips) were missing the `<primary_focus_selection>` wrappers, causing the LLM to default to analyzing the background PDF image/text instead of the user's query.
  - Added `<primary_focus_selection>` wrapping to `isPrimaryUserContext` refs in `buildLLMMessages`.

**4. UI UX Fixes:**
- **Settings Sync**: Added a broadcast loop in `main.ts` `saveSettings()` to trigger sidebar UI updates (`syncModelControls`, `syncReasoningControl`), ensuring the chat sidebar dropdowns instantly reflect changes made in the settings tab. (Resolved Bug 3).
- **Chat Auto-Scroll**: Implemented a "smart scroll" threshold in `chatSidebar.ts` `scrollToBottom`. It now only forces a scroll if the user is already near the bottom, preventing jarring jumps during streaming. (Resolved Bug 4).
