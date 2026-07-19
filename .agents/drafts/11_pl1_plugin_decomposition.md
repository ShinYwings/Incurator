# Milestone Draft: PL-1 Plugin God-file Decomposition

## 1. Problem Statement
The Obsidian plugin currently suffers from severe structural technical debt due to massive "god-files" that have accumulated thousands of lines of code. Specifically:
- `plugin/src/ui/chatSidebar.ts` (~4,900 lines)
- `plugin/src/agent/llmClient.ts` (~2,400 lines)
- `plugin/src/ui/externalPdfView.ts` (~1,900 lines)
- `plugin/main.ts` (~2,200 lines)

These monolithic files violate modularity principles, create massive merge conflicts, impede testability, and slow down development. They contain deeply coupled logic (e.g., UI rendering mixed with state management, prompt compilation, and network I/O).

## 2. Objective
Decompose these god-files into a cohesive, modular package structure. The final architecture should feature focused, single-responsibility files without altering any existing user-facing behavior, Obsidian lifecycle hooks, or backend API contracts.

## 3. Strict Constraints (No-Code Wall & Modularity)
1. **Zero Behavioral Change**: This is a pure structural refactoring milestone. You MUST NOT introduce new features, alter the UI layout, change the chat history persistence format, or modify how the plugin communicates with the backend `plugin_api`.
2. **Sub-Package Organization**: 
   - Extract `chatSidebar.ts` into a `plugin/src/ui/chat/` directory (e.g., separating `ChatSidebarView`, `MessageRenderer`, `ChatInputContainer`, `ContextChipsRenderer`).
   - Extract `llmClient.ts` into a `plugin/src/agent/llm/` directory (e.g., separating the base network client, prompt builders, token truncators, and stream handlers).
   - Extract `externalPdfView.ts` into a `plugin/src/ui/pdf/` directory (e.g., separating PDF.js rendering, annotation syncing, and text-selection bridging).
3. **Circular Dependencies**: You MUST prevent circular imports. If shared interfaces are needed, move them to `plugin/src/types.ts` or a dedicated `types/` sub-package.
4. **Lifecycle Hooks**: The `main.ts` file must remain the entry point, but it should act as a lightweight facade/coordinator that imports and wires up these sub-modules.
5. **Test Integrity**: The `vitest` suite MUST continue to pass. If a test relied on mocking a private method inside a god-file, you must refactor the test to mock the new decomposed module correctly.

## 4. Next Step for Executors
- Analyze the current import graphs and internal structures of these files.
- Run the Arena Workflow (Persona Proposals -> Critique -> Master Plan) to draft `PLAN_TEMPLATE.md`.
- Detail the exact file-by-file target structure and the incremental steps required to decompose them safely.
