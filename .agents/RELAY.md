# RELAY — Active Milestone: v0.34.0 (CM-1 Command Module God-File Decomposition)

## Goal

Decompose backend command-module god-files (`cli.py`, `mcp_server.py`, `plugin_api.py`) into modular package structures (`backend/src/curator/commands/`, etc.) with zero regression in CLI commands, MCP tools, or plugin API endpoints.

## Plan Reference

- Master Plan: `.agents/plans/01_system_stability_overhaul.md`
- PM Draft Briefing: `.agents/drafts/10_cm1_god_file_decomposition.md`
- Target Implementation Plan: `.agents/plans/10_cm1_god_file_decomposition.md` (to be synthesized by Executors)

## Analysis & Reasoning

- Previous release `v0.33.0` (PR #84) was merged into `master`.
- `master` was sanitized to IDLE (`fe55925`).
- Created branch `release/v0.34.0` from `master`.
- Authored PM draft briefing `.agents/drafts/10_cm1_god_file_decomposition.md` targeting the remaining CM-1 slice of `System Stability Overhaul`:
  - `cli.py` (7,611 LOC) houses 25+ subcommand groups.
  - `mcp_server.py` (3,491 LOC) houses all MCP tool definitions and handlers.
  - `plugin_api.py` (1,100 LOC) houses local HTTP endpoints.

## Progress Status

- [x] Post-merge IDLE reset on `master` completed.
- [x] Created `release/v0.34.0` branch.
- [x] Authored `.agents/drafts/10_cm1_god_file_decomposition.md`.
- [ ] Executors synthesize `.agents/plans/10_cm1_god_file_decomposition.md` via Arena debate.
- [ ] Characterization coverage & implementation of CM-1 decomposition.

## Critical Context / Blockers

- Ensure 100% backward compatibility of CLI argument parsing, console output, MCP tool names/schemas, and plugin API HTTP endpoints.
- Ensure all tests under `backend/tests/` pass via `scripts/backend-check pytest`.

## Immediate Next Action

Executors (Claude Code / Codex):
1. Read `.agents/drafts/10_cm1_god_file_decomposition.md` and `.agents/plans/01_system_stability_overhaul.md`.
2. Synthesize `.agents/plans/10_cm1_god_file_decomposition.md` using `.agents/PLAN_TEMPLATE.md`.
3. Stop for human approval if required by the workflow, then proceed to TDD implementation.
