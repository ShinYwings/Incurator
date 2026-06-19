# Draft: Popover Tool Execution & Sandbox Scope Violation

## 1. Core Problem Definition
The user reported a severe violation of the agent's operational boundaries and file access scope when using the Popover quick query feature.
When querying the agent via the inline popover, the agent unexpectedly attempts to create new files to extract PDF text (e.g., running a `find_mvg_text.py` script) and searches extensively through the entire file system. The user explicitly noted that the file search scope must be strictly bounded to the vault directory, the Zotero folder, and the Zotero library (PDF storage location).

### Deep Code Analysis & Root Cause ("Why")
1. **MCP Tool Injection & Incurator Exposure**: The user questioned why MCP tools are involved if they don't explicitly use them. The answer is that the plugin *does* expose Incurator (and potentially other system tools) as an MCP server. `llmClient.ts` (`streamChat`) unconditionally injects the entire MCP toolset (`this.mcpManager.getAllTools()`) into the LLM request body for both Sidechat and Popover. The LLM, seeing these tools, autonomously decides to use them (e.g., executing a hallucinated `find_mvg_text.py` via an exposed command runner) to answer questions, completely bypassing intended ephemeral constraints.
2. **Dangerous Prompt Duplication (Sidechat vs Popover)**: The user correctly suspected that the prompts are not shared. `chatSidebar.ts` relies on `buildBaseSystemPrompt` from `systemPrompt.ts`, whereas the Popover relies on a completely isolated, hardcoded string in `quickQueryContext.ts`. This fragmentation means that any file access boundary restrictions applied to one feature are missing from the other. Both features occasionally search the entire filesystem because neither prompt securely limits the MCP tool execution layer.
3. **Lack of Strict Sandboxing**: The MCP tools themselves (or the environment they execute in) do not have a hard-coded security sandbox restricting path access. If a tool allows arbitrary path execution or file creation, the agent can traverse outside the intended boundaries (Vault, Zotero Folder, Zotero Library).

## 2. Constraints & Success Criteria
- **Unify Prompt Architecture**: The system prompt generation MUST be centralized. `quickQueryContext.ts` must be refactored to consume the core boundary rules from `systemPrompt.ts` (or a shared configuration layer) instead of using a hardcoded duplicate.
- **Tool Isolation**: The `quickQueryPopover` execution path MUST be completely isolated from global MCP tools. The LLM Client must be updated to accept a parameter that explicitly disables tool injection for ephemeral UI features.
- **Strict Path Sandboxing**: Any file-system or command-execution MCP tools must be updated to enforce strict path validation. Execution and read/write operations MUST be mathematically proven to reside within the allowed roots: the Vault, the Zotero folder, or the Zotero Library.
- **Zero-Creation Policy in Popover**: The Popover must never result in side-effects like file creation.
- **Success Measure**: Triggering a popover query on PDF text must result in a direct LLM response using ONLY the injected text context, completely bypassing any tool calls or external script execution.
