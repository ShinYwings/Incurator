# A - CLI Domain Analysis

Date: 2026-07-09

## Design Constraints From Codebase

- `backend/src/curator/cli.py` is 7,611 lines.
- It creates the root `app` at line 66 and registers many Typer apps with
  `add_typer()`.
- It contains root commands such as `reset`, `init`, `status`, `add`, `build`,
  `update`, `sync`, `query`, `reindex`, and `lint`.
- It contains hidden plugin command groups under `wiki plugin ...`.
- Existing tests import `curator.cli.app` and private helpers including
  `_maybe_auto_export`, `_filter_sync_structural_issues`,
  `_parse_persona_done_response`, and `_run_curator_persona_wizard`.

## Docs And Spec Invariants

- `SYSTEM_BEHAVIOR.md` documents human CLI commands and hidden plugin command
  behavior.
- `PLUGIN_SCHEMA.md` lists the hidden `wiki plugin ...` command namespace.
- `MCP_USER_GUIDE.md` documents `wiki mcp install` and MCP startup expectations.

## Alternatives And Tradeoffs

- Keep one file: lowest short-term risk, but fails the CM-1 goal.
- Split by command group with facades: best balance of low behavior risk and
  reviewability.
- Split by lower-level service domain: rejected for this milestone because it
  would mix transport refactor with service redesign.

## Final Decision

Create `curator.commands` as the internal package. Keep `curator.cli` as the
entrypoint and compatibility export module. Move command handlers by command
group only after characterization tests lock the command tree.

Each extracted command group module must instantiate its own isolated
`typer.Typer()` object and decorate commands against that local object. The root
facade (`curator.cli`) is the only place that constructs the top-level CLI tree:
it imports sub-app objects from command modules and wires them with
`app.add_typer()` in the existing order.

Do not create a centralized app registry module that owns all sub-app objects
and then imports command modules for side-effect registration. That shape creates
a cyclic dependency: the registry imports command modules, while command modules
must import the registry's app objects for decorators.

## Pseudocode

```python
# curator/commands/sources.py
source_app = typer.Typer(...)

@source_app.command("ls")
def list_sources(...): ...

# curator/cli.py
app = typer.Typer(...)
from .commands.sources import source_app
app.add_typer(source_app, name="source")
from .commands.helpers import _ok, _err, _warn, _resolve_root_or_die
from .commands.syncing import _maybe_auto_export, _filter_sync_structural_issues
```

## Required Characterization

- Assert root command/group names and hidden groups are unchanged.
- Assert selected help text remains stable for:
  `wiki --help`, `wiki db autosync --help`, `wiki plugin source register --help`,
  `wiki mcp install --help`.
- Assert direct imports from `curator.cli` keep working.
