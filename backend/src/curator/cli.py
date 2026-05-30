"""Command-line interface for incurator.

Stage 1 commands:
    wiki init [PATH]         Scaffold a new wiki project.
    wiki status              Show the current wiki's stats and config.
    wiki version             Show version.

Stage 2 commands:
    wiki add <path> [-r]     Copy a file or folder into raw/, parse, track.
    wiki sources list        List all tracked sources.
    wiki sources show <id>   Show details for one source (with text preview).
    wiki sources rm <id>     Remove a source from tracking.

Later stages add: ingest, query, sync, serve.
"""

from __future__ import annotations
from . import constants as consts

import json
import hashlib
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import __version__
from . import config as cfg
from . import constants as consts
from . import db
from . import ingest_llm
from . import ingest_raw
from . import lint as lint_module
from . import page_writer
from . import query as query_module
from . import search
from .workspace.provisioner import (
    CurateTemplateData,
    VALID_AGENTS,
    default_project_name,
    detect_workspace_scenario,
    make_integration_copy_prompt,
    make_rule_integration_prompt,
    prepare_workspace,
    render_mcp_snippet,
    top_level_target,
)
from .llm import (
    LLMError,
    ClaudeCodeError,
    detect_ram_gb,
    has_enough_ram_for_local,
    FailoverClient,
    GeminiCliError,
    ModelNotFound,
    OllamaNotRunning,
    _cli_installed,
    build_client,
    describe_backend,
    list_models_on_host,
    list_ollama_models_with_vision,
    make_client_by_key,
)

