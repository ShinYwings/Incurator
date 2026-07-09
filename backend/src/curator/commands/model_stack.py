# ruff: noqa: F403,F405
# mypy: disable-error-code=name-defined
"""Model Stack commands for the `wiki` CLI."""

from __future__ import annotations

from .common import *

models_app = typer.Typer(
    name="models",
    help="Provision the search stack (embedding + reranker GGUFs).",
    hidden=True,
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)

@models_app.command("ensure")
def models_ensure(
    serve_ollama: bool = typer.Option(True, "--serve-ollama/--no-serve-ollama", help="Auto-start Ollama if not running."),
    pull_embed: bool = typer.Option(True, "--ollama-embed/--no-ollama-embed", help="Pull an Ollama embedding model only when configured."),
    install_llama: bool = typer.Option(True, "--llama/--no-llama", help="Install llama-cpp-python (Metal on macOS)."),
    download_embedder: bool = typer.Option(True, "--embedder/--no-embedder", help="Download the embedding GGUF."),
    download_reranker: bool = typer.Option(True, "--reranker/--no-reranker", help="Download the reranker GGUF."),
    smoke: bool = typer.Option(False, "--smoke", help="Load providers and run a tiny live embedding/reranker sanity check."),
    force: bool = typer.Option(False, "--force", help="Re-download GGUF models even if present."),
) -> None:
    """Provision the v0.3.2 search stack (idempotent; safe to re-run on update).

    Installs `llama-cpp-python`, downloads the embedding + reranker GGUFs, and
    pins model paths when a vault is available. Ollama serving/pull steps are
    retained for chat and fallback embedding profiles. Every step degrades
    gracefully — search stays functional (FTS5/RRF) even if a model is
    unavailable. `setup.sh` calls this after install.
    """
    from .. import model_setup

    # Vault is optional here: `setup.sh` runs this before any vault exists. Global
    # steps (serve/pull/install/download) still run; per-vault config is persisted
    # only when a vault resolves.
    try:
        paths = _resolve_root_or_die()
    except typer.Exit:
        paths = None
    console.print()
    console.print("[dim]Provisioning search models…[/dim]")
    report = model_setup.ensure_search_models(
        paths,
        serve_ollama=serve_ollama,
        pull_embed=pull_embed,
        install_llama=install_llama,
        download_embedder=download_embedder,
        download_reranker=download_reranker,
        force=force,
    )
    _render_model_report(report)
    if smoke:
        config = cfg.load_config(paths) if paths is not None else cfg.DEFAULT_CONFIG
        smoke_report = model_setup.smoke_test_search_models(config)
        _render_model_report(smoke_report)
        report.steps.extend(smoke_report.steps)
    if report.ok:
        _ok("Search stack ready.")
    else:
        _hint("Some steps degraded — search still works (FTS5/RRF). Re-run `wiki models ensure` after fixing.")


@models_app.command("status")
def models_status() -> None:
    """Show search-stack model/dependency status as JSON."""
    from .. import model_setup

    paths = _resolve_root_or_die()
    config = cfg.load_config(paths)
    search_cfg = config.get("search", {})
    host = (config.get("llm", {}).get("ollama", {}) or {}).get("host") or consts.DEFAULT_OLLAMA_HOST
    embed_spec = str(search_cfg.get("embedding") or "")
    embed_provider, _, embed_model = embed_spec.partition("::")
    embed_path = str(search_cfg.get("embedding_model_path") or "")
    embed_cached = model_setup.models_cache_dir() / str(search_cfg.get("embedding_gguf_file") or consts.DEFAULT_EMBED_GGUF_FILE)
    reranker_spec = str(search_cfg.get("reranker") or "")
    reranker_provider, _, reranker_model = reranker_spec.partition("::")
    reranker_path = str(search_cfg.get("reranker_model_path") or "")
    reranker_cached = model_setup.models_cache_dir() / str(search_cfg.get("reranker_gguf_file") or consts.DEFAULT_RERANK_GGUF_FILE)
    ollama_models = list_models_on_host(host, timeout=3.0)
    _print_json({
        "ok": True,
        "ollamaReachable": model_setup._ollama_reachable(host),
        "embedProvider": embed_provider.strip(),
        "embedModel": embed_model.strip(),
        "embedPulled": any(
            m == embed_model.strip() or m.startswith(embed_model.split(":")[0].strip())
            for m in ollama_models
        ) if embed_provider.strip() == consts.BACKEND_OLLAMA and embed_model.strip() else False,
        "embeddingModelPath": embed_path,
        "embeddingPresent": bool((embed_path and Path(embed_path).exists()) or embed_cached.exists()),
        "llamaCppInstalled": model_setup.llama_cpp_installed(),
        "rerankerProvider": reranker_provider.strip(),
        "rerankerModel": reranker_model.strip(),
        "rerankerModelPath": reranker_path,
        "rerankerPresent": bool((reranker_path and Path(reranker_path).exists()) or reranker_cached.exists()),
        "modelsCacheDir": str(model_setup.models_cache_dir()),
    })

