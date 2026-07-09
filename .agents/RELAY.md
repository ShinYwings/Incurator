# RELAY - Active Milestone: v0.34.0 (CM-1 Command Module God-File Decomposition)

## Goal

Decompose the backend command-module god-files into modular package structures
with zero regression in CLI commands, MCP tools, or plugin API endpoints.

Target files:

- `backend/src/curator/cli.py`
- `backend/src/curator/mcp_server.py`
- `backend/src/curator/plugin_api.py`

## Plan Reference

- Parent Master Plan: `.agents/plans/01_system_stability_overhaul.md`
- PM Draft Briefing: `.agents/drafts/10_cm1_god_file_decomposition.md`
- Plan Template: `.agents/PLAN_TEMPLATE.md`
- Target Implementation Plan: `.agents/plans/10_cm1_god_file_decomposition.md`
  (synthesized; awaiting human approval before implementation)
- Evidence Ledger: `.agents/plans/10_roadmap_evidence.md`
- Domain Analyses:
  - `.agents/plans/A_cm1_cli_domain_analysis.md`
  - `.agents/plans/B_cm1_mcp_domain_analysis.md`
  - `.agents/plans/C_cm1_plugin_api_domain_analysis.md`
- Arena Folder: `.agents/plans/10_cm1_god_file_decomposition_arena/`

## Analysis & Reasoning

- Current branch: `release/v0.34.0`.
- Current worktree at relay refresh: clean.
- `USER_REPORT.md` is empty; no inbox items need triage before continuing.
- `ROADMAP.md` marks System Stability Overhaul as active, with v0.34.0 focused
  on CM-1 command-module decomposition.
- Existing briefing identifies three backend monoliths:
  - `cli.py` contains the root Typer app plus 25+ command groups.
  - `mcp_server.py` contains the MCP server, tool definitions, JSON-RPC handling,
    schema formatting, and dispatch logic.
  - `plugin_api.py` contains local HTTP handlers used by the Obsidian plugin.
- This relay refresh only updated live coordination state. No application code,
  docs, tests, or version files were changed.
- Arena planning completed on 2026-07-09. The plan is intentionally marked
  DRAFT because project workflow requires human approval before implementation.
- Plan review corrections were incorporated on 2026-07-09:
  - CLI command modules must own isolated `typer.Typer()` sub-apps; `curator.cli`
    wires the tree top-down. No central Typer app registry.
  - MCP modules must expose `register_*_tools(mcp)` registrars. No module-level
    `@mcp.tool()` decorators.
  - Extracted `curator.plugin_api.*` modules must rewrite parent-sibling imports
    from single-dot to double-dot relative imports.

## Progress Status

- [x] Post-merge IDLE reset on `master` completed.
- [x] Created `release/v0.34.0` branch.
- [x] Authored `.agents/drafts/10_cm1_god_file_decomposition.md`.
- [x] Verified current relay state against branch, inbox, roadmap, draft, parent
  plan, and plan template on 2026-07-09.
- [x] Synthesize `.agents/plans/10_cm1_god_file_decomposition.md` via the Arena
  workflow.
- [x] Update `.agents/ROADMAP.md` with the synthesized plan reference.
- [x] Incorporate plan-review corrections for CLI cycles, MCP registrar shape,
  and plugin API relative-import shifts.
- [x] Human approval received to proceed with implementation.
- [ ] Add characterization coverage before moving code.
- [ ] Implement CM-1 decomposition with behavior-preserving exports and
  registrations.
- [ ] Run backend checks and required testbed validation.

## Critical Context / Blockers

- Preserve 100% backward compatibility for CLI argument parsing, command names,
  option names, console output expectations, and public imports from
  `curator.cli`.
- Preserve MCP tool names, input schemas, result shapes, and JSON-RPC behavior.
- Preserve plugin API routes, request payloads, response payloads, and error
  semantics.
- Characterization tests must precede extraction. If a characterization test
  exposes buggy existing behavior, stop and ask whether to preserve or fix it.
- CLI extraction must avoid a centralized Typer sub-app registry. Each command
  group module owns its own sub-app; root `curator.cli` imports sub-apps and
  calls `app.add_typer()`.
- MCP extraction must use registrar functions that receive the dynamic FastMCP
  instance from `build_server()`. Module-level tool decorators are forbidden.
- Plugin API package extraction must rewrite `from . import <curator sibling>` to
  `from .. import <curator sibling>` in extracted modules.
- Version bump and changelog are mandatory for any implementation branch that
  changes code.

## Immediate Next Action

Next executor:

1. Review `.agents/plans/10_cm1_god_file_decomposition.md` and supporting domain
   analyses/evidence.
2. Wait for human approval of the plan.
3. After approval, start P0 characterization tests before moving any code.
