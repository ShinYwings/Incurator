# Defense And Consensus

Date: 2026-07-09 | Agent Persona: system_synthesizer

## 1. Consensus

The final plan adopts a facade plus registrar package model, with stricter gates
than the initial proposal:

- Public modules remain stable: `curator.cli`, `curator.mcp_server`, and
  `curator.plugin_api`.
- New package internals are allowed only after characterization tests lock the
  current surfaces.
- CLI extraction is first because Typer registration is easiest to snapshot and
  many tests already use `CliRunner`.
- CLI command modules must own isolated sub-app instances. The root facade wires
  the CLI tree top-down. No centralized Typer app registry is allowed.
- MCP extraction is second and must preserve `build_server()` as the only public
  construction entrypoint.
- MCP domain modules must expose `register_*_tools(mcp)` functions. Module-level
  `@mcp.tool()` registration is forbidden.
- Plugin API extraction is third and must be performed as an atomic
  module-to-package conversion with full re-exports.
- Plugin API extraction must rewrite extracted relative imports from single-dot
  sibling imports to double-dot parent imports.
- No schema changes are allowed.

## 2. Rejected Alternatives

- Full rewrite into a new command framework: rejected because the current Typer
  and FastMCP surfaces are already documented and tested.
- Move business logic into command packages: rejected because command packages
  should remain transport adapters.
- Delete compatibility exports: rejected because tests and possible user scripts
  already import private helpers from `curator.cli`.
- One giant extraction commit: rejected because rollback would be too expensive.

## 3. Implementation Shape

The implementation plan must phase the work as:

1. Docs/spec note for behavior-preserving architecture only.
2. Characterization tests.
3. CLI package extraction.
4. MCP package extraction.
5. Plugin API package extraction.
6. Full local CI, testbed smoke, version bump, changelog, plan cleanup, PR.
