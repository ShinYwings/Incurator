# Backend CLI Simplification Plan

Date: 2026-06-02

## Goal

Reduce confusion in the `wiki` backend command surface by separating:

- human-facing public commands,
- plugin/backend local JSON commands,
- external-agent MCP commands,
- development/testbed commands,
- deprecated or legacy commands.

The target is not to remove backend capability. The target is to make the CLI
surface explain itself and keep rarely used implementation commands out of the
normal user path.

## Current Evidence

The backend currently exposes many command groups from `backend/src/curator/cli.py`:

- Top-level user/runtime commands:
  - `wiki init`
  - `wiki status`
  - `wiki version`
  - `wiki reset`
  - `wiki add`
  - `wiki build`
  - `wiki refresh`
  - `wiki sync`
  - `wiki query`
  - `wiki lint`
  - `wiki reindex`
- Source management:
  - `wiki ls`
  - `wiki source ls`
  - `wiki source show`
  - `wiki source rm`
  - `wiki source retry`
  - single public namespace: `wiki source ...`
- Background jobs:
  - `wiki jobs list`
  - `wiki jobs run`
- Config:
  - `wiki config get`
  - `wiki config set`
  - `wiki config provider`
  - `wiki config models list`
  - `wiki config models use`
- Workspace:
  - `wiki workspace init`
  - `wiki workspace list`
- Device registry:
  - `wiki devices sync`
  - `wiki devices status`
- Zotero/plugin local backend commands:
  - `wiki zotero search`
  - `wiki zotero metadata`
  - `wiki zotero annotations`
  - `wiki zotero resolve-pdf`
- MCP:
  - `wiki mcp`
  - `wiki mcp connect`
  - `wiki mcp install`
- Testbed/dev:
  - `wiki testbed ...`
- Persona:
  - `wiki persona ...` registered as a Typer group, exact subcommands still need
    a focused pass.

The plugin currently calls these backend commands directly:

- Dashboard:
  - `wiki status`
  - `wiki add`
  - `wiki build --wait`
  - `wiki sync`
  - `wiki lint`
  - `wiki reindex`
  - `wiki reset --force`
  - `wiki config provider`
  - `wiki config set`
- Zotero:
  - `wiki zotero search`
  - `wiki zotero metadata`
  - `wiki zotero annotations`
  - `wiki zotero resolve-pdf`

Remaining plugin MCP calls are planned to move to backend JSON commands. If
those commands are added as another public top-level group, the CLI surface will
become even more confusing.

## Design Decision

Use a three-lane CLI model:

### Lane 1 — Public Human CLI

These should remain visible in normal `wiki --help` and guides:

- `wiki init`
- `wiki status`
- `wiki add`
- `wiki build`
- `wiki sync`
- `wiki query`
- `wiki lint`
- `wiki reindex`
- `wiki ls`
- `wiki source ...`
- `wiki jobs ...`
- `wiki config provider`
- `wiki workspace ...`
- `wiki version`

Potentially public but should be reviewed:

- `wiki reset` — powerful/destructive, keep but make help text explicit.
- `wiki refresh` — public forward-propagation command for refreshing L4
  Exhibitions from changed L3 Concepts.
- `wiki curate` — advanced/workspace-agent L4 generation; keep directly
  callable but hide from default help.
- `wiki config get/set` — useful but low-level; candidate to hide from normal
  guide while keeping available.
- `wiki config models ...` — likely setup-only; keep, but document under
  advanced config.

### Lane 2 — Plugin Local Backend API

Plugin-only commands should live under one explicit namespace, not mixed into
normal user workflows.

Recommended namespace:

```bash
wiki plugin ...
```

Examples:

```bash
wiki plugin zotero search
wiki plugin zotero metadata
wiki plugin zotero annotations
wiki plugin zotero resolve-pdf
wiki plugin source status
wiki plugin source import
wiki plugin source rebind
wiki plugin pdf context
wiki plugin pdf search
wiki plugin query
wiki plugin promote
```

This is not `wiki plugin-ipc` and does not start a daemon. It is just an explicit
command namespace for JSON request/response commands used by the Obsidian plugin.

The current `wiki zotero ...` commands should be migrated to
`wiki plugin zotero ...` once plugin calls are updated. Because the user stated
backward compatibility is not required for the plugin/backend local boundary,
the old `wiki zotero` namespace can be removed after the migration rather than
kept as an alias.

### Lane 3 — External Agent / Dev

These should stay available but not be treated as normal user commands:

- `wiki mcp ...` — external agents only.
- `wiki devices ...` — currently mostly backend launcher/device registry
  plumbing; likely advanced/diagnostic.
- `wiki testbed ...` — development only.

Typer supports hidden command groups/commands. The plan should evaluate hiding
these from normal `wiki --help` while keeping direct invocation possible:

```python
typer.Typer(..., hidden=True)
@app.command(hidden=True)
```

If Typer group hiding is insufficient for the installed version, keep them
visible but move them into an "Advanced / internal" docs section and simplify
their command help.

## Proposed Public Surface

The normal user mental model should be:

