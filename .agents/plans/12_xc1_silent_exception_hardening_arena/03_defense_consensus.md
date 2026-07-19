# Defense and Consensus: Observable, Contract-Preserving Fallbacks
Date: 2026-07-19 | Agent Persona: System Synthesizer

## 1. Resolved Decisions

- Scope is the 28 syntactically silent broad handlers, not all 148 broad
  handlers in target packages.
- Each site receives a classification and failure-injection test before change.
- Narrow only standard-library/config/parser operations with known exception
  sets. Third-party clients and cleanup may retain `Exception` with an explicit
  reason and debug log.
- MCP diagnostics use logging only; stdout and tool envelopes do not change.
- No new warning field is introduced. Existing CLI warnings are used only where
  already documented.
- The static test checks both silent bodies and the reviewed allowlist, preventing
  cosmetic log-only compliance from being mistaken for narrowing.
