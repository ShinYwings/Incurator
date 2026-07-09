# Critique on Facade Registrar Split

Date: 2026-07-09 | Agent Persona: red_teamer

## 1. Vulnerabilities & Flaws

The proposal is directionally correct but has five failure modes:

1. Typer registration order can change help output and callback behavior even if
   command names survive.
2. Moving decorators can change function names, module-qualified callback names,
   defaults, or hidden command visibility.
3. FastMCP tool registration may depend on closure-local helpers inside
   `build_server()`. Extracting tools without preserving closure state can break
   runtime behavior while still listing tool names.
4. Replacing `plugin_api.py` with a package is an import-system edge. Python
   cannot have both `plugin_api.py` and `plugin_api/` at the same path. The move
   must happen atomically, with `__init__.py` re-exporting names, and tests must
   catch direct imports.
5. Broad "extract all CLI groups" commits will be unreviewable and hard to
   revert.
6. A central Typer app registry would create a cyclic import if command modules
   import registry-owned app objects while the registry imports command modules
   for decorator side effects.
7. Moving `plugin_api.py` one package level deeper without changing relative
   imports from `.` to `..` will make extracted modules look for `db`,
   `ingest_raw`, and other siblings under `curator.plugin_api`.
8. Extracted MCP modules cannot use module-level decorators because the
   `FastMCP` instance is created inside `build_server()`.

## 2. Suggested Alternatives

- Add a pre-refactor `test_command_surface_characterization.py` that uses
  Typer's command tree directly and selected `CliRunner(... --help)` snapshots.
- Keep a phase gate after each major surface:
  CLI first, MCP second, plugin API third.
- For MCP, extract helper functions before extracting decorated tool bodies.
  Then introduce registrar modules one domain at a time. Module-level
  registration is forbidden; every domain module should expose
  `register_*_tools(mcp)`.
- For `plugin_api`, first add tests for the export list and representative
  return envelopes, then replace the module with a package in one commit and
  rewrite extracted sibling imports from `from . import ...` to
  `from .. import ...`.
- Stop if any characterization reveals an existing bug; do not silently "fix"
  behavior during decomposition.
