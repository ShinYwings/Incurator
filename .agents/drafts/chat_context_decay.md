# Draft: Chat Context Decay & Cmd+Shift+L Context Injection Failure

## 1. Core Problem Definition
The user has reported a critical failure in the agent's attention mechanism during extended chat sessions.
Specifically, as the conversation lengthens—especially after the user has repeatedly requested full-document inspections or modifications early in the session—the agent loses its ability to focus on newly injected, highly localized context.

When the user utilizes the `Cmd+Shift+L` shortcut (which triggers the `incurator-obsidian-agent:line-reference` command) to extract and query a specific, localized excerpt of a document that doesn't make sense, the agent fundamentally ignores this precise injection. Instead of answering the targeted question about the extracted text, the agent defaults to its earlier behavioral pattern: it attempts to modify or analyze the entire file.

### Deep Code Analysis & Root Cause ("Why")
1. **Context Window Saturation**: The `chatSidebar.ts` maintains a rolling history of `ChatMessage` objects. While there is a `CONTINUITY_MESSAGE_LIMIT` (6), the sheer token volume of earlier whole-document diffs and comprehensive prompts heavily saturates the LLM's context window.
2. **Attention Dilution**: The system prompt in `systemPrompt.ts` defines `<primary_focus_selection>` and provides an `editableSelectionInstruction`. However, when placed at the top of a massive context payload, the relative attention weight of these instructions is diluted by the massive volume of historical text. The LLM falls back into the established "whole-document modification" pattern.
3. **Missing High-Priority Anchors**: Currently, there is no dynamic prompt weighting or "recency anchoring" mechanism. The extracted text from `Cmd+Shift+L` is simply appended as another turn, without overriding the implicit task vectors established by the early conversation.

## 2. Constraints & Success Criteria
- **Task**: Investigate and implement prompt engineering techniques (e.g., from web/GitHub research) to enforce strict attention on the latest query in long contexts.
- **Dynamic Weighting / Recency Anchoring**: The system must explicitly prioritize the `Cmd+Shift+L` context. This could involve placing a strict, high-weight directive at the very end of the prompt (the "recency effect" location) that forcefully overrides prior whole-document tasks.
- **Context Compaction Integration**: This issue must be evaluated alongside the planned "Chat Session Context Compaction" milestone to ensure stale whole-document contexts can be aggressively truncated when a localized query is made.
- **Success Measure**: When `Cmd+Shift+L` is used to ask a question about a specific text snippet, the agent MUST output a direct answer regarding ONLY that snippet, and MUST NOT output an `ai-agent-edit` block for the entire file.
