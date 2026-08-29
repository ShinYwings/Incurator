# ruff: noqa: F401
"""Shared helpers for the `wiki` CLI command modules."""

from __future__ import annotations
from .. import constants as consts
import json
import logging
import sys
import os
from importlib import resources
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from .. import __version__
from .. import config as cfg
from .. import llm_identity
from .. import db
from .. import ingest_llm
from .. import ingest_raw
from .. import lint as lint_module
from .. import query as query_module
from .. import runtime_state
from .. import search
from ..workspace.provisioner import (
    CurateTemplateData,
    default_project_name,
    detect_workspace_scenario,
    make_integration_copy_prompt,
    make_rule_integration_prompt,
    normalize_agent,
    prepare_workspace,
    render_mcp_snippet,
    top_level_target,
)
from ..llm import (
    LLMError,
    ClaudeCodeError,
    FailoverClient,
    ModelNotFound,
    OllamaNotRunning,
    _cli_installed as _cli_installed_impl,
    build_client as _build_client_impl,
    describe_backend,
    list_models_on_host as _list_models_on_host_impl,
    list_ollama_models_with_vision,
    make_client_by_key as _make_client_by_key_impl,
)
console = Console()
_log = logging.getLogger(__name__)

def _cli_override(name: str):
    cli_module = sys.modules.get("curator.cli")
    if cli_module is None:
        return None
    override = getattr(cli_module, name, None)
    current = globals().get(name)
    if override is not None and override is not current:
        return override
    return None