```text
wiki init       create/configure a vault
wiki status     inspect health
wiki add        register sources + instant L1
wiki build      run L2/L3 extraction
wiki query      ask the knowledge graph
wiki sync       repair/reverify generated DAG state
wiki lint       structural checks
wiki reindex    rebuild search index
wiki ls         list tracked sources
wiki source     inspect/remove/retry sources
wiki jobs       inspect/run background jobs
wiki config     configure providers/models
wiki workspace  create/list curate.yml workspaces
```

Everything else should be hidden or advanced:

```text
wiki plugin     Obsidian plugin JSON API
wiki mcp        external agent server
wiki devices    synced-device launcher diagnostics
wiki testbed    development fixtures
wiki reset      destructive maintenance
wiki refresh     forward propagation from L3 Concepts into L4 Exhibitions
wiki persona    pending review against current dashboard/config flow
```

## Implementation Steps

1. Docs/spec update first
   - Update `docs/specs/system_behavior/SYSTEM_BEHAVIOR_v0.2.2.md` with the
     three-lane CLI policy.
   - Update `docs/specs/plugin_schema/PLUGIN_SCHEMA_v0.2.2.md` to say plugin
     local backend calls use `wiki plugin ...` JSON commands.
   - Update `docs/guides/WORKFLOW_GUIDE.md` and Korean counterpart if present
     for the public command set.
   - Update `docs/guides/PLUGIN_GUIDE.md` and `docs/guides/PLUGIN_GUIDE_KR.md`
     for plugin-local backend command namespace.

2. Add tests before command migration
   - Backend pytest for `wiki plugin zotero ...` JSON output.
   - Backend pytest or CLI smoke for `wiki --help` not showing hidden internal
     groups if Typer supports it.
   - Plugin tests ensuring Zotero calls invoke `plugin zotero ...`, not
     top-level `zotero ...`.

3. Introduce `plugin_app`
   - Add a Typer group:

     ```python
     plugin_app = typer.Typer(
         name="plugin",
         help="JSON backend API for the local Obsidian plugin.",
         hidden=True,
     )
     ```

   - Move current Zotero JSON commands under `wiki plugin zotero ...`.
   - Add future local plugin commands under this namespace instead of adding new
     public groups.

4. Update plugin callers
   - Change `main.ts` Zotero command args from:

     ```ts
     ["zotero", "search", ...]
     ```

     to:

     ```ts
     ["plugin", "zotero", "search", ...]
     ```

   - Continue the pending MCP-removal work by adding:
     - `wiki plugin source status/import/rebind`
     - `wiki plugin pdf context/search`
     - `wiki plugin query`
     - `wiki plugin promote`

5. Hide or relocate advanced groups
   - Prefer hidden:
     - `wiki mcp`
     - `wiki testbed`
     - `wiki devices`
     - `wiki plugin`
   - Keep direct invocation working.
   - Keep docs for external agents/dev scripts.

6. Review ambiguous commands
   - `wiki refresh`: resolved. It replaces the old `wiki update` command and
     remains public.
   - `wiki persona`: compare with current dashboard/config persona flow and
     decide whether it remains public or becomes advanced.
   - `wiki config get/set`: keep for scripting, but document as advanced.

7. Remove old plugin-local public namespace
   - Remove top-level `wiki zotero ...` after plugin migration and tests pass.
   - Do not keep compatibility aliases unless the user asks for them.

## Verification Plan

Run after implementation:

```bash
backend/.venv/bin/pytest backend/tests/test_zotero_tools.py backend/tests/test_runtime_state.py -q
```

Add and run new tests:

```bash
backend/.venv/bin/pytest backend/tests/test_plugin_cli.py -q
```

Plugin validation:

```bash
cd plugin
npm test -- --run src/ui/zoteroWizardModal.test.ts src/agent/incuratorClient.test.ts
env OBSIDIAN_PLUGIN_DIR= npm run build
```

Testbed smoke:

```bash
VAULT_ROOT=testbed backend/.venv/bin/wiki status
VAULT_ROOT=testbed backend/.venv/bin/wiki plugin zotero resolve-pdf --attachment-key DOESNOTEXIST --custom-paths ~/Zotero
```

If `wiki --help` visibility is changed, capture before/after output and verify
the public surface is shorter while hidden commands remain directly callable.

## Open Questions

1. Should `wiki reset` remain visible in normal help, or should it be hidden as
   an advanced/destructive command?
2. Resolved: `wiki refresh` is the real user workflow for L3→L4 forward
   propagation. `wiki update` is removed from the v0.2.2 public CLI.
3. Should `wiki persona` stay public, given the dashboard now writes persona
   settings through backend config commands?
4. Do we want hidden commands only, or also a `wiki advanced ...` namespace for
   discoverability?

## Recommended Next Action

Start with the low-risk mechanical cleanup:

1. Add hidden `wiki plugin zotero ...`.
2. Update plugin Zotero calls.
3. Remove top-level `wiki zotero ...`.
4. Update docs/tests.

Then handle `mcp/devices/testbed/update/persona` visibility as a second pass.
