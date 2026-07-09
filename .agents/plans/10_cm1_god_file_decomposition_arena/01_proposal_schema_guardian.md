# Schema Guardian Proposal: No Schema Or Contract Drift

Date: 2026-07-09 | Agent Persona: schema_guardian

## 1. Core Logic & Implementation

CM-1 must be a structural refactor only. It must not:

- Add, remove, rename, or migrate DB tables.
- Change JSON keys returned by hidden plugin commands.
- Change MCP tool names, parameter names, defaults, or result shapes.
- Change CLI command names, hidden flags, option names, default values, exit
  codes, or JSON envelopes.

The compatibility layer is part of the contract. Existing imports from tests and
downstream scripts must keep working:

- `from curator.cli import app`
- `from curator.cli import _maybe_auto_export`
- `from curator.cli import _filter_sync_structural_issues`
- `from curator.mcp_server import build_server`
- `from curator import plugin_api`

Add a test that asserts these imports before any extraction happens.

Docs update should be limited to internal architecture notes in
`SYSTEM_BEHAVIOR.md`, `PLUGIN_SCHEMA.md`, and guide references if they mention
module ownership. No user-facing command behavior should be rewritten because no
behavior is intended to change.

## 2. Pros & Cons

Pros:

- Prevents a refactor from becoming a hidden schema or public API release.
- Keeps version bump as a minor release due to code/package architecture change,
  while avoiding migration work.
- Gives review a clear invariant: generated outputs should be behavior-identical.

Cons:

- Retaining compatibility exports leaves some old names in facade files.
- Refactor may need more imports than ideal during the transition.