def _print_audit_summary(audit: dict) -> None:
    if not audit.get("ok"):
        console.print(f"[red]{audit.get('error', 'audit failed')}[/red]")
        raise typer.Exit(1)
    console.print(f"[bold]{audit['kind']}[/bold] {audit['id']}")
    synthesis = audit.get("synthesis")
    if synthesis:
        console.print(f"[cyan]Synthesis[/cyan]: {synthesis.get('title')}")
        console.print(synthesis.get("statement", ""))
    query_trace = audit.get("query_trace")
    if query_trace:
        console.print(
            f"[cyan]Trace[/cyan]: {query_trace.get('traceId')} "
            f"route={query_trace.get('route')}"
        )
        reason = query_trace.get("routeReason") or ""
        if reason:
            console.print(f"[cyan]Route reason[/cyan]: {reason}")
        # ROADMAP A7. Stored is not the same as visible: this fact was misread
        # twice from single runs, and it lived in a JSON column that only
        # `--json | jq` reached. An empty derived search query is a legitimate
        # result for a whole-corpus question, and it is NOT the same as no
        # derivation running at all -- both store an empty query, so the status
        # is what tells them apart. Print both.
        derivation = (query_trace.get("retrievalTrace") or {}).get(
            "context_service", {}
        ).get("derivation")
        if derivation:
            if derivation.get("status") == "derived":
                terms = (
                    "no search terms"
                    if derivation.get("search_query_empty")
                    else "search terms derived"
                )
                intent = derivation.get("routing_intent") or "none stated"
                console.print(
                    f"[cyan]Derivation[/cyan]: derived - {terms}, intent={intent}"
                )
            else:
                console.print(
                    "[cyan]Derivation[/cyan]: not run - routed on the raw question"
                )
    console.print(f"[cyan]Reports[/cyan]: {len(audit.get('community_reports') or [])}")
    console.print(f"[cyan]Entities[/cyan]: {len(audit.get('entities') or [])}")
    console.print(f"[cyan]Relations[/cyan]: {len(audit.get('relations') or [])}")
    console.print(f"[cyan]Knowledge units[/cyan]: {len(audit.get('knowledge_units') or [])}")
    console.print(f"[cyan]Source spans[/cyan]: {len(audit.get('source_spans') or [])}")
    console.print(f"[cyan]Prompt runs[/cyan]: {len(audit.get('prompt_runs') or [])}")
    for warning in audit.get("warnings") or []:
        console.print(f"[yellow]warning:[/yellow] {warning}")
    for warning in audit.get("dependency_warnings") or []:
        console.print(f"[yellow]dependency:[/yellow] {warning}")
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
        "why": "[#1 in Structuring & Directory Assembly] Outstanding at reassembling extracted knowledge into structured JSON or Markdown tables. Flawless at creating hierarchical directory tree structures.",
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
        tag = str(m["tag"])
        vision_badge = " [magenta]👁[/magenta]" if bool(m["vision"]) else ""
        installed_mark = "✓" if _is_installed(tag) else ""
        desc = f"{m['why']} [dim]({m['tip']})[/dim]"
        table.add_row(
            tag + vision_badge,
            str(m["size"]),
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
def _hint(text: str) -> None:
    """Print a one-liner tip in a subdued style."""
    console.print(f"[dim]💡 {text}[/dim]")
# `highlight=False` on all three: Rich's automatic highlighter colours paths and
# `key=value` pairs magenta/bright-magenta, which on a dark theme reads as RED.
# A user reading `✓ embedding-config: set embedding_model_path=/…/x.gguf` saw a
# red-looking line and asked whether setup had failed. It had not — the ✓ was
# green (`1;32`) and only the path was magenta (`35`/`95`).
#
# Severity is the marker's job here. A second, competing colour signal applied by
# a generic highlighter can only muddy it, so these lines print their text plain.
def _err(text: str) -> None:
    console.print(f"[bold red]✗[/bold red] {text}", highlight=False)
def _ok(text: str) -> None:
    console.print(f"[bold green]✓[/bold green] {text}", highlight=False)
def _warn(text: str) -> None:
    console.print(f"[bold yellow]![/bold yellow] {text}", highlight=False)
def _refresh_search_index_impl(paths: cfg.WikiPaths, *, embed: bool = True) -> None:
    """Rebuild the DB-native search index for this project (v0.3.2).

    Friendly: emits hints instead of raising. Callers (sync/ingest/lint --fix)
    are non-fatal — the source of truth is `state.sqlite` regardless. FTS5
    lexical search always works; vector embeddings degrade gracefully when the
    embedder is unavailable.
    """
    try:
        console.print("[dim]Rebuilding search index…[/dim]")
        result = search.update_index(paths, embed=embed)
        if result.degraded:
            _warn(f"Vector embedding skipped: {result.warning}")
            _ok("BM25 (FTS5) index updated")
            _hint("Vector search is stale; BM25 search remains available. Rerun `wiki reindex --embed` once the embedder is healthy.")
        else:
            _ok("Search index updated")
    except search.SearchBackendError as e:
        _warn(f"Search index update failed: {e}")
        _hint("Search may be stale; rerun later with `wiki reindex`.")
def _resolve_root_or_die_impl(hint_path: Path | None = None) -> cfg.WikiPaths:
    """Find the wiki project root from hint_path, cwd, or VAULT_ROOT env var."""
    import os
    env_root = os.environ.get("VAULT_ROOT")
    if env_root:
        root_path = Path(env_root).resolve()
        if (root_path / consts.INTERNAL_DIR / consts.SETTINGS_FILE).exists():
            # Don't persist testbed vaults to global last_root
            try:
                import yaml as _yaml
                _d = _yaml.safe_load(
                    (root_path / consts.INTERNAL_DIR / consts.SETTINGS_FILE).read_text(encoding="utf-8")
                ) or {}
                if not _d.get("testbed", False):
                    cfg.set_last_root(root_path)
            except Exception:
                _log.debug(
                    "Could not inspect VAULT_ROOT settings before recording last root",
                    exc_info=True,
                )
                cfg.set_last_root(root_path)
            return cfg.paths_from_config(root_path)

    # Discovery starts from hint_path if provided, else CWD
    root = cfg.find_wiki_root(start=hint_path)
    
    # Fallback to last_root is ONLY allowed if NO hint_path was provided
    # (e.g. running a global command from a neutral directory)
    if root is None and hint_path is None:
        last_root = cfg.get_last_root()
        if last_root and (last_root / consts.INTERNAL_DIR / consts.SETTINGS_FILE).exists():
            import yaml as _yaml
            try:
                _cfg_data = _yaml.safe_load(
                    (last_root / consts.INTERNAL_DIR / consts.SETTINGS_FILE).read_text(encoding="utf-8")
                ) or {}
            except Exception:
                _log.debug(
                    "Could not inspect last-root settings; treating it as non-testbed",
                    exc_info=True,
                )
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
    # An absolute path, not the bare name. `wiki` is frequently a shell alias or
    # a venv console script that only resolves in an interactive login shell --
    # measured here: `command -v wiki` finds nothing in a spawned process's PATH.
    # A registered server whose command cannot be found is registered and dead:
    # `agy mcp list` lists it, and the model reports that no MCP tools exist.
    # `resolve_wiki_command` already exists for exactly this reason on the
    # Obsidian install path; it falls back to the bare name when the repo-root
    # venv is genuinely absent.
    from ..mcp.server import resolve_wiki_command

    entry = {
        "command": resolve_wiki_command(),
        "args": ["mcp"],
        "env": {"VAULT_ROOT": str(vault_root)},
    }
    targets = [
        Path.home() / ".gemini" / "settings.json",
        # The file the agy CLI actually reads its MCP registry from. Measured
        # against agy 1.1.22: with `incurator` written only to the two paths
        # below, `agy mcp list` reported "No MCP servers configured" and the
        # model answered that the tools were not available. Driving `agy mcp
        # add` and diffing ~/.gemini shows the CLI writes THIS path (mirroring
        # into the antigravity one). Registering here is what made the server
        # appear in `agy mcp list` and its tools become callable.
        Path.home() / ".gemini" / "config" / "mcp_config.json",
        Path.home() / ".gemini" / consts.CLOUD_ANTIGRAVITY / "mcp_config.json",
        vault_root / ".claude" / "settings.json",
    ]
    updated = []
    for config_path in targets:
        try:
            data: dict = {}
            if config_path.exists():
                loaded = json.loads(config_path.read_text(encoding="utf-8")) or {}
                if not isinstance(loaded, dict):
                    raise ValueError("top-level JSON is not an object")
                data = loaded
            servers = data.get("mcpServers")
            if servers is None:
                servers = {}
                data["mcpServers"] = servers
            elif not isinstance(servers, dict):
                raise ValueError("mcpServers is not an object")
            servers["incurator"] = entry
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            updated.append(str(config_path))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            _warn(f"Skipped MCP config sync for {config_path}: {type(exc).__name__}: {exc}")
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
def _filter_sync_structural_issues(
    paths: cfg.WikiPaths,
    issues: list[lint_module.LintIssue],
) -> list[lint_module.LintIssue]:
    """Drop non-actionable findings from sync reports.

    L1-only Contexts are expected immediately after `wiki add`; L2/L3 may still
    be pending until `wiki build` runs, so their temporary lack of incoming DAG
    links must not block logical checks or produce persistent review reports.
    """

    context_ids_pending_l2: set[str] = set()
    try:
        with db.connect(paths.state_db) as conn:
            rows = conn.execute(
                "SELECT context_id FROM sources "
                "WHERE context_id IS NOT NULL AND context_id != '' "
                "AND l1_status = 'done' AND l2_status IN ('pending', 'running', 'skipped')"
            ).fetchall()
            context_ids_pending_l2 = {str(row["context_id"]) for row in rows}
    except Exception:
        context_ids_pending_l2 = set()

    filtered: list[lint_module.LintIssue] = []
    for issue in issues:
        check = getattr(issue.check, "value", str(issue.check))
        page = str(issue.page)
        if (
            check == "orphan_page"
            and page.startswith(f"{consts.LAYER_L1}/")
            and Path(page).stem in context_ids_pending_l2
        ):
            continue
        filtered.append(issue)
    return filtered
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

    if needs_review and not console.is_interactive:
        pass # The user can run wiki lint to see details
def _latest_sync_report_path(paths: cfg.WikiPaths) -> Path:
    return paths.sync_report
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
        show = typer.confirm("Sync report has review findings. Show them now?", default=False)
        if show:
            console.print("[dim]Review findings from the latest sync report; these are not a `wiki status` runtime error.[/dim]")
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
    counts: dict[str, dict[str, int]] = {layer: {} for layer in ("l1", "l2", "l3", "l4")}
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
    from .. import sync as sync_module

    class CliSyncCallbacks(sync_module.SyncCallbacks):
        def on_node_check(self, node_id: str):
            console.print(f"  [dim]Verifying {node_id}...[/dim]", end="\r")

        def on_node_repair(self, node_id: str, rebuilt_count: int = 0, message: str | None = None):
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
    logic_gaps: list = []
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

    structural_report.issues = _filter_sync_structural_issues(paths, structural_report.issues)
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
            # UNSET: this write is about l4 only. Without it the default None
            # clears `layer_error` — the same shared-column clobber fixed in
            # compile_global_l3 — erasing the reason the line above just wrote
            # and leaving l3_status='error' with no explanation at all.
            db.set_sources_layer_status(
                paths.state_db, source_ids, "l4", "pending", error=db.UNSET
            )
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
    """Clear stale layer errors once sync has verified the current graph.

    Clearing errors is all this does, which is what the name and the original
    docstring always claimed. It used to also promote `l3_status`/`l4_status`
    to `done` — for EVERY source with `l2_status='done'`, gated only on whether
    *any* `CON-*.md` file existed anywhere on disk. That promotion was not
    per-source and consulted no record of what a given source actually
    contributed, so a source whose L3 was genuinely `skipped` came out of sync
    indistinguishable from one the compiler had really completed.

    Layer status is computed by the compiler (SYSTEM_BEHAVIOR §26.3) and is
    already terminal and correct when `compile_global_l3` finishes. Recomputing
    it here would duplicate compile-time policy into the sync command and create
    a second place for §4.1 to drift; if a repair genuinely needs to advance a
    status, that belongs in `compile_global_l3`'s own re-run. Deleting the
    promotion also removes the last filesystem glob from status computation.
    """
    with db.connect(paths.state_db) as conn:
        stale = [
            int(row["id"])
            for row in conn.execute(
                "SELECT id FROM sources WHERE layer_error IS NOT NULL "
                "AND layer_error <> '' AND l2_status = 'done' "
                "AND l3_status <> 'error' AND l4_status <> 'error'"
            ).fetchall()
        ]
    if stale:
        db.set_sources_layer_error(paths.state_db, stale, None)
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
        consts.CLOUD_DEEPSEEK: {
            "cfg_key": "model",
            "backend": consts.BACKEND_DEEPSEEK_API,
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
                "efforts": list(model.get("efforts", []) or []),
                "default_effort": str(model.get("default_effort", "") or ""),
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
        _err(f"Unknown cloud provider '{cloud_provider}'. Use: antigravity-cli, claude-code, codex-cli, deepseek-api.")
        return False

    # Determine currently active model tags from primary/fallback values
    active_tags: set[str] = set()
    for slot in ("primary", "fallback"):
        provider_name, model_name = cfg.split_provider_model(llm_cfg.get(slot, ""))
        if provider_name == cloud_provider and model_name:
            active_tags.add(model_name)

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
    for model_info in models:
        model_tag = str(model_info["tag"])
        # Flexible match: exact or version-prefixed
        active_mark = ""
        for tag in active_tags:
            if model_tag == tag or (tag and tag.startswith(model_tag)):
                active_mark = "✓"
                break
        
        # In active_only mode, we used to 'continue' here, but the user wants to see 
        # the full list for the primary provider. We now show ALL models for the 
        # requested provider, but the caller will skip OTHER providers.
        any_shown = True
        if active_mark:
            shown_tags.add(model_tag)
        
        table.add_row(model_tag, str(model_info["desc"]), active_mark)

    # If active_only and some active tags weren't in our curated list, show them anyway
    if active_only:
        for tag in active_tags:
            if tag and tag not in shown_tags:
                table.add_row(tag, "[dim]User-defined model[/dim]", "✓")
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
def _pick_effort(entry: dict | None) -> str:
    """Prompt for a reasoning/effort level from the model entry. Returns '' when
    the model has no effort dimension (e.g. custom or Ollama models)."""
    efforts = list((entry or {}).get("efforts", []) or [])
    if not efforts:
        return ""
    if len(efforts) == 1:
        return efforts[0]

    default_effort = (entry or {}).get("default_effort", "") or efforts[0]
    default_idx = (efforts.index(default_effort) + 1) if default_effort in efforts else 1

    console.print()
    console.print("  [dim]Reasoning effort:[/dim]")
    for i, e in enumerate(efforts, 1):
        console.print(f"  [cyan]{i}[/cyan]  {e}")
    while True:
        raw = typer.prompt(
            f"Select effort (1–{len(efforts)})",
            default=str(default_idx),
        ).strip()
        try:
            idx = int(raw)
            if 1 <= idx <= len(efforts):
                return efforts[idx - 1]
        except ValueError:
            if raw in efforts:
                return raw
        console.print(f"[red]Enter a number between 1 and {len(efforts)}.[/red]")
def _pick_cloud_model(cloud_provider: str, llm_cfg: dict) -> tuple[str, str]:
    """Interactive picker for cloud provider models. Returns (model_tag, effort)."""
    models = _CLOUD_MODELS.get(cloud_provider, [])
    if not models:
        _err(f"Unknown cloud provider '{cloud_provider}'.")
        raise typer.Exit(code=1)

    console.print()
    for i, m in enumerate(models, 1):
        efforts = m.get("efforts") or []
        effort_hint = f"  [dim]({'/'.join(efforts)})[/dim]" if efforts else ""
        console.print(f"  [cyan]{i}[/cyan]  {m['tag']}  [dim]— {m['desc']}[/dim]{effort_hint}")
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
                entry = models[idx - 1]
                return entry["tag"], _pick_effort(entry)
        except ValueError:
            if raw:
                tag_map = {m["tag"]: m for m in models}
                return (raw if raw in tag_map else raw), _pick_effort(tag_map.get(raw))
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
    curated_names = [str(m["tag"]) for m in _RECOMMENDED_MODELS]
    extra_live = [m for m in live_models if m not in curated_names]
    options = curated_names + extra_live

    _curated_desc = {str(m["tag"]): f"{m['size']} · {m['tip']}" for m in _RECOMMENDED_MODELS}
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
        (consts.BACKEND_DEEPSEEK_API,  "DeepSeek API      (API key — DEEPSEEK_API_KEY)"),
    ]:
        if key == exclude:
            continue
        console.print(f"  [cyan]{n}[/cyan]  {label}")
        n += 1
    console.print()
def _pick_backend_menu(exclude: str | None = None, prompt: str = "Choice") -> str:
    """Show backend menu and return the chosen backend key."""
    _print_backend_menu(exclude)
    keys = [
        k
        for k in (
            consts.BACKEND_OLLAMA,
            consts.BACKEND_CLAUDE_CODE,
            consts.BACKEND_ANTIGRAVITY_CLI,
            consts.BACKEND_CODEX_CLI,
            consts.BACKEND_DEEPSEEK_API,
        )
        if k != exclude
    ]
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
def _ensure_npm_impl(install_cmd: str) -> bool:
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
        except OSError as exc:
            _warn(f"NVM installer could not start: {exc}")

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


    elif backend == consts.BACKEND_DEEPSEEK_API:
        deepseek_cfg = overrides.setdefault(consts.BACKEND_DEEPSEEK_API, {})
        base_url = typer.prompt("DeepSeek base URL", default="https://api.deepseek.com").strip()
        api_key_env = typer.prompt("DeepSeek API key env var", default="DEEPSEEK_API_KEY").strip()
        deepseek_cfg["base_url"] = base_url or "https://api.deepseek.com"
        deepseek_cfg["api_key_env"] = api_key_env or "DEEPSEEK_API_KEY"
        if not os.environ.get(deepseek_cfg["api_key_env"]):
            _hint(
                f"Set [bold]{deepseek_cfg['api_key_env']}[/bold] before running LLM tasks, "
                "or store a key with `wiki config set llm.deepseek-api.api_key <key>`."
            )
        console.print()
        console.print("[bold]deepseek-api Model Selection[/bold]")
        sel_model, sel_effort = _pick_cloud_model(backend, overrides)
        if sel_model:
            overrides["_pending_model"] = sel_model
            overrides["_pending_effort"] = sel_effort

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
                        except OSError as exc:
                            _warn(f"Could not launch '{cli_cmd}' for authentication: {exc}")
                    else:
                        _warn(f"Install failed. Run manually: {install_cmd}")
        else:
            _ok(f"'{cli_cmd}' CLI found.")

        # Offer model selection
        console.print()
        console.print(f"[bold]{backend} Model Selection[/bold]")
        sel_model, sel_effort = _pick_cloud_model(backend, overrides)
        if sel_model:
            overrides["_pending_model"] = sel_model
            overrides["_pending_effort"] = sel_effort
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
    # Step 2: Configure the primary backend (model selected inside)
    console.print(f"[dim]--- {primary} (primary) ---[/dim]")
    _configure_backend(primary, overrides)
    model = overrides.pop("_pending_model", "")
    overrides["primary"] = cfg.join_provider_model(primary, model)
    overrides["primary_effort"] = overrides.pop("_pending_effort", "")

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
        overrides["fallback_effort"] = overrides.pop("_pending_effort", "")
    else:
        overrides["fallback"] = ""
        overrides["fallback_effort"] = ""

    return overrides
def _run_curator_persona_wizard(client, current_persona: dict | None = None, recent_domains: list[str] | None = None) -> dict | None:
    """Multi-turn LLM interview to build/refine the Curator persona. Returns persona dict or None (skipped)."""
    from ..prompts import build_persona_interview_messages, PERSONA_INTERVIEW_CURATOR_OPENER
    import json as _json

    opener = PERSONA_INTERVIEW_CURATOR_OPENER
    # When refining an existing persona, show context to the LLM and user
    context_prefix = ""
    if current_persona:
        context_prefix = f"Current persona: {_json.dumps(current_persona, ensure_ascii=False)}\n"
        if recent_domains:
            context_prefix += f"Recently ingested domains: {', '.join(recent_domains)}\n"
        context_prefix += "Based on the above, I'll ask whether you'd like to refine anything.\n\n"

    opener_with_context = context_prefix + opener
    typer.echo("\n" + opener_with_context)

    # Display the opener only. Ask Q1 immediately so users do not need to type
    # a throwaway "yes" before the real interview begins.
    history: list[dict] = []
    messages = build_persona_interview_messages(history, is_workspace=False)
    try:
        first_q: str = client.chat(messages)
    except Exception as exc:
        typer.echo(f"[LLM error] {exc}")
        return None
    parsed = _parse_persona_done_response(first_q)
    if parsed is not None:
        persona = parsed.get("persona")
        if persona is None:
            typer.echo("Skipping persona setup.")
            return None
        typer.echo("Curator persona interview complete.")
        return persona
    history.append({"role": "assistant", "content": first_q})
    typer.echo(f"\nCurator: {first_q}\n")

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

        parsed = _parse_persona_done_response(content)
        if parsed is not None:
            persona = parsed.get("persona")
            if persona is None:
                typer.echo("Skipping persona setup.")
                return None
            typer.echo("Curator persona interview complete.")
            return persona

        typer.echo(f"\nCurator: {content}\n")

    typer.echo("Persona interview ended. Using default STEM persona.")
    return None
def _parse_persona_done_response(content: str) -> dict | None:
    """Parse the persona wizard's final done JSON, forgiving common LLM wrappers."""

    import json as _json
    import re as _re

    cleaned = _re.sub(r"```(?:json)?\s*|\s*```", "", content).strip()
    candidates = [cleaned]
    if cleaned.startswith("{{") and cleaned.endswith("}}"):
        candidates.append(cleaned[1:-1].strip())
    match = _re.search(r"\{.*\}", cleaned, _re.DOTALL)
    if match:
        matched = match.group().strip()
        candidates.append(matched)
        if matched.startswith("{{") and matched.endswith("}}"):
            candidates.append(matched[1:-1].strip())

    for candidate in candidates:
        try:
            parsed = _json.loads(candidate)
        except _json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and parsed.get("done"):
            return parsed
    return None
def _maybe_auto_evolve_curator_persona(
    paths: "cfg.WikiPaths",
    config: dict,
    client,
    new_domains: list[str],
) -> None:
    """Silently update Curator persona if new_domains are outside its current scope.

    Makes a single non-interactive LLM call. Updates settings.yml in-place.
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
        "Do not change confidence thresholds or output_intent unless clearly needed.\n\n"
        "Return only valid JSON — no prose, no code fences. Either null or the updated JSON."
    )
    try:
        from ..llm import ChatMessage
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
        _log.debug("Curator persona auto-evolution skipped", exc_info=True)
def _run_artist_persona_wizard(client, project: str) -> dict | None:
    """Multi-turn LLM interview to build an Artist persona. Returns persona dict or None (skipped)."""
    from ..prompts import build_persona_interview_messages, PERSONA_INTERVIEW_ARTIST_OPENER

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
    parsed = _parse_persona_done_response(first_q)
    if parsed is not None:
        persona = parsed.get("persona")
        if persona is None:
            typer.echo("Skipping persona setup.")
            return None
        typer.echo("Artist persona interview complete.")
        return persona
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

        parsed = _parse_persona_done_response(content)
        if parsed is not None:
            persona = parsed.get("persona")
            if persona is None:
                typer.echo("Skipping persona setup.")
                return None
            typer.echo("Artist persona interview complete.")
            return persona

        typer.echo(f"\nCurator: {content}\n")

    typer.echo("Persona interview ended. Artist persona not set.")
    return None
def _offer_install_impl(overrides: dict, llm_cfg: dict) -> None:
    """After wizard, offer to install CLI tools and/or pull Ollama models."""
    import subprocess
    import sys

    # These offers are interactive (typer.confirm). When stdin is not a TTY —
    # e.g. invoked as a subprocess by the Obsidian dashboard — skip them entirely
    # so the command never blocks on, or aborts at, a prompt. The provider change
    # has already been saved by the caller.
    if not sys.stdin.isatty():
        return

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
    ClaudeCodeError,
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

    from ..config import split_provider_model
    llm_cfg = config.get("llm", {})
    primary_key, _ = split_provider_model(llm_cfg.get("primary", ""))
    fallback_key, _ = split_provider_model(llm_cfg.get("fallback", ""))

    # If no explicit primary, fall back to full auto build (legacy mode).
    if not primary_key:
        client = build_client(config)
        client.ensure_ready()
        return client

    # --- Try primary ---
    p_client = make_client_by_key(primary_key, config)
    try:
        p_client.ensure_ready()
        # Primary OK.
        # If an explicit fallback is configured, build the full FailoverClient;
        # otherwise return p_client directly to avoid eagerly constructing cloud
        # clients that may require API keys the user hasn't set.
        if fallback_key:
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
                    return p_client if not fallback_key else build_client(config)
                except Exception:
                    _log.debug(
                        "Primary LLM remained unavailable after model pull",
                        exc_info=True,
                    )
                    # Fall through to the configured fallback.
            else:
                _warn(f"Pull failed. Run manually: ollama pull {model_name}")
    except _ALL_LLM_ERRORS as e:
        _err(str(e))

    # --- Primary failed, try fallback ---
    if not fallback_key:
        raise typer.Exit(code=1)

    console.print()
    if not typer.confirm(
        f"Primary ([bold]{primary_key}[/bold]) is not available. "
        f"Use fallback ([bold]{fallback_key}[/bold])?",
        default=True,
    ):
        raise typer.Exit(code=1)

    f_client = make_client_by_key(fallback_key, config)
    try:
        f_client.ensure_ready()
        _ok(f"Using fallback: [bold]{fallback_key}[/bold]")
        return f_client
    except _ALL_LLM_ERRORS as e:
        _err(f"Fallback also failed: {e}")
        raise typer.Exit(code=1)
def _start_client_impl(config: dict):
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
def _requeue_stale_sources(paths: cfg.WikiPaths, stale_files: list) -> None:
    """Mark sources of stale Collection files for L1-L4 regeneration."""
    from ..migrate import _parse_frontmatter  # noqa: PLC0415

    requeued = 0
    with db.connect(paths.state_db) as conn:
        for sf in stale_files:
            try:
                text = sf.path.read_text(encoding="utf-8-sig", errors="ignore")
                fm = _parse_frontmatter(text)
                relpath = fm.get("source_path", "")
                if not relpath:
                    continue
                # Strip wikilink brackets if present: [[path]] → path
                relpath = relpath.strip().strip("[]")
                row = conn.execute(
                    "SELECT id FROM sources WHERE relpath = ?", (relpath,)
                ).fetchone()
                if row:
                    conn.execute(
                        "UPDATE sources SET l1_status='pending', l2_status='pending', "
                        "l3_status='pending', l4_status='pending' WHERE id = ?",
                        (row["id"],),
                    )
                    requeued += 1
            except Exception as exc:
                _warn(f"Could not requeue {sf.path.name}: {exc}")

    if requeued:
        _ok(f"Re-queued {requeued} source(s) for regeneration. Run [bold]wiki build[/bold] to process them.")
    else:
        _warn("No matching source rows found for the stale files.")
def _spawn_background_worker(paths: cfg.WikiPaths) -> None:
    import subprocess
    import sys
    wiki_bin = Path(sys.executable).with_name("wiki")
    if not wiki_bin.exists():
        repo_wiki = Path(__file__).resolve().parents[3] / ".venv" / "bin" / "wiki"
        wiki_bin = repo_wiki
    try:
        # Pass VAULT_ROOT explicitly so the detached process can resolve the
        # vault root without relying on CWD discovery (which silently exits
        # when the child process CWD doesn't match `_resolve_root_or_die`).
        env = {**__import__('os').environ, "VAULT_ROOT": str(paths.root)}
        subprocess.Popen(
            [str(wiki_bin), "jobs", "run"],
            cwd=str(paths.root),
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            env=env,
        )
        _ok("Started detached background daemon to process jobs asynchronously.")
    except Exception as e:
        _err(f"Failed to start background daemon: {e}")
_AUTO_EXPORT_DEFERRED = False
def _maybe_auto_export_impl(paths: cfg.WikiPaths) -> None:
    """When `auto_sync.enabled` (default-on), write this device's snapshot after
    a mutating command (add/build/sync/update).

    LWW-gated: skipped when no row is newer than `last_export_ts` — changes that
    do not bump an LWW column cannot propagate to peers anyway, so re-exporting
    an identical snapshot would be pure churn. Best-effort: any failure is
    logged but never breaks the host command. The explicit `wiki db autosync`
    path is unaffected by this flag.
    """
    if _AUTO_EXPORT_DEFERRED:
        return
    try:
        config = cfg.load_config(paths)
        block = config.get("auto_sync") or {}
        if not block.get("enabled"):
            return
        from curator import db_sync
        if not db_sync.local_has_unexported_changes(paths.internal, paths.state_db):
            return
        out = db_sync.export_for_device(
            paths.internal, paths.state_db, dir_name=block.get("dir", "sync")
        )
        console.print(f"[dim]Auto-sync: exported snapshot → {out.name}[/dim]")
    except Exception as e:  # pragma: no cover — defensive
        console.print(f"[dim]Auto-sync export skipped: {e}[/dim]")
_SOURCE_RETRY_LAYER_COLUMNS = ("l1_status", "l2_status", "l3_status", "l4_status")
_SOURCE_RETRY_ADD_REASONS = {"empty_file", "missing_context"}
_SOURCE_RETRY_BUILD_REASONS = {"parse_error", "llm_error", "invalid_atom_output"}
def _source_has_layer_error(row) -> bool:
    return bool(row["layer_error"]) or any(
        (row[column] or "") == "error" for column in _SOURCE_RETRY_LAYER_COLUMNS
    )
def _source_retry_is_l1(row) -> bool:
    return (row["error_reason"] or "") in _SOURCE_RETRY_ADD_REASONS or (
        row["l1_status"] or ""
    ) == "error"
def _source_retry_is_build(row) -> bool:
    if (row["error_reason"] or "") in _SOURCE_RETRY_BUILD_REASONS:
        return True
    return any((row[column] or "") == "error" for column in ("l2_status", "l3_status", "l4_status")) or (
        _source_has_layer_error(row) and not _source_retry_is_l1(row)
    )
def _load_retryable_source_rows(paths: cfg.WikiPaths, source_id: int | None):
    retryable_where = """
        (
            status = 'error'
            OR COALESCE(l1_status, '') = 'error'
            OR COALESCE(l2_status, '') = 'error'
            OR COALESCE(l3_status, '') = 'error'
            OR COALESCE(l4_status, '') = 'error'
            OR COALESCE(layer_error, '') <> ''
        )
    """
    with db.connect(paths.state_db) as conn:
        if source_id is not None:
            rows = conn.execute(
                f"SELECT * FROM sources WHERE id = ? AND {retryable_where}",
                (source_id,),
            ).fetchall()
            if rows:
                return rows
            exists = conn.execute(
                "SELECT id FROM sources WHERE id = ?",
                (source_id,),
            ).fetchone()
            if exists:
                _err(f"Source #{source_id} has no retryable error or layer error.")
            else:
                _err(f"No source with id {source_id}.")
            raise typer.Exit(code=1)
        return conn.execute(
            f"SELECT * FROM sources WHERE {retryable_where} ORDER BY id ASC"
        ).fetchall()
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
        console.print(f"[dim]  Pass 3 — synthesizing {theme_count} concept(s) into L4 Synthesis...[/dim]")

    def on_curation_drafting(self, cur_id: str, topic: str) -> None:
        console.print(f"  [magenta]creating[/magenta] [dim]synthesis[/dim] [cyan]{cur_id}[/cyan]  {topic}")
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
def _atom_display_title(paths, atom_id: str) -> str:
    """Return a short human-readable title for an Atom (H1 or ID fallback)."""
    from .. import page_writer as _pw
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
    from .. import contradiction as _cd
    from .. import page_writer as _pw
    from ..prompts import build_contradiction_resolution_messages
    from ..llm import LLMError
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
        else:
            console.print(result.answer, markup=False, highlight=False)
        console.print()

    def on_error(self, error: str) -> None:
        if self._stream_active:
            console.print()
            self._stream_active = False
        console.print()
        _err(error)
def _run_query_repl(
    paths, client, callbacks, run_kwargs, *,
    initial_question: str | None = None,
    curate_spec=None,
) -> bool:
    """Interactive REPL: ask questions until the user submits an empty line.

    If initial_question is provided, it is answered first before prompting
    for further input — so `wiki query "question"` enters the same REPL.
    Read-only with respect to the DAG: querying never creates L1-L4 nodes.
    Sessionless: answers are returned/streamed; durable artifacts come only from
    explicit promotion to 02_Wiki.
    """
    from rich.prompt import Prompt
    import uuid

    last_question: str | None = None
    last_answer: str | None = None
    last_source_span_ids: list[str] = []
    had_failure = False
    session_id = f"QRY-{uuid.uuid4().hex[:8]}"

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
        from .. import intent as intent_module

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
                            paths, last_question, last_answer, category, slug,
                            source_links=query_module.resolve_source_links(
                                paths, last_source_span_ids
                            ),
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
        if result.error:
            had_failure = True
        if result.answer:
            last_question = user_input
            last_answer = result.answer
            last_source_span_ids = result.source_span_ids

    if last_answer and last_question and console.is_interactive:
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
                    paths, last_question, last_answer, category, slug,
                    source_links=query_module.resolve_source_links(
                        paths, last_source_span_ids
                    ),
                )
                callbacks.on_wiki_saved(saved, category)
            except OSError as e:
                _err(f"Failed to save wiki page: {e}")
    return had_failure
def _render_model_report(report) -> None:
    for step in report.steps:
        if step.ok:
            _ok(f"{step.name}: {step.detail}")
        else:
            _warn(f"{step.name}: {step.detail}")
_SEVERITY_STYLE = {
    lint_module.Severity.ERROR: ("bold red", "✗"),
    lint_module.Severity.WARNING: ("yellow", "!"),
    lint_module.Severity.INFO: ("cyan", "i"),
}
def _render_lint_report_terminal_impl(report: lint_module.LintReport) -> None:
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
    ci_issues = [
        i for i in report.issues
        if i.check == lint_module.CheckId.COMPILER_INTEGRITY
    ]
    if ci_issues:
        ci_errors = sum(1 for i in ci_issues if i.severity == lint_module.Severity.ERROR)
        ci_color = "red" if ci_errors else "yellow"
        summary_lines.append(
            f"  [bold]Compiler Integrity:[/bold] "
            f"[{ci_color}]{len(ci_issues)} findings ({ci_errors} release-blocking)[/{ci_color}]"
        )
    gq_issues = [
        i for i in report.issues
        if i.check == lint_module.CheckId.GRAPH_QUALITY
    ]
    if gq_issues:
        gq_errors = sum(1 for i in gq_issues if i.severity == lint_module.Severity.ERROR)
        gq_color = "red" if gq_errors else "yellow"
        summary_lines.append(
            f"  [bold]Graph Quality:[/bold] "
            f"[{gq_color}]{len(gq_issues)} findings ({gq_errors} release-blocking)[/{gq_color}]"
        )
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
        from ..llm import build_client, ChatMessage
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
def _show_curator_persona() -> None:
    paths = _resolve_root_or_die()
    config = cfg.load_config(paths)
    persona = cfg.get_curator_persona(config)
    area = persona.get("area", "")
    text_first_line = (persona.get("text", "") or "").splitlines()[0] if persona.get("text") else ""
    typer.echo(f"Area:                  {area}")
    typer.echo(f"Description:           {text_first_line}")
    typer.echo(f"Verification:          {persona.get('verification_philosophy', '')}")
    typer.echo(f"Output intent:         {persona.get('output_intent', '')}")
    conf = persona.get("confidence", {})
    typer.echo(f"Confidence thresholds: high={conf.get('high_threshold', 0.85)}, low={conf.get('low_threshold', 0.55)}")
    typer.echo(f"Last updated:          {persona.get('updated_at') or '(never)'}")
def _print_json(payload: dict) -> None:
    console.print_json(data=payload)
def _plugin_paths_impl(workspace_path: str = "") -> cfg.WikiPaths:
    return _resolve_root_or_die(Path(workspace_path).expanduser() if workspace_path else None)


def _plugin_paths(workspace_path: str = "") -> cfg.WikiPaths:
    override = _cli_override("_plugin_paths")
    if override is not None:
        return override(workspace_path)
    return _plugin_paths_impl(workspace_path)


def _git_manager_for_plugin(workspace_path: str = ""):
    from ..git_manager import GitManager
    return GitManager(_plugin_paths(workspace_path).root)


def build_client(*args, **kwargs):
    override = _cli_override("build_client")
    if override is not None:
        return override(*args, **kwargs)
    return _build_client_impl(*args, **kwargs)


def make_client_by_key(*args, **kwargs):
    override = _cli_override("make_client_by_key")
    if override is not None:
        return override(*args, **kwargs)
    return _make_client_by_key_impl(*args, **kwargs)


def list_models_on_host(*args, **kwargs):
    override = _cli_override("list_models_on_host")
    if override is not None:
        return override(*args, **kwargs)
    return _list_models_on_host_impl(*args, **kwargs)


def _cli_installed(cmd: str) -> bool:
    override = _cli_override("_cli_installed")
    if override is not None:
        return override(cmd)
    return _cli_installed_impl(cmd)


def _refresh_search_index(paths: cfg.WikiPaths, *, embed: bool = True) -> None:
    override = _cli_override("_refresh_search_index")
    if override is not None:
        return override(paths, embed=embed)
    return _refresh_search_index_impl(paths, embed=embed)


def _resolve_root_or_die(hint_path: Path | None = None) -> cfg.WikiPaths:
    override = _cli_override("_resolve_root_or_die")
    if override is not None:
        return override(hint_path)
    return _resolve_root_or_die_impl(hint_path)


def _ensure_npm(install_cmd: str) -> bool:
    override = _cli_override("_ensure_npm")
    if override is not None:
        return override(install_cmd)
    return _ensure_npm_impl(install_cmd)


def _offer_install(overrides: dict, llm_cfg: dict) -> None:
    override = _cli_override("_offer_install")
    if override is not None:
        return override(overrides, llm_cfg)
    return _offer_install_impl(overrides, llm_cfg)


def _start_client(config: dict):
    override = _cli_override("_start_client")
    if override is not None:
        return override(config)
    return _start_client_impl(config)


def _maybe_auto_export(paths: cfg.WikiPaths) -> None:
    override = _cli_override("_maybe_auto_export")
    if override is not None:
        return override(paths)
    return _maybe_auto_export_impl(paths)


def _render_lint_report_terminal(report: lint_module.LintReport) -> None:
    override = _cli_override("_render_lint_report_terminal")
    if override is not None:
        return override(report)
    return _render_lint_report_terminal_impl(report)




def _render_search_index_gap(stats: dict) -> None:
    """Report knowledge units the vault holds but search cannot find.

    Deliberately narrow. The first version of this also listed per-layer error
    counts and "never produced anything" — then `wiki status` was actually read,
    and the **Pipeline Layer Status** table below already prints exactly that
    (`L3 | 0 done | 36 error`), and `Collections` already prints
    `L4 Synthesis/ 0`. Duplicating them made the output longer and less legible,
    with unlabelled continuation rows that did not say which layer they meant.

    The index gap is the one signal nothing showed. It was **61% of the corpus**
    when `knowledge_value_arena` measured it and 11% when this shipped, and the
    only way to see it was to query the DB by hand (ROADMAP A3/A4).

    Silent when the gap is zero: a warning that always prints is a warning nobody
    reads.
    """
    unindexed = int(stats.get("units_unindexed") or 0)
    if not unindexed:
        return
    live = int(stats.get("units_live") or 0)
    pct = f" ({unindexed / live:.0%})" if live else ""
    table = Table(title="Search index", show_header=False, box=None, padding=(0, 2))
    table.add_column(style="dim", width=22)
    table.add_column()
    table.add_row(
        "not indexed",
        f"[yellow]{unindexed}{pct} knowledge unit(s) the vault holds but "
        f"search cannot find[/yellow]",
    )
    console.print(table)


__all__ = [name for name in globals() if not name.startswith("__") or name == "__version__"]
