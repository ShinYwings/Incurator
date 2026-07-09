# ruff: noqa: F403,F405
# mypy: disable-error-code=name-defined
"""Inspect commands for the `wiki` CLI."""

from __future__ import annotations

from .common import *

inspect_app = typer.Typer(
    name="inspect",
    help="Inspect synthesis, report, and answer evidence chains.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)

@inspect_app.command("synthesis")
def inspect_synthesis(
    synthesis_id: str,
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Inspect one L4 synthesis node's L4-to-L1 evidence chain."""
    from ..inspection import synthesis_audit

    paths = _resolve_root_or_die()
    audit = synthesis_audit.build_synthesis_audit(paths.state_db, synthesis_id)
    if json_output:
        _print_json(audit)
    else:
        _print_audit_summary(audit)


@inspect_app.command("report")
def inspect_report(
    report_id: str,
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Inspect one L3 community report's source support."""
    from ..inspection import synthesis_audit

    paths = _resolve_root_or_die()
    audit = synthesis_audit.build_report_audit(paths.state_db, report_id)
    if json_output:
        _print_json(audit)
    else:
        _print_audit_summary(audit)


@inspect_app.command("answer")
def inspect_answer(
    trace_id: str,
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Inspect one persisted query answer trace."""
    from ..inspection import synthesis_audit

    paths = _resolve_root_or_die()
    audit = synthesis_audit.build_answer_audit(paths.state_db, trace_id)
    if json_output:
        _print_json(audit)
    else:
        _print_audit_summary(audit)

