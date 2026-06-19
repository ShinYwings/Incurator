# Draft: Prompt Architecture Overhaul & Refactoring

## 1. Core Problem Definition
The user has mandated a comprehensive refactoring of the entire prompt generation architecture. The current prompt logic is fragmented across multiple files, causing systemic bugs, inconsistent model outputs, and critical boundary violations. 

Currently:
1. `systemPrompt.ts` manages the main chat prompt but suffers from attention decay in long sessions. It also contains monolithic blocks of text that are hard to maintain.
2. `quickQueryContext.ts` duplicates a hardcoded prompt string, omitting crucial MCP execution boundaries and causing the "Popover Tool Sandbox Violation" bug.
3. The prompt instructions regarding `ai-agent-edit` (Diff Viewer) are brittle, causing inconsistent outputs across models (some batch, some split, some fail) and resulting in UI/UX desyncs.

### Deep Code Analysis & Root Cause ("Why")
The prompt construction relies on string concatenation of monolithic blocks (e.g., `BASE_INSTRUCTIONS`, `EXTERNAL_INCURATOR_MCP_ADDENDUM`) without a semantic structuring or templating system. Because constraints (like "no filesystem access" or "strict edit block format") are scattered or duplicated, any update to the agent's core capabilities requires modifying multiple isolated strings. Furthermore, there is no dynamic weighting mechanism to enforce critical constraints (like avoiding token limits or restricting tool scopes) at the very end of the prompt where LLM attention is strongest.

## 2. Constraints & Success Criteria
- **Centralized Prompt Registry**: All base instructions, tool constraints, and output formatting rules MUST be centralized into a single architectural layer. 
- **Componentized Generation**: Refactor `systemPrompt.ts`, `quickQueryContext.ts`, and context prioritization into a cohesive builder pattern. Prompts must be assembled from composable blocks (e.g., `getBoundaryConstraints()`, `getOutputFormatRules()`) so that both Sidechat and Popover inherit the exact same core security and behavioral rules.
- **Dynamic Anchoring**: Implement a mechanism to inject absolute invariants (e.g., "Do not use MCP tools outside the vault", "Output strict ai-agent-edit blocks") at the very end of the final LLM payload to prevent context decay.
- **Test-Driven Refactoring**: The prompt assembly logic must be strictly unit-tested (e.g., `systemPrompt.test.ts`) to ensure that enabling/disabling features accurately reflects the correct prompt structure without regressions.
