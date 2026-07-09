# Relay State (PL-1 Plugin God-file Decomposition)

- **Goal**: Decompose plugin god-files (`chatSidebar.ts`, `llmClient.ts`, `externalPdfView.ts`) into a cohesive module structure without breaking existing features.
- **Plan Reference**: Pending (Needs Arena Draft)
- **Branch**: `release/v0.35.0`

### Progress Status
- Just initialized milestone v0.35.0. No work has started.

### Critical Context / Blockers
- This is a plugin-side Typescript refactor. The API contract with the backend must remain identical.
- We are starting from State 2 (Needs Draft).

### Immediate Next Action
- The Brain (Gemini) will author a deep analysis draft in `.agents/drafts/` defining the problem constraints and target structure for PL-1.
- Once the draft is available, Executors (Claude Code) will synthesize the `PLAN_TEMPLATE.md` via the Arena workflow.
