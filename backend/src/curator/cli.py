"""Command-line interface for incurator."""

from __future__ import annotations

import typer

from .commands import common as _common
from .commands import config as _config_commands
from .commands import core as _core
from .commands import db as _db_commands
from .commands import devices as _devices_commands
from .commands import inspect as _inspect_commands
from .commands import insights as _insight_commands
from .commands import jobs as _jobs_commands
from .commands import mcp as _mcp_commands
from .commands import model_stack as _model_stack_commands
from .commands import persona as _persona_commands
from .commands import plugin as _plugin_commands
from .commands import prompts as _prompt_commands
from .commands import sources as _source_commands
from .commands import workspace as _workspace_commands
from .commands.config import config_app
from .commands.db import db_app
from .commands.devices import devices_app
from .commands.inspect import inspect_app
from .commands.insights import insight_app
from .commands.jobs import jobs_app
from .commands.mcp import mcp_app
from .commands.model_stack import models_app
from .commands.persona import persona_app
from .commands.plugin import plugin_app
from .commands.prompts import prompt_app
from .commands.sources import source_app
from .commands.workspace import testbed_app, workspace_app

app = typer.Typer(
    name="wiki",
    help="incurator — an AI-maintained personal knowledge base.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)

register_core_commands = _core.register_core_commands
reset = _core.reset
version = _core.version
init = _core.init
status = _core.status
migrate_vault = _core.migrate_vault
add = _core.add
build = _core.build
update = _core.update
sync = _core.sync
query = _core.query
reindex = _core.reindex
lint = _core.lint

for _name in _common.__all__:
    globals()[_name] = getattr(_common, _name)

for _module in (
    _config_commands,
    _core,
    _db_commands,
    _devices_commands,
    _inspect_commands,
    _insight_commands,
    _jobs_commands,
    _mcp_commands,
    _model_stack_commands,
    _persona_commands,
    _plugin_commands,
    _prompt_commands,
    _source_commands,
    _workspace_commands,
):
    for _name, _value in vars(_module).items():
        if not _name.startswith("__") and _name not in globals():
            globals()[_name] = _value

register_core_commands(app)
app.add_typer(source_app, name="source")
app.add_typer(inspect_app, name="inspect")
app.add_typer(workspace_app, name="workspace")
app.add_typer(config_app, name="config")
app.add_typer(persona_app, name="persona")
app.add_typer(testbed_app, name="testbed", hidden=True)
app.add_typer(jobs_app, name="jobs", hidden=True)
app.add_typer(plugin_app, name="plugin", hidden=True)
app.add_typer(devices_app, name="devices", hidden=True)
app.add_typer(db_app, name="db")
app.add_typer(models_app, name="models", hidden=True)
app.add_typer(prompt_app, name="prompt")
app.add_typer(insight_app, name="insight")
app.add_typer(mcp_app, name="mcp", hidden=True)


def main() -> None:
    """Entry point used by the `wiki` console script."""
    app()


if __name__ == "__main__":
    main()
