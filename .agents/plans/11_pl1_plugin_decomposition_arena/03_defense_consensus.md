# Consensus: Incremental Facades With Owner-Module Tests

Date: 2026-07-09 | Agent Persona: System Synthesizer

## Decision

Use current file paths as stable facades, but do not make them comment-only
compatibility shells. Each phase must move executable logic to a new owner
module and move the corresponding tests to that owner module.

## Required Compromises

- `main.ts` decomposition is limited to coordinator-safe helpers in v0.35.0.
  The primary PL-1 goal is the three plugin god-files under `src/`.
- `ChatSidebarView`, `LLMClient`, and `ExternalPdfView` remain the public class
  names. If class-private state blocks clean extraction, extract pure helpers
  first and leave orchestration methods in the class until a later slice.
- No new runtime dependency is required for cycle detection. Prefer
  `tsc --noEmit`, import-surface tests, and explicit one-way module rules unless
  the repo already has a suitable tool.
- Source-contract tests must assert behavior/ownership in the new modules and
  facade export compatibility, not old file length or incidental strings.
