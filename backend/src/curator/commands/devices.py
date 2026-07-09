# ruff: noqa: F403,F405
# mypy: disable-error-code=name-defined
"""Devices commands for the `wiki` CLI."""

from __future__ import annotations

from .common import *

devices_app = typer.Typer(
    name="devices",
    help="Inspect synced device profiles and per-device backend launchers.",
    hidden=True,
    no_args_is_help=False,
    add_completion=False,
    rich_markup_mode="rich",
)

@devices_app.command("sync")
def devices_sync(
    syncthing_config: Optional[Path] = typer.Option(
        None,
        "--syncthing-config",
        help="Path to Syncthing config.xml. Defaults to standard platform locations.",
    ),
    backend_command: Optional[str] = typer.Option(
        None,
        "--backend-command",
        help="Per-device command used by Obsidian/MCP to start Incurator.",
    ),
    backend_args: Optional[str] = typer.Option(
        None,
        "--backend-args",
        help="Per-device backend args as JSON array or shell-like text.",
    ),
) -> None:
    """Refresh `.curator/devices.json` from Syncthing and local backend info."""
    from .. import device_registry

    paths = _resolve_root_or_die()
    registry = device_registry.sync_device_registry(
        paths.root,
        syncthing_config=syncthing_config,
        backend_command=backend_command,
        backend_args=device_registry.parse_args_text(backend_args),
    )
    path = device_registry.registry_path(paths.root)
    _ok(f"Device registry updated: [bold]{path}[/bold]")
    local_id = registry.get("local_device_id", "local")
    local = registry.get("devices", {}).get(local_id, {})
    backend = local.get("backend", {})
    console.print(f"Local device: [bold]{local.get('name', local_id)}[/bold]")
    console.print(f"Backend: [cyan]{backend.get('command', 'wiki')} {' '.join(backend.get('args', []))}[/cyan]")


@devices_app.command("status")
def devices_status() -> None:
    """Show synced devices and known per-device backend launchers."""
    from .. import device_registry

    paths = _resolve_root_or_die()
    registry = device_registry.load_registry(paths.root)
    devices = registry.get("devices", {})
    if not devices:
        _warn("No device registry yet.")
        _hint("Run [bold]wiki devices sync[/bold] inside the synced vault.")
        return

    local_id = registry.get("local_device_id") or device_registry.infer_registry_local_device_id(devices)
    table = Table(title="Synced Devices", show_header=True, box=None, padding=(0, 1))
    table.add_column("local")
    table.add_column("name")
    table.add_column("system")
    table.add_column("backend command")
    table.add_column("backend args")
    table.add_column("updated", justify="right")
    for device_id, device in sorted(devices.items(), key=lambda item: str(item[1].get("name", item[0]))):
        backend = device.get("backend") or {}
        platform_info = device.get("platform") or {}
        args = backend.get("args") or []
        table.add_row(
            "yes" if device_id == local_id else "",
            str(device.get("name") or device_id[:12]),
            str(platform_info.get("system") or ""),
            str(backend.get("command") or ""),
            " ".join(str(arg) for arg in args),
            str(device.get("updated_at") or ""),
        )
    console.print(table)


@devices_app.callback(invoke_without_command=True)
def devices_default(ctx: typer.Context) -> None:
    """Show device status when `wiki devices` is run without a subcommand."""
    if ctx.invoked_subcommand is None:
        devices_status()

