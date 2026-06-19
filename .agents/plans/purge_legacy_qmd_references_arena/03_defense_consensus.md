# Defense And Consensus

Date: 2026-06-20 | Agent Persona: system_synthesizer

## 1. Final Consensus

The purge should remove active qmd runtime/build/API references, not erase every
historical sentence in benchmark archives. The implementation must update both
backend producers and plugin consumers so `search_*` is the only live status API.

## 2. Guardrails

- No search algorithm rewrite.
- No schema migration.
- No removal of `lex:`, `vec:`, or `hyde:` structured expansion semantics.
- No compatibility aliases using the retired token in active code.
- If a legacy behavior is still needed, generalize it without literal qmd naming.

