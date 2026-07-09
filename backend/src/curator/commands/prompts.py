# ruff: noqa: F403,F405
# mypy: disable-error-code=name-defined
"""Prompts commands for the `wiki` CLI."""

from __future__ import annotations

from .common import *

prompt_app = typer.Typer(
    name="prompt",
    help="Inspect the v0.3.1 prompt registry, contracts, traces, and evals.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)

@prompt_app.command("list")
def prompt_list(family: str = typer.Option("", help="Filter by family.")) -> None:
    """List registered prompt contracts."""
    from .. import prompting
    contracts = prompting.REGISTRY.list(family=family or None)
    for c in contracts:
        console.print(f"[cyan]{c.prompt_id}[/cyan]@{c.version}  [dim]{c.family}/{c.role}[/dim]  {c.purpose}")
    console.print(f"\n[dim]{len(contracts)} prompt(s)[/dim]")


@prompt_app.command("show")
def prompt_show(prompt_id: str) -> None:
    """Show one prompt contract's templates and validators."""
    from .. import prompting
    try:
        c = prompting.REGISTRY.get(prompt_id)
    except KeyError:
        console.print(f"[red]Unknown prompt:[/red] {prompt_id}")
        raise typer.Exit(1)
    console.print(f"[bold]{c.prompt_id}@{c.version}[/bold] ({c.family}/{c.role})")
    console.print(f"purpose: {c.purpose}")
    console.print(f"validators: {', '.join(c.validators) or '(none)'}")
    console.print(f"output_model: {c.output_model.__name__ if c.output_model else '(text)'}")
    console.print(f"\n[dim]--- system ---[/dim]\n{c.system_template}")
    console.print(f"\n[dim]--- user ---[/dim]\n{c.user_template}")


@prompt_app.command("trace")
def prompt_trace(trace_id: str) -> None:
    """Show a recorded prompt run (PTR-…)."""
    paths = _resolve_root_or_die()
    run = db.get_prompt_run(paths.state_db, trace_id)
    if run is None:
        console.print(f"[red]Unknown prompt trace:[/red] {trace_id}")
        raise typer.Exit(1)
    for k, v in run.items():
        console.print(f"[cyan]{k}[/cyan]: {v}")


@prompt_app.command("eval")
def prompt_eval() -> None:
    """Run the offline prompt-eval fixtures (no LLM)."""
    from ..prompting import evals
    outcomes = evals.run_all()
    passed = sum(1 for o in outcomes if o.passed)
    for o in outcomes:
        mark = "[green]PASS[/green]" if o.passed else "[red]FAIL[/red]"
        console.print(f"{mark} {o.case.name}")
    console.print(f"\n[dim]{passed}/{len(outcomes)} eval fixtures passed[/dim]")
    if passed != len(outcomes):
        raise typer.Exit(1)