app = typer.Typer(
    name="wiki",
    help="incurator — an AI-maintained personal knowledge base.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)

sources_app = typer.Typer(
    name="sources",
    help="Manage tracked source files in raw/.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)
app.add_typer(sources_app, name="sources")

workspace_app = typer.Typer(
    name="workspace",
    help="Manage workspace curate.yml Knowledge Requirement Specifications.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)
app.add_typer(workspace_app, name="workspace")

config_app = typer.Typer(
    name="config",
    help="Configure the LLM provider and Ollama models.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)
app.add_typer(config_app, name="config")

persona_app = typer.Typer(help="Manage the Curator and Artist personas.")
app.add_typer(persona_app, name="persona")

config_models_app = typer.Typer(
    name="models",
    help="Discover and select Ollama models (local or remote).",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)
config_app.add_typer(config_models_app, name="models")

testbed_app = typer.Typer(
    name="testbed",
    help="[Dev Only] Manage development testbed environments and scenarios.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)
app.add_typer(testbed_app, name="testbed")

benchmark_app = typer.Typer(
    name="benchmark",
    help="[Dev Only] Cross-model quality and performance benchmarks.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)
app.add_typer(benchmark_app, name="benchmark")

jobs_app = typer.Typer(
    name="jobs",
    help="Inspect and run queued background ingest jobs.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)
app.add_typer(jobs_app, name="jobs")

devices_app = typer.Typer(
    name="devices",
    help="Inspect synced device profiles and per-device backend launchers.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)
app.add_typer(devices_app, name="devices")

console = Console()


# ---------------------------------------------------------------------------
# Recommended model catalogue
# ---------------------------------------------------------------------------

_RECOMMENDED_MODELS = [
    {
        "tag": "deepseek-r1:32b",
        "size": "32B",
        "why": "[Logical Extraction & Assembly] Verifies complex logical structures and technical derivations. Currently the strongest local model for assembling knowledge into a DAG format.",
        "tip": "Highly recommended as the primary model for daily information analysis and summarization.",
        "vision": False,
    },
    {
        "tag": "gemma4:31b",
        "size": "31B",
        "why": "[Visual Knowledge Extraction & Synthesis] Perfectly matches diagrams with text. Extracts metadata from documents containing visual information while preserving the context of images.",
        "tip": "Optimized for analyzing sources with visual data.",
        "vision": True,
    },
    {
        "tag": "qwen3.6:35b",
        "size": "35B",
        "why": "[#1 in Structuring & Directory Assembly] Outstanding at reassembling extracted knowledge into QMD, JSON, or Markdown tables. Flawless at creating hierarchical directory tree structures.",
        "tip": "Ideal for large-scale text synthesis and formatting tasks.",
        "vision": False,
    },
    {
        "tag": "mistral-small3.1:24b",
        "size": "24B",
        "why": "[Information Densification & Filtering] Filters noise from massive source chunks and assembles only the core insights. Synthesizes the pipeline's key structure concisely and clearly.",
        "tip": "Highly efficient for text summarization; fits in 12GB VRAM.",
        "vision": False,
    },
    {
        "tag": "gemma4:26b",
        "size": "26B",
        "why": "[Large-Scale Parallel Synthesis] Quickly reads similar concepts from multiple sources, removes duplicates, and integrates them into a single knowledge base. Great for assembling Unified Vault info into a single note.",
        "tip": "Efficient for tasks involving simultaneous synthesis of multiple knowledge sources.",
        "vision": True,
    },
    {
        "tag": "internlm2:20b",
        "size": "20B",
        "why": "[Long-Context Consistency] Excels when searching through complex narratives spanning dozens of pages. Maintains context definitions while passing information to agents.",
        "tip": "Best for summarizing entire textbooks or long documents in one go.",
        "vision": False,
    },
    {
        "tag": "phi4:14b",
        "size": "14B",
        "why": "[Structural Preprocessing & Correction] Exceptional at logical structure recognition despite its smaller size. Serves as a great intermediate filter by correcting and organizing fragile structured data and formulas.",
        "tip": "Optimal for lightning-fast preprocessing of simple documents.",
        "vision": False,
    },
    {
        "tag": consts.DEFAULT_OLLAMA_MODEL,
        "size": "7B",
        "why": "[Fast Logical Validation] Quickly verifies that individual paragraphs retrieved via RAG are not contradictory. Acts as a high-speed defensive worker to prevent agents from acting on incorrect information.",
        "tip": "Best for conflict detection and consistency checks.",
        "vision": False,
    },
    {
        "tag": "llama3.2-vision:11b",
        "size": "11B",
        "why": "[Visual Data Specialist] A vision-focused agent that decomposes camera calibration images or graphs in papers into searchable text and attributes for the RAG system.",
        "tip": "Useful for quickly summarizing purely visual information into text.",
        "vision": True,
    },
    {
        "tag": "deepseek-r1:8b",
        "size": "8B",
        "why": "[Simple Structuring & Classification] Best for lightweight tasks like automating the organization of simple text or bibliographic info from RAG into defined directory structures.",
        "tip": "Recommended for lightweight file classification and sorting.",
        "vision": False,
    },
]


def _show_recommended_models(host: str) -> None:
    """Print the curated model recommendation table with live install status."""
    from rich.table import Table as RichTable

    installed_raw = list_models_on_host(host, timeout=3.0)
    installed_lower = {m.lower() for m in installed_raw}

    def _is_installed(tag: str) -> bool:
        def normalize(s: str) -> str:
            return s.lower().replace("-", "")

        tag_lower = tag.lower()
        tag_norm = normalize(tag_lower)
        base = tag_lower.split(":")[0]
        rec_version = tag_lower.split(":")[1] if ":" in tag_lower else "latest"

        for m in installed_lower:
            m_lower = m.lower()
            if m_lower == tag_lower or m_lower.startswith(tag_lower) or normalize(m_lower) == tag_norm:
                return True
            
            m_base = m_lower.split(":")[0]
            m_version = m_lower.split(":")[1] if ":" in m_lower else "latest"
            if normalize(m_base) == normalize(base) and m_version == rec_version:
                return True
        return False

    table = RichTable(
        show_header=True,
        box=None,
        padding=(0, 1),
        header_style="bold dim",
        show_lines=False,
    )
    table.add_column("Model Tag",       style="cyan",    min_width=22, no_wrap=True)
    table.add_column("Size",            style="yellow",  min_width=14, no_wrap=True)
    table.add_column("Description",     min_width=60, max_width=85)
    table.add_column("Installed",       style="green",   min_width=4,  no_wrap=True, justify="center")

    for m in _RECOMMENDED_MODELS:
        vision_badge = " [magenta]👁[/magenta]" if m["vision"] else ""
        installed_mark = "✓" if _is_installed(m["tag"]) else ""
        desc = f"{m['why']} [dim]({m['tip']})[/dim]"
        table.add_row(
            m["tag"] + vision_badge,
            m["size"],
            desc,
            installed_mark,
        )

    console.print()
    console.print("[bold]Recommended Models[/bold]  [dim](👁 = Vision support / ✓ = Installed in Ollama)[/dim]")
    console.print(table)
    console.print(
        "[dim]Use: [bold]wiki config models use <tag>[/bold]  "
        "·  Re-run [bold]wiki add[/bold] after changing models[/dim]"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hint(text: str) -> None:
    """Print a one-liner tip in a subdued style."""
    console.print(f"[dim]💡 {text}[/dim]")


def _err(text: str) -> None:
    console.print(f"[bold red]✗[/bold red] {text}")


def _ok(text: str) -> None:
    console.print(f"[bold green]✓[/bold green] {text}")


def _warn(text: str) -> None:
    console.print(f"[bold yellow]![/bold yellow] {text}")


def _refresh_qmd_index(paths: cfg.WikiPaths, *, embed: bool = True) -> None:
    """Run `qmd update` (and optionally `qmd embed`) for this project.

    Friendly: emits hints instead of raising when qmd isn't built or fails;
    callers (sync/ingest/lint --fix) are non-fatal — the source of truth is
    on disk regardless.
    """
    if not search.is_available():
        bin_path = search.get_qmd_binary()
        if bin_path and not bin_path.exists():
            _hint(
                "qmd binary not found. Install it globally via npm: "
                "[bold]npm install -g @tobilu/qmd[/bold]"
            )
        else:
            _hint(
                "qmd binary present but not responding. "
                "Try `qmd --version` to diagnose."
            )
        return
    try:
        console.print("[dim]Updating qmd index…[/dim]")
        search.update_index(paths, embed=embed)
        _ok("qmd index updated")
    except search.SearchBackendError as e:
        _warn(f"qmd index update failed: {e}")
        _hint("Search is now stale; rerun later with `wiki reindex`.")


def _resolve_root_or_die(hint_path: Path | None = None) -> cfg.WikiPaths:
    """Find the wiki project root from hint_path, cwd, or VAULT_ROOT env var."""
    import os
    env_root = os.environ.get("VAULT_ROOT")
    if env_root:
        root_path = Path(env_root).resolve()
        if (root_path / consts.INTERNAL_DIR / consts.CONFIG_FILE).exists():
            # Don't persist testbed vaults to global last_root
            try:
                import yaml as _yaml
                _d = _yaml.safe_load(
                    (root_path / consts.INTERNAL_DIR / consts.CONFIG_FILE).read_text(encoding="utf-8")
                ) or {}
                if not _d.get("testbed", False):
                    cfg.set_last_root(root_path)
            except Exception:
                cfg.set_last_root(root_path)
            return cfg.paths_from_config(root_path)

    # Discovery starts from hint_path if provided, else CWD
    root = cfg.find_wiki_root(start=hint_path)
    
    # Fallback to last_root is ONLY allowed if NO hint_path was provided
    # (e.g. running a global command from a neutral directory)
    if root is None and hint_path is None:
        last_root = cfg.get_last_root()
        if last_root and (last_root / consts.INTERNAL_DIR / consts.CONFIG_FILE).exists():
            import yaml as _yaml
            try:
                _cfg_data = _yaml.safe_load(
                    (last_root / consts.INTERNAL_DIR / consts.CONFIG_FILE).read_text(encoding="utf-8")
                ) or {}
            except Exception:
                _cfg_data = {}
            if not _cfg_data.get("testbed", False):
                return cfg.paths_from_config(last_root)

    if root is None:
        _err("Not inside an incurator project.")
        if hint_path:
            _err(f"No vault root found upward from: [bold]{hint_path}[/bold]")
        _hint("Run [bold]wiki init[/bold] to create one, or set VAULT_ROOT env var.")
        raise typer.Exit(code=1)

    cfg.set_last_root(root)
    return cfg.paths_from_config(root)


def _sync_mcp_configs(vault_root: Path) -> list[str]:
    """Upsert VAULT_ROOT into known MCP config files. Returns list of updated paths."""
    import json
    entry = {
        "command": "wiki",
        "args": ["mcp"],
        "env": {"VAULT_ROOT": str(vault_root)},
    }
    targets = [
        Path.home() / ".gemini" / "settings.json",
        Path.home() / ".gemini" / consts.CLOUD_ANTIGRAVITY / "mcp_config.json",
        vault_root / ".claude" / "settings.json",
    ]
    updated = []
    for config_path in targets:
        try:
            data: dict = {}
            if config_path.exists():
                data = json.loads(config_path.read_text(encoding="utf-8")) or {}
            data.setdefault("mcpServers", {})["incurator"] = entry
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            updated.append(str(config_path))
        except Exception:
            pass
    return updated


def _format_bytes(n: int) -> str:
    """Human-readable byte count: 1234 → '1.2 KB'."""
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    if n < 1024 * 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    return f"{n / (1024 * 1024 * 1024):.2f} GB"


def _status_style(status: str) -> str:
    return {
        "pending": "yellow",
        "force_pending": "yellow",
        "curated": "green",
        "error": "red",
        "skipped": "dim",
    }.get(status, "white")


def _node_id_from_collection_page(relpath: str) -> str:
    return Path(relpath).stem


def _sync_blocked_node_ids(report: lint_module.LintReport) -> set[str]:
    blocked: set[str] = set()
    for issue in report.errors + report.warnings:
        if not issue.page.startswith((f"{consts.LAYER_L1}/", f"{consts.LAYER_L2}/", f"{consts.LAYER_L3}/", f"{consts.LAYER_L4}/")):
            continue
        if lint_module.is_safe_fixable(issue):
            continue
        blocked.add(_node_id_from_collection_page(issue.page))
    return blocked


def _render_sync_preflight_summary(report: lint_module.LintReport) -> None:
    needs_review = report.needs_review
    blocked = _sync_blocked_node_ids(report)

    table = Table(title="Sync Preflight", show_header=False, box=None, padding=(0, 2))
    table.add_column(style="dim", width=22)
    table.add_column()
    table.add_row("safe-fixable", str(len(report.safe_fixable)))
    table.add_row("needs-review", str(len(needs_review)))
    table.add_row("blocked logical checks", str(len(blocked)))
    console.print(table)

    if needs_review and console.is_interactive:
        show = typer.confirm("Sync report has review items. Show details?", default=True)
        if show:
            for issue in needs_review[:20]:
                console.print(
                    f"  [yellow]•[/yellow] [{issue.severity.value}] "
                    f"[cyan]{issue.page}[/cyan]: {issue.message}"
                )
            if len(needs_review) > 20:
                console.print(f"  [dim]...and {len(needs_review) - 20} more[/dim]")


def _latest_sync_report_path(paths: cfg.WikiPaths) -> Path:
    return paths.internal / "sync-report.json"


def _gap_to_dict(gap) -> dict:
    return {
        "layer": getattr(gap, "layer", ""),
        "node_id": getattr(gap, "node_id", ""),
        "message": getattr(gap, "message", ""),
        "reasoning": getattr(gap, "reasoning", ""),
    }


def _write_latest_sync_report(
    paths: cfg.WikiPaths,
    *,
    reason: str,
    structural_report: lint_module.LintReport,
    structural_gaps: list,
    logic_gaps: list,
    fixed: int = 0,
    rebuilt: int = 0,
    health: str | None = None,
) -> None:
    remaining = len(structural_gaps) + len(logic_gaps) + len(structural_report.needs_review)
    if health is None:
        health = "fixed" if fixed or rebuilt else ("review_needed" if remaining else "clean")
    payload = {
        "generated_at": ingest_llm._now_iso(),
        "reason": reason,
        "health": health,
        "safe_fixed": fixed,
        "rebuilt_downstream": rebuilt,
        "safe_fixable": len(structural_report.safe_fixable),
        "needs_review": len(structural_report.needs_review),
        "blocked_logical_checks": len(_sync_blocked_node_ids(structural_report)),
        "equivalence_candidates": [],
        "structural_gaps": [_gap_to_dict(g) for g in structural_gaps],
        "logical_gaps": [_gap_to_dict(g) for g in logic_gaps],
        "structural_issues": [
            {
                "severity": issue.severity.value,
                "check": issue.check.value,
                "page": issue.page,
                "message": issue.message,
                "fixable": issue.fixable,
            }
            for issue in (structural_report.errors + structural_report.warnings)
        ],
    }
    try:
        paths.internal.mkdir(parents=True, exist_ok=True)
        _latest_sync_report_path(paths).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass


def _load_latest_sync_report(paths: cfg.WikiPaths) -> dict | None:
    report_path = _latest_sync_report_path(paths)
    if not report_path.exists():
        return None
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _invalidate_latest_sync_report(paths: cfg.WikiPaths, *, reason: str) -> None:
    payload = {
        "generated_at": ingest_llm._now_iso(),
        "reason": reason,
        "health": "stale",
        "invalidated": True,
        "safe_fixed": 0,
        "safe_fixable": 0,
        "needs_review": 0,
        "blocked_logical_checks": 0,
        "equivalence_candidates": [],
        "structural_gaps": [],
        "logical_gaps": [],
        "structural_issues": [],
    }
    try:
        paths.internal.mkdir(parents=True, exist_ok=True)
        _latest_sync_report_path(paths).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass


def _render_latest_sync_report_summary(paths: cfg.WikiPaths) -> None:
    payload = _load_latest_sync_report(paths)
    if not payload:
        return
    logical = payload.get("logical_gaps") or []
    structural = payload.get("structural_gaps") or []
    structural_issues = payload.get("structural_issues") or []
    total_review = int(payload.get("needs_review") or 0)
    safe_fixed = int(payload.get("safe_fixed") or 0)
    rebuilt = int(payload.get("rebuilt_downstream") or 0)
    blocked = int(payload.get("blocked_logical_checks") or 0)
    equivalence = payload.get("equivalence_candidates") or []

    table = Table(title="Latest Sync Report", show_header=False, box=None, padding=(0, 2))
    table.add_column(style="dim", width=22)
    table.add_column()
    table.add_row("generated", str(payload.get("generated_at") or "?"))
    table.add_row("health", str(payload.get("health") or "?"))
    table.add_row("reason", str(payload.get("reason") or "sync"))
    if payload.get("invalidated"):
        table.add_row("state", "stale; rerun wiki sync for current logical report")
    table.add_row("logical gaps", str(len(logical)))
    table.add_row("structural gaps", str(len(structural)))
    table.add_row("equivalence candidates", str(len(equivalence)))
    table.add_row("needs-review", str(total_review))
    table.add_row("safe-fixed", str(safe_fixed))
    table.add_row("rebuilt downstream", str(rebuilt))
    table.add_row("blocked logical checks", str(blocked))
    console.print(table)

    has_details = bool(logical or structural or structural_issues)
    if has_details and console.is_interactive:
        show = typer.confirm("Sync report has details. Show them now?", default=False)
        if show:
            for gap in (structural + logical)[:20]:
                console.print(
                    f"  [yellow]•[/yellow] [{gap.get('layer', '?')}] "
                    f"[bold]{gap.get('node_id', '?')}[/bold]: {gap.get('message', '')}"
                )
                if gap.get("reasoning"):
                    console.print(f"    [dim]{gap['reasoning']}[/dim]")
            for issue in structural_issues[:20]:
                console.print(
                    f"  [yellow]•[/yellow] [{issue.get('severity', '?')}] "
                    f"[cyan]{issue.get('page', '?')}[/cyan]: {issue.get('message', '')}"
                )


def _layer_status_counts(paths: cfg.WikiPaths) -> dict[str, dict[str, int]]:
    counts = {layer: {} for layer in ("l1", "l2", "l3", "l4")}
    if not paths.state_db.exists():
        return counts
    with db.connect(paths.state_db) as conn:
        for layer in counts:
            rows = conn.execute(
                f"SELECT {layer}_status AS status, COUNT(*) AS n "
                f"FROM sources GROUP BY {layer}_status"
            ).fetchall()
            counts[layer] = {str(row["status"] or "unknown"): int(row["n"]) for row in rows}
    return counts


def _render_pipeline_status(paths: cfg.WikiPaths) -> None:
    counts = _layer_status_counts(paths)
    if not any(counts[layer] for layer in counts):
        return
    table = Table(title="Pipeline Layer Status", show_header=True, header_style="bold")
    table.add_column("Layer")
    table.add_column("done", justify="right", style="green")
    table.add_column("pending", justify="right", style="yellow")
    table.add_column("error", justify="right", style="red")
    table.add_column("skipped", justify="right", style="dim")
    for label, layer in (("L1", "l1"), ("L2", "l2"), ("L3", "l3"), ("L4", "l4")):
        row = counts[layer]
        table.add_row(
            label,
            str(row.get("done", 0)),
            str(row.get("pending", 0) + row.get("force_pending", 0) + row.get("running", 0)),
            str(row.get("error", 0)),
            str(row.get("skipped", 0)),
        )
    console.print(table)


def _run_sync_report_only(paths: cfg.WikiPaths, config: dict, *, reason: str) -> None:
    """Run the default sync repair loop after add/curate/query."""
    from . import sync as sync_module

    class CliSyncCallbacks(sync_module.SyncCallbacks):
        def on_node_check(self, node_id: str):
            console.print(f"  [dim]Verifying {node_id}...[/dim]", end="\r")

        def on_node_repair(self, node_id: str, rebuilt_count: int = 0):
            # Clear the progress line and show repair
            console.print(" " * 60, end="\r")
            console.print(f"  [green]✓[/green] [bold]{node_id}[/bold] repaired.")

    cb = CliSyncCallbacks()

    console.print(f"[dim]Running sync repair after {reason}...[/dim]")
    change_report = sync_module.scan_for_changes(paths)
    dirty_pages = change_report.modified + change_report.new
    dirty_node_ids = [Path(ref).stem for ref in dirty_pages]

    console.print("[dim]Step 1: Structural verification...[/dim]")
    structural_gaps = sync_module.run_mode_a(paths, callbacks=cb)
    console.print(" " * 60, end="\r")

    console.print("[dim]Step 2: Health checks (lint)...[/dim]")
    structural_report = lint_module.run_lint(paths, deep=False, client=None, progress_callback=cb.on_node_check)

    client = None
    logic_gaps = []
    repaired = 0
    rebuilt = 0
    try:
        client = _start_client(config)
        llm_fixed = lint_module.apply_llm_fixes(
            paths,
            structural_report.issues,
            client,
            progress_callback=cb.on_node_check,
            limit_to=dirty_pages,
        )
        if llm_fixed:
            structural_report = lint_module.run_lint(paths, deep=False, client=None, progress_callback=cb.on_node_check)
        fixed_count = lint_module.apply_fixes(paths, structural_report.issues)
        structural_gap_fixed = sync_module.repair_structural_gaps(paths, structural_gaps)
        nested_fixed = sync_module.repair_nested_frontmatter(paths)
        repaired += llm_fixed + fixed_count + structural_gap_fixed + nested_fixed
        if repaired:
            structural_report = lint_module.run_lint(paths, deep=False, client=None, progress_callback=cb.on_node_check)
            structural_report.auto_fixed = repaired
            structural_gaps = sync_module.run_mode_a(paths, callbacks=cb)
        deep_report = lint_module.run_lint(
            paths,
            deep=True,
            client=client,
            progress_callback=cb.on_node_check,
            limit_to=dirty_pages,
        )
        structural_report.issues.extend(
            issue for issue in deep_report.issues if issue not in structural_report.issues
        )
        blocked_node_ids = _sync_blocked_node_ids(structural_report)
        console.print("[dim]Step 3: Logical verification via LLM...[/dim]")
        logic_gaps, repair = sync_module.repair_logical_gaps(
            paths,
            client,
            blocked_node_ids=blocked_node_ids,
            target_node_ids=dirty_node_ids,
            max_iterations=2,
            callbacks=cb,
        )
        console.print(" " * 60, end="\r")
        repaired += repair.fixed
        rebuilt += repair.rebuilt_downstream
    except Exception as e:
        _warn(f"Sync logical verification unavailable: {e}")
    finally:
        if client is not None:
            client.close()

    structural_issues = structural_report.errors + structural_report.warnings
    blocked_node_ids = _sync_blocked_node_ids(structural_report)
    _write_latest_sync_report(
        paths,
        reason=reason,
        structural_report=structural_report,
        structural_gaps=structural_gaps,
        logic_gaps=logic_gaps,
        fixed=repaired,
        rebuilt=rebuilt,
    )

    total_gaps = len(structural_gaps) + len(logic_gaps)
    if structural_issues:
        _warn(f"{len(structural_issues)} structural issue(s) found by sync preflight.")
    if blocked_node_ids:
        _warn(f"{len(blocked_node_ids)} node(s) blocked from logical checks by structural review items.")
    if total_gaps:
        _mark_layer_status_from_sync_gaps(paths, structural_gaps + logic_gaps)
        _warn(f"{total_gaps} verification gap(s) remain after sync repair.")
        for gap in (structural_gaps + logic_gaps)[:10]:
            console.print(f"  [yellow]•[/yellow] [{gap.layer}] [bold]{gap.node_id}[/bold]: {gap.message}")
            if gap.reasoning:
                console.print(f"    [dim]{gap.reasoning}[/dim]")
        if total_gaps > 10:
            console.print(f"  [dim]...and {total_gaps - 10} more[/dim]")
    elif not structural_issues:
        _mark_clean_sync_status(paths)
        if repaired or rebuilt:
            _ok(f"Sync repaired {repaired} issue(s), rebuilt {rebuilt} downstream page(s), and is now clean.")
        else:
            _ok("Sync clean.")


def _mark_layer_status_from_sync_gaps(paths: cfg.WikiPaths, gaps: list) -> None:
    """Reflect logical sync gaps in per-source layer status for resumable runs."""
    concept_gaps = [g for g in gaps if getattr(g, "layer", "") == consts.TYPE_L3]
    exhibition_gaps = [g for g in gaps if getattr(g, "layer", "") == consts.TYPE_L4]
    if not concept_gaps and not exhibition_gaps:
        return

    if concept_gaps:
        with db.connect(paths.state_db) as conn:
            rows = conn.execute(
                "SELECT id FROM sources WHERE l2_status = 'done' ORDER BY id ASC"
            ).fetchall()
        source_ids = [int(row["id"]) for row in rows]
        if source_ids:
            reason = "sync_logical_gap:" + ",".join(g.node_id for g in concept_gaps[:5])
            db.set_sources_layer_status(paths.state_db, source_ids, "l3", "error", error=reason)
            db.set_sources_layer_status(paths.state_db, source_ids, "l4", "pending")
    if exhibition_gaps:
        with db.connect(paths.state_db) as conn:
            rows = conn.execute(
                "SELECT id FROM sources WHERE l3_status = 'done' ORDER BY id ASC"
            ).fetchall()
        source_ids = [int(row["id"]) for row in rows]
        if source_ids:
            reason = "sync_logical_gap:" + ",".join(g.node_id for g in exhibition_gaps[:5])
            db.set_sources_layer_status(paths.state_db, source_ids, "l4", "error", error=reason)


def _mark_clean_sync_status(paths: cfg.WikiPaths) -> None:
    """Clear stale layer errors once sync has verified the current graph."""
    with db.connect(paths.state_db) as conn:
        l2_done = [
            int(row["id"])
            for row in conn.execute("SELECT id FROM sources WHERE l2_status = 'done'").fetchall()
        ]
        l3_done = [
            int(row["id"])
            for row in conn.execute("SELECT id FROM sources WHERE l3_status = 'done'").fetchall()
        ]
    if l2_done and paths.concepts.exists() and any(paths.concepts.glob(f"{consts.PREFIX_L3}-*.md")):
        db.set_sources_layer_status(paths.state_db, l2_done, "l3", "done")
    if l3_done and paths.exhibitions.exists() and any(paths.exhibitions.glob(f"{consts.PREFIX_L4}-*.md")):
        db.set_sources_layer_status(paths.state_db, l3_done, "l4", "done")


def _resolve_curate_workspace(explicit: Path | None) -> Path | None:
    if explicit is not None:
        return explicit.expanduser().resolve()

    import os

    env_workspace = os.environ.get("WORKSPACE_PATH")
    if env_workspace:
        return Path(env_workspace).expanduser().resolve()

    cwd = Path.cwd().resolve()
    for candidate in (cwd, *cwd.parents):
        if (candidate / consts.FILE_CURATE_YML).exists():
            return candidate
    return None


def _curate_spec_hash(workspace: Path | None) -> str:
    if workspace is None:
        return ""
    curate_file = workspace / consts.FILE_CURATE_YML
    if not curate_file.exists():
        return ""
    return hashlib.sha256(curate_file.read_bytes()).hexdigest()[:12]


def _find_workspace_exhibition(paths: cfg.WikiPaths, project: str, spec_hash: str) -> Path | None:
    if not paths.exhibitions.exists() or not project or not spec_hash:
        return None
    for md_path in sorted(paths.exhibitions.glob(f"{consts.PREFIX_L4}-*.md")):
        parsed = page_writer.read_page(md_path)
        if not parsed:
            continue
        if (
            parsed.frontmatter.get("workspace") == project
            and parsed.frontmatter.get("curate_spec_hash") == spec_hash
            and not parsed.frontmatter.get("superseded_by")
        ):
            return md_path
    return None


# ---------------------------------------------------------------------------
# Stage 1 commands
# ---------------------------------------------------------------------------

_VALID_CLOUD = ()

def _build_curated_ollama() -> list[tuple[str, str]]:
    """Load Ollama recommended models from models.json."""
    from curator.models import load_models_catalogue
    data = load_models_catalogue()
    result = []
    for model in data.get("providers", {}).get(consts.BACKEND_OLLAMA, {}).get("models", []):
        mid = model.get("id", "")
        label = model.get("label", mid)
        vram = model.get("vram_gb")
        vision = " · vision" if model.get("supports_vision") else ""
        think = " · thinking" if model.get("supports_thinking") else ""
        vram_str = f" · ~{vram} GB VRAM" if vram else ""
        desc = f"{label}{vram_str}{vision}{think}"
        result.append((mid, desc))
    return result


# Curated Ollama model list: (model_name, description) — sourced from models.json
_CURATED_MODELS = _build_curated_ollama()


def _build_cloud_models() -> dict[str, list[dict]]:
    """Build the cloud model table from models.json (single source of truth)."""
    from curator.models import load_models_catalogue

    _PROVIDER_CFG_KEYS = {
        consts.CLOUD_ANTIGRAVITY: {
            "cfg_key": "model",
            "backend": consts.BACKEND_ANTIGRAVITY_CLI,
        },
        consts.CLOUD_CLAUDE: {
            "cfg_key": "model",
            "backend": consts.BACKEND_CLAUDE_CODE,
        },
        consts.CLOUD_OPENAI: {
            "cfg_key": "model",
            "backend": consts.BACKEND_CODEX_CLI,
        },
    }

    data = load_models_catalogue()
    result: dict[str, list[dict]] = {}

    for provider, info in data.get("providers", {}).items():
        cfg = _PROVIDER_CFG_KEYS.get(provider)
        if not cfg:
            continue
        backend = cfg["backend"]
        entries = []
        for model in info.get("models", []):
            mid = model.get("id", "")
            if not mid:
                continue
            entries.append({
                "tag": mid,
                "desc": model.get("label", mid),
                "cfg_key": cfg["cfg_key"],
            })
        if entries:
            result[backend] = entries

    return result


_CLOUD_MODELS: dict[str, list[dict]] = _build_cloud_models()



def _show_cloud_models(cloud_provider: str, llm_cfg: dict, active_only: bool = False) -> bool:
    """Print a Rich table of curated cloud models for the given provider.
    Returns True if any models were actually shown.
    """
    from rich.table import Table as RichTable

    models = _CLOUD_MODELS.get(cloud_provider)
    if not models:
        _err(f"Unknown cloud provider '{cloud_provider}'. Use: antigravity-cli, claude-code, codex-cli.")
        return

    # Determine currently active model tags from primary/fallback values
    active_tags: set[str] = set()
    for slot in ("primary", "fallback"):
        p, m = cfg.split_provider_model(llm_cfg.get(slot, ""))
        if p == cloud_provider and m:
            active_tags.add(m)

    table = RichTable(
        show_header=True,
        box=None,
        padding=(0, 1),
        header_style="bold dim",
        show_lines=False,
    )
    table.add_column("Model Tag", style="cyan",   min_width=26, no_wrap=True)
    table.add_column("Description",                min_width=30, max_width=44, no_wrap=True)
    table.add_column("✓",         style="green",  min_width=2,  justify="center", no_wrap=True)

    shown_tags = set()
    any_shown = False
    for m in models:
        # Flexible match: exact or version-prefixed
        active_mark = ""
        for tag in active_tags:
            if m["tag"] == tag or (tag and tag.startswith(m["tag"])):
                active_mark = "✓"
                break
        
        # In active_only mode, we used to 'continue' here, but the user wants to see 
        # the full list for the primary provider. We now show ALL models for the 
        # requested provider, but the caller will skip OTHER providers.
        any_shown = True
        if active_mark:
            shown_tags.add(m["tag"])
        
        table.add_row(m["tag"], m["desc"], active_mark)

    # If active_only and some active tags weren't in our curated list, show them anyway
    if active_only:
        for tag in active_tags:
            if tag and tag not in shown_tags:
                table.add_row(tag, "[dim]custom[/dim]", "[dim]User-defined model[/dim]", "✓")
                any_shown = True

    if active_only and not any_shown:
        return False

    console.print(
        f"[bold]{cloud_provider.capitalize()} Models[/bold]  "
        "[dim](Active ✓ = Currently configured model)[/dim]"
    )
    console.print(table)
    console.print(
        "[dim]Update: [bold]wiki config models use <tag>[/bold]  "
        "·  Re-run [bold]wiki add[/bold] after changing models[/dim]"
    )
    return True


def _pick_cloud_model(cloud_provider: str, llm_cfg: dict) -> tuple[str, str]:
    """Interactive picker for cloud provider models. Returns (model_tag, '') — cfg_key unused."""
    models = _CLOUD_MODELS.get(cloud_provider, [])
    if not models:
        _err(f"Unknown cloud provider '{cloud_provider}'.")
        raise typer.Exit(code=1)

    console.print()
    for i, m in enumerate(models, 1):
        console.print(f"  [cyan]{i}[/cyan]  {m['tag']}  [dim]— {m['desc']}[/dim]")
    console.print("  [dim]0[/dim]  custom model name")
    console.print()

    # Default: first non-thinking model, or first overall
    default_entry = models[0]
    default_idx = models.index(default_entry) + 1

    while True:
        raw = typer.prompt(
            f"Select model (1–{len(models)}, or 0 for custom)",
            default=str(default_idx),
        ).strip()
        if raw == "0":
            tag = typer.prompt("Model tag", default=default_entry["tag"]).strip() or default_entry["tag"]
            return tag, ""
        try:
            idx = int(raw)
            if 1 <= idx <= len(models):
                return models[idx - 1]["tag"], ""
        except ValueError:
            if raw:
                tag_map = {m["tag"]: m for m in models}
                return (raw if raw in tag_map else raw), ""
        console.print(f"[red]Enter a number between 0 and {len(models)}.[/red]")


def _pick_ollama_model(host: str) -> str:
    """Show model picker. Tries live discovery first, falls back to curated list."""
    console.print()
    console.print(f"[dim]Connecting to Ollama at {host} …[/dim]")
    live_models = list_models_on_host(host, timeout=3.0)
    live_set = set(live_models)

    if live_models:
        console.print(f"[dim green]Found {len(live_models)} model(s) installed on this host.[/dim green]")
    else:
        console.print("[dim yellow]Ollama not reachable — showing curated model list.[/dim yellow]")

    # Build a merged option list: curated first (with Installed badge for local ones),
    # then any locally-installed models not in the curated list.
    curated_names = [m["tag"] for m in _RECOMMENDED_MODELS]
    extra_live = [m for m in live_models if m not in curated_names]
    options = curated_names + extra_live

    _curated_desc = {m["tag"]: f"{m['size']} · {m['tip']}" for m in _RECOMMENDED_MODELS}
    console.print()
    for i, m in enumerate(options, 1):
        desc = _curated_desc.get(m, "")
        badge = "  [bold green][Installed][/bold green]" if m in live_set else ""
        desc_str = f"  [dim]— {desc}[/dim]" if desc else ""
        console.print(f"  [cyan]{i}[/cyan]  {m}{desc_str}{badge}")
    console.print("  [dim]0[/dim]  custom model name")
    console.print()

    default_model = consts.DEFAULT_OLLAMA_MODEL
    # Prefer the first installed model as default if deepseek is not installed
    if live_models and default_model not in live_set:
        default_model = live_models[0]
    default_idx = next(
        (i + 1 for i, m in enumerate(options) if m == default_model), None
    )
    prompt_hint = f"  (1–{len(options)}, or 0 for custom)"
    if default_idx:
        prompt_hint += f"  [default {default_idx}={default_model}]"

    while True:
        raw = typer.prompt(f"Select model{prompt_hint}", default=str(default_idx or "0")).strip()
        if raw == "0":
            custom = typer.prompt("Model name", default=default_model).strip()
            return custom or default_model
        try:
            idx = int(raw)
            if 1 <= idx <= len(options):
                return options[idx - 1]
        except ValueError:
            # Maybe they typed a model name directly
            if raw:
                return raw
        console.print(f"[red]Enter a number between 0 and {len(options)}.[/red]")




def _print_backend_menu(exclude: str | None = None) -> None:
    """Print the backend menu, optionally skipping one entry."""
    _claude_ok = _cli_installed(consts.CLOUD_CLAUDE)
    _agy_ok = _cli_installed("agy")
    _codex_ok = _cli_installed("codex")
    n = 1
    for key, label in [
        (consts.BACKEND_OLLAMA,        "Local Ollama      (GPU/CPU — local)"),
        (consts.BACKEND_CLAUDE_CODE,   f"Claude Code CLI   (claude Pro/Max — "
                          f"{'[green]installed[/green]' if _claude_ok else '[yellow]not installed[/yellow]'})"),
        (consts.BACKEND_ANTIGRAVITY_CLI, f"Antigravity CLI   (Google — "
                            f"{'[green]installed[/green]' if _agy_ok else '[yellow]not installed[/yellow]'})"),
        (consts.BACKEND_CODEX_CLI,     f"Codex CLI         (OpenAI — "
                          f"{'[green]installed[/green]' if _codex_ok else '[yellow]not installed[/yellow]'})"),
    ]:
        if key == exclude:
            continue
        console.print(f"  [cyan]{n}[/cyan]  {label}")
        n += 1
    console.print()


def _pick_backend_menu(exclude: str | None = None, prompt: str = "Choice") -> str:
    """Show backend menu and return the chosen backend key."""
    _print_backend_menu(exclude)
    keys = [k for k in (consts.BACKEND_OLLAMA, consts.BACKEND_CLAUDE_CODE, consts.BACKEND_ANTIGRAVITY_CLI, consts.BACKEND_CODEX_CLI) if k != exclude]
    valid: dict[str, str] = {}
    for i, k in enumerate(keys, 1):
        valid[str(i)] = k
        valid[k] = k

    while True:
        raw = typer.prompt(f"{prompt} (1–{len(keys)})", default="1").strip().lower()
        if raw in valid:
            return valid[raw]
        console.print(f"[red]Enter 1–{len(keys)}.[/red]")


def _install_ollama_binary() -> bool:
    """Install the Ollama binary if not present. Returns True if now available."""
    import subprocess as _sp
    import sys

    if _cli_installed(consts.BACKEND_OLLAMA):
        return True

    _warn("Ollama is not installed.")
    if not typer.confirm("Install Ollama now?", default=True):
        _hint("Install manually: [bold]https://ollama.com/download[/bold]")
        return False

    if sys.platform.startswith("linux"):
        console.print("[dim]Running: curl -fsSL https://ollama.com/install.sh | sh[/dim]")
        res = _sp.run("curl -fsSL https://ollama.com/install.sh | sh", shell=True)
    elif sys.platform == "darwin":
        if _cli_installed("brew"):
            console.print("[dim]Running: brew install ollama[/dim]")
            res = _sp.run(["brew", "install", consts.BACKEND_OLLAMA])
        else:
            _hint("Install Homebrew first (https://brew.sh) or download Ollama from https://ollama.com/download")
            return False
    else:
        _hint("Download Ollama from: [bold]https://ollama.com/download[/bold]")
        return False

    if res.returncode == 0 and _cli_installed(consts.BACKEND_OLLAMA):
        _ok("Ollama installed.")
        return True

    _warn("Ollama install failed. Try manually: https://ollama.com/download")
    return False


def _ensure_ollama_running(host: str) -> bool:
    """Ensure Ollama is installed and running. Returns True if ready."""
    import subprocess as _sp
    import time

    if list_models_on_host(host, timeout=2.0) is not None:
        return True  # already up

    if not _cli_installed(consts.BACKEND_OLLAMA):
        if not _install_ollama_binary():
            return False

    _warn(f"Ollama not running at {host}.")
    if not typer.confirm("Start Ollama now? (ollama serve)", default=True):
        return False

    console.print("[dim]Starting Ollama in background…[/dim]")
    _sp.Popen(
        [consts.BACKEND_OLLAMA, "serve"],
        stdout=_sp.DEVNULL,
        stderr=_sp.DEVNULL,
        start_new_session=True,
    )
    for i in range(10):
        time.sleep(1)
        console.print(f"[dim]  waiting… ({i+1}s)[/dim]", end="\r")
        if list_models_on_host(host, timeout=1.0):
            console.print()
            _ok("Ollama is ready.")
            return True
    console.print()
    _warn("Ollama did not respond in 10 s. It may still be starting.")
    return False


def _ensure_npm(install_cmd: str) -> bool:
    """Ensure npm is available; auto-installs Node via NVM into user space if needed."""
    import shutil
    import subprocess as _sp
    import os
    from pathlib import Path

    # 1. First check if any NVM Node bin already exists, and activate it
    nvm_dir = Path.home() / ".nvm"
    node_base = nvm_dir / "versions" / "node"
    if node_base.exists():
        for d in sorted(node_base.iterdir(), reverse=True):
            if d.is_dir() and (d / "bin" / "npm").exists():
                bin_dir = str(d / "bin")
                if bin_dir not in os.environ.get("PATH", ""):
                    os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
                return True

    # 2. Check if there is an existing user-space npm on PATH (e.g. from nvm/n/etc)
    npm_path = shutil.which("npm")
    if npm_path and str(Path(npm_path).resolve()).startswith(str(Path.home())):
        return True

    # 3. If NVM doesn't exist at all, download & install NVM
    nvm_sh = nvm_dir / "nvm.sh"
    if not nvm_sh.exists():
        console.print("[dim]NVM not found. Installing NVM…[/dim]")
        try:
            _sp.run("curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash", shell=True, check=False)
        except Exception:
            pass

    # 4. If NVM exists but no node installed, install Node via NVM
    if nvm_sh.exists():
        console.print("[dim]Installing Node LTS via NVM…[/dim]")
        _sp.run(f"bash -c 'source {nvm_sh} && nvm install --lts'", shell=True, check=False)

        # Look for new bin path again
        if node_base.exists():
            for d in sorted(node_base.iterdir(), reverse=True):
                if d.is_dir() and (d / "bin" / "npm").exists():
                    bin_dir = str(d / "bin")
                    if bin_dir not in os.environ.get("PATH", ""):
                        os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
                    return True

    _warn("Could not set up NVM/Node. Install Node manually and retry.")
    return False


def _configure_backend(
    backend: str,
    overrides: dict,
) -> None:
    """Prompt for backend-specific settings, merge into overrides, and offer install."""
    """Prompt for backend-specific settings, merge into overrides, and offer install."""
    import subprocess as _sp

    if backend == consts.BACKEND_OLLAMA:
        host = typer.prompt("Ollama host", default="http://localhost:11434").strip()
        overrides.setdefault(consts.BACKEND_OLLAMA, {})["host"] = host
        _ensure_ollama_running(host)
        model = _pick_ollama_model(host)
        overrides["_pending_model"] = model
        # Offer to pull if model is missing
        live = list_models_on_host(host, timeout=3.0)
        if live:
            tag = model.split(":")[0]
            if not any(m == model or m.startswith(tag) for m in live):
                console.print()
                _warn(f"Model '{model}' is not pulled yet.")
                if typer.confirm(f"Pull it now? (ollama pull {model})", default=True):
                    console.print(f"[dim]Running: ollama pull {model}[/dim]")
                    res = _sp.run([consts.BACKEND_OLLAMA, "pull", model])
                    if res.returncode == 0:
                        _ok(f"Model '{model}' pulled.")
                    else:
                        _warn(f"Pull failed. Run manually: ollama pull {model}")
            else:
                _ok(f"Model '{model}' is available.")
        else:
            _hint(f"Once Ollama is running: [bold]ollama pull {model}[/bold]")


    elif backend in (consts.BACKEND_CLAUDE_CODE, consts.BACKEND_ANTIGRAVITY_CLI, consts.BACKEND_CODEX_CLI):
        _CLI_INFO = {
            consts.BACKEND_CLAUDE_CODE:     ("claude",  "npm install -g @anthropic-ai/claude-code"),
            consts.BACKEND_ANTIGRAVITY_CLI: ("agy",     "curl -fsSL https://antigravity.google/cli/install.sh | bash"),
            consts.BACKEND_CODEX_CLI:       ("codex",   "npm install -g @openai/codex"),
        }
        cli_cmd, install_cmd = _CLI_INFO[backend]
        if not _cli_installed(cli_cmd):
            console.print()
            _warn(f"'{cli_cmd}' CLI is not installed.")
            if _ensure_npm(install_cmd):
                if typer.confirm(f"Install now? ({install_cmd})", default=True):
                    import shutil
                    from pathlib import Path
                    npm_path = shutil.which("npm")
                    if not npm_path:
                        _nvm_dir = Path.home() / ".nvm" / "versions" / "node"
                        if _nvm_dir.exists():
                            for _d in sorted(_nvm_dir.iterdir(), reverse=True):
                                if _d.is_dir() and (_d / "bin" / "npm").exists():
                                    npm_path = str(_d / "bin" / "npm")
                                    break

                    pkg_name = (
                        install_cmd.rsplit(" ", 1)[-1]
                        if install_cmd.startswith("npm install -g ")
                        else ""
                    )
                    if npm_path and pkg_name:
                        console.print(f"[dim]Running: {npm_path} install -g {pkg_name}[/dim]")
                        res = _sp.run([npm_path, "install", "-g", pkg_name])
                    else:
                        console.print(f"[dim]Running: {install_cmd}[/dim]")
                        res = _sp.run(install_cmd, shell=True)

                    if res.returncode == 0:
                        _ok(f"'{cli_cmd}' installed.")
                        console.print(f"[bold green]Launching '{cli_cmd}' to authenticate...[/bold green]")
                        try:
                            # Run the installed CLI command interactively so the user can directly log in/authenticate
                            _sp.run([cli_cmd], check=False)
                        except Exception:
                            pass
                    else:
                        _warn(f"Install failed. Run manually: {install_cmd}")
        else:
            _ok(f"'{cli_cmd}' CLI found.")

        # Offer model selection
        console.print()
        console.print(f"[bold]{backend} Model Selection[/bold]")
        sel_model, _ = _pick_cloud_model(backend, overrides)
        if sel_model:
            overrides["_pending_model"] = sel_model


def _run_init_wizard() -> dict:
    """Run interactive LLM setup wizard. Returns dict of llm config overrides."""
    overrides: dict = {}

    console.print()
    console.print("[bold cyan]LLM Setup Wizard[/bold cyan]")
    console.print("[dim]Press Enter to accept the default shown in parentheses.[/dim]")
    console.print()

    # Step 1: Primary backend
    console.print("Which do you [bold]primarily[/bold] use for LLM inference?")
    primary = _pick_backend_menu(prompt="Primary backend")
    overrides: dict = {}

    # Step 2: Configure the primary backend (model selected inside)
    console.print(f"[dim]--- {primary} (primary) ---[/dim]")
    _configure_backend(primary, overrides)
    model = overrides.pop("_pending_model", "")
    overrides["primary"] = cfg.join_provider_model(primary, model)

    # Step 3: Fallback backend
    console.print()
    if typer.confirm("Set up automatic fallback?", default=True):
        console.print()
        console.print("Fallback backend:")
        fallback = _pick_backend_menu(exclude=primary, prompt="Fallback")
        console.print(f"[dim]--- {fallback} (fallback) ---[/dim]")
        _configure_backend(fallback, overrides)
        fb_model = overrides.pop("_pending_model", "")
        overrides["fallback"] = cfg.join_provider_model(fallback, fb_model)
    else:
        overrides["fallback"] = ""

    return overrides


def _run_curator_persona_wizard(client, current_persona: dict | None = None, recent_domains: list[str] | None = None) -> dict | None:
    """Multi-turn LLM interview to build/refine the Curator persona. Returns persona dict or None (skipped)."""
    from .prompts import build_persona_interview_messages, PERSONA_INTERVIEW_CURATOR_OPENER
    import json as _json
    import re as _re

    opener = PERSONA_INTERVIEW_CURATOR_OPENER
    # When refining an existing persona, show context to the LLM and user
    context_prefix = ""
    if current_persona:
        context_prefix = f"Current persona: {_json.dumps(current_persona, ensure_ascii=False)}\n"
        if recent_domains:
            context_prefix += f"Recently ingested domains: {', '.join(recent_domains)}\n"
        context_prefix += "Based on the above, I'll ask whether you'd like to refine anything.\n\n"

    opener_with_context = context_prefix + opener
    history: list[dict] = [{"role": "assistant", "content": opener_with_context}]
    typer.echo("\n" + opener_with_context)

    for _ in range(12):
        user_input = typer.prompt("You").strip()
        if not user_input:
            continue
        history.append({"role": "user", "content": user_input})
        messages = build_persona_interview_messages(history, is_workspace=False)
        try:
            content: str = client.chat(messages)
        except Exception as exc:
            typer.echo(f"[LLM error] {exc}")
            break

        history.append({"role": "assistant", "content": content})

        json_match = _re.search(r'\{.*\}', content, _re.DOTALL)
        if json_match:
            try:
                parsed = _json.loads(json_match.group())
                if parsed.get("done"):
                    persona = parsed.get("persona")
                    if persona is None:
                        typer.echo("Skipping persona setup.")
                        return None
                    return persona
            except _json.JSONDecodeError:
                pass

        typer.echo(f"\nCurator: {content}\n")

    typer.echo("Persona interview ended. Using default STEM persona.")
    return None


def _maybe_auto_evolve_curator_persona(
    paths: "cfg.WikiPaths",
    config: dict,
    client,
    new_domains: list[str],
) -> None:
    """Silently update Curator persona if new_domains are outside its current scope.

    Makes a single non-interactive LLM call. Updates config.yml in-place.
    Failures are silently swallowed — never blocks wiki add.
    """
    if not new_domains:
        return
    current_persona = config.get("persona", {})
    if not current_persona:
        return

    import json as _json
    import re as _re

    prompt = (
        "You are a knowledge-base configuration assistant.\n\n"
        "Below is a Curator persona (vault-wide knowledge profile) and domains "
        "observed in a recent ingestion run.\n\n"
        f"Current persona:\n{_json.dumps(current_persona, ensure_ascii=False)}\n\n"
        f"Newly observed domains: {', '.join(new_domains)}\n\n"
        "If these domains are already well-covered by the current persona, return exactly: null\n\n"
        "If the persona should evolve to better reflect these domains (while staying true "
        "to the vault's core identity), return ONLY an updated JSON object with the SAME "
        "schema as the current persona. Update the area, text, knowledge_artifacts, "
        "verification_philosophy, or disambiguation_keywords fields as appropriate. "
        "Do not change confidence thresholds or exhibition_intent unless clearly needed.\n\n"
        "Return only valid JSON — no prose, no code fences. Either null or the updated JSON."
    )
    try:
        from .llm import ChatMessage
        raw = client.chat([ChatMessage(role="user", content=prompt)], temperature=0.2)
        raw_stripped = _re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
        if raw_stripped.lower() in ("null", ""):
            return
        updated = _json.loads(raw_stripped)
        if not isinstance(updated, dict):
            return
        import datetime
        updated["updated_at"] = datetime.datetime.now().isoformat()
        config["persona"] = updated
        cfg.save_config(paths, config)
        console.print("[dim]  · Curator persona quietly updated with new domain context.[/dim]")
    except Exception:
        pass


def _run_artist_persona_wizard(client, project: str) -> dict | None:
    """Multi-turn LLM interview to build an Artist persona. Returns persona dict or None (skipped)."""
    from .prompts import build_persona_interview_messages, PERSONA_INTERVIEW_ARTIST_OPENER
    import json as _json
    import re as _re

    opener = PERSONA_INTERVIEW_ARTIST_OPENER.format(project=project)
    typer.echo("\n" + opener)

    # Opener is display-only — not in history.  History starts with the first
    # LLM-generated question so there are no consecutive assistant messages.
    history: list[dict] = []

    # Ask Q1 immediately without waiting for user acknowledgment
    messages = build_persona_interview_messages(history, is_workspace=True, project=project)
    try:
        first_q: str = client.chat(messages)
    except Exception as exc:
        typer.echo(f"[LLM error] {exc}")
        return None
    history.append({"role": "assistant", "content": first_q})
    typer.echo(f"\nCurator: {first_q}\n")

    for _ in range(12):
        user_input = typer.prompt("You").strip()
        if not user_input:
            continue
        history.append({"role": "user", "content": user_input})
        messages = build_persona_interview_messages(history, is_workspace=True, project=project)
        try:
            content: str = client.chat(messages)
        except Exception as exc:
            typer.echo(f"[LLM error] {exc}")
            break

        history.append({"role": "assistant", "content": content})

        json_match = _re.search(r'\{.*\}', content, _re.DOTALL)
        if json_match:
            try:
                parsed = _json.loads(json_match.group())
                if parsed.get("done"):
                    persona = parsed.get("persona")
                    if persona is None:
                        typer.echo("Skipping persona setup.")
                        return None
                    return persona
            except _json.JSONDecodeError:
                pass

        typer.echo(f"\nCurator: {content}\n")

    typer.echo("Persona interview ended. Artist persona not set.")
    return None


def _offer_install(overrides: dict, llm_cfg: dict) -> None:
    """After wizard, offer to install CLI tools and/or pull Ollama models."""
    import subprocess

    primary = overrides.get("primary") or llm_cfg.get("primary", "")
    model   = overrides.get("model")   or llm_cfg.get("model", consts.DEFAULT_OLLAMA_MODEL)
    host    = overrides.get("host")    or llm_cfg.get("host", consts.DEFAULT_OLLAMA_HOST)

    if primary in (consts.BACKEND_CLAUDE_CODE, consts.BACKEND_ANTIGRAVITY_CLI):
        cli_cmd = consts.CLOUD_CLAUDE if primary == consts.BACKEND_CLAUDE_CODE else "agy"
        install_cmd = (
            "npm install -g @anthropic-ai/claude-code"
            if primary == consts.BACKEND_CLAUDE_CODE
            else "curl -fsSL https://antigravity.google/cli/install.sh | bash"
        )
        if not _cli_installed(cli_cmd):
            console.print()
            console.print(f"[yellow]'{cli_cmd}' is not installed.[/yellow]")
            if _ensure_npm(install_cmd):
                if typer.confirm(f"Install now? ({install_cmd})", default=True):
                    import shutil
                    from pathlib import Path
                    npm_path = shutil.which("npm")
                    if not npm_path:
                        _nvm_dir = Path.home() / ".nvm" / "versions" / "node"
                        if _nvm_dir.exists():
                            for _d in sorted(_nvm_dir.iterdir(), reverse=True):
                                if _d.is_dir() and (_d / "bin" / "npm").exists():
                                    npm_path = str(_d / "bin" / "npm")
                                    break

                    pkg_name = (
                        install_cmd.rsplit(" ", 1)[-1]
                        if install_cmd.startswith("npm install -g ")
                        else ""
                    )
                    if npm_path and pkg_name:
                        console.print(f"[dim]Running: {npm_path} install -g {pkg_name}[/dim]")
                        res = subprocess.run([npm_path, "install", "-g", pkg_name])
                    else:
                        console.print(f"[dim]Running: {install_cmd}[/dim]")
                        res = subprocess.run(install_cmd, shell=True)

                    if res.returncode == 0:
                        _ok(f"'{cli_cmd}' installed.")
                    else:
                        _warn(f"Install failed. Run manually: {install_cmd}")

    # Ollama model pull (only when the wizard explicitly picked a model)
    if overrides.get("model") and model:
        live = list_models_on_host(host, timeout=3.0)
        if live:
            tag = model.split(":")[0]
            if not any(m == model or m.startswith(tag) for m in live):
                console.print()
                console.print(f"[yellow]Model '{model}' not found locally on {host}.[/yellow]")
                if typer.confirm(f"Pull it now? (ollama pull {model})", default=True):
                    console.print(f"[dim]Running: ollama pull {model}[/dim]")
                    res = subprocess.run([consts.BACKEND_OLLAMA, "pull", model])
                    if res.returncode == 0:
                        _ok(f"Model '{model}' pulled.")
                    else:
                        _warn(f"Pull failed. Run manually: ollama pull {model}")
            else:
                _ok(f"Model '{model}' already available.")
        else:
            console.print()
            _hint(
                f"Ollama not reachable at {host}. "
                f"After starting it run: [bold]ollama pull {model}[/bold]"
            )


_ALL_LLM_ERRORS = (
    OllamaNotRunning, ModelNotFound,
    ClaudeCodeError, GeminiCliError,
    LLMError,
)


def _start_client_inner(config: dict):
    """Build and verify the LLM client.

    - Tries the primary backend first.
    - On ModelNotFound: offers `ollama pull <model>` and retries.
    - On any other failure: if a fallback is configured, asks the user
      whether to use it. The FailoverClient returned afterwards handles
      automatic mid-session switching during actual inference calls.
    """
    import subprocess as _sp

    llm_cfg = config.get("llm", {})
    primary = llm_cfg.get("primary", "")
    fallback = llm_cfg.get("fallback", "")

    # If no explicit primary, fall back to full auto build (legacy mode).
    if not primary:
        client = build_client(config)
        client.ensure_ready()
        return client

    # --- Try primary ---
    p_client = make_client_by_key(primary, config)
    try:
        p_client.ensure_ready()
        # Primary OK.
        # If an explicit fallback is configured, build the full FailoverClient;
        # otherwise return p_client directly to avoid eagerly constructing cloud
        # clients that may require API keys the user hasn't set.
        if fallback:
            return build_client(config)
        return p_client
    except ModelNotFound as e:
        _err(str(e))
        model_name = llm_cfg.get("model", consts.DEFAULT_OLLAMA_MODEL)
        if typer.confirm(f"Pull model now? (ollama pull {model_name})", default=True):
            console.print(f"[dim]Running: ollama pull {model_name}[/dim]")
            res = _sp.run([consts.BACKEND_OLLAMA, "pull", model_name])
            if res.returncode == 0:
                _ok(f"Model '{model_name}' pulled. Retrying…")
                try:
                    p_client.ensure_ready()
                    return p_client if not fallback else build_client(config)
                except Exception:
                    pass  # fall through to fallback logic
            else:
                _warn(f"Pull failed. Run manually: ollama pull {model_name}")
    except _ALL_LLM_ERRORS as e:
        _err(str(e))

    # --- Primary failed, try fallback ---
    if not fallback:
        raise typer.Exit(code=1)

    console.print()
    if not typer.confirm(
        f"Primary ([bold]{primary}[/bold]) is not available. "
        f"Use fallback ([bold]{fallback}[/bold])?",
        default=True,
    ):
        raise typer.Exit(code=1)

    f_client = make_client_by_key(fallback, config)
    try:
        f_client.ensure_ready()
        _ok(f"Using fallback: [bold]{fallback}[/bold]")
        return f_client
    except _ALL_LLM_ERRORS as e:
        _err(f"Fallback also failed: {e}")
        raise typer.Exit(code=1)


def _start_client(config: dict):
    client = _start_client_inner(config)

    if isinstance(client, FailoverClient):
        chain = " → ".join(type(p).__name__.replace("Client", "") for p in client.providers)
        active = type(client.active_provider).__name__.replace("Client", "")
        provider_label = f"{active} [dim]({chain})[/dim]"
    else:
        provider_label = type(client).__name__.replace("Client", "")

    _ok(f"LLM ready · [bold]{provider_label}[/bold] (model: {client.model})")
    return client


def _instant_l1_enabled(config: dict) -> bool:
    return bool((config or {}).get("llm", {}).get("instant_l1", True))



@app.command()
def version() -> None:
    """Show the incurator version."""
    console.print(f"incurator [bold cyan]{__version__}[/bold cyan]")
@app.command()
def init(
    vault_path: str = typer.Argument(
        ...,
        help="Path to the vault root (where 02_Wiki, 03_Notes, etc. live).",
    ),
    raw_dirs: list[str] = typer.Option(
        [consts.DIR_WIKI, consts.DIR_NOTES, consts.DIR_RESOURCES, consts.DIR_ARCHIVES],
        "--raw",
        "-r",
        help="Source directories to monitor (relative to vault root). Repeatable.",
    ),
    interactive: bool = typer.Option(
        True,
        "--interactive/--no-interactive",
        help="Run interactive LLM setup wizard (default: on). Use --no-interactive for CI/scripting.",
    ),
) -> None:
    """Initialise a Curator project inside an Obsidian vault.

    If the directory already exists (or is an existing Obsidian vault), only
    missing topology directories and .curator/ files are created — nothing is
    overwritten.

    Creates:
      .obsidian/                 — Obsidian vault marker (created if absent)
      00_System/ … 06_Archives/ — Vault topology (created if absent)
      .curator/config.yml        — project configuration
      .curator/state.sqlite      — tracking database
      .curator/Collections/      — 01_Contexts/ 02_Atoms/ 03_Concepts/ 04_Exhibitions/
      .curator/overview.md       — domain manifest
      .curator/index.md          — DAG routing table
      .curator/log.md            — ingest log
      .curator/ledger.md         — override ledger
    """
    import shutil

    import os
    root = Path(vault_path).resolve()

    # Create vault root if it doesn't exist yet
    if not root.exists():
        try:
            root.mkdir(parents=True)
        except (OSError, PermissionError) as e:
            _err(f"Cannot create vault root '{root}': {e}")
            raise typer.Exit(code=1) from e
        _ok(f"Created vault root: {root}")
    elif root.is_file():
        _err(f"Path '{root}' is a file, not a directory.")
        raise typer.Exit(code=1)
    elif not os.access(root, os.W_OK):
        _err(f"No write permission on '{root}'. Check directory permissions.")
        raise typer.Exit(code=1)

    # Guarantee this is an Obsidian vault (.obsidian/ is the vault marker)
    obsidian_dir = root / ".obsidian"
    if not obsidian_dir.exists():
        obsidian_dir.mkdir()
        _ok("Created Obsidian vault marker: .obsidian/")

    # Auto-install Obsidian plugin if available in the source tree
    plugin_src = Path(__file__).resolve().parents[3] / "plugin"
    if plugin_src.exists():
        plugin_dest = obsidian_dir / "plugins" / "incurator-obsidian-agent"
        plugin_dest.mkdir(parents=True, exist_ok=True)

        build_plugin = False
        if interactive:
            build_plugin = typer.confirm("Build and install the Obsidian plugin for this vault?", default=True)
        else:
            build_plugin = True

        if build_plugin:
            import subprocess
            import os
            console.print("[dim]Building Obsidian plugin via npm... (this may take a moment)[/dim]")
            try:
                # Force OBSIDIAN_PLUGIN_DIR to empty so esbuild.config.mjs outputs to
                # plugin_src/main.js instead of the vault. dotenv reads from .env directly
                # (bypassing subprocess env), so we must set it to "" rather than just pop it.
                build_env = dict(os.environ)
                build_env["OBSIDIAN_PLUGIN_DIR"] = ""
                subprocess.run(["npm", "install"], cwd=str(plugin_src), check=True, capture_output=True, env=build_env)
                subprocess.run(["npm", "run", "build"], cwd=str(plugin_src), check=True, capture_output=True, env=build_env)
                _ok("Obsidian plugin built successfully.")
            except subprocess.CalledProcessError as e:
                err_msg = e.stderr.decode("utf-8", errors="replace").strip() if e.stderr else ""
                _warn(f"Failed to build Obsidian plugin. npm exit code {e.returncode}.\n[dim]{err_msg}[/dim]")
            except FileNotFoundError:
                _warn("npm command not found. Cannot build Obsidian plugin.")

        copied_any = False
        for fname in ["main.js", "manifest.json", "styles.css"]:
            src_file = plugin_src / fname
            if src_file.exists():
                shutil.copy2(src_file, plugin_dest / fname)
                copied_any = True
        if copied_any:
            _ok(f"Installed Obsidian plugin to {plugin_dest.relative_to(root)}")

    paths = cfg.WikiPaths(
        root=root,
        raw_dirs_override=raw_dirs,
    )
    already_initialized = paths.is_initialized()

    # Always ensure the vault topology exists (idempotent, never overwrites)
    created_dirs: list[str] = []
    for d in cfg.VAULT_TOPOLOGY:
        target = root / d
        if not target.exists():
            target.mkdir(parents=True, exist_ok=True)
            created_dirs.append(d)

    if already_initialized:
        cfg.set_last_root(root)
        console.print()
        console.print(f"[dim cyan]Curator already initialised at {root}[/dim cyan]")
        if created_dirs:
            console.print("[dim]Created missing vault directories:[/dim]")
            for d in created_dirs:
                _ok(d)
        else:
            console.print("[dim]Vault topology is complete — nothing to create.[/dim]")
        console.print()
        _hint("Run [bold]wiki status[/bold] to review current state.")
        raise typer.Exit(code=0)

    console.print()
    console.print(
        Panel.fit(
            f"[bold cyan]Initialising incurator[/bold cyan]\n"
            f"[dim]{root}[/dim]",
            border_style="cyan",
        )
    )

    # 1. Build config
    config = dict(cfg.DEFAULT_CONFIG)
    config["paths"] = {
        "raw_dirs": raw_dirs,
        "collections_dir": cfg.DEFAULT_COLLECTIONS_DIR,
    }
    # Cloud provider + API keys
    llm = dict(config.get("llm", {}))

    if not interactive:
        # --no-interactive with no flags: skip provider setup entirely
        _hint("LLM provider not configured. Run [bold]wiki config provider[/bold] to set it up.")
    else:
        # Interactive mode: ask user how they want to configure
        console.print()
        console.print("[bold]LLM Provider Setup[/bold]")
        console.print("  [cyan]1[/cyan]  Interactive wizard  [dim](set up now)[/dim]")
        console.print("  [cyan]2[/cyan]  CLI flags           [dim](I'll run `wiki config-provider --primary ...` later)[/dim]")
        console.print()
        choice = typer.prompt("Choose setup method (1/2)", default="1").strip()
        if choice == "1":
            wizard_overrides = _run_init_wizard()
            llm.update(wizard_overrides)
            _offer_install(wizard_overrides, llm)
        else:
            _hint("Run [bold]wiki config provider --primary ollama|antigravity-cli|claude-code ...[/bold] to configure.")

    if "provider" in llm:
        del llm["provider"]
    config["llm"] = llm

    # 2. Create directory structure
    paths.internal.mkdir(parents=True, exist_ok=True)
    paths.collections.mkdir(parents=True, exist_ok=True)
    for layer in cfg.COLLECTION_LAYERS:
        (paths.collections / layer).mkdir(parents=True, exist_ok=True)

    # 3. Write config.yml
    cfg.save_config(paths, config)
    _ok(f"Config:    {paths.config_file.relative_to(root)}")

    # 4. Init the state database
    db.init_db(paths.state_db)
    _ok(f"Database:  {paths.state_db.relative_to(root)}")

    # 5. Copy template files
    templates_dir = Path(__file__).parent / "workspace" / "templates"

    # index.md (in .curator/ root, not Collections/)
    index_src = templates_dir / consts.FILE_INDEX_MD
    if index_src.exists() and not paths.index.exists():
        shutil.copy2(index_src, paths.index)
        _ok(f"Index:     {paths.index.relative_to(root)}")

    # overview.md
    if not paths.overview.exists():
        paths.overview.write_text(
            "---\ntitle: Domain Manifest\ntype: overview\n---\n\n"
            "# .curator/overview.md — Domain Manifest\n\n"
            "*List the knowledge domains tracked in this vault.*\n",
            encoding="utf-8",
        )
        _ok(f"Overview:  {paths.overview.relative_to(root)}")

    # ledger.md
    if not paths.ledger.exists():
        paths.ledger.write_text(
            "---\ntitle: Ledger\ntype: ledger\n---\n\n"
            "# .curator/ledger.md — Override Ledger\n\n"
            "*High-priority human corrections that silently override L1-L4 nodes.*\n",
            encoding="utf-8",
        )
        _ok(f"Ledger:    {paths.ledger.relative_to(root)}")

    # log.md
    if not paths.log.exists():
        paths.log.write_text(
            "---\ntitle: Curator Log\ntype: log\n---\n\n# .curator/log.md — Hash Registry\n\n",
            encoding="utf-8",
        )
        _ok(f"Log:       {paths.log.relative_to(root)}")

    # qmd index.yml — pin qmd to this project's collections + per-vault DB
    try:
        if search.write_qmd_config(paths):
            _ok(f"QMD cfg:   {paths.qmd_config_file.relative_to(root)}")
        else:
            _hint(f"qmd config already exists at {paths.qmd_config_file.relative_to(root)}")
    except search.SearchBackendError as e:
        _warn(f"Could not write qmd config: {e}")

    # 6. Curator persona interview (requires LLM to be configured)
    if interactive and config.get("llm", {}).get("primary"):
        console.print()
        console.print("[bold]Curator Persona Setup[/bold]")
        console.print("[dim]This shapes how knowledge is verified and synthesized vault-wide.[/dim]")
        try:
            _persona_client = _start_client(config)
            _curator_persona = _run_curator_persona_wizard(_persona_client)
            if _curator_persona is not None:
                import datetime as _dt_persona
                _curator_persona["updated_at"] = _dt_persona.datetime.now().isoformat()
                config["persona"] = _curator_persona
                cfg.save_config(paths, config)
                _ok("Curator persona saved.")
        except Exception as _persona_exc:
            _warn(f"Persona setup skipped: {_persona_exc}")
            _hint("Run [bold]wiki persona update[/bold] later to configure.")

    # 7. Summary
    cfg.set_last_root(root)
    _updated_mcp = _sync_mcp_configs(root)

    console.print()
    console.print("[bold green]Curator initialised![/bold green]")
    console.print()
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="dim", width=18)
    table.add_column()
    if created_dirs:
        table.add_row("Vault dirs", ", ".join(created_dirs))
    table.add_row("Source dirs", ", ".join(raw_dirs))
    table.add_row("Collections", str(paths.collections.relative_to(root)))
    table.add_row("Config", str(paths.config_file.relative_to(root)))
    table.add_row("LLM backend", describe_backend(config))
    if _updated_mcp:
        table.add_row("MCP configs", f"{len(_updated_mcp)} updated")
    console.print(table)
    console.print()
    if not config.get("llm", {}).get("primary"):
        _hint("LLM provider not set. Run [bold]wiki config provider[/bold] to configure.")
    else:
        _hint("Next: run [bold]wiki add[/bold] to discover & summarize sources, then [bold]wiki curate[/bold].")

@config_app.command("get")
def config_get(
    key: str = typer.Argument(..., help="Dot-separated config key, e.g. external.zotero.roots"),
    global_only: bool = typer.Option(False, "--global", help="Read from global config only."),
) -> None:
    """Print a config key value from the merged (global + project) config.

    \b
      wiki config get external.zotero.roots
      wiki config get llm.primary
    """
    import json as _json

    if global_only:
        raw: dict = {}
        global_cfg_file = cfg.get_global_config_dir() / consts.FILE_CONFIG_YML
        if global_cfg_file.exists():
            import yaml as _yaml
            with global_cfg_file.open("r", encoding="utf-8") as f:
                raw = _yaml.safe_load(f) or {}
    else:
        try:
            paths = _resolve_root_or_die()
            raw = cfg.load_config(paths)
        except SystemExit:
            raw = {}
            global_cfg_file = cfg.get_global_config_dir() / consts.FILE_CONFIG_YML
            if global_cfg_file.exists():
                import yaml as _yaml
                with global_cfg_file.open("r", encoding="utf-8") as f:
                    raw = _yaml.safe_load(f) or {}

    parts = key.split(".")
    val: object = raw
    for part in parts:
        if isinstance(val, dict):
            val = val.get(part)
        else:
            val = None
            break

    if val is None:
        console.print("[dim](not set)[/dim]")
    elif isinstance(val, (dict, list)):
        console.print(_json.dumps(val, indent=2, ensure_ascii=False))
    else:
        console.print(str(val))


@config_app.command("set")
def config_set(
    key: str = typer.Argument(..., help="Dot-separated config key, e.g. external.zotero.roots"),
    value: str = typer.Argument(..., help="Value to set. Lists use JSON: '[\"path1\",\"path2\"]'"),
    append: bool = typer.Option(False, "--append", help="Append to an existing list instead of replacing."),
    global_cfg: bool = typer.Option(True, "--global/--local", help="Write to global config (default) or project config."),
) -> None:
    """Set a config key in the global or project config file.

    \b
      wiki config set external.zotero.roots "$HOME/Zotero/storage"
      wiki config set external.zotero.roots '["~/Zotero/storage","~/Documents/Zotero"]'
      wiki config set external.zotero.roots ~/Documents/Zotero --append
      wiki config set --local llm.primary ollama
    """
    import json as _json
    import yaml as _yaml

    # Determine target config file
    if global_cfg:
        config_dir = cfg.get_global_config_dir()
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / consts.FILE_CONFIG_YML
    else:
        paths = _resolve_root_or_die()
        config_file = paths.config_file

    existing: dict = {}
    if config_file.exists():
        with config_file.open("r", encoding="utf-8") as f:
            existing = _yaml.safe_load(f) or {}

    # Parse value: try JSON first, then treat as plain string
    try:
        parsed_value: object = _json.loads(value)
    except (ValueError, TypeError):
        parsed_value = str(value).replace("~", str(Path.home()))

    # Navigate/create nested dict and apply
    parts = key.split(".")
    target = existing
    for part in parts[:-1]:
        if not isinstance(target.get(part), dict):
            target[part] = {}
        target = target[part]  # type: ignore[assignment]

    leaf = parts[-1]
    if append:
        current = target.get(leaf)
        if isinstance(current, list):
            existing_list = current
        elif current is not None:
            existing_list = [current]
        else:
            existing_list = []
        items = parsed_value if isinstance(parsed_value, list) else [parsed_value]
        for item in items:
            if item not in existing_list:
                existing_list.append(item)
        target[leaf] = existing_list
    else:
        target[leaf] = parsed_value

    with config_file.open("w", encoding="utf-8") as f:
        _yaml.safe_dump(existing, f, sort_keys=False, default_flow_style=False, allow_unicode=True)

    scope = "global" if global_cfg else "project"
    console.print(f"[green]✓[/green] {scope} config updated: [bold]{key}[/bold] = {_json.dumps(parsed_value, ensure_ascii=False)}")
    console.print(f"[dim]  {config_file}[/dim]")


@config_app.command("provider")
def config_provider(
    primary: str = typer.Option(
        "",
        "--primary", "-p",
        help="Primary backend: ollama | claude-code | antigravity-cli",
    ),
    model: str = typer.Option(
        "",
        "--model", "-m",
        help="Ollama model name (e.g. qwen2.5:7b, gemma4:32b).",
    ),
    host: str = typer.Option(
        "",
        "--host",
        help="Ollama host URL (e.g. http://localhost:11434).",
    ),
) -> None:
    """Reconfigure the LLM provider for the current project.

    Run without flags for the interactive wizard, or pass flags to set directly:

    \b
      wiki config provider --primary ollama --model gemma4:32b
      wiki config provider --primary antigravity-cli
      wiki config provider --primary claude-code
    """
    paths = _resolve_root_or_die()
    current_config = cfg.load_config(paths)
    llm = dict(current_config.get("llm", {}))

    any_flag = bool(primary or model or host)

    if any_flag:
        overrides = {}
        _valid_primary = (consts.BACKEND_OLLAMA, consts.BACKEND_CLAUDE_CODE, consts.BACKEND_ANTIGRAVITY_CLI)

        # Resolve provider
        provider = primary or consts.BACKEND_OLLAMA
        if provider not in _valid_primary:
            _warn(f"Unknown --primary '{provider}'. Use: {' | '.join(_valid_primary)}")
            raise typer.Exit(code=1)

        if host:
            llm.setdefault(consts.BACKEND_OLLAMA, {})["host"] = host

        if model:
            # Model provided directly via flag
            llm["primary"] = cfg.join_provider_model(provider, model)
        else:
            # Offer interactive model selection for cloud backends
            if provider in (consts.BACKEND_CLAUDE_CODE, consts.BACKEND_ANTIGRAVITY_CLI, consts.BACKEND_CODEX_CLI):
                console.print()
                console.print(f"[bold]{provider} Model Selection[/bold]")
                sel_model, _ = _pick_cloud_model(provider, llm)
                llm["primary"] = cfg.join_provider_model(provider, sel_model or "")
            elif provider == consts.BACKEND_OLLAMA:
                if not model:
                    sel_model = _pick_ollama_model(llm.get(consts.BACKEND_OLLAMA, {}).get("host", consts.DEFAULT_OLLAMA_HOST))
                    llm["primary"] = cfg.join_provider_model(provider, sel_model)
                else:
                    llm["primary"] = cfg.join_provider_model(provider, model)
            else:
                llm["primary"] = provider

        overrides["primary"] = llm["primary"]
        _offer_install(overrides, llm)
    else:
        # Interactive wizard
        overrides = _run_init_wizard()
        llm.update(overrides)
        _offer_install(overrides, llm)

    llm.pop("provider", None)
    current_config["llm"] = llm
    cfg.save_config(paths, current_config)

    console.print()
    console.print("[bold green]Provider settings saved.[/bold green]")
    console.print(f"[dim]Backend: {describe_backend(current_config)}[/dim]")
    console.print()


@app.command()
def status() -> None:
    """Show the current wiki's stats, paths, and config."""
    paths = _resolve_root_or_die()
    ingest_llm._mark_existing_l3_done_if_present(paths)
    config = cfg.load_config(paths)
    stats = db.get_stats(paths.state_db)

    def _count_md(folder: Path) -> int:
        if not folder.exists():
            return 0
        return sum(1 for p in folder.glob("*.md") if not p.name.startswith("."))

    raw_files = 0
    for raw_dir in paths.raw_dirs:
        if raw_dir.exists():
            raw_files += sum(1 for p in raw_dir.rglob("*") if p.is_file() and not p.name.startswith("."))

    _DEFAULT_MODELS = {
        consts.BACKEND_ANTIGRAVITY_CLI: consts.DEFAULT_ANTIGRAVITY_MODEL,
        consts.BACKEND_CLAUDE_CODE:     consts.DEFAULT_CLAUDE_MODEL,
        consts.BACKEND_CODEX_CLI:       consts.DEFAULT_CODEX_MODEL,
        consts.BACKEND_OLLAMA:          consts.DEFAULT_OLLAMA_MODEL,
    }

    def _get_backend_model(key: str, llm_cfg: dict) -> str:
        for slot in ("primary", "fallback"):
            p, m = cfg.split_provider_model(llm_cfg.get(slot, ""))
            if p == key:
                return m or _DEFAULT_MODELS.get(key, "?")
        return "?"

    def _get_backend_label(key: str, _llm_cfg: dict = {}) -> str:
        if key == consts.BACKEND_OLLAMA:
            return "Ollama"
        elif key == consts.BACKEND_CLAUDE_CODE:
            return "Claude Code"
        elif key == consts.BACKEND_ANTIGRAVITY_CLI:
            return "Antigravity CLI"
        elif key == consts.BACKEND_CODEX_CLI:
            return "Codex CLI"
        return key if key else "?"

    console.print()
    console.print(
        Panel.fit(
            f"[bold cyan]incurator[/bold cyan]  [dim]@ {paths.root}[/dim]",
            border_style="cyan",
        )
    )

    cfg_table = Table(title="Config", show_header=False, box=None, padding=(0, 2))
    cfg_table.add_column(style="dim", width=22)
    cfg_table.add_column()
    llm = config.get("llm", {})
    search_cfg = config.get("search", {})

    primary_prov, primary_model = cfg.split_provider_model(llm.get("primary", ""))
    cfg_table.add_row("Primary", f"{_get_backend_label(primary_prov, llm)}  ({primary_model or '?'})")

    fb_prov, fb_model = cfg.split_provider_model(llm.get("fallback", ""))
    if fb_prov:
        cfg_table.add_row("Fallback", f"{_get_backend_label(fb_prov, llm)}  ({fb_model or '?'})")
    else:
        cfg_table.add_row("Fallback", "none")

    ollama_cfg = llm.get(consts.BACKEND_OLLAMA, {})
    if primary_prov == consts.BACKEND_OLLAMA or fb_prov == consts.BACKEND_OLLAMA:
        cfg_table.add_row("Ollama host", ollama_cfg.get("host", "?"))

    cfg_table.add_row("Search backend", search_cfg.get("backend", "?"))
    cfg_table.add_row("Reranking", "on" if search_cfg.get("rerank") else "off")
    qmd_bin = search.get_qmd_binary()
    if search.is_available():
        version = search.get_version() or "installed"
        cfg_table.add_row("QMD binary", f"[green]{version}[/green]  [dim]{qmd_bin}[/dim]")
    elif qmd_bin is not None:
        cfg_table.add_row("QMD binary", f"[yellow]not built[/yellow]  [dim]{qmd_bin}[/dim]")
    else:
        cfg_table.add_row("QMD binary", "[red]not found[/red]")
    console.print(cfg_table)

    table = Table(title="Sources", show_header=False, box=None, padding=(0, 2))
    table.add_column(style="dim", width=22)
    table.add_column()
    table.add_row("Raw source files", str(raw_files))
    table.add_row("Sources tracked (DB)", str(stats["sources_total"]))
    table.add_row("Sources summarized (L1)", str(stats.get("sources_l1_done", 0)))
    table.add_row("Ingest runs", str(stats["ingest_runs"]))
    total_in = stats.get("total_input_tokens", 0)
    total_out = stats.get("total_output_tokens", 0)
    total_cost = stats.get("total_cost_usd", 0.0)
    if total_in or total_out:
        def _fmt_tokens(n: int) -> str:
            if n >= 1_000_000:
                return f"{n / 1_000_000:.1f}M"
            if n >= 1_000:
                return f"{n / 1_000:.1f}K"
            return str(n)
        cost_str = f"  [dim](${total_cost:.4f})[/dim]" if total_cost > 0 else ""
        table.add_row(
            "Total LLM tokens",
            f"in {_fmt_tokens(total_in)} / out {_fmt_tokens(total_out)}{cost_str}",
        )
    console.print(table)

    pages_table = Table(title="Collections", show_header=False, box=None, padding=(0, 2))
    pages_table.add_column(style="dim", width=22)
    pages_table.add_column()

    l1 = _count_md(paths.contexts)
    l2 = _count_md(paths.atoms)
    l3 = _count_md(paths.concepts)
    l4 = _count_md(paths.exhibitions)
    pages_table.add_row("L1 Contexts/",     str(l1))
    pages_table.add_row("L2 Atoms/",        str(l2))
    pages_table.add_row("L3 Concepts/",     str(l3))
    pages_table.add_row("L4 Exhibitions/",  str(l4))
    pages_table.add_row("[bold]total[/bold]", f"[bold]{l1+l2+l3+l4}[/bold]")
    console.print(pages_table)

    _render_pipeline_status(paths)
    active_jobs = db.list_ingest_jobs(paths.state_db, states=("queued", "running"), limit=8)
    if active_jobs:
        jobs_table = Table(title="Background Jobs", show_header=True, box=None, padding=(0, 1))
        jobs_table.add_column("id", justify="right", style="dim")
        jobs_table.add_column("type", style="cyan")
        jobs_table.add_column("state")
        jobs_table.add_column("phase", style="dim")
        jobs_table.add_column("source")
        for job in active_jobs:
            jobs_table.add_row(
                str(job.get("id", "")),
                str(job.get("job_type", "")),
                str(job.get("state", "")),
                str(job.get("phase", "") or ""),
                str(job.get("source_name", "") or job.get("source_id", "")),
            )
        console.print(jobs_table)
    _render_latest_sync_report_summary(paths)

    try:
        def _silent_cb(node_id): pass
        sync_preflight = lint_module.run_lint(paths, deep=False, client=None, progress_callback=_silent_cb)
        _render_sync_preflight_summary(sync_preflight)
    except Exception as e:
        _warn(f"Sync preflight summary unavailable: {e}")

    console.print()
    if stats["sources_total"] == 0:
        _hint("No sources yet. Add them with [bold]wiki add[/bold]")
    elif stats.get("sources_l1_done", 0) == 0:
        _hint(
            f"{stats['sources_total']} source(s) tracked but not summarized. "
            f"Run [bold]wiki add[/bold] to create L1 Contexts."
        )


# ---------------------------------------------------------------------------
# Stage 2 commands
# ---------------------------------------------------------------------------


@app.command()
def add(
    path: Optional[Path] = typer.Argument(
        None, help="Specific file or directory to register. If omitted, scans all raw directories."
    ),
    recursive: bool = typer.Option(
        True,
        "--recursive",
        "-r",
        help="Recursively discover files if path is a directory.",
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Force re-generation of L1 Contexts even if they exist"
    ),
    no_sync: bool = typer.Option(
        False,
        "--no-sync",
        help="Skip the default sync repair/verification after add.",
    ),
) -> None:
    """Register sources and generate instant L1 Contexts (structural, no LLM).

    If a [path] is provided, only that file or directory is registered.
    If no path is provided, the Curator scans all source directories (02_Wiki,
    03_Notes, 04_Resources) for new or changed files.

    L1 is generated immediately from document structure without an LLM call.
    Run `wiki build` afterwards to extract L2 Atoms + L3 Concepts.
    """
    paths = _resolve_root_or_die()
    if not paths.state_db.exists():
        _err("Vault not fully initialized. Run `wiki init <path>` first.")
        raise typer.Exit(code=1)
    config = cfg.load_config(paths)

    console.print()
    if path:
        console.print(f"[dim]Registering source(s) from {path}...[/dim]")
    else:
        console.print("[dim]Scanning source directories for changes...[/dim]")
    console.print()

    # Phase 1: discover and register new/changed files
    if path:
        discovered = 0
        for file_to_add in ingest_raw.iter_addable_files(path, recursive=recursive):
            outcome = ingest_raw.add_file(paths, file_to_add)
            if outcome.ok:
                discovered += 1
            if outcome.result == ingest_raw.AddResult.ERROR:
                _err(outcome.message)
        removed = 0
        if discovered:
            _ok(f"Registered {discovered} new/changed file(s) from path.")
        else:
            console.print("[dim]No new or changed files found in specified path.[/dim]")
    else:
        discovered, removed = ingest_llm._auto_discover_pending(paths)

    if discovered or removed:
        msg = []
        if discovered:
            msg.append(f"{discovered} new/changed file(s)")
        if removed:
            msg.append(f"{removed} missing file(s) removed")
        _ok("Discovered " + ", ".join(msg) if discovered and not removed else ", ".join(msg))
    else:
        console.print("[dim]No new or changed files found.[/dim]")

    # Phase 2: generate L1 Summaries
    # --force: consider all sources (pending + curated) so deleted summary files
    # are regenerated even when the source content hasn't changed.
    with db.connect(paths.state_db) as conn:
        if force:
            candidate_rows = conn.execute(
                "SELECT id, relpath, content_hash, context_id FROM sources "
                "WHERE status IN ('pending', 'force_pending', 'curated', 'error') ORDER BY id ASC"
            ).fetchall()
        else:
            # Always include curated sources too so we can detect missing summary files
            candidate_rows = conn.execute(
                "SELECT id, relpath, content_hash, context_id FROM sources "
                "WHERE status IN ('pending', 'force_pending', 'curated') ORDER BY id ASC"
            ).fetchall()

    pending_rows = []
    for row in candidate_rows:
        if force:
            # Always re-generate under --force; reset curated rows back to force_pending
            with db.connect(paths.state_db) as conn:
                conn.execute(
                    "UPDATE sources SET status = 'force_pending', error_reason = NULL, "
                    "l1_status = 'pending', l2_status = 'pending', "
                    "l3_status = 'pending', l4_status = 'pending', layer_error = NULL "
                    "WHERE id = ?",
                    (row["id"],),
                )
            pending_rows.append(row)
            continue

        sid = row["context_id"]
        if not sid:
            pending_rows.append(row)
        else:
            # Smart heal: DB says done but context file was deleted — regenerate
            context_path = paths.contexts / f"{sid}.md"
            if not context_path.exists():
                pending_rows.append(row)

    has_concepts = any(paths.concepts.glob("*.md")) if paths.concepts.exists() else False
    if not pending_rows and not force:
        if not discovered:
            if has_concepts:
                _hint("All sources have L1 Contexts. Run [bold]wiki build[/bold] for L2/L3, or [bold]wiki curate[/bold] for L4.")
            else:
                _hint("All sources have L1 Contexts. Run [bold]wiki build[/bold] to extract L2 Atoms + L3 Concepts.")
        return

    if pending_rows:
        console.print()
        source_label = "selected" if force else "pending"
        console.print(
            f"[dim]Generating L1 Contexts for {len(pending_rows)} {source_label} source(s)...[/dim]"
        )
        console.print()

    # L1 is structural-only — no LLM client is started here. The deeper
    # LLM-heavy L2/L3 extraction is a separate step (`wiki build`).
    summarized = 0
    for row in pending_rows:
        console.print(f"  [dim]summarizing[/dim] {row['relpath']}")
        db.set_source_layer_status(paths.state_db, row["id"], "l1", "running")
        context_id = ingest_raw.generate_l1_structural_context(
            paths,
            source_id=row["id"],
            relpath=row["relpath"],
            content_hash=row["content_hash"],
            existing_context_id=row["context_id"],
        )
        if context_id:
            _ok(f"  L1 [{context_id}] ← {row['relpath']}")
            summarized += 1
        else:
            db.set_source_layer_status(
                paths.state_db, row["id"], "l1", "error", error="summary_failed"
            )
            _warn(f"  Summary failed for {row['relpath']}")

    if summarized > 0:
        _refresh_qmd_index(paths, embed=False)
        _invalidate_latest_sync_report(paths, reason="add changed L1")
        if not no_sync:
            _run_sync_report_only(paths, config, reason="add")

    console.print()
    _ok(f"L1 registration complete: {discovered} discovered, {summarized} summarized")
    _hint("Run [bold]wiki build[/bold] to extract L2 Atoms + L3 Concepts.")


@app.command()
def build(
    wait: bool = typer.Option(
        False,
        "--wait",
        help="Run L2/L3 synchronously now instead of queuing to the background worker.",
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Rebuild L2/L3 even if they already exist."
    ),
    no_sync: bool = typer.Option(
        False, "--no-sync", help="Skip the default sync repair/verification after build."
    ),
) -> None:
    """Build L2 Atoms + L3 Concepts from registered L1 Contexts.

    `wiki add` registers sources and generates instant L1 (structural, no LLM).
    This command runs the deeper, LLM-heavy extraction. By default the work is
    queued to the background worker (processed when MCP is active, or run
    `wiki jobs run` to drain the queue now); use --wait to run it synchronously.
    """
    paths = _resolve_root_or_die()
    config = cfg.load_config(paths)

    # Collect L1-ready sources that still need L2/L3.
    with db.connect(paths.state_db) as conn:
        if force:
            rows = conn.execute(
                "SELECT id, relpath FROM sources WHERE l1_status = 'done' ORDER BY id ASC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, relpath FROM sources "
                "WHERE l1_status = 'done' "
                "AND (l2_status IN ('pending', 'error') OR l3_status IN ('pending', 'error')) "
                "ORDER BY id ASC"
            ).fetchall()
    source_ids = [int(r["id"]) for r in rows]

    if force:
        for sid in source_ids:
            db.set_source_layer_status(paths.state_db, sid, "l2", "pending")
            db.set_source_layer_status(paths.state_db, sid, "l3", "pending")

    if not source_ids and not force:
        _hint(
            "Nothing to build — all L1 sources already have L2/L3. "
            "Run [bold]wiki curate[/bold] to stage L4 Exhibitions."
        )
        return

    # Default: enqueue to the background worker (non-blocking).
    if not wait:
        from . import ingest_worker

        job_ids = ingest_worker.enqueue_l2_l3_for_sources(
            paths, source_ids, trigger="wiki_build"
        )
        console.print()
        _ok(f"Queued {len(job_ids)} L2/L3 job(s).")
        _hint(
            "The background worker processes these when MCP is active, or run "
            "[bold]wiki jobs run[/bold] to process the queue now."
        )
        return

    # Synchronous build — the only path that starts an LLM client.
    console.print()
    console.print("[dim]Building L2 Atoms + L3 Concepts...[/dim]")
    console.print()
    client = _start_client(config)
    try:
        l3_results = ingest_llm.run_l1_to_l3(
            paths,
            client,
            lambda: CliIngestCallbacks(mode="batch"),
            mode="batch",
            auto_discover=False,
            force=force,
        )
        atoms_created = sum(r.fragments_created for r in l3_results if r.ok)
        atoms_updated = sum(r.fragments_updated for r in l3_results if r.ok)
        console.print()
        _ok(f"Build complete: {atoms_created} atoms created, {atoms_updated} updated")

        if atoms_created or atoms_updated:
            _refresh_qmd_index(paths, embed=True)
            _invalidate_latest_sync_report(paths, reason="build changed L2-L3")

            # Progressively reinforce Curator persona from newly observed domains
            new_ctx_ids = [
                ch.id for r in l3_results if r.ok
                for ch in r.changes if ch.layer == consts.LAYER_L1
            ]
            if new_ctx_ids:
                new_domains = ingest_llm._collect_domains_from_contexts(paths, new_ctx_ids)
                _maybe_auto_evolve_curator_persona(paths, config, client, new_domains)

            if not no_sync:
                _run_sync_report_only(paths, config, reason="build")

        # Forward propagation (L3 -> L4): merge new facts into existing Exhibitions.
        from . import sync as sync_module

        dirty_exhs = sync_module.find_dirty_exhibitions(paths)
        if dirty_exhs:
            console.print()
            console.print(
                f"[dim]New information affects {len(dirty_exhs)} existing Exhibition(s).[/dim]"
            )
            do_merge = console.is_interactive and typer.confirm(
                "Merge these new facts into affected Exhibitions now?", default=True
            )
            if do_merge:
                updated_count = 0
                for exh_id in dirty_exhs:
                    console.print(f"  [dim]Merging into {exh_id}...[/dim]", end="\r")
                    if sync_module.propagate_downstream_to_exhibition(paths, client, exh_id):
                        console.print(" " * 60, end="\r")
                        _ok(f"[bold]{exh_id}[/bold] updated with latest data.")
                        updated_count += 1
                    else:
                        console.print(" " * 60, end="\r")
                if updated_count > 0:
                    _refresh_qmd_index(paths)
            else:
                _hint("Run [bold]wiki update[/bold] later to merge these into Exhibitions.")
        else:
            _hint("Run [bold]wiki curate[/bold] to stage L4 Exhibitions.")
    finally:
        client.close()


@jobs_app.command("list")
def jobs_list(
    all: bool = typer.Option(False, "--all", help="Show completed and failed jobs too."),
    limit: int = typer.Option(50, "--limit", "-n", help="Maximum jobs to show."),
) -> None:
    """List background ingest jobs."""
    paths = _resolve_root_or_die()
    states = None if all else ("queued", "running")
    jobs = db.list_ingest_jobs(paths.state_db, states=states, limit=limit)
    if not jobs:
        console.print("[dim]No background jobs.[/dim]")
        return
    table = Table(title="Background Jobs", show_header=True, box=None, padding=(0, 1))
    table.add_column("id", justify="right", style="dim")
    table.add_column("source", justify="right")
    table.add_column("type", style="cyan")
    table.add_column("state")
    table.add_column("phase", style="dim")
    table.add_column("progress", justify="right")
    table.add_column("name")
    for job in jobs:
        progress = job.get("progress")
        progress_text = f"{float(progress or 0.0) * 100:.0f}%"
        table.add_row(
            str(job.get("id", "")),
            str(job.get("source_id", "")),
            str(job.get("job_type", "")),
            str(job.get("state", "")),
            str(job.get("phase", "") or ""),
            progress_text,
            str(job.get("source_name", "") or ""),
        )
    console.print(table)


@jobs_app.command("run")
def jobs_run(
    limit: Optional[int] = typer.Option(None, "--limit", "-n", help="Maximum jobs to run."),
) -> None:
    """Run queued L2/L3 jobs in the foreground."""
    from . import ingest_worker

    paths = _resolve_root_or_die()
    config = cfg.load_config(paths)
    results = ingest_worker.run_queued_jobs(paths, config, limit=limit)
    if not results:
        _ok("No queued jobs.")
        return
    ok_count = sum(1 for result in results if result.get("ok"))
    failed = [result for result in results if not result.get("ok")]
    _ok(f"Processed {ok_count} job(s).")
    for result in failed:
        job = result.get("job") or {}
        _err(f"Job #{job.get('id')} failed: {result.get('error')}")
    _refresh_qmd_index(paths, embed=True)


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
    from . import device_registry

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
    from . import device_registry

    paths = _resolve_root_or_die()
    registry = device_registry.load_registry(paths.root)
    devices = registry.get("devices", {})
    if not devices:
        _warn("No device registry yet.")
        _hint("Run [bold]wiki devices sync[/bold] inside the synced vault.")
        return

    local_id = registry.get("local_device_id")
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



@sources_app.command("list")
def sources_list_cmd(
    status_filter: str = typer.Option(
        None,
        "--status",
        "-s",
        help="Only show sources with this status (pending|force_pending|curated|error).",
    ),
) -> None:
    """List all tracked sources."""
    paths = _resolve_root_or_die()
    ingest_llm._mark_existing_l3_done_if_present(paths)
    rows = ingest_raw.list_sources(paths, status_filter=status_filter)

    if not rows:
        console.print()
        if status_filter:
            _warn(f"No sources with status '{status_filter}'")
        else:
            _warn("No sources tracked yet.")
            _hint("Discover them with [bold]wiki add[/bold]")
        return

    _ERROR_REASON_LABEL = {
        "empty_file":  ("empty/unreadable",  "wiki add error — file has no extractable text"),
        "missing_context": ("missing L1",    "wiki add error — L1 Context is missing or invalid"),
        "parse_error": ("parse failed",       "wiki curate error — file could not be parsed"),
        "llm_error":   ("LLM error",          "wiki curate error — LLM call failed"),
        "invalid_atom_output": ("bad atom",   "wiki add error — L2 Atom output was invalid"),
    }

    table = Table(
        title=f"Sources ({len(rows)})",
        show_header=True,
        header_style="bold",
        row_styles=["", "dim"],
    )
    table.add_column("#", justify="right", style="cyan", width=5)
    table.add_column("Type", width=6)
    table.add_column("Size", justify="right", width=9)
    table.add_column("Added", width=10)
    table.add_column("Status", width=18)
    table.add_column("L1", justify="center", width=8)
    table.add_column("L2", justify="center", width=8)
    table.add_column("L3", justify="center", width=8)
    table.add_column("L4", justify="center", width=8)
    table.add_column("Path", overflow="fold")

    def _layer_status_cell(value: str | None) -> str:
        value = value or "pending"
        style = {
            "done": "green",
            "running": "cyan",
            "error": "red",
            "pending": "yellow",
            "skipped": "dim",
        }.get(value, "white")
        label = {
            "done": "done",
            "running": "run",
            "error": "err",
            "pending": "pend",
            "skipped": "skip",
        }.get(value, value[:4])
        return f"[{style}]{label}[/{style}]"

    error_rows: list[dict] = []
    layer_error_rows: list[dict] = []
    for row in rows:
        added_short = row["added_at"][:10] if row["added_at"] else ""
        status = row["status"]
        error_reason = row["error_reason"] if "error_reason" in row.keys() else None
        layer_error = row["layer_error"] if "layer_error" in row.keys() else None
        if status == "error" and error_reason:
            label, _ = _ERROR_REASON_LABEL.get(error_reason, (error_reason, ""))
            status_styled = f"[red]error: {label}[/red]"
            error_rows.append(dict(row))
        else:
            status_styled = f"[{_status_style(status)}]{status}[/{_status_style(status)}]"
        if layer_error and any(
            (row[f"{layer}_status"] if f"{layer}_status" in row.keys() else "") == "error"
            for layer in ("l1", "l2", "l3", "l4")
        ):
            layer_error_rows.append(dict(row))
        table.add_row(
            str(row["id"]),
            row["file_type"],
            _format_bytes(row["bytes"]),
            added_short,
            status_styled,
            _layer_status_cell(row["l1_status"] if "l1_status" in row.keys() else None),
            _layer_status_cell(row["l2_status"] if "l2_status" in row.keys() else None),
            _layer_status_cell(row["l3_status"] if "l3_status" in row.keys() else None),
            _layer_status_cell(row["l4_status"] if "l4_status" in row.keys() else None),
            row["relpath"],
        )

    console.print()
    console.print(table)

    # Per-error hints
    if error_rows or layer_error_rows:
        console.print()
        console.rule("[red]Error details[/red]")
        shown_reasons: set[str] = set()
        for row in error_rows:
            reason = row.get("error_reason") or ""
            _, desc = _ERROR_REASON_LABEL.get(reason, (reason, "unknown error"))
            console.print(f"  [cyan]#{row['id']}[/cyan]  {row['relpath']}")
            console.print(f"       [red]{desc}[/red]")
            if reason == "empty_file":
                console.print(f"       [dim]→ The file has no extractable text (scanned PDF?). "
                               f"Run [bold]wiki sources rm {row['id']}[/bold] to remove it.[/dim]")
            elif reason == "missing_context":
                console.print("       [dim]→ Re-run [bold]wiki add --force[/bold] to regenerate L1 Contexts.[/dim]")
            elif reason in ("parse_error", "llm_error"):
                console.print(f"       [dim]→ Re-try with [bold]wiki curate {row['id']} --force[/bold][/dim]")
            shown_reasons.add(reason)
        for row in layer_error_rows:
            if row.get("status") == "error":
                continue
            layer_error = row.get("layer_error") or ""
            failed_layers = [
                layer.upper()
                for layer in ("l1", "l2", "l3", "l4")
                if row.get(f"{layer}_status") == "error"
            ]
            console.print(f"  [cyan]#{row['id']}[/cyan]  {row['relpath']}")
            console.print(
                f"       [red]{', '.join(failed_layers)} layer error — {layer_error}[/red]"
            )
            if layer_error == "concept_clustering_failed":
                console.print(
                    "       [dim]→ L2 Atoms were written, but L3 Concept clustering failed. "
                    "Re-run [bold]wiki add --force[/bold] after fixing the LLM/JSON issue.[/dim]"
                )
        console.print()
    else:
        console.print()


@sources_app.command("show")
def sources_show_cmd(
    source_id: int = typer.Argument(..., help="The source ID (from `wiki sources list`)."),
    preview_chars: int = typer.Option(
        800,
        "--preview",
        "-p",
        help="Number of characters of parsed text to preview.",
    ),
) -> None:
    """Show details for one source, including a text preview."""
    paths = _resolve_root_or_die()
    row = ingest_raw.get_source(paths, source_id)
    if row is None:
        _err(f"No source with id {source_id}")
        raise typer.Exit(code=1)

    # Re-parse the file to get title and a preview — we don't store parsed text
    # in the DB to keep it small. This is cheap (local file).
    from . import parsers

    file_path = paths.root / row["relpath"]
    if not file_path.exists():
        _err(f"Source file missing from disk: {file_path}")
        raise typer.Exit(code=1)

    try:
        parsed = parsers.parse(file_path)
    except parsers.ParserError as e:
        _err(f"Parse failed: {e}")
        raise typer.Exit(code=1)

    console.print()
    console.print(
        Panel.fit(
            f"[bold]#{row['id']}[/bold]  [cyan]{parsed.title}[/cyan]",
            border_style="cyan",
        )
    )

    meta_table = Table(show_header=False, box=None, padding=(0, 2))
    meta_table.add_column(style="dim", width=16)
    meta_table.add_column()
    meta_table.add_row("Path", row["relpath"])
    meta_table.add_row("Type", parsed.file_type)
    meta_table.add_row("Size", _format_bytes(row["bytes"]))
    meta_table.add_row("Words", f"{parsed.word_count:,}")
    meta_table.add_row("Added", row["added_at"])
    meta_table.add_row("Status", f"[{_status_style(row['status'])}]{row['status']}[/{_status_style(row['status'])}]")
    meta_table.add_row("Hash", row["content_hash"][:16] + "…")
    if row["last_ingested"]:
        meta_table.add_row("Last ingested", row["last_ingested"])
    for k, v in parsed.metadata.items():
        if k == "pdf_pages" and isinstance(v, list):
            meta_table.add_row(k, f"{len(v)} page(s)")
        elif k == "pdf_images" and isinstance(v, list):
            meta_table.add_row(k, f"{len(v)} image(s)")
        else:
            meta_table.add_row(k, str(v)[:80])
    console.print(meta_table)

    console.print()
    console.print("[dim]── text preview ──[/dim]")
    preview = parsed.text[:preview_chars]
    if len(parsed.text) > preview_chars:
        preview += f"\n\n[dim]… ({len(parsed.text) - preview_chars:,} more characters)[/dim]"
    console.print(preview)
    console.print()


@sources_app.command("rm")
def sources_rm_cmd(
    source_id: int = typer.Argument(..., help="The source ID to remove."),
    keep_file: bool = typer.Option(
        False,
        "--keep-file",
        help="Only remove from tracking; don't delete the file from raw/.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip the confirmation prompt.",
    ),
) -> None:
    """Remove a source from tracking (and optionally delete the file)."""
    paths = _resolve_root_or_die()
    row = ingest_raw.get_source(paths, source_id)
    if row is None:
        _err(f"No source with id {source_id}")
        raise typer.Exit(code=1)

    if not yes:
        action = "remove from tracking" if keep_file else "remove from tracking AND delete file"
        confirm = typer.confirm(
            f"About to {action}: #{source_id} {row['relpath']}. Proceed?"
        )
        if not confirm:
            console.print("[dim]Cancelled.[/dim]")
            raise typer.Exit(code=0)

    ok, msg = ingest_raw.remove_source(paths, source_id, delete_file=not keep_file)
    if ok:
        _ok(msg)
    else:
        _err(msg)
        raise typer.Exit(code=1)


@sources_app.command("retry")
def sources_retry_cmd(
    source_id: Optional[int] = typer.Argument(
        None,
        help="Specific source ID to retry. If omitted, retries all sources with status='error'.",
    ),
) -> None:
    """Retry errored sources: re-runs wiki add depending on error type.

    \b
      empty_file/missing_context → re-runs L1 Context generation
      parse_error → re-runs full L1→L3 pipeline (atoms + concepts)
      llm_error   → re-runs full L1→L3 pipeline (atoms + concepts)
    """
    paths = _resolve_root_or_die()
    config = cfg.load_config(paths)

    with db.connect(paths.state_db) as conn:
        if source_id is not None:
            rows = conn.execute(
                "SELECT * FROM sources WHERE id = ? AND status = 'error'", (source_id,)
            ).fetchall()
            if not rows:
                _err(f"Source #{source_id} is not in error state.")
                raise typer.Exit(code=1)
        else:
            rows = conn.execute(
                "SELECT * FROM sources WHERE status = 'error' ORDER BY id ASC"
            ).fetchall()

    if not rows:
        _ok("No errored sources found.")
        return

    add_rows    = [r for r in rows if (r["error_reason"] or "") in ("empty_file", "missing_context")]
    curate_rows = [r for r in rows if (r["error_reason"] or "") in ("parse_error", "llm_error")]
    unknown_rows = [r for r in rows if (r["error_reason"] or "") not in ("empty_file", "missing_context", "parse_error", "llm_error")]

    console.print()
    console.print(f"[bold]Retrying {len(rows)} errored source(s)…[/bold]")

    # ── Re-add (empty_file) ──────────────────────────────────────────────────
    if add_rows:
        console.print()
        console.print(f"[dim]  Phase: re-generating L1 Contexts for {len(add_rows)} source(s)…[/dim]")
        client = None if _instant_l1_enabled(config) else _start_client(config)
        try:
            for row in add_rows:
                with db.connect(paths.state_db) as conn:
                    conn.execute(
                        "UPDATE sources SET status = 'pending', error_reason = NULL, "
                        "l1_status = 'pending', l2_status = 'pending', "
                        "l3_status = 'pending', l4_status = 'pending', layer_error = NULL "
                        "WHERE id = ?",
                        (row["id"],),
                    )
                console.print(f"  [dim]summarizing[/dim] {row['relpath']}")
                context_id = ingest_raw.generate_l1_summary(
                    paths,
                    source_id=row["id"],
                    relpath=row["relpath"],
                    content_hash=row["content_hash"],
                    client=client,
                    config=config,
                    existing_context_id=row["context_id"],
                )
                if context_id:
                    _ok(f"  L1 [{context_id}] ← {row['relpath']}")
                else:
                    _warn(f"  Still failed: {row['relpath']}")
        finally:
            if client is not None:
                client.close()

    # ── Re-add L1-L3 (parse_error / llm_error) ──────────────────────────────
    if curate_rows:
        console.print()
        console.print(f"[dim]{describe_backend(config)}…[/dim]")
        client = _start_client(config)
        try:
            for row in curate_rows:
                with db.connect(paths.state_db) as conn:
                    conn.execute(
                        "UPDATE sources SET status = 'force_pending', error_reason = NULL, "
                        "l2_status = 'pending', l3_status = 'pending', "
                        "l4_status = 'pending', layer_error = NULL WHERE id = ?",
                        (row["id"],),
                    )
            l3_results = ingest_llm.run_l1_to_l3(
                paths, client,
                lambda: CliIngestCallbacks(mode="batch"),
                mode="batch",
                auto_discover=False,
            )
            for result in l3_results:
                if result.ok:
                    _ok(f"  Retried #{result.source_id}")
                else:
                    _warn(f"  Still failed #{result.source_id}: {result.error}")
        finally:
            client.close()

    # ── Unknown error_reason ─────────────────────────────────────────────────
    for row in unknown_rows:
        _warn(f"  #{row['id']} has unknown error_reason '{row['error_reason']}' — skipping.")

    console.print()
    _hint("Run [bold]wiki sources list -s error[/bold] to check remaining errors.")


# ---------------------------------------------------------------------------
# Stage 3 — LLM ingest
# ---------------------------------------------------------------------------


class CliIngestCallbacks(ingest_llm.IngestCallbacks):
    """Rich terminal rendering of ingest progress."""

    def __init__(self, mode: str = "interactive") -> None:
        self.mode = mode
        self._stream_active = False
        self._stream_char_count = 0

    def on_start(self, source_id: int, source_title: str, context_id: str) -> None:
        console.print()
        console.rule(f"[bold cyan]Source #{source_id}[/bold cyan]  {source_title}")
        if context_id:
            console.print(f"[dim]L1 Context: {context_id}[/dim]")

    def on_pass1_start(self, fragment_count: int) -> None:
        console.print(f"[dim]  Pass 1 — drafting {fragment_count} Atom(s) (L2)...[/dim]")

    def on_fragment_drafting(self, fragment_id: str, name: str, operation: str) -> None:
        console.print()
        op_color = "green" if operation == "created" else "yellow"
        console.print(
            f"  [{op_color}]{operation}[/{op_color}] [dim]atom[/dim] "
            f"[cyan]{fragment_id}[/cyan]  {name}"
        )
        console.print("[dim]┄[/dim]" * 60)
        self._stream_active = True
        self._stream_char_count = 0

    def on_stream_chunk(self, chunk: str) -> None:
        if self._stream_active:
            console.print(chunk, end="", style="dim", highlight=False)
            self._stream_char_count += len(chunk)

    def on_fragment_written(self, page: ingest_llm.PageChange) -> None:
        if self._stream_active:
            console.print()
            console.print("[dim]┄[/dim]" * 60)
            self._stream_active = False

    def on_pass2_start(self, fragment_count: int) -> None:
        console.print()
        console.print(f"[dim]  Pass 2 — clustering {fragment_count} atom(s) into Concepts (L3)...[/dim]")

    def on_theme_drafting(self, theme_id: str, name: str) -> None:
        console.print(f"  [green]creating[/green] [dim]concept[/dim] [cyan]{theme_id}[/cyan]  {name}")
        console.print("[dim]┄[/dim]" * 60)
        self._stream_active = True

    def on_theme_written(self, page: ingest_llm.PageChange) -> None:
        if self._stream_active:
            console.print()
            console.print("[dim]┄[/dim]" * 60)
            self._stream_active = False

    def on_pass3_start(self, theme_count: int) -> None:
        console.print()
        console.print(f"[dim]  Pass 3 — synthesizing {theme_count} concept(s) into Exhibitions (L4)...[/dim]")

    def on_curation_drafting(self, cur_id: str, topic: str) -> None:
        console.print(f"  [magenta]creating[/magenta] [dim]exhibition[/dim] [cyan]{cur_id}[/cyan]  {topic}")
        console.print("[dim]┄[/dim]" * 60)
        self._stream_active = True

    def on_curation_written(self, page: ingest_llm.PageChange) -> None:
        if self._stream_active:
            console.print()
            console.print("[dim]┄[/dim]" * 60)
            self._stream_active = False

    def on_finalizing(self) -> None:
        console.print()
        console.print("[dim]finalizing (committing pages, rebuilding index, appending log)...[/dim]")

    def ask_confirm(self, summary: ingest_llm.SummaryData) -> bool:
        return True

    def on_complete(self, result: ingest_llm.IngestResult) -> None:
        console.print()
        if result.skipped:
            _warn(f"Skipped by user: {result.source_title}")
            return
        _ok(
            f"Curated [bold]{result.source_title}[/bold] — "
            f"{result.fragments_created} atoms created, {result.fragments_updated} updated"
        )

    def on_error(self, error: str) -> None:
        console.print()
        _err(error)


@app.command()
def curate(
    force: bool = typer.Option(
        False,
        "--force", "-f",
        help="Delete existing Exhibitions and regenerate from all Concepts.",
    ),
    no_sync: bool = typer.Option(
        False,
        "--no-sync",
        help="Skip the default sync repair/verification after curating.",
    ),
    workspace: Optional[Path] = typer.Option(
        None,
        "--workspace",
        help="Path to a workspace directory containing curate.yml (source filter).",
    ),
) -> None:
    """Stage L4 Exhibitions from L3 Concepts.

    Reads Concept pages from .curator/Collections/03_Concepts/ and synthesizes
    Exhibition pages in 04_Exhibitions/.  Use [bold]wiki add[/bold] first to build
    L1 Contexts → L2 Atoms → L3 Concepts.

    Use --workspace PATH to load a curate.yml and restrict which Concepts are
    included based on their source provenance (sources.include/exclude patterns).
    """
    paths = _resolve_root_or_die()
    curate_spec = None
    workspace = _resolve_curate_workspace(workspace)
    if workspace is None:
        if console.is_interactive:
            workspace = paths.root / consts.DIR_WORKSPACES / "Curator Workspace"
            _warn(f"No workspace found; initializing default workspace at {workspace}.")
            data = CurateTemplateData(
                project=default_project_name(workspace),
                description=f"Knowledge workspace for {default_project_name(workspace)}",
            )
            prepare_workspace(
                vault_root=paths.root,
                workspace=workspace,
                agent="none",
                curate_data=data,
                install_rules=False,
            )
        else:
            _err("wiki curate requires a workspace with curate.yml. Pass --workspace or set WORKSPACE_PATH.")
            raise typer.Exit(code=1)
    if workspace is not None:
        from .curate_yml import load_curate_spec
        try:
            curate_spec = load_curate_spec(workspace)
            if curate_spec is None:
                _err(f"No curate.yml found in {workspace}.")
                raise typer.Exit(code=1)
            else:
                src_info = f", sources.include={curate_spec.sources.include}" if curate_spec.sources.include else ""
                console.print(
                    f"[dim]curate.yml loaded: project=[bold]{curate_spec.project}[/bold]"
                    f"{src_info}[/dim]"
                )
        except ValueError as e:
            _err(f"curate.yml invalid: {e}")
            raise typer.Exit(code=1)

    config = cfg.load_config(paths)

    if force:
        import shutil as _shutil
        if paths.exhibitions.exists():
            _shutil.rmtree(str(paths.exhibitions))
            console.print("[dim]Existing Exhibitions cleared (--force).[/dim]")

    console.print()
    console.print(f"[dim]{describe_backend(config)}…[/dim]")
    client = _start_client(config)

    syn_staged: list = []
    try:
        today = ingest_llm._now_iso()
        import tempfile
        import shutil
        staging = Path(tempfile.mkdtemp(prefix="curator-l4-"))
        try:
            cb = CliIngestCallbacks(mode="batch")
            syn_staged = ingest_llm.run_l4_scoped(paths, client, cb, curate_spec, today, staging)
            spec_hash = _curate_spec_hash(workspace)
            existing_workspace_exh = (
                ingest_llm.find_workspace_exhibition(paths, curate_spec.project)
                if curate_spec is not None else None
            )
            target = None
            for idx, (sp, fp, _) in enumerate(syn_staged):
                target = fp
                content = sp.read_text(encoding="utf-8")
                parsed = page_writer.parse_page(content)
                if curate_spec is not None:
                    parsed.frontmatter["workspace"] = curate_spec.project
                    parsed.frontmatter["curate_spec_hash"] = spec_hash
                    parsed.frontmatter["workspace_path"] = str(workspace)
                if existing_workspace_exh is not None and idx == 0:
                    target = existing_workspace_exh
                    existing = page_writer.read_page(existing_workspace_exh)
                    if existing:
                        parsed.frontmatter["id"] = existing.frontmatter.get("id", existing_workspace_exh.stem)
                content = parsed.to_markdown()
                # Intelligent Merge: If exhibition exists and not force, use Smart Update.
                if not force and target.exists():
                    from . import sync as sync_module
                    console.print(f"  [dim]Merging updates into existing Exhibition: {target.name}...[/dim]")
                    # Use the just-staged concept data via propagate_downstream_to_exhibition
                    sync_module.propagate_downstream_to_exhibition(paths, client, target.stem)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    page_writer.write_page(target, content)

            # Write the active Exhibition ID back into curate.yml for MCP anchor tracking
            if curate_spec is not None and target is not None and workspace is not None:
                try:
                    from .curate_yml import write_exhibition_to_spec
                    write_exhibition_to_spec(workspace, target.stem)
                except Exception:
                    pass

            # Clean up any stale duplicate workspace Exhibitions for this project.
            if curate_spec is not None and target is not None and paths.exhibitions.exists():
                for dup in sorted(paths.exhibitions.glob(f"{consts.PREFIX_L4}-*.md")):
                    if dup == target:
                        continue
                    try:
                        dup_page = page_writer.read_page(dup)
                        if dup_page and dup_page.frontmatter.get("workspace") == curate_spec.project:
                            dup.unlink()
                            console.print(f"[dim]  removed duplicate workspace Exhibition: {dup.name}[/dim]")
                    except Exception:
                        pass

            from . import page_writer as _pw
            _pw.rebuild_index(paths, today)
            all_ch = [c for _, _, c in syn_staged]
            if all_ch:
                scope_label = curate_spec.project if curate_spec else "global"
                bullets = [f"{c.operation}: [[{c.path.replace('.md', '')}]]" for c in all_ch]
                _pw.append_log_entry(paths, today, "curate", scope_label, bullets)
                with db.connect(paths.state_db) as conn:
                    rows = conn.execute(
                        "SELECT id FROM sources WHERE l3_status = 'done'"
                    ).fetchall()
                    source_ids = [row["id"] for row in rows]
                db.set_sources_layer_status(paths.state_db, source_ids, "l4", "done")
            ingest_llm._update_ledger(paths)
            ingest_llm._update_overview(paths)
        finally:
            shutil.rmtree(str(staging), ignore_errors=True)
    finally:
        client.close()

    console.print()
    console.rule("[bold]Curate summary[/bold]")
    if syn_staged:
        console.print(f"  [magenta]{len(syn_staged)} exhibition(s) created[/magenta]")
    else:
        console.print("  [dim]No exhibitions generated — ensure L3 Concepts exist.[/dim]")
        _hint("Run [bold]wiki add[/bold] first to build L1 Contexts → L2 Atoms → L3 Concepts.")
    console.print()

    if syn_staged:
        _refresh_qmd_index(paths, embed=True)

        if not no_sync:
            _run_sync_report_only(paths, config, reason="curate")

        console.print()
        _hint("Run [bold]wiki status[/bold] to see updated page counts.")
        _hint("Ask a question with [bold]wiki query \"<your question>\"[/bold]")


# ---------------------------------------------------------------------------
# Stage 3c — update (forward propagation)
# ---------------------------------------------------------------------------

@app.command()
def update(
    exh_id: Optional[str] = typer.Argument(
        None,
        help="Target Exhibition (EXH-). Omit to update all 'dirty' Exhibitions.",
    ),
) -> None:
    """Forward propagation: reflect latest L3 changes into L4 Exhibitions.
    
    This command identifies Exhibitions that reference Concepts (L3) with newer
    information and performs a 'Smart Update' (merging new facts without 
    overwriting human/agent edits).
    """
    from . import sync as sync_module
    
    paths = _resolve_root_or_die()
    config = cfg.load_config(paths)
    client = _start_client(config)
    
    console.print()
    console.rule("[bold cyan]Update — Forward Propagation[/bold cyan]")
    
    target_ids = []
    if exh_id:
        target_ids = [exh_id]
    else:
        console.print("[dim]Scanning for Exhibitions with updated concepts...[/dim]")
        target_ids = sync_module.find_dirty_exhibitions(paths)
        
    if not target_ids:
        _ok("All Exhibitions are already up-to-date with their referenced concepts.")
        return

    console.print(f"[dim]Found {len(target_ids)} exhibition(s) requiring update.[/dim]")
    
    updated_count = 0
    for tid in target_ids:
        console.print(f"  [dim]Merging updates into {tid}...[/dim]", end="\r")
        if sync_module.propagate_downstream_to_exhibition(paths, client, tid):
            console.print(" " * 60, end="\r")
            _ok(f"[bold]{tid}[/bold] updated with latest concept data.")
            updated_count += 1
        else:
            console.print(" " * 60, end="\r")
            console.print(f"  [dim]• {tid} already consistent.[/dim]")
            
    if updated_count > 0:
        _refresh_qmd_index(paths)
        _ok(f"Forward propagation complete. {updated_count} exhibitions updated.")
    else:
        _ok("All exhibitions are consistent.")


# ---------------------------------------------------------------------------


@app.command()
def sync(
    node_id: Optional[str] = typer.Argument(
        None,
        help="Target node (CTX-/ATM-/CON-/EXH-). Omit for global verification.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Report gaps without fixing or rebuilding routing tables.",
    ),
    no_fix: bool = typer.Option(
        False,
        "--no-fix",
        help="Report-only mode: do not apply structural or logical repairs.",
    ),
    deep: bool = typer.Option(
        False,
        "--deep",
        help="Force full LLM logical verification (Mode C) even without manual changes.",
    ),
    no_deep: bool = typer.Option(
        False,
        "--no-deep",
        help="Skip LLM contradiction detection entirely (fast structural check only).",
    ),
    no_interactive: bool = typer.Option(
        False,
        "--no-interactive",
        help="Run contradiction detection but only report — do not prompt for resolution.",
    ),
    full: bool = typer.Option(
        False,
        "--full",
        help="Run the full structural + LLM verification path instead of the v0.2.1 incremental fast path.",
    ),
    backward: bool = typer.Option(
        False,
        "--backward",
        help="Run the legacy backward verification/repair path explicitly.",
    ),
) -> None:
    """Run deductive verification and rebuild routing tables.

    \b
    Mode A (no node_id): global reverse verification — traces L4 Exhibitions back
    to L1 Contexts and flags any logical discontinuities.

    Mode B (node_id given): targeted bidirectional propagation — traces upstream
    to L1 and downstream to L4 from the given node, flagging broken references.

    By default, wiki sync runs LLM contradiction detection and prompts for
    interactive resolution when a TTY is present. Use --no-deep to skip the
    LLM step entirely, or --no-interactive to report only without prompting.

    By default sync applies safe structural repairs and logical backprop repairs,
    then re-verifies the affected graph. Use --no-fix or --dry-run for report-only
    behavior.

    Finishes by rebuilding index.md, ledger.md, log.md, and overview.md unless
    --dry-run is given.
    """
    from . import sync as sync_module

    class CliSyncCallbacks(sync_module.SyncCallbacks):
        def on_node_check(self, node_id: str):
            console.print(f"  [dim]Verifying {node_id}...[/dim]", end="\r")

        def on_node_repair(self, node_id: str, rebuilt_count: int = 0, message: Optional[str] = None):
            console.print(" " * 60, end="\r")
            detail = f" ({message})" if message else ""
            console.print(f"  [green]✓[/green] [bold]{node_id}[/bold] repaired{detail}.")

    cb = CliSyncCallbacks()

    paths = _resolve_root_or_die()
    db.init_db(paths.state_db)
    config = cfg.load_config(paths)
    console.print()
    console.rule("[bold cyan]Sync — Deductive Verification[/bold cyan]")

    if not any([node_id, dry_run, no_fix, deep, no_deep, no_interactive, full, backward]):
        result = sync_module.run_incremental_sync(paths, client=None, config=config)
        changed_count = len(result.get("changed_nodes", []))
        affected_count = len(result.get("affected_nodes", []))
        if changed_count:
            console.print(
                f"[dim]Incremental sync: {changed_count} changed node(s), "
                f"{affected_count} downstream node(s) affected.[/dim]"
            )
            _hint("Run [bold]wiki sync --full[/bold] for LLM logical verification.")
        else:
            console.print("[dim]Incremental sync: no body-hash changes detected.[/dim]")
        _ok("Routing tables rebuilt (incremental).")
        return
 
    # 0. Change detection (Manual changes)
    change_report = sync_module.scan_for_changes(paths)
    dirty_nodes = change_report.modified + change_report.new
    dirty_node_ids = [Path(ref).stem for ref in dirty_nodes]
    logical_target_ids = [node_id] if node_id else dirty_node_ids
    if change_report.total_changes() > 0:
        msg = f"[dim]Changes detected: {len(change_report.modified)} modified, {len(change_report.new)} new, {len(change_report.deleted)} deleted[/dim]"
        console.print(msg)
    else:
        console.print(f"[dim]No manual changes detected (cached {change_report.unchanged_count} pages)[/dim]")

    # 1. Full Static Verification (Always runs for everyone)
    if node_id:
        console.print(f"[dim]Mode B: targeted structural verification for {node_id}...[/dim]")
        gaps = sync_module.run_mode_b(paths, node_id, callbacks=cb)
    else:
        console.print("[dim]Mode A: global structural verification (L4 → L1)...[/dim]")
        gaps = sync_module.run_mode_a(paths, callbacks=cb)
    
    console.print("[dim]Fast structural lint verification...[/dim]")
    structural_report = lint_module.run_lint(paths, deep=False, client=None, progress_callback=cb.on_node_check)
    console.print(" " * 60, end="\r")

    should_fix = not no_fix and not dry_run
    client = _start_client(config)
    
    try:
        structural_fixed = 0
        rebuilt = 0
        if should_fix:
            console.print("[dim]Applying safe structural lint repairs...[/dim]")
            # Static repairs (deterministic)
            fixed_count = lint_module.apply_fixes(paths, structural_report.issues, progress_callback=cb.on_node_check)
            gap_fixed = sync_module.repair_structural_gaps(paths, gaps, callbacks=cb)
            nested_fixed = sync_module.repair_nested_frontmatter(paths, callbacks=cb)
            
            structural_fixed = fixed_count + gap_fixed + nested_fixed
            if structural_fixed > 0:
                structural_report = lint_module.run_lint(paths, deep=False, client=None, progress_callback=cb.on_node_check)
                # Any node that was fixed is now also 'dirty' for deep verification
                # (Optional optimization: only if we think structural fix needs logical re-verify)

            # 2. Targeted LLM-based repairs (only for dirty/requested nodes)
            target_pages = []
            if node_id:
                subdir = sync_module._subdir_for_id(node_id)
                if subdir:
                    relpath = f"{subdir}/{node_id}.md"
                    if relpath not in target_pages:
                        target_pages.append(relpath)
            else:
                target_pages = list(dirty_nodes)
                
            llm_fixed = lint_module.apply_llm_fixes(
                paths, structural_report.issues, client, 
                progress_callback=cb.on_node_check,
                limit_to=target_pages
            )
            structural_fixed += llm_fixed
            
            if structural_fixed > 0:
                structural_report = lint_module.run_lint(paths, deep=False, client=None, progress_callback=cb.on_node_check)
                structural_report.auto_fixed = structural_fixed
                gaps = sync_module.run_mode_b(paths, node_id) if node_id else sync_module.run_mode_a(paths, callbacks=cb)
                console.print(" " * 60, end="\r")
                _ok(f"{structural_fixed} safe structural lint issue(s) fixed.")

        structural_issues = structural_report.errors + structural_report.warnings
        needs_review = structural_report.needs_review
        blocked_node_ids = _sync_blocked_node_ids(structural_report)

        # Gate both deep lint and Mode C on whether there are dirty nodes or --deep.
        run_llm_verification = bool(logical_target_ids) or deep
        # Contradiction detection runs by default unless --no-deep
        run_contradiction_check = not no_deep
        # Interactive mode: prompt for resolution when TTY present and --no-interactive not set
        run_interactive = run_contradiction_check and not no_interactive and _interactive()

        # 3. Targeted Deep Lint Verification (LLM contradiction check)
        contradiction_issues: list = []
        if run_contradiction_check:
            try:
                target_pages = []
                if node_id:
                    subdir = sync_module._subdir_for_id(node_id)
                    if subdir:
                        relpath = f"{subdir}/{node_id}.md"
                        if relpath not in target_pages:
                            target_pages.append(relpath)
                else:
                    target_pages = list(dirty_nodes)

                deep_report = lint_module.run_lint(
                    paths, deep=True, client=client,
                    progress_callback=cb.on_node_check,
                    # When run_llm_verification is active, scan all; else scope to dirty
                    limit_to=target_pages if not (run_llm_verification or deep) else None,
                )
                console.print(" " * 60, end="\r")
                from .lint import CheckId as _CheckId
                for issue in deep_report.issues:
                    if issue not in structural_report.issues:
                        structural_report.issues.append(issue)
                    if issue.check == _CheckId.CONTRADICTION:
                        contradiction_issues.append(issue)
                structural_issues = structural_report.errors + structural_report.warnings
                needs_review = structural_report.needs_review
                blocked_node_ids = _sync_blocked_node_ids(structural_report)
            except Exception as e:
                _warn(f"Contradiction/equivalence scan unavailable: {e}")

        # 3b. Interactive contradiction resolution wizard
        if run_interactive and contradiction_issues:
            _contradiction_resolution_wizard(paths, client, contradiction_issues)
        if structural_issues:
            console.print()
            _warn(
                f"{len(structural_issues)} structural lint issue(s) detected "
                "(safe repairs run by default; use [bold]wiki sync[/bold] again after review):"
            )
            for issue in structural_issues[:20]:
                console.print(
                    f"  [yellow]•[/yellow] [{issue.severity.value}] "
                    f"[cyan]{issue.page}[/cyan]: {issue.message}"
                )
            if len(structural_issues) > 20:
                console.print(f"  [dim]...and {len(structural_issues) - 20} more[/dim]")
            if needs_review:
                _warn(f"{len(needs_review)} issue(s) need review; unresolved links were not deleted.")
            if blocked_node_ids:
                _warn(
                    f"{len(blocked_node_ids)} node(s) have structural review items; "
                    "related logical checks will be skipped."
                )

        structural_gaps = list(gaps)
        if not run_llm_verification:
            console.print(
                "[dim]Mode C: skipped — no manual changes detected. "
                "Use [bold]--deep[/bold] to force full LLM verification.[/dim]"
            )
            logic_gaps: list = []
            logical_fixed = 0
            rebuilt = 0
        else:  # run_llm_verification
            console.print("[dim]Mode C: LLM logical deduction verification...[/dim]")
            if should_fix:
                logic_gaps, repair_result = sync_module.repair_logical_gaps(
                    paths,
                    client,
                    blocked_node_ids=blocked_node_ids,
                    target_node_ids=logical_target_ids if not deep else None,
                    max_iterations=2,
                    callbacks=cb,
                )
                console.print(" " * 60, end="\r")
                rebuilt = repair_result.rebuilt_downstream
                logical_fixed = repair_result.fixed
                if logical_fixed or rebuilt:
                    _ok(
                        f"Logical sync repaired {logical_fixed} node(s) and rebuilt "
                        f"{rebuilt} downstream page(s)."
                    )
            else:
                logic_gaps = sync_module.run_mode_c(
                    paths,
                    client,
                    blocked_node_ids=blocked_node_ids,
                    target_node_ids=logical_target_ids if not deep else None,
                    callbacks=cb,
                )
                console.print(" " * 60, end="\r")
                logical_fixed = 0
        gaps = structural_gaps + logic_gaps
        fixed_for_report = int(getattr(structural_report, "auto_fixed", 0) or 0) + logical_fixed
        if not dry_run:
            _write_latest_sync_report(
                paths,
                reason="sync" if should_fix else "sync --no-fix",
                structural_report=structural_report,
                structural_gaps=structural_gaps,
                logic_gaps=logic_gaps,
                fixed=fixed_for_report,
                rebuilt=rebuilt,
            )

        if gaps:
            console.print()
            _warn(f"{len(gaps)} verification gap(s) remain:")
            for gap in gaps:
                console.print(f"  [yellow]•[/yellow] [{gap.layer}] [bold]{gap.node_id}[/bold]: {gap.message}")
                if gap.reasoning:
                    console.print(f"    [dim]{gap.reasoning}[/dim]")
            if not dry_run:
                _mark_layer_status_from_sync_gaps(paths, gaps)
                _warn("Layer status updated from remaining sync gaps.")
        else:
            console.print()
            if structural_issues:
                _warn("No logical gaps detected, but structural lint issues remain.")
            else:
                if not dry_run:
                    _mark_clean_sync_status(paths)
                _ok("No logical or structural gaps detected.")

        if gaps and not dry_run:
            _hint("Review remaining gaps, then rerun [bold]wiki sync[/bold].")
    finally:
        client.close()

    if not dry_run:
        # Update page hashes in DB for next fast sync
        sync_module.update_all_page_hashes(paths)
        sync_module.finalize_routing_tables(paths)
        _ok("Routing tables rebuilt (index.md, ledger.md, log.md, overview.md).")
    else:
        _hint("--dry-run: routing tables not modified.")


# ---------------------------------------------------------------------------
# Contradiction resolution wizard (used by wiki sync interactive mode)
# ---------------------------------------------------------------------------


def _atom_display_title(paths, atom_id: str) -> str:
    """Return a short human-readable title for an Atom (H1 or ID fallback)."""
    from . import page_writer as _pw
    page = _pw.read_page(paths.atoms / f"{atom_id}.md")
    if page:
        for line in (page.body or "").splitlines():
            if line.startswith("# "):
                return line[2:].strip()
        name = page.frontmatter.get("name", "")
        if name:
            return str(name)
    return atom_id


def _contradiction_resolution_wizard(paths, client, issues: list) -> None:
    """Interactive wizard: step through contradiction issues, offer D/R/S."""
    from . import contradiction as _cd
    from . import page_writer as _pw
    from .prompts import build_contradiction_resolution_messages
    from .llm import LLMError
    import json

    console.print()
    console.rule("[bold yellow]Contradiction Review[/bold yellow]")
    console.print(
        f"[dim]Found {len(issues)} potential contradiction(s). "
        "Review each: [bold][D][/bold]ismiss  [bold][R][/bold]esolve  [bold][S][/bold]kip  [bold][Q][/bold]uit[/dim]"
    )

    for i, issue in enumerate(issues, 1):
        atom_a_rel = issue.page                          # f"{consts.LAYER_L2}/ATM-xxx.md"
        atom_b_rel = issue.context.get("other_page", "") # f"{consts.LAYER_L2}/ATM-yyy.md"
        atom_a_id = Path(atom_a_rel).stem
        atom_b_id = Path(atom_b_rel).stem
        reasoning = issue.context.get("reasoning", issue.suggestion or "")

        console.print()
        console.print(f"[bold cyan][{i}/{len(issues)}][/bold cyan]  "
                      f"[bold]{atom_a_id}[/bold]  {_atom_display_title(paths, atom_a_id)}")
        console.print(f"       [bold]{atom_b_id}[/bold]  {_atom_display_title(paths, atom_b_id)}")
        if reasoning:
            console.print()
            console.print("[dim]LLM reasoning:[/dim]")
            for line in reasoning.splitlines()[:6]:
                console.print(f"  [dim]{line}[/dim]")

        console.print()
        choice = typer.prompt("[D]ismiss / [R]esolve / [S]kip / [Q]uit", default="S").strip().upper()

        if choice == "Q":
            console.print("[dim]Stopped review.[/dim]")
            break
        elif choice == "D":
            _cd.add_dismissed(paths, atom_a_id, atom_b_id, reason="dismissed via wiki sync")
            _cd.clear_flagged(paths, atom_a_id, atom_b_id)
            _ok(f"Dismissed: {atom_a_id} ↔ {atom_b_id}")
        elif choice == "R":
            console.print("[dim]Asking LLM to propose a resolution…[/dim]")
            try:
                page_a = _pw.read_page(paths.atoms / f"{atom_a_id}.md")
                page_b = _pw.read_page(paths.atoms / f"{atom_b_id}.md")
                if page_a is None or page_b is None:
                    _warn("Could not read atom files for resolution.")
                    continue
                messages = build_contradiction_resolution_messages(
                    path_a=atom_a_rel,
                    content_a=page_a.to_markdown(),
                    path_b=atom_b_rel,
                    content_b=page_b.to_markdown(),
                    conflict_reasoning=reasoning,
                )
                raw = client.chat(messages, json_mode=True, temperature=0.3)
                proposal = json.loads(raw)
            except (LLMError, json.JSONDecodeError, Exception) as e:
                _warn(f"Resolution failed: {e}")
                continue

            console.print()
            console.print("[bold]Proposed resolution:[/bold]")
            console.print(f"  [dim]{proposal.get('reasoning', '')}[/dim]")
            console.print()
            console.print(f"  [cyan]Atom A ({atom_a_id}) revised body:[/cyan]")
            for line in (proposal.get("atom_a_body_revised", "") or "").splitlines()[:4]:
                console.print(f"    {line}")
            console.print(f"  [cyan]Atom B ({atom_b_id}) revised body:[/cyan]")
            for line in (proposal.get("atom_b_body_revised", "") or "").splitlines()[:4]:
                console.print(f"    {line}")

            apply = typer.confirm("Apply this resolution?", default=False)
            if apply:
                _cd.apply_resolution(paths, atom_a_id, atom_b_id, proposal)
                _ok(f"Resolved: {atom_a_id} ↔ {atom_b_id} (is_verified_by_human set)")
            else:
                console.print("[dim]Resolution not applied.[/dim]")
        # S or anything else: skip silently


# ---------------------------------------------------------------------------
# Stage 4 — query
# ---------------------------------------------------------------------------


class CliQueryCallbacks(query_module.QueryCallbacks):
    """Rich terminal rendering of query progress."""

    def __init__(self) -> None:
        self._stream_active = False

    def on_start(self, question: str, mode: str) -> None:
        console.print()
        console.rule("[bold cyan]Query[/bold cyan]")
        console.print(f"[bold]Q:[/bold] {question}")
        console.print(f"[dim]mode: {mode}[/dim]")
        console.print()

    def on_classifying_intent(self) -> None:
        console.print("[dim]  understanding question…[/dim]")

    def on_intent_classified(self, intent: str) -> None:
        if intent == "chitchat":
            console.print("[dim]  → casual question, no search needed[/dim]")
        else:
            console.print("[dim]  → wiki question, searching…[/dim]")

    def on_chitchat_reply(self, reply: str) -> None:
        console.print()
        console.print("[dim]" + "─" * 72 + "[/dim]")
        console.print(reply)
        console.print("[dim]" + "─" * 72 + "[/dim]")
        console.print()

    def on_searching(self) -> None:
        console.print("[dim]  searching wiki (BM25 + vector + rerank)…[/dim]")

    def on_search_done(self, results) -> None:
        if getattr(results, "fallback_mode", ""):
            _warn("GPU OOM — fell back to BM25 search (no vector/rerank).")
        if not len(results):
            return
        console.print(f"[dim]  found {len(results)} relevant page(s):[/dim]")
        for i, hit in enumerate(results.hits, start=1):
            score_color = (
                "green" if hit.score > 0.7 else "yellow" if hit.score > 0.4 else "dim"
            )
            path = hit.full_path or hit.path
            title = hit.title or path
            console.print(
                f"    [dim]{i}.[/dim] [{score_color}]{hit.score:.2f}[/{score_color}] "
                f"[cyan]{path}[/cyan]  [dim]{title[:60]}[/dim]"
            )

    def on_no_results(self) -> None:
        console.print()
        _warn("No matching wiki pages found.")

    def on_synthesizing(self) -> None:
        console.print()
        console.print("[dim]  synthesizing answer…[/dim]")
        console.print("[dim]" + "─" * 72 + "[/dim]")
        self._stream_active = True

    def on_stream_chunk(self, chunk: str) -> None:
        if self._stream_active:
            console.print(chunk, end="", highlight=False)

    def on_saved(self, saved_path: str) -> None:
        if self._stream_active:
            console.print()
            self._stream_active = False
        console.print()
        _ok(f"Saved answer as [cyan]{saved_path}[/cyan]")

    def on_wiki_saved(self, saved_path: str, category: str) -> None:
        if self._stream_active:
            console.print()
            self._stream_active = False
        console.print()
        _ok(
            f"Promoted to [cyan]{saved_path}[/cyan]  "
            f"[dim](category: {category})[/dim]"
        )

    def on_complete(self, result) -> None:
        if self._stream_active:
            console.print()
            console.print("[dim]" + "─" * 72 + "[/dim]")
            self._stream_active = False
        console.print()

    def on_error(self, error: str) -> None:
        if self._stream_active:
            console.print()
            self._stream_active = False
        console.print()
        _err(error)


@app.command()
def query(
    question: Optional[str] = typer.Argument(
        None,
        help="The question to ask the wiki. If omitted, enters interactive chat mode (press Enter on empty line to exit).",
    ),
    mode: str = typer.Option(
        "hybrid",
        "--mode",
        help="Search mode: hybrid | lex | vec",
    ),
    lex: bool = typer.Option(
        False,
        "--lex",
        help="Shortcut for --mode lex (BM25 only, fastest).",
    ),
    vec: bool = typer.Option(
        False,
        "--vec",
        help="Shortcut for --mode vec (vector only).",
    ),
    limit: int = typer.Option(
        8, "--limit", "-n", help="Max number of search hits to consider."
    ),
    min_score: float = typer.Option(
        0.6, "--min-score", help="Drop hits below this score."
    ),
    no_rerank: bool = typer.Option(
        False, "--no-rerank", help="Skip LLM reranking in hybrid mode."
    ),
    save_as: Optional[str] = typer.Option(
        None,
        "--save-as",
        help="Save the answer as a new L4 Exhibition page (EXH-UUID.md). "
             "The value is used as the page title hint.",
    ),
    scope: str = typer.Option(
        "all",
        "--scope",
        help="Restrict to a single Curator layer: all | contexts | atoms | concepts | exhibitions.",
    ),
    no_intent_classify: bool = typer.Option(
        False,
        "--no-intent-classify",
        help="Skip intent classification step (saves ~3 sec per query).",
    ),
    update: bool = typer.Option(
        False,
        "--update",
        help="After answering, create a new L2 Atom from the answer insight.",
    ),
    workspace: Optional[Path] = typer.Option(
        None,
        "--workspace",
        help="Path to a workspace directory containing curate.yml. Defaults to WORKSPACE_PATH or current workspace.",
    ),
    curate: bool = typer.Option(
        False,
        "--curate",
        help="Create and maintain a session Exhibition: first answer creates an ephemeral L4 page; "
             "each follow-up appends to it. Prompted at session end whether to keep or discard.",
    ),
) -> None:
    """Ask a question: search the wiki, synthesize an answer with citations.

    Without an argument, enters interactive chat mode. Type an empty line to exit.
    Within a session you can say 'save to wiki' / 'save' etc. to promote the
    last answer into 02_Wiki under an auto-determined category folder.

    Use --update to automatically create a new L2 Atom from the synthesized answer,
    feeding new knowledge back into the L1-L3 pipeline for future curation.

    Use --curate to build a session-scoped L4 Exhibition across all turns, then
    decide at the end whether to keep it as a permanent knowledge record.

    The query pipeline:
      1. Translate question to English (for non-English input)
      2. QMD search (BM25 + vector + rerank by default)
      3. Synthesize a cited answer from Curator pages, streamed to the terminal
      4. Optionally save as an Exhibition page (--save-as) or promote to 02_Wiki
    """
    paths = _resolve_root_or_die()
    config = cfg.load_config(paths)
    curate_spec = None
    workspace = _resolve_curate_workspace(workspace)
    if workspace is not None:
        from .curate_yml import load_curate_spec
        try:
            curate_spec = load_curate_spec(workspace)
            if curate_spec is not None:
                console.print(
                    f"[dim]curate.yml loaded for query: "
                    f"project=[bold]{curate_spec.project}[/bold][/dim]"
                )
        except ValueError as e:
            console.print(f"[yellow]Warning:[/yellow] curate.yml invalid: {e}. Proceeding without workspace scope.")

    # Auto-sync: if there are pending sources, add them first (L1-L3)
    pending = db.get_pending_count(paths.state_db)
    if pending > 0:
        import subprocess
        console.print(f"[yellow]{pending} pending source(s) found — running wiki add before query…[/yellow]")
        subprocess.run(["wiki", "add"], check=False)

    # Resolve search mode shortcuts
    if lex:
        mode = "lex"
    elif vec:
        mode = "vec"
    if mode not in ("hybrid", "lex", "vec"):
        _err(f"Invalid mode '{mode}'. Use hybrid, lex, or vec.")
        raise typer.Exit(code=1)

    if scope not in ("all", "contexts", "atoms", "concepts", "exhibitions"):
        _err(
            f"Invalid scope '{scope}'. Use all, contexts, atoms, concepts, or exhibitions."
        )
        raise typer.Exit(code=1)
    if not search.is_available():
        _err("qmd binary not available.")
        _hint(
            "Install it globally via npm: "
            "[bold]npm install -g @tobilu/qmd[/bold]"
        )
        raise typer.Exit(code=1)

    collection_pages = 0
    for layer_dir in (paths.contexts, paths.atoms, paths.concepts, paths.exhibitions):
        if layer_dir.exists():
            collection_pages += sum(
                1 for p in layer_dir.glob("*.md") if not p.name.startswith(".")
            )
    if collection_pages == 0:
        _err("Curator collections are empty.")
        _hint("Run [bold]wiki add[/bold] then [bold]wiki curate[/bold] first.")
        raise typer.Exit(code=1)

    console.print()
    console.print(f"[dim]{describe_backend(config)}…[/dim]")
    client = _start_client(config)

    run_kwargs = dict(
        mode=mode,
        limit=limit,
        min_score=min_score,
        rerank=not no_rerank,
        save_as=save_as,
        scope=scope,
        classify_intent_first=not no_intent_classify,
        workspace_project=curate_spec.project if curate_spec else None,
        query_boost_terms=[x for x in ([curate_spec.persona.domain, curate_spec.persona.subdomain] + curate_spec.persona.disambiguation_keywords) if x] if curate_spec else None,
        ephemeral_exhibition=False if save_as else True,
    )

    callbacks = CliQueryCallbacks()

    try:
        _run_query_repl(
            paths, client, callbacks, run_kwargs,
            initial_question=question,
            update_knowledge=update,
            curate_spec=curate_spec,
            create_session_exhibition=curate,
        )
    finally:
        client.close()


def _run_query_repl(
    paths, client, callbacks, run_kwargs, *,
    initial_question: str | None = None,
    update_knowledge: bool = False,
    curate_spec=None,
    create_session_exhibition: bool = False,
) -> None:
    """Interactive REPL: ask questions until the user submits an empty line.

    If initial_question is provided, it is answered first before prompting
    for further input — so `wiki query "question"` enters the same REPL.
    update_knowledge=True creates a new L2 Atom from each synthesized answer.
    create_session_exhibition=True builds a running L4 Exhibition across all turns.
    """
    from rich.prompt import Prompt
    import uuid

    last_question: str | None = None
    last_answer: str | None = None
    session_id = f"QRY-{uuid.uuid4().hex[:8]}"
    session_exh_path: Path | None = None

    console.print()
    console.rule("[bold cyan]Wiki Chat[/bold cyan]")
    console.print(
        "[dim]Ask questions about your wiki. "
        "Press [bold]Enter[/bold] (empty line) or [bold]Ctrl+C[/bold] to exit.[/dim]"
    )
    console.print(
        "[dim]Say 'save to wiki' / 'save' to promote the last answer to 02_Wiki.[/dim]"
    )

    pending = initial_question  # consumed on the first iteration, no extra print needed

    while True:
        if pending:
            user_input = pending
            pending = None
        else:
            try:
                user_input = Prompt.ask("\n[bold cyan]Q[/bold cyan]").strip()
            except (EOFError, KeyboardInterrupt):
                console.print()
                break

        if not user_input:
            break

        # Run intent classification to detect promote vs wiki vs chitchat
        from . import intent as intent_module

        intent_result = intent_module.classify_intent(client, user_input)

        if intent_result.intent == "promote":
            if last_answer and last_question:
                confirmed = Prompt.ask(
                    "  [yellow]Save to 02_Wiki?[/yellow]",
                    choices=["yes", "no"],
                    default="yes",
                )
                if confirmed == "yes":
                    console.print("[dim]  Classifying category/slug...[/dim]")
                    try:
                        category, slug = query_module.classify_wiki_topic(
                            client, last_question, last_answer
                        )
                        saved = query_module.save_wiki_page(
                            paths, last_question, last_answer, category, slug
                        )
                        callbacks.on_wiki_saved(saved, category)
                    except OSError as e:
                        _err(f"Failed to save wiki page: {e}")
            else:
                _warn("No answer to save. Please ask a question first.")
            continue

        # Normal wiki query (or chitchat — run_query handles it)
        result = query_module.run_query(
            paths,
            client,
            user_input,
            callbacks,
            **{**run_kwargs, "classify_intent_first": False, "session_id": session_id},
        )
        if result.answer:
            last_question = user_input
            last_answer = result.answer
            if result.saved_path:
                config = cfg.load_config(paths)
                _run_sync_report_only(paths, config, reason="query")

            if update_knowledge:
                today = ingest_llm._now_iso()
                atom_id = ingest_llm.add_atom_from_insight(
                    paths, client, result.answer, today, source_hint="query"
                )
                if atom_id:
                    console.print(f"[dim]  → new atom created: [cyan]{atom_id}[/cyan][/dim]")

            if create_session_exhibition:
                if session_exh_path is None:
                    try:
                        rel = query_module._save_curation_page(
                            paths,
                            user_input,
                            result.answer,
                            title=user_input[:60],
                            hits=result.hits,
                            session_id=session_id,
                            ephemeral=True,
                        )
                        session_exh_path = paths.exhibitions / Path(rel).name
                        console.print(
                            f"[dim]  → session Exhibition created: "
                            f"[cyan]{session_exh_path.name}[/cyan][/dim]"
                        )
                    except ValueError:
                        pass  # no L3 Concepts yet — skip silently
                elif session_exh_path.exists():
                    query_module.update_curation_page(
                        paths, session_exh_path, user_input, result.answer, result.hits
                    )

    if last_answer and last_question and run_kwargs.get("save_as") is None and console.is_interactive:
        confirmed = Prompt.ask(
            "  [yellow]Save session answer to 02_Wiki?[/yellow]",
            choices=["yes", "no"],
            default="no",
        )
        if confirmed == "yes":
            try:
                category, slug = query_module.classify_wiki_topic(
                    client, last_question, last_answer
                )
                saved = query_module.save_wiki_page(
                    paths, last_question, last_answer, category, slug
                )
                callbacks.on_wiki_saved(saved, category)
            except OSError as e:
                _err(f"Failed to save wiki page: {e}")

    if create_session_exhibition and session_exh_path and session_exh_path.exists():
        if console.is_interactive:
            keep = Prompt.ask(
                f"  [yellow]Keep session Exhibition?[/yellow] "
                f"([dim]{session_exh_path.name}[/dim])",
                choices=["yes", "no"],
                default="no",
            )
            if keep == "yes":
                page = page_writer.read_page(session_exh_path)
                if page:
                    page.frontmatter["ephemeral"] = False
                    page_writer.write_page(session_exh_path, page.to_markdown())
                    _ok(f"Exhibition retained: [[{consts.LAYER_L4}/{session_exh_path.stem}]]")
            else:
                session_exh_path.unlink(missing_ok=True)
                page_writer.rebuild_index(paths, page_writer.today_iso())
        else:
            session_exh_path.unlink(missing_ok=True)
            page_writer.rebuild_index(paths, page_writer.today_iso())


@app.command()
def reindex() -> None:
    """Force a full rebuild of the QMD search index.

    Normally this runs automatically after `wiki curate`, so you only need
    this if the index gets out of sync (e.g. you edited wiki pages manually).
    """
    paths = _resolve_root_or_die()
    if not search.is_available():
        _err("qmd binary not available.")
        _hint(
            "Install it globally via npm: "
            "[bold]npm install -g @tobilu/qmd[/bold]"
        )
        raise typer.Exit(code=1)

    console.print()
    console.print("[dim]Rebuilding search index (this may take a minute)…[/dim]")
    try:
        search.update_index(paths, embed=True)
        _ok("Search index rebuilt")
    except search.SearchBackendError as e:
        _err(f"Index rebuild failed: {e}")
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Stage 5 — lint
# ---------------------------------------------------------------------------


_SEVERITY_STYLE = {
    lint_module.Severity.ERROR: ("bold red", "✗"),
    lint_module.Severity.WARNING: ("yellow", "!"),
    lint_module.Severity.INFO: ("cyan", "i"),
}


def _render_lint_report_terminal(report: lint_module.LintReport) -> None:
    """Pretty-print a LintReport to the terminal using Rich."""
    console.print()
    # Summary panel
    score = report.health_score
    score_color = "green" if score >= 80 else "yellow" if score >= 50 else "red"
    summary_lines = [
        f"[bold]Health score:[/bold] [{score_color}]{score}/100[/{score_color}]",
        f"[bold]Pages checked:[/bold] {report.pages_checked}",
        f"[bold]Duration:[/bold] {report.duration_seconds:.2f}s",
        "",
        f"  [red]{len(report.errors)} errors[/red]"
        f" · [yellow]{len(report.warnings)} warnings[/yellow]"
        f" · [cyan]{len(report.infos)} infos[/cyan]",
    ]
    if report.auto_fixed:
        summary_lines.append(f"  [green]auto-fixed: {report.auto_fixed}[/green]")
    console.print(
        Panel.fit("\n".join(summary_lines), title="Lint Report", border_style="cyan")
    )

    if not report.issues:
        console.print()
        _ok("No issues found. Your wiki is in good shape!")
        return

    # Group by severity → display
    def _render_group(
        title: str, issues: list[lint_module.LintIssue], color: str
    ) -> None:
        if not issues:
            return
        console.print()
        console.rule(f"[bold {color}]{title} ({len(issues)})[/bold {color}]")

        # Group by page for cleaner reading
        by_page: dict[str, list[lint_module.LintIssue]] = {}
        for issue in issues:
            by_page.setdefault(issue.page, []).append(issue)

        for page, page_issues in by_page.items():
            console.print(f"\n  [cyan]{page}[/cyan]")
            for issue in page_issues:
                style, glyph = _SEVERITY_STYLE[issue.severity]
                # Escape any brackets in the message since wikilinks look
                # like Rich markup tags
                from rich.markup import escape as _escape
                safe_msg = _escape(issue.message)
                safe_suggestion = _escape(issue.suggestion) if issue.suggestion else ""
                console.print(
                    f"    [{style}]{glyph}[/{style}] "
                    f"[dim]{issue.check.value}:[/dim] {safe_msg}"
                )
                if safe_suggestion:
                    console.print(f"      [dim]→ {safe_suggestion}[/dim]")
                if lint_module.is_safe_fixable(issue):
                    console.print(
                        "      [green dim]✓ safe auto-fixable[/green dim]"
                    )
                elif issue.fixable:
                    console.print(
                        "      [yellow dim]! needs review if no confident reconnect is found[/yellow dim]"
                    )

    _render_group("Errors", report.errors, "red")
    _render_group("Warnings", report.warnings, "yellow")
    _render_group("Info", report.infos, "cyan")


@app.command("lint")
def lint(
    deep: bool = typer.Option(
        False,
        "--deep",
        help="Run LLM-powered contradiction detection (slower, requires LLM).",
    ),
    fix: bool = typer.Option(
        False,
        "--fix",
        help="Auto-fix safe structural issues; unresolved broken links are kept for review.",
    ),
    save: bool = typer.Option(
        False,
        "--save",
        help="Save the report as .curator/Collections/04_Exhibitions/EXH-lint-YYYY-MM-DD.md",
    ),
    max_pairs: int = typer.Option(
        10,
        "--max-pairs",
        help="Max page pairs to check in --deep mode.",
    ),
) -> None:
    """Lint the wiki for broken links, orphans, missing pages, and more.

    Fast checks (default) run entirely in Python and finish in seconds.
    Use --deep to also scan page pairs for contradictions (requires LLM).
    """
    paths = _resolve_root_or_die()

    # Automatically refresh all manifest and log files during lint
    from . import page_writer as _pw
    from . import ingest_llm as _ingest
    today = _pw.today_iso()
    _pw.rebuild_index(paths, today)
    _ingest._update_overview(paths)
    _ingest._update_ledger(paths)
    _pw.append_log_entry(
        paths,
        today,
        "lint",
        "system",
        ["Ran wiki lint and updated all manifests"],
    )

    # Start LLM client for --deep and/or --fix
    client = None
    if deep or fix:
        config = cfg.load_config(paths)
        console.print(f"[dim]{describe_backend(config)}…[/dim]")
        try:
            client = _start_client(config)
        except Exception as e:
            if deep:
                raise
            console.print(f"[yellow]! LLM unavailable ({e}). --fix will use simple repairs only.[/yellow]")

    try:
        console.print()
        if deep:
            console.print("[dim]Running fast checks + contradiction detection…[/dim]")
        else:
            console.print("[dim]Running fast checks…[/dim]")

        def _lint_cb(node_id: str):
            console.print(f"  [dim]Linting {node_id}...[/dim]", end="\r")

        report = lint_module.run_lint(paths, deep=deep, client=client, progress_callback=_lint_cb)
        console.print(" " * 60, end="\r")

        # Auto-fix: LLM relinking first, then deterministic non-destructive fixes.
        if fix:
            llm_fixed = 0
            if client is not None:
                console.print("[dim]Running LLM-based safe link reconnection…[/dim]")
                llm_fixed = lint_module.apply_llm_fixes(paths, report.issues, client)
                if llm_fixed > 0:
                    report = lint_module.run_lint(paths, deep=False, client=None, progress_callback=_lint_cb)
                    console.print(" " * 60, end="\r")

            fixed_count = lint_module.apply_fixes(paths, report.issues)
            total_fixed = llm_fixed + fixed_count
            report.auto_fixed = total_fixed
            if fixed_count > 0:
                report = lint_module.run_lint(paths, deep=False, client=None, progress_callback=_lint_cb)
                console.print(" " * 60, end="\r")
                report.auto_fixed = total_fixed

    finally:
        if client is not None:
            client.close()

    _render_lint_report_terminal(report)

    # Save as an L4 Synthesis page
    if save:
        import uuid as _uuid
        today = lint_module.page_writer.today_iso()
        cur_id = f"EXH-lint-{today}-{_uuid.uuid4().hex[:4]}"
        target_path = paths.exhibitions / f"{cur_id}.md"
        content = lint_module.render_report_markdown(report, paths)
        lint_module.page_writer.write_page(target_path, content)
        lint_module.page_writer.rebuild_index(paths, today)
        console.print()
        _ok(f"Saved report to [cyan]{consts.LAYER_L4}/{cur_id}.md[/cyan]")

    # Exit code: 1 if there are errors, 0 otherwise (for CI use)
    if report.errors:
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# wiki config models — Discover and select Ollama models
# ---------------------------------------------------------------------------

def _show_ollama_installed(host: str, llm_cfg: dict, active_only: bool = False) -> bool:
    """Check and display installed models on an Ollama host."""
    targets = [("local", host)]

    _, configured_model = cfg.split_provider_model(
        llm_cfg.get("primary", "") if consts.BACKEND_OLLAMA in llm_cfg.get("primary", "")
        else llm_cfg.get("fallback", "")
    )
    any_found = False

    for label, h in targets:
        models_vision = list_ollama_models_with_vision(h, timeout=5.0)
        if not models_vision:
            if not active_only:
                console.print(f"\n[bold]Ollama models — {label}[/bold]  [dim]{h}[/dim]")
                _warn(f"  Ollama unreachable at {h}")
            continue

        table = Table(show_header=True, box=None, padding=(0, 2))
        table.add_column("Model", style="cyan")
        table.add_column("Vision", style="magenta")
        table.add_column("Active", style="green")
        
        found_in_target = False
        shown_active = False
        for m, vision in sorted(models_vision, key=lambda x: x[0]):
            # Strict match for active: must match configured_model exactly
            is_active = configured_model and (m == configured_model or m.startswith(configured_model + ":"))
            
            active_mark = "✓" if is_active else ""
            vision_mark = "✓" if vision else ""
            table.add_row(m, vision_mark, active_mark)
            found_in_target = True
            if is_active:
                shown_active = True
        
        # If we didn't find the configured model in Ollama's installed list, add it as a fallback row
        if configured_model and not shown_active:
            table.add_row(configured_model, "[dim]?[/dim]", "✓")
            found_in_target = True
        
        if found_in_target:
            console.print(f"\n[bold]Ollama models — {label}[/bold]  [dim]{h}[/dim]")
            console.print(table)
            any_found = True
        elif not active_only:
            console.print(f"\n[bold]Ollama models — {label}[/bold]  [dim]{h}[/dim]")
            console.print(table)
            any_found = True

    return any_found


@config_models_app.command("list")
def models_list(
    host: str = typer.Option(
        "",
        "--host",
        "-H",
        help="Ollama host URL to query (overrides config). Only used when primary provider is ollama.",
    ),
    show_all: bool = typer.Option(
        False,
        "--all",
        help="Show all recommended and available models (default: show only active).",
    ),
) -> None:
    """List models for the configured LLM provider.

    By default, only shows currently active/configured models.
    Use --all to see the full catalogue and recommendations.
    """
    import os
    env_root = os.environ.get("VAULT_ROOT")
    discovered = None
    
    if env_root:
        discovered = Path(env_root).resolve()
    else:
        # Walk up from CWD
        discovered = cfg.find_wiki_root()
        # Fallback to last successful root (same as wiki status)
        if not discovered:
            last = cfg.get_last_root()
            if last and (last / consts.INTERNAL_DIR).exists():
                discovered = last

    if discovered is not None and (discovered / consts.INTERNAL_DIR).exists():
        paths = cfg.paths_from_config(discovered)
        llm_cfg = cfg.load_config(paths).get("llm", {})
    else:
        # If still not found, we will show all recommendations
        llm_cfg = {}
        show_all = True
    
    primary_raw = llm_cfg.get("primary", "")
    primary, _ = cfg.split_provider_model(primary_raw)
    active_only = not show_all
    any_found = False

    _CLOUD_BACKENDS = (consts.BACKEND_CLAUDE_CODE, consts.BACKEND_ANTIGRAVITY_CLI, consts.BACKEND_CODEX_CLI)

    # 1. Show Primary Backend models
    if primary in _CLOUD_BACKENDS:
        any_found = _show_cloud_models(primary, llm_cfg, active_only=active_only)
    elif primary == consts.BACKEND_OLLAMA or (not primary and host):
        target_host = host or llm_cfg.get(consts.BACKEND_OLLAMA, {}).get("host", consts.DEFAULT_OLLAMA_HOST)
        any_found = _show_ollama_installed(target_host, llm_cfg, active_only=active_only)
        if not any_found and primary == consts.BACKEND_OLLAMA and not active_only:
            _hint("Start Ollama with [bold]ollama serve[/bold] or set [bold]llm.ollama.host[/bold] in config.")
    else:
        if not active_only:
            console.print("[dim]Primary backend not set. Showing all curated recommendations:[/dim]" if not primary
                          else f"[yellow]Unknown primary '{primary}'. Showing all curated recommendations.[/yellow]")

    if active_only:
        if not any_found:
            if not discovered:
                console.print(f"\n[yellow]Not inside a wiki project.[/yellow] (cwd: {Path.cwd()})")
                console.print("Use [bold]wiki config models list --all[/bold] to see all recommendations.")
            else:
                console.print("\n[bold]Current Active Configuration[/bold]")
                console.print(f"  Primary: [cyan]{primary_raw or '(not set)'}[/cyan]")
        return

    # 2. Show recommendations for other providers
    console.print("\n[bold dim]--- Recommended Models (Global) ---[/bold dim]")
    for cp in _CLOUD_BACKENDS:
        if cp != primary:
            _show_cloud_models(cp, llm_cfg)
    ollama_host = host or llm_cfg.get(consts.BACKEND_OLLAMA, {}).get("host", consts.DEFAULT_OLLAMA_HOST)
    _show_recommended_models(ollama_host)


@config_models_app.command("use")
def models_use(
    model: str = typer.Argument(
        None, help="Model tag to activate. Omit to pick interactively from the model list."
    ),
    host: str = typer.Option(
        "",
        "--host",
        "-H",
        help="Ollama host to verify model availability (default: from config). Ollama only.",
    ),
) -> None:
    """Set the active model in project config.

    For Ollama: shows recommendation list; pulls the model if not yet downloaded.
    For cloud providers (claude-code/antigravity-cli): shows curated list and saves
    the selection to the appropriate config key (e.g. claude_model, gemini_model).
    """
    import subprocess

    paths = _resolve_root_or_die()
    config = cfg.load_config(paths)
    llm_cfg = config.get("llm", {})

    primary_raw = llm_cfg.get("primary", "")
    primary, _ = cfg.split_provider_model(primary_raw)

    # --- Cloud providers ---
    if primary and primary != consts.BACKEND_OLLAMA:
        if host:
            console.print("[dim]--host is an Ollama-only option. Ignoring.[/dim]")
        if primary not in (consts.BACKEND_CLAUDE_CODE, consts.BACKEND_ANTIGRAVITY_CLI, consts.BACKEND_CODEX_CLI):
            _err(f"Unknown primary '{primary}'.")
            raise typer.Exit(code=1)

        if not model:
            model, _ = _pick_cloud_model(primary, llm_cfg)
            if not model:
                console.print("[dim]Cancelled.[/dim]")
                raise typer.Exit()
        # Write in new 'provider::model' format
        config.setdefault("llm", {})["primary"] = cfg.join_provider_model(primary, model)
        cfg.save_config(paths, config)
        _ok(
            f"Model set: [bold]{model}[/bold] "
            f"→  {paths.config_file.relative_to(paths.root)}"
        )
        _hint("Run [bold]wiki add[/bold] to start using the new model.")
        return

    # --- Ollama ---
    target_host = host or llm_cfg.get(consts.BACKEND_OLLAMA, {}).get("host", consts.DEFAULT_OLLAMA_HOST)

    # No model given → show recommendation table and prompt interactively
    if not model:
        _show_recommended_models(target_host)
        console.print()
        model = typer.prompt(
            "  Enter model tag (Enter = Cancel)",
            default="",
            show_default=False,
        ).strip()
        if not model:
            console.print("[dim]Cancelled.[/dim]")
            raise typer.Exit()

    available = list_models_on_host(target_host, timeout=5.0)

    if available:
        if not any(m == model or m.startswith(model) for m in available):
            console.print(f"[dim]Model '{model}' not found locally — pulling…[/dim]")
            try:
                subprocess.run([consts.BACKEND_OLLAMA, "pull", model], check=True)
            except FileNotFoundError:
                _warn("'ollama' CLI not found in PATH. Is Ollama installed?")
                raise typer.Exit(code=1)
            except subprocess.CalledProcessError as e:
                _warn(f"ollama pull failed (exit {e.returncode}).")
                raise typer.Exit(code=1)
            _ok(f"Pulled {model}")
        else:
            _ok(f"Verified: {model} is available on {target_host}")
    else:
        _warn(f"Ollama unreachable at {target_host} — saving model without verification.")

    config.setdefault("llm", {}).setdefault(consts.BACKEND_OLLAMA, {})["model"] = model
    cfg.save_config(paths, config)
    _ok(f"Model set to [bold]{model}[/bold] in {paths.config_file.relative_to(paths.root)}")
    _hint("Run [bold]wiki add[/bold] to start using the new model.")


# ---------------------------------------------------------------------------
# Workspace commands — curate.yml Knowledge Requirement Specification
# ---------------------------------------------------------------------------

def _csv_items(items: Optional[list[str]]) -> list[str]:
    result: list[str] = []
    for item in items or []:
        for part in item.split(","):
            part = part.strip()
            if part:
                result.append(part)
    return result


def _interactive() -> bool:
    import sys
    return bool(sys.stdin.isatty())


def _ask_source_dirs(vault_root: Path) -> list[str]:
    """Interactively select which vault directories to include. Returns fnmatch patterns."""
    raw_dirs = [consts.DIR_NOTES, consts.DIR_RESOURCES, consts.DIR_WIKI]
    available: list[tuple[str, int]] = []
    for d in raw_dirs:
        dir_path = vault_root / d
        if dir_path.exists():
            count = sum(1 for _ in dir_path.rglob("*.md"))
            if count > 0:
                available.append((d, count))

    if not available:
        return []

    console.print("\nAvailable source directories:")
    for i, (d, count) in enumerate(available):
        console.print(f"  [{i + 1}] {d}/ ({count} files)")
    sel_text = typer.prompt(
        "Include directories (comma-separated numbers, empty = all)", default=""
    )
    if not sel_text.strip():
        return []
    indices = [
        int(x.strip()) - 1
        for x in sel_text.split(",")
        if x.strip().isdigit()
    ]
    return [
        f"{available[i][0]}/**"
        for i in indices
        if 0 <= i < len(available)
    ]


def _collect_curate_template_data(
    *,
    path: Path,
    vault_root: Path,
    yes: bool,
    project: Optional[str],
    description: Optional[str],
    min_confidence: float,
) -> CurateTemplateData:
    project_default = project or default_project_name(path)
    description_default = description or f"Knowledge workspace for {project_default}"
    include_patterns: list[str] = []

    if not yes and _interactive():
        project_default = typer.prompt("Project id", default=project_default)
        description_default = typer.prompt("Description", default=description_default)
        min_confidence = float(typer.prompt("Minimum confidence", default=str(min_confidence)))
        include_patterns = _ask_source_dirs(vault_root)

    if not (0.0 <= float(min_confidence) <= 1.0):
        _err("--min-confidence must be in [0.0, 1.0].")
        raise typer.Exit(code=1)

    return CurateTemplateData(
        project=project_default,
        description=description_default,
        min_confidence=float(min_confidence),
        include_patterns=include_patterns,
    )


def _print_workspace_prepare_result(result) -> None:
    def _rel(path: Path) -> str:
        try:
            return str(path.relative_to(result.workspace))
        except ValueError:
            return str(path)

    created = [_rel(p) for p in result.created]
    updated = [_rel(p) for p in result.updated]
    preserved = [_rel(p) for p in result.preserved]

    console.print(f"[green]✓[/green] Workspace prepared at [bold]{result.workspace}[/bold]")
    console.print(f"  Agent runtime: [bold]{result.agent}[/bold]")
    if created:
        console.print(f"  Created: {', '.join(created[:8])}{' …' if len(created) > 8 else ''}")
    if updated:
        console.print(f"  Updated: {', '.join(updated[:8])}{' …' if len(updated) > 8 else ''}")
    if preserved:
        console.print(f"  Preserved existing: {', '.join(preserved[:5])}{' …' if len(preserved) > 5 else ''}")


def _print_copy_paste_prompt(agent: str, rule_file: str) -> None:
    prompt = make_integration_copy_prompt(agent, rule_file)
    console.print()
    console.print("[dim]Give this prompt to your agent to integrate Curator manually:[/dim]")
    console.print()
    for line in prompt.splitlines():
        console.print(line)
    console.print()


def _try_llm_rule_integration(
    path: Path,
    agent: str,
    paths: "cfg.WikiPaths",
    yes: bool,
) -> bool:
    """Use LLM to integrate Curator hooks into the existing agent rule file.

    Returns True if the file was successfully modified by the LLM.
    Falls back to printing a copy-paste prompt on failure or user refusal.
    """
    import difflib

    try:
        rule_file, _ = top_level_target(agent)
    except ValueError:
        return False

    rule_path = path / rule_file
    if not rule_path.exists():
        return False
    existing = rule_path.read_text(encoding="utf-8")
    if not existing.strip():
        return False

    prompt_text = make_rule_integration_prompt(existing, agent, str(path))
    modified: str | None = None
    try:
        from .llm import build_client, ChatMessage
        _config = cfg.load_config(paths)
        with build_client(_config) as _client:
            modified = _client.chat(
                [ChatMessage(role="user", content=prompt_text)],
                temperature=0.2,
            )
        modified = modified.strip()
    except Exception as exc:
        _warn(f"LLM rule integration unavailable: {exc}")
        _print_copy_paste_prompt(agent, rule_file)
        return False

    if not modified or modified == existing.strip():
        return False

    diff = list(difflib.unified_diff(
        existing.splitlines(keepends=True),
        (modified + "\n").splitlines(keepends=True),
        fromfile=f"{rule_file} (original)",
        tofile=f"{rule_file} (with Curator)",
        n=3,
    ))
    if not diff:
        return False

    console.print()
    console.print(f"[bold]Proposed changes to {rule_file}:[/bold]")
    for line in diff:
        line_stripped = line.rstrip("\n")
        if line.startswith("+") and not line.startswith("+++"):
            console.print(f"[green]{line_stripped}[/green]")
        elif line.startswith("-") and not line.startswith("---"):
            console.print(f"[red]{line_stripped}[/red]")
        else:
            console.print(line_stripped)
    console.print()

    if yes:
        do_write = True
    else:
        answer = typer.prompt(
            f"Apply Curator integration to {rule_file}?",
            default="y",
            prompt_suffix=" [Y/n]: ",
        ).strip().lower()
        do_write = answer in ("", "y", "yes")

    if do_write:
        rule_path.write_text(modified + "\n", encoding="utf-8")
        _ok(f"Integrated Curator hooks into {rule_file}.")
        return True

    _print_copy_paste_prompt(agent, rule_file)
    return False


@workspace_app.command("init")
def workspace_init(
    path: Path = typer.Argument(..., help="Path for the new workspace directory."),
    agent: str = typer.Option(
        consts.BACKEND_CLAUDE_CODE,
        "--agent",
        help="Agent runtime: codex | claude-code | antigravity | none.",
    ),
    no_rules: bool = typer.Option(
        False,
        "--no-rules",
        help="Only create/sync curate.yml; do not install agent rules.",
    ),
    force_curate: bool = typer.Option(
        False,
        "--force-curate",
        help="Overwrite curate.yml from template values.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes", "-y",
        help="Accept template defaults without prompting.",
    ),
    project: Optional[str] = typer.Option(None, "--project", help="curate.yml project id."),
    description: Optional[str] = typer.Option(None, "--description", help="curate.yml description."),
    min_confidence: float = typer.Option(0.60, "--min-confidence", help="curate.yml confidence floor."),
) -> None:
    """Scaffold or sync a workspace with curate.yml and agent rules."""
    path = path.expanduser().resolve()
    paths = _resolve_root_or_die(hint_path=path)
    project_name = project or default_project_name(path)

    # 1. Interactive agent selection (which agent rules to install)
    _agent_explicit = agent != consts.BACKEND_CLAUDE_CODE
    if not yes and _interactive() and not _agent_explicit:
        agent = typer.prompt(
            "Agent runtime",
            default=consts.BACKEND_CLAUDE_CODE,
            prompt_suffix=" [claude-code/codex/antigravity/none]: ",
        ).strip() or consts.BACKEND_CLAUDE_CODE

    if agent not in VALID_AGENTS:
        _err(f"Invalid --agent '{agent}'. Use: {' | '.join(sorted(VALID_AGENTS))}")
        raise typer.Exit(code=1)

    # 1b. Show scenario-appropriate intro message
    _scenario = detect_workspace_scenario(path, agent)
    if _scenario == "agent-only":
        console.print()
        console.print(
            f"[cyan]Found existing [bold]{agent}[/bold] setup.[/cyan] "
            "Integrating Curator knowledge navigation..."
        )
    elif _scenario == "full":
        console.print()
        console.print("[dim]Curator is already integrated here. Updating rules to latest templates.[/dim]")

    # 1c. Agent-only: try LLM-assisted integration of Curator into existing rule file
    _llm_integrated = False
    if _scenario == "agent-only" and not no_rules and agent != "none":
        _llm_integrated = _try_llm_rule_integration(
            path=path,
            agent=agent,
            paths=paths,
            yes=yes,
        )

    # 2. Artist Persona wizard → collects domain, description, topics
    #    Results populate curate.yml so manual prompts are not needed.
    persona: dict | None = None
    if not yes and _interactive():
        console.print()
        console.print("[bold]Artist Persona Setup[/bold]")
        console.print("[dim]The wizard will configure both the persona and curate.yml for this workspace.[/dim]")
        _ws_config = cfg.load_config(paths)
        try:
            _ws_client = _start_client(_ws_config)
        except (Exception, SystemExit) as _llm_exc:
            _warn(f"Could not start LLM for persona wizard: {_llm_exc}")
            _hint("Falling back to manual prompts.")
            _ws_client = None
        if _ws_client is not None:
            try:
                persona = _run_artist_persona_wizard(_ws_client, project_name)
            except (Exception, SystemExit) as _exc:
                _warn(f"Persona wizard failed: {_exc}")
                _hint("Falling back to manual prompts.")

    # 3. Build curate.yml data — from persona output or manual prompts
    if persona is not None:
        data = CurateTemplateData(
            project=project_name,
            description=persona.get("goal", f"Knowledge workspace for {path.name}"),
            min_confidence=persona.get("confidence", {}).get("low_threshold", min_confidence),
        )
        # Source selection is not part of the persona wizard — ask separately
        if not yes and _interactive():
            data.include_patterns = _ask_source_dirs(paths.root)
    else:
        # Fallback: manual prompts (--yes or LLM unavailable)
        data = _collect_curate_template_data(
            path=path,
            vault_root=paths.root,
            yes=yes,
            project=project,
            description=description,
            min_confidence=min_confidence,
        )

    # 4. Scaffold workspace files
    result = prepare_workspace(
        vault_root=paths.root,
        workspace=path,
        agent=agent,
        curate_data=data,
        force_curate=force_curate,
        install_rules=not no_rules,
        install_managed_block=not _llm_integrated,
    )
    _print_workspace_prepare_result(result)

    # 5. Save persona into curate.yml
    if persona is not None:
        try:
            import yaml as _yaml_ws
            import datetime as _dt_ws
            _curate_file = path / consts.FILE_CURATE_YML
            _raw_curate = _yaml_ws.safe_load(_curate_file.read_text(encoding="utf-8")) or {}
            persona["updated_at"] = _dt_ws.datetime.now().isoformat()
            _raw_curate["persona"] = persona
            _curate_file.write_text(
                _yaml_ws.dump(_raw_curate, sort_keys=False, default_flow_style=False, allow_unicode=True),
                encoding="utf-8",
            )
            _ok("Artist persona saved to curate.yml")
        except Exception as _save_exc:
            _warn(f"Could not save persona: {_save_exc}")

    # 6. Auto-register MCP settings for Claude Code agents
    if agent == consts.BACKEND_CLAUDE_CODE:
        try:
            from .workspace.provisioner import merge_mcp_settings
            settings_path = paths.root / ".claude" / "settings.json"
            merge_mcp_settings(settings_path, vault_root=paths.root, workspace=path)
            console.print("  [green]✓[/green] MCP settings updated at [dim].claude/settings.json[/dim]")
        except Exception as e:
            console.print(f"  [yellow]Warning:[/yellow] Could not update .claude/settings.json: {e}")
            console.print(f"  Set WORKSPACE_PATH={path} before running the MCP server to enable scoped search.")
    else:
        console.print(f"  Set WORKSPACE_PATH={path} before running the MCP server to enable scoped search.")


@workspace_app.command("list")
def workspace_list() -> None:
    """List all workspaces with curate.yml under the vault's 01_Workspaces/."""
    from .curate_yml import find_workspaces
    from rich.table import Table

    paths = _resolve_root_or_die()
    workspaces = find_workspaces(paths.root)

    if not workspaces:
        console.print("[dim]No workspaces with curate.yml found under 01_Workspaces/.[/dim]")
        console.print("  Use [bold]wiki workspace init <path>[/bold] to create one.")
        raise typer.Exit(0)

    table = Table(title="Workspaces with curate.yml", show_header=True, header_style="bold")
    table.add_column("Project", style="cyan")
    table.add_column("Path", style="dim")
    table.add_column("Domains")
    table.add_column("min_confidence")
    table.add_column("Exhibition")

    for ws_path, spec in workspaces:
        try:
            rel = ws_path.relative_to(paths.root)
        except ValueError:
            rel = ws_path
        persona_domain = spec.persona.domain or spec.persona.subdomain or ""
        domains = persona_domain if persona_domain else "[dim]—[/dim]"
        table.add_row(
            spec.project,
            str(rel),
            domains,
            f"{spec.min_confidence:.2f}",
            spec.exhibition or "[dim]—[/dim]",
        )

    console.print(table)


# ---------------------------------------------------------------------------
# wiki persona commands
# ---------------------------------------------------------------------------


@persona_app.callback(invoke_without_command=True)
def persona_main(ctx: typer.Context) -> None:
    """Show or manage the vault persona."""
    if ctx.invoked_subcommand is None:
        _show_curator_persona()


def _show_curator_persona() -> None:
    paths = _resolve_root_or_die()
    config = cfg.load_config(paths)
    persona = cfg.get_curator_persona(config)
    area = persona.get("area", "")
    text_first_line = (persona.get("text", "") or "").splitlines()[0] if persona.get("text") else ""
    typer.echo(f"Area:                  {area}")
    typer.echo(f"Description:           {text_first_line}")
    typer.echo(f"Verification:          {persona.get('verification_philosophy', '')}")
    typer.echo(f"Exhibition intent:     {persona.get('exhibition_intent', '')}")
    conf = persona.get("confidence", {})
    typer.echo(f"Confidence thresholds: high={conf.get('high_threshold', 0.85)}, low={conf.get('low_threshold', 0.55)}")
    typer.echo(f"Last updated:          {persona.get('updated_at') or '(never)'}")


@persona_app.command("update")
def persona_update(
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace name under 01_Workspaces/"),
) -> None:
    """Re-run the persona interview and update config.yml or curate.yml."""
    paths = _resolve_root_or_die()
    config = cfg.load_config(paths)
    client = _start_client(config)

    if workspace:
        ws_path = paths.root / consts.DIR_WORKSPACES / workspace
        curate_file = ws_path / consts.FILE_CURATE_YML
        if not curate_file.exists():
            typer.echo(f"No curate.yml found at {curate_file}", err=True)
            raise typer.Exit(1)
        import yaml as _yaml
        raw = _yaml.safe_load(curate_file.read_text(encoding="utf-8")) or {}
        project = raw.get("project", workspace)
        typer.echo(f"Updating Artist persona for: {project}")
        persona = _run_artist_persona_wizard(client, project)
        if persona is not None:
            import datetime as _dt
            persona["updated_at"] = _dt.datetime.now().isoformat()
            raw["persona"] = persona
            curate_file.write_text(
                _yaml.dump(raw, sort_keys=False, default_flow_style=False, allow_unicode=True),
                encoding="utf-8",
            )
            typer.echo(f"Artist persona updated in {curate_file}")
        else:
            typer.echo("Persona update skipped.")
    else:
        typer.echo("Updating Curator persona...")
        from . import ingest_llm as _il
        recent_domains = _il.read_recent_domains(paths)
        persona = _run_curator_persona_wizard(client, current_persona=config.get("persona", {}), recent_domains=recent_domains)
        if persona is not None:
            import datetime as _dt
            persona["updated_at"] = _dt.datetime.now().isoformat()
            config["persona"] = persona
            cfg.save_config(paths, config)
            typer.echo("Curator persona updated in config.yml")
        else:
            typer.echo("Persona update skipped.")


# ---------------------------------------------------------------------------
# Stage 7 — MCP server (workspace agent integration)
# ---------------------------------------------------------------------------


mcp_app = typer.Typer(
    name="mcp",
    help="Run or install the incurator MCP server for workspace agents.",
    no_args_is_help=False,
    add_completion=False,
    rich_markup_mode="rich",
    invoke_without_command=True,
)
app.add_typer(mcp_app, name="mcp")


@mcp_app.callback()
def mcp_callback(ctx: typer.Context) -> None:
    """Default `wiki mcp` (no subcommand) starts the stdio server."""
    if ctx.invoked_subcommand is not None:
        return

    # Guard: running interactively from a terminal is almost certainly a mistake.
    # Print usage instead of starting a raw JSON-RPC server into a TTY.
    import sys as _sys
    if _sys.stdin.isatty():
        console.print("[bold]wiki mcp[/bold] — Incurator MCP server (stdio transport)")
        console.print()
        console.print("This command is meant to be started by an MCP client (Claude Code,")
        console.print("Antigravity CLI, etc.), not run directly in a terminal.")
        console.print()
        console.print("[bold]Setup:[/bold]")
        console.print("  [dim]wiki mcp install[/dim]   — print config snippet to paste into your MCP client")
        console.print("  [dim]wiki mcp connect --agent claude-code --workspace <path>[/dim]")
        console.print()
        console.print("[bold]Manual start (for debugging):[/bold]")
        console.print("  [dim]VAULT_ROOT=<vault> wiki mcp 2>/dev/null[/dim]   — pipe output to an MCP client")
        raise typer.Exit(0)

    paths = _resolve_root_or_die()
    # Pin VAULT_ROOT so the server picks up the same vault even if MCP clients
    # spawn it from an unrelated cwd.
    import os as _os
    _os.environ["VAULT_ROOT"] = str(paths.root)
    try:
        from . import mcp_server
    except ImportError as e:
        _err(str(e))
        _hint("Install with: [bold]cd backend && uv pip install -e '.[mcp]'[/bold]")
        raise typer.Exit(code=1)
    mcp_server.serve_stdio()


@mcp_app.command("connect")
def mcp_connect_cmd(
    agent: str = typer.Option(
        ...,
        "--agent",
        help="Agent runtime: codex | claude-code | antigravity.",
    ),
    workspace: Path = typer.Option(
        ...,
        "--workspace",
        help="Workspace directory to connect to incurator MCP.",
    ),
    force_curate: bool = typer.Option(
        False,
        "--force-curate",
        help="Overwrite curate.yml from template values.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes", "-y",
        help="Accept template defaults without prompting.",
    ),
    project: Optional[str] = typer.Option(None, "--project", help="curate.yml project id."),
    description: Optional[str] = typer.Option(None, "--description", help="curate.yml description."),
    min_confidence: float = typer.Option(0.60, "--min-confidence", help="curate.yml confidence floor."),
) -> None:
    """Prepare workspace rules and print an MCP snippet for one agent runtime."""
    if agent == "none" or agent not in VALID_AGENTS:
        _err("Invalid --agent. Use: codex | claude-code | antigravity")
        raise typer.Exit(code=1)

    paths = _resolve_root_or_die()
    workspace = workspace.expanduser().resolve()
    data = _collect_curate_template_data(
        path=workspace,
        vault_root=paths.root,
        yes=yes,
        project=project,
        description=description,
        min_confidence=min_confidence,
    )
    result = prepare_workspace(
        vault_root=paths.root,
        workspace=workspace,
        agent=agent,
        curate_data=data,
        force_curate=force_curate,
        install_rules=True,
    )

    _print_workspace_prepare_result(result)
    console.print()
    console.print(
        Panel.fit(
            f"[bold]incurator MCP connect[/bold]\n"
            f"[dim]agent: {agent}\n"
            f"vault: {paths.root}\n"
            f"workspace: {workspace}[/dim]",
            border_style="cyan",
        )
    )
    console.print(render_mcp_snippet(vault_root=paths.root, workspace=workspace))
    console.print()
    _hint("Paste this into the selected agent's MCP settings, then restart the agent.")


@mcp_app.command("install")
def mcp_install_cmd(
    target: str = typer.Argument(
        "all",
        help="Which client to print a snippet for: claude | gemini | all.",
    ),
) -> None:
    """Print MCP config snippets to paste into your agent's settings.

    Does NOT modify any settings files — copy/paste the printed JSON into
    your client's configuration manually. Both Claude (Code / Desktop) and
    Gemini CLI use the same MCP `mcpServers` format.
    """
    paths = _resolve_root_or_die()
    try:
        from . import mcp_server
    except ImportError as e:
        _err(str(e))
        _hint("Install with: [bold]cd backend && uv pip install -e '.[mcp]'[/bold]")
        raise typer.Exit(code=1)

    snippets = mcp_server.render_install_snippets(paths)
    target = target.lower()
    if target not in (consts.CLOUD_CLAUDE, consts.CLOUD_GEMINI, "all"):
        _err(f"Unknown target '{target}'. Use claude | gemini | all.")
        raise typer.Exit(code=1)

    console.print()
    console.print(
        Panel.fit(
            f"[bold]incurator MCP install[/bold]\n[dim]vault: {paths.root}[/dim]",
            border_style="cyan",
        )
    )

    if target in (consts.CLOUD_CLAUDE, "all"):
        console.print()
        console.rule("[bold]Claude Code / Desktop[/bold]")
        console.print(
            "Paste into one of:\n"
            "  • Claude Code:    [cyan]~/.claude/settings.json[/cyan]\n"
            "  • Claude Desktop: [cyan]~/Library/Application Support/Claude/claude_desktop_config.json[/cyan] (macOS)\n"
            "                    [cyan]%APPDATA%\\Claude\\claude_desktop_config.json[/cyan] (Windows)"
        )
        console.print()
        console.print(snippets[consts.CLOUD_CLAUDE])

    if target in (consts.CLOUD_GEMINI, "all"):
        console.print()
        console.rule("[bold]Gemini CLI[/bold]")
        console.print(
            "Paste into:\n"
            "  • [cyan]~/.gemini/settings.json[/cyan]"
        )
        console.print()
        console.print(snippets[consts.CLOUD_GEMINI])

    console.print()
    _hint(
        "If your client merges with existing `mcpServers`, add only the "
        "[bold]incurator[/bold] entry."
    )
    _hint("After pasting, restart the agent so it reloads MCP config.")


def main() -> None:
    """Entry point used by the `wiki` console script."""
    app()


if __name__ == "__main__":
    main()

# ---------------------------------------------------------------------------
# Testbed Commands
# ---------------------------------------------------------------------------

@testbed_app.command(name="init")
def testbed_init(
    scenario: str = typer.Argument("testbed_template", help="Scenario name from scripts/dev/"),
    force: bool = typer.Option(False, "--force", "-f", help="Recreate the testbed."),
    llm: Optional[str] = typer.Option(None, "--llm", help="Primary LLM provider (ollama|antigravity-cli|cloud|claude-code)"),
    model: Optional[str] = typer.Option(None, "--model", help="Specific model name to use for the provider."),
):
    """Initialize a testbed vault using a specific scenario."""
    from . import testbed_manager
    try:
        root = testbed_manager.init_testbed(scenario, force=force, llm_provider=llm, llm_model=model)
        _ok(f"Testbed initialized at [bold]{root}[/bold] using scenario [cyan]{scenario}[/cyan].")
        _hint("Run commands with [bold]VAULT_ROOT=testbed wiki ...[/bold]")
    except Exception as e:
        _err(str(e))
        raise typer.Exit(1)

@testbed_app.command(name="list")
def testbed_list():
    """List available testbed scenarios."""
    from . import testbed_manager
    scenarios = testbed_manager.list_scenarios()
    if not scenarios:
        _warn("No scenarios found in scripts/dev/.")
        return

    table = Table(title="Available Testbed Scenarios", box=None)
    table.add_column("Scenario Name", style="cyan")
    for s in sorted(scenarios):
        table.add_row(s)
    console.print(table)


# ---------------------------------------------------------------------------
# benchmark commands
# ---------------------------------------------------------------------------

@benchmark_app.command(name="run")
def benchmark_run(
    scenario: str = typer.Argument("GS_Testbed", help="Testbed scenario name."),
    models: list[str] = typer.Option(
        ["gemini-flash"], "--models", "-m",
        help="Model keys to benchmark. Repeat for multiple: -m gemini-flash -m qwen2.5:7b",
    ),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Results directory."),
):
    """Run a cross-model benchmark on a testbed scenario.

    Example:
        wiki benchmark run GS_Testbed --models gemini-flash --models qwen2.5:7b
    """
    import sys as _sys
    _bench_dir = Path(__file__).resolve().parents[4] / "scripts" / "benchmark"
    if str(_bench_dir) not in _sys.path:
        _sys.path.insert(0, str(_bench_dir))

    try:
        import benchmark as _bm  # type: ignore[import]
    except ImportError as e:
        _err(f"Benchmark module not found: {e}")
        raise typer.Exit(1)

    results_dir = Path(output) if output else (Path(__file__).resolve().parents[4] / "scripts" / "benchmark" / "results")
    runs: list[_bm.BenchmarkRun] = []
    for model_key in models:
        try:
            run = _bm.run_benchmark(scenario, model_key, results_dir)
            runs.append(run)
        except Exception as e:
            _err(f"Benchmark failed for {model_key}: {e}")

    if len(runs) >= 2:
        _bm._print_comparison_table(runs)


@benchmark_app.command(name="compare")
def benchmark_compare(
    file_a: str = typer.Argument(..., help="Path to first result JSON."),
    file_b: str = typer.Argument(..., help="Path to second result JSON."),
):
    """Compare two benchmark result JSON files side-by-side."""
    import sys as _sys
    _bench_dir = Path(__file__).resolve().parents[4] / "scripts" / "benchmark"
    if str(_bench_dir) not in _sys.path:
        _sys.path.insert(0, str(_bench_dir))

    try:
        import benchmark as _bm  # type: ignore[import]
    except ImportError as e:
        _err(f"Benchmark module not found: {e}")
        raise typer.Exit(1)

    try:
        _bm.compare_runs(Path(file_a), Path(file_b))
    except Exception as e:
        _err(str(e))
        raise typer.Exit(1)
