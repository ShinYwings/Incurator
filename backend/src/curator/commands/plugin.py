# ruff: noqa: F403,F405
# mypy: disable-error-code=name-defined
"""Plugin commands for the `wiki` CLI."""

from __future__ import annotations

import logging
import sys

from .common import *

_log = logging.getLogger(__name__)

plugin_app = typer.Typer(
    name="plugin",
    help="JSON backend API for the local Obsidian plugin.",
    hidden=True,
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)

plugin_zotero_app = typer.Typer(
    name="zotero",
    help="Read Zotero metadata and attachments for the local Obsidian plugin.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)
plugin_app.add_typer(plugin_zotero_app, name="zotero")

plugin_source_app = typer.Typer(
    name="source",
    help="Read and mutate source registry state for the local Obsidian plugin.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)
plugin_app.add_typer(plugin_source_app, name="source")

plugin_pdf_app = typer.Typer(
    name="pdf",
    help="Read PDF context and source-page search results for the local Obsidian plugin.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)
plugin_app.add_typer(plugin_pdf_app, name="pdf")

plugin_context_app = typer.Typer(name="context", no_args_is_help=True, add_completion=False)
plugin_app.add_typer(plugin_context_app, name="context")
plugin_curate_app = typer.Typer(name="curate", no_args_is_help=True, add_completion=False)
plugin_app.add_typer(plugin_curate_app, name="curate")
plugin_prompt_app = typer.Typer(name="prompt", no_args_is_help=True, add_completion=False)
plugin_app.add_typer(plugin_prompt_app, name="prompt")
plugin_insight_app = typer.Typer(name="insight", no_args_is_help=True, add_completion=False)
plugin_app.add_typer(plugin_insight_app, name="insight")
plugin_trace_app = typer.Typer(name="trace", no_args_is_help=True, add_completion=False)
plugin_app.add_typer(plugin_trace_app, name="trace")
plugin_synthesis_app = typer.Typer(name="synthesis", no_args_is_help=True, add_completion=False)
plugin_app.add_typer(plugin_synthesis_app, name="synthesis")
plugin_secret_app = typer.Typer(name="secret", no_args_is_help=True, add_completion=False)
plugin_app.add_typer(plugin_secret_app, name="secret")


@plugin_secret_app.command("set")
def plugin_secret_set(
    name: str = typer.Option(..., "--name", help="Secret name, e.g. deepseek-api-key."),
    value: str = typer.Option(..., "--value", help="Secret value to encrypt and store."),
) -> None:
    """Store a provider secret so it survives a plugin update.

    The plugin's key and the backend's are configured SEPARATELY and on purpose —
    they can be different accounts or different tiers. This command therefore
    stores under whatever name the caller gives (the plugin uses
    `obsidian-deepseek-api-key`, the backend's own `wiki config provider` uses
    `deepseek-api-key`); it shares the encryption, not the value.

    The plugin deliberately strips its API key from `data.json` (PLUGIN_SCHEMA
    §2.4) so it cannot ride Obsidian Sync or a git-tracked vault, and its only
    other restore path was `process.env`, which a GUI-launched Obsidian does not
    have. So the key was memory-only and every update lost it — reproduced
    deterministically: deploying the plugin and reloading was enough, and it
    blocked the acceptance test twice in one day.

    The value is encrypted at rest by `secret_store` under the machine-local
    `.cache/config/secrets/`. The response never echoes it back.
    """
    from .. import secret_store

    if not value.strip():
        _print_json({"ok": False, "name": name, "error": "empty secret value"})
        return
    reference = secret_store.set_secret(name, value)
    _print_json({"ok": True, "name": name, "reference": reference})


@plugin_secret_app.command("get")
def plugin_secret_get(
    name: str = typer.Option(..., "--name", help="Secret name, e.g. deepseek-api-key."),
) -> None:
    """Return a stored provider secret, or an explicit absence.

    Absence is `ok: true, present: false` rather than an error: a first run has
    no key, and the plugin needs to prompt for one rather than surface a crash.
    """
    from .. import secret_store

    try:
        value = secret_store.get_secret(f"secret:{name}")
    except Exception:  # noqa: BLE001 - absent, unreadable, or a foreign key
        _log.debug("secret %s unavailable", name, exc_info=True)
        value = ""
    _print_json({"ok": True, "name": name, "present": bool(value), "value": value})

@plugin_secret_app.command("rm")
def plugin_secret_rm(
    name: str = typer.Option(..., "--name", help="Secret name, e.g. deepseek-api-key."),
) -> None:
    """Forget a stored provider secret.

    Signing out has to reach this. Clearing the key from `data.json` alone only
    hides it: the encrypted store is a SEPARATE machine-local file, and the
    plugin restores from it at launch, so a sign-out that skips this step is
    undone by the next restart with no indication to the user.

    Deleting a key that is not there is `ok: true, deleted: false`, not an
    error — sign-out must succeed whether or not a key was ever stored.
    """
    from .. import secret_store

    try:
        deleted = secret_store.delete_secret(f"secret:{name}")
    except Exception:  # noqa: BLE001 - unreadable or foreign store
        _log.debug("secret %s not removable", name, exc_info=True)
        deleted = False
    _print_json({"ok": True, "name": name, "deleted": deleted})

plugin_correction_app = typer.Typer(name="correction", no_args_is_help=True, add_completion=False)
plugin_app.add_typer(plugin_correction_app, name="correction")
plugin_models_app = typer.Typer(name="models", no_args_is_help=True, add_completion=False)
plugin_app.add_typer(plugin_models_app, name="models")
plugin_git_app = typer.Typer(name="git", no_args_is_help=True, add_completion=False)
plugin_app.add_typer(plugin_git_app, name="git")

@plugin_app.command("version")
def plugin_version() -> None:
    """Return backend version JSON for the local plugin."""
    build: dict[str, object] = {
        "backend_version": __version__,
        "plugin_version": __version__,
        "git_commit": "",
        "schema": {
            "state_db": db.SCHEMA_VERSION,
            "vault": consts.VAULT_SCHEMA_VERSION,
        },
    }
    try:
        text = (
            resources.files("curator.data")
            .joinpath("build_manifest.json")
            .read_text(encoding="utf-8")
        )
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            build.update(parsed)
    except (OSError, json.JSONDecodeError, TypeError):
        _log.debug("Could not load packaged build manifest", exc_info=True)
    from .. import device_registry
    _print_json({
        "ok": True,
        "version": __version__,
        "repo_path": device_registry.detect_repo_root(),
        "build": build,
    })


@plugin_git_app.command("status")
def plugin_git_status(
    workspace_path: str = typer.Option("", "--workspace-path", help="Vault root override."),
) -> None:
    """Return Git/GitHub repository status JSON for the local plugin."""
    try:
        _print_json(_git_manager_for_plugin(workspace_path).status())
    except Exception as exc:
        _print_json({"ok": False, "error": str(exc)})


@plugin_git_app.command("log")
def plugin_git_log(
    limit: int = typer.Option(10, "--limit", "-n", help="Maximum commits."),
    workspace_path: str = typer.Option("", "--workspace-path", help="Vault root override."),
) -> None:
    """Return recent Git commit history JSON for the local plugin."""
    try:
        _print_json(_git_manager_for_plugin(workspace_path).recent_commits(limit=limit))
    except Exception as exc:
        _print_json({"ok": False, "error": str(exc)})


@plugin_git_app.command("diff")
def plugin_git_diff(
    stat: bool = typer.Option(False, "--stat", help="Return a capped diff stat."),
    workspace_path: str = typer.Option("", "--workspace-path", help="Vault root override."),
) -> None:
    """Return Git diff summary JSON for the local plugin."""
    try:
        # The plugin contract currently exposes a stat view only. Keep the flag
        # for command-shape parity with `git diff --stat`.
        _ = stat
        _print_json(_git_manager_for_plugin(workspace_path).diff_stat())
    except Exception as exc:
        _print_json({"ok": False, "error": str(exc)})


@plugin_git_app.command("history")
def plugin_git_history(
    file_path: str = typer.Option(..., "--file-path", help="Vault file path."),
    query: str = typer.Option("", "--query", help="Selected text or search excerpt."),
    limit: int = typer.Option(10, "--limit", "-n", help="Maximum commits."),
    workspace_path: str = typer.Option("", "--workspace-path", help="Vault root override."),
) -> None:
    """Return selected-text or file Git history JSON for the local plugin."""
    try:
        _print_json(
            _git_manager_for_plugin(workspace_path).history(
                file_path=file_path,
                query=query,
                limit=limit,
            )
        )
    except Exception as exc:
        _print_json({"ok": False, "error": str(exc)})


@plugin_git_app.command("push")
def plugin_git_push(
    workspace_path: str = typer.Option("", "--workspace-path", help="Vault root override."),
) -> None:
    """Push current branch JSON for the local plugin."""
    try:
        _print_json(_git_manager_for_plugin(workspace_path).push())
    except Exception as exc:
        _print_json({"ok": False, "error": str(exc)})


@plugin_git_app.command("commit")
def plugin_git_commit(
    message: str = typer.Option(..., "--message", "-m", help="Commit message."),
    workspace_path: str = typer.Option("", "--workspace-path", help="Vault root override."),
) -> None:
    """Create a guarded Git commit JSON for an explicit sidechat request."""
    try:
        _print_json(_git_manager_for_plugin(workspace_path).commit_all(message))
    except Exception as exc:
        _print_json({"ok": False, "error": str(exc)})


@plugin_source_app.command("status")
def plugin_source_status(
    file_hash: str = typer.Option("", "--file-hash", help="Content hash lookup."),
    source_id: Optional[int] = typer.Option(None, "--source-id", help="Source row id."),
    relpath: str = typer.Option("", "--relpath", help="Vault-relative source path."),
    source_path: str = typer.Option("", "--source-path", help="Source path."),
    file_path: str = typer.Option("", "--file-path", help="Source file path."),
    path: str = typer.Option("", "--path", help="Source path alias."),
    status_filter: str = typer.Option("", "--status", help="Optional list-mode status filter."),
    limit: int = typer.Option(50, "--limit", "-n", help="Maximum list rows."),
    workspace_path: str = typer.Option("", "--workspace-path", help="Vault root override."),
) -> None:
    """Return source status/list JSON for the local plugin."""
    from .. import plugin_api

    try:
        _print_json(
            plugin_api.source_status(
                _plugin_paths(workspace_path),
                file_hash=file_hash,
                source_id=source_id,
                relpath=relpath,
                source_path=source_path,
                file_path=file_path,
                path=path,
                status_filter=status_filter,
                limit=limit,
            )
        )
    except Exception as exc:
        _print_json({"ok": False, "error": str(exc)})
        raise typer.Exit(code=1)


@plugin_source_app.command("import")
def plugin_source_import(
    file_path: str = typer.Option("", "--file-path", help="File to import or reference."),
    zotero_attachment_key: str = typer.Option("", "--zotero-attachment-key", help="Resolve this Zotero attachment key before import."),
    zotero_custom_paths: str = typer.Option("", "--zotero-custom-paths", help="Zotero data directory or zotero.sqlite path."),
    policy: str = typer.Option("mirror_03_to_04", "--policy", help="Import policy."),
    destination: str = typer.Option("", "--destination", help="Destination relpath/folder."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Return proposal only."),
    logical_source_id: str = typer.Option("", "--logical-source-id", help="Optional logical source id."),
    workspace_path: str = typer.Option("", "--workspace-path", help="Vault root override."),
) -> None:
    """Import/reference a source and return JSON."""
    from .. import plugin_api

    try:
        _print_json(
            plugin_api.import_source(
                _plugin_paths(workspace_path),
                file_path=file_path,
                zotero_attachment_key=zotero_attachment_key,
                zotero_custom_paths=zotero_custom_paths,
                policy=policy,
                destination=destination,
                dry_run=dry_run,
                logical_source_id=logical_source_id,
            )
        )
    except Exception as exc:
        _print_json({"ok": False, "error": str(exc)})
        raise typer.Exit(code=1)


@plugin_source_app.command("register")
def plugin_source_register(
    source_id: Optional[int] = typer.Option(None, "--source-id", help="Source row id."),
    relpath: str = typer.Option("", "--relpath", help="Vault-relative source path."),
    source_path: str = typer.Option("", "--source-path", help="Source path."),
    file_path: str = typer.Option("", "--file-path", help="Source file path."),
    path: str = typer.Option("", "--path", help="Source path alias."),
    force: bool = typer.Option(False, "--force", help="Regenerate L1."),
    build: bool = typer.Option(True, "--build/--no-build", help="Queue L2/L3 build."),
    asset_dir: str = typer.Option("", "--asset-dir", help="Vault-relative folder for extracted PDF images."),
    workspace_path: str = typer.Option("", "--workspace-path", help="Vault root override."),
) -> None:
    """Register a source, generate instant L1, and optionally queue L2/L3."""
    from .. import plugin_api

    try:
        _print_json(
            plugin_api.register_source(
                _plugin_paths(workspace_path),
                source_id=source_id,
                relpath=relpath,
                source_path=source_path,
                file_path=file_path,
                path=path,
                force=force,
                build=build,
                asset_dir=asset_dir,
            )
        )
    except Exception as exc:
        _print_json({"ok": False, "error": str(exc)})
        raise typer.Exit(code=1)


@plugin_source_app.command("relocate")
def plugin_source_relocate(
    source_id: Optional[int] = typer.Option(None, "--source-id", help="Source row id."),
    from_path: str = typer.Option("", "--from", help="Current vault-relative path."),
    to_path: str = typer.Option(..., "--to", help="New vault-relative path."),
    workspace_path: str = typer.Option("", "--workspace-path", help="Vault root override."),
) -> None:
    """Record that a registered source moved inside the vault."""
    from .. import plugin_api

    try:
        _print_json(
            plugin_api.relocate_source(
                _plugin_paths(workspace_path),
                source_id=source_id,
                from_path=from_path,
                to_path=to_path,
            )
        )
    except Exception as exc:
        _print_json({"ok": False, "error": str(exc)})
        raise typer.Exit(code=1)


@plugin_source_app.command("missing")
def plugin_source_missing(
    source_id: Optional[int] = typer.Option(None, "--source-id", help="Source row id."),
    from_path: str = typer.Option("", "--from", help="Vault-relative path of the removed file."),
    restored: bool = typer.Option(False, "--restored", help="Clear the mark instead of setting it."),
    workspace_path: str = typer.Option("", "--workspace-path", help="Vault root override."),
) -> None:
    """Flag a registered source whose file left the vault (knowledge is kept)."""
    from .. import plugin_api

    try:
        _print_json(
            plugin_api.mark_source_file_missing(
                _plugin_paths(workspace_path),
                source_id=source_id,
                from_path=from_path,
                missing=not restored,
            )
        )
    except Exception as exc:
        _print_json({"ok": False, "error": str(exc)})
        raise typer.Exit(code=1)


@plugin_source_app.command("rebind")
def plugin_source_rebind(
    source_id: Optional[int] = typer.Option(None, "--source-id", help="Source row id."),
    logical_source_id: str = typer.Option("", "--logical-source-id", help="Logical source id."),
    source_path: str = typer.Option("", "--source-path", help="Source path."),
    file_path: str = typer.Option("", "--file-path", help="Source file path."),
    path: str = typer.Option("", "--path", help="Source path alias."),
    new_path: str = typer.Option(..., "--new-path", help="New source path."),
    apply: bool = typer.Option(False, "--apply", help="Apply the rebind."),
    update_hash: bool = typer.Option(True, "--update-hash/--keep-hash", help="Update content hash."),
    workspace_path: str = typer.Option("", "--workspace-path", help="Vault root override."),
) -> None:
    """Return or apply a source rebind proposal."""
    from .. import plugin_api

    try:
        _print_json(
            plugin_api.rebind_source(
                _plugin_paths(workspace_path),
                source_id=source_id,
                logical_source_id=logical_source_id,
                source_path=source_path,
                file_path=file_path,
                path=path,
                new_path=new_path,
                apply=apply,
                update_hash=update_hash,
            )
        )
    except Exception as exc:
        _print_json({"ok": False, "error": str(exc)})
        raise typer.Exit(code=1)


@plugin_pdf_app.command("context")
def plugin_pdf_context(
    file_path: str = typer.Option("", "--file-path", help="PDF file path."),
    source_id: Optional[int] = typer.Option(None, "--source-id", help="Tracked source row id."),
    relpath: str = typer.Option("", "--relpath", help="Vault-relative source relpath."),
    source_path: str = typer.Option("", "--source-path", help="Tracked source path alias."),
    file_hash: str = typer.Option("", "--file-hash", help="Tracked source content hash."),
    zotero_attachment_key: str = typer.Option("", "--zotero-attachment-key", help="Zotero attachment item key."),
    zotero_custom_paths: str = typer.Option("", "--zotero-custom-paths", help="Zotero data directory or zotero.sqlite path."),
    query: str = typer.Option("", "--query", help="Optional page scoring query."),
    page_num: int = typer.Option(0, "--page-num", help="Current 1-based page number."),
    radius: int = typer.Option(2, "--radius", help="Page window radius."),
    max_pages: int = typer.Option(8, "--max-pages", help="Maximum pages."),
    workspace_path: str = typer.Option("", "--workspace-path", help="Vault root override."),
) -> None:
    """Return PDF page-window context JSON."""
    from .. import plugin_api

    try:
        _print_json(
            plugin_api.pdf_context(
                _plugin_paths(workspace_path),
                file_path=file_path,
                source_id=source_id,
                relpath=relpath,
                source_path=source_path,
                file_hash=file_hash,
                zotero_attachment_key=zotero_attachment_key,
                zotero_custom_paths=zotero_custom_paths,
                query_text=query,
                page_num=page_num,
                radius=radius,
                max_pages=max_pages,
            )
        )
    except Exception as exc:
        _print_json({"ok": False, "error": str(exc)})
        raise typer.Exit(code=1)


@plugin_pdf_app.command("toc")
def plugin_pdf_toc(
    file_path: str = typer.Option(..., "--file-path", help="PDF file path."),
) -> None:
    """Return PDF Table of Contents (Outline) as JSON."""
    from ..parsers import pdf as pdf_parser
    from pathlib import Path as _P

    try:
        toc = pdf_parser._extract_pdf_toc(_P(file_path))
        _print_json({"ok": True, "outline": toc})
    except Exception as exc:
        _print_json({"ok": False, "error": str(exc)})
        raise typer.Exit(code=1)


@plugin_pdf_app.command("transcribe")
def plugin_pdf_transcribe(
    image_file: str = typer.Option("", "--image-file", help="Path to a PNG to transcribe to LaTeX."),
    text: str = typer.Option("", "--text", help="Raw PDF-selection text to clean up as LaTeX."),
    workspace_path: str = typer.Option("", "--workspace-path", help="Vault root override."),
    scope: str = typer.Option(
        "region",
        "--scope",
        help="'region' for a user-drawn crop, 'page' for a whole rendered page.",
    ),
) -> None:
    """Transcribe interactive PDF content to LaTeX via the dedicated extract model.

    ``--scope`` picks the prompt. The region prompt says "transcribe ONLY the
    selected PDF region", which is right for a snip and wrong for a whole page:
    handed a full page it makes the model guess which part was "selected", and
    measured on a real page it returned the visually highlighted sentence
    instead of the displayed equation that was actually being asked about.
    ``read_pdf_page_image`` (v0.55.0) sends whole pages, so it asks for ``page``.

    Resolves ``llm.latex_extract_model → llm.vision_model → main-if-vision``
    (SYSTEM_BEHAVIOR §26.2a); a configured-but-non-vision model raises. Used by the
    plugin's interactive PDF surfaces so they run on the selected PDF extraction
    model, not the plugin main chat model. JSON: ``{ok, latex, model}`` or
    ``{ok:false, error}``.
    """
    from pathlib import Path as _P

    from .. import config as _cfg
    from .. import ingest_raw as _ing
    from .. import llm as _llm
    from .. import vision as _vision

    base_client = None
    client = None
    try:
        if not image_file and not text.strip():
            _print_json({"ok": False, "error": "Provide --image-file or --text."})
            raise typer.Exit(code=1)
        paths = _plugin_paths(workspace_path)
        config = _cfg.load_config(paths)
        base_client = _llm.build_client(config)
        client = _ing._resolve_extract_client(config, base_client)
        if client is None:
            _print_json({
                "ok": False,
                "error": "No vision model configured. Set a PDF ingest or LaTeX/region "
                         "model in the Incurator Dashboard → LLM Provider card.",
            })
            raise typer.Exit(code=1)
        if image_file:
            data = _P(image_file).read_bytes()
            prompt = (
                _vision.PDF_LATEX_TRANSCRIBE_PROMPT
                if scope == "page"
                else _vision.PDF_INTERACTIVE_LATEX_TRANSCRIBE_PROMPT
            )
            raw = client.describe_image(data, prompt=prompt)
            # The page prompt does not ask for a <transcription> wrapper, so the
            # interactive normalizer (which extracts that block) would find none.
            latex = (
                _vision.normalize_vision_latex(raw)
                if scope == "page"
                else _vision.normalize_interactive_latex_transcription(raw)
            )
        else:
            latex = _vision.normalize_interactive_latex_transcription(
                client.chat(
                    [
                        _llm.ChatMessage(
                            "system",
                            "You are a LaTeX transcription assistant. The user will "
                            "give you raw text extracted from a PDF, which may contain "
                            "garbled or missing math. Convert it to clean Markdown with "
                            "proper LaTeX delimiters: inline math as $...$, display math "
                            "as $$...$$. Preserve the user's selected text faithfully. "
                            "Return exactly one <transcription>...</transcription> block "
                            "and no explanations, summaries, labels, or code fences "
                            "outside that block.",
                        ),
                        _llm.ChatMessage("user", text),
                    ],
                    temperature=0.0,
                )
            )
        _print_json({"ok": True, "latex": latex, "model": getattr(client, "model", "?")})
    except typer.Exit:
        raise
    except Exception as exc:
        _print_json({"ok": False, "error": str(exc)})
        raise typer.Exit(code=1)
    finally:
        if client is not None and callable(getattr(client, "close", None)):
            client.close()
        if base_client is not None and base_client is not client:
            close_base = getattr(base_client, "close", None)
            if callable(close_base):
                close_base()


@plugin_pdf_app.command("search")
def plugin_pdf_search(
    query: str = typer.Option(..., "--query", help="Search query."),
    source_id: Optional[int] = typer.Option(None, "--source-id", help="Source row id."),
    source_path: str = typer.Option("", "--source-path", help="Source path."),
    file_path: str = typer.Option("", "--file-path", help="Source file path."),
    path: str = typer.Option("", "--path", help="Source path alias."),
    relpath: str = typer.Option("", "--relpath", help="Vault-relative source path."),
    limit: int = typer.Option(8, "--limit", "-n", help="Maximum hits."),
    workspace_path: str = typer.Option("", "--workspace-path", help="Vault root override."),
) -> None:
    """Search tracked source pages and return JSON."""
    from .. import plugin_api

    try:
        _print_json(
            plugin_api.search_sources(
                _plugin_paths(workspace_path),
                query_text=query,
                source_id=source_id,
                source_path=source_path,
                file_path=file_path,
                path=path,
                relpath=relpath,
                limit=limit,
            )
        )
    except Exception as exc:
        _print_json({"ok": False, "error": str(exc)})
        raise typer.Exit(code=1)


@plugin_app.command("query")
def plugin_query(
    question: str = typer.Option(..., "--question", "-q", help="Question to answer."),
    input_language: str = typer.Option("", "--input-language", help="Detected original input language."),
    english_query: str = typer.Option("", "--english-query", help="English query to use for internal search/reasoning."),
    final_output_language: str = typer.Option("", "--final-output-language", help="Language for the final answer."),
    workspace_path: str = typer.Option("", "--workspace-path", help="Workspace/vault path."),
    force_new: bool = typer.Option(False, "--force-new", help="Accepted for compatibility; queries are sessionless."),
) -> None:
    """Run curator_query for the local plugin and return JSON."""
    from .. import plugin_api

    try:
        result = plugin_api.curator_query(
            _plugin_paths(workspace_path),
            question=question,
            input_language=input_language,
            english_query=english_query,
            final_output_language=final_output_language,
            workspace_path=workspace_path,
            force_new=force_new,
        )
    except Exception as exc:
        result = {"ok": False, "question": question, "error": str(exc)}
    _print_json(result)
    if not result.get("ok"):
        raise typer.Exit(code=1)


@plugin_context_app.command("fetch")
def plugin_context_fetch(
    query: str = typer.Option(..., "--query", "-q", help="Question/query to fetch context for."),
    workspace_path: str = typer.Option("", "--workspace-path", help="Workspace/vault path."),
    limit_tokens: int = typer.Option(8000, "--limit-tokens", min=1, help="Maximum backend evidence tokens."),
) -> None:
    """Return a ContextService evidence pack for local plugin provider grounding."""
    from .. import plugin_api

    try:
        _print_json(
            plugin_api.fetch_context(
                _plugin_paths(workspace_path),
                query_text=query,
                workspace_path=workspace_path,
                limit_tokens=limit_tokens,
            )
        )
    except Exception as exc:
        _print_json({"ok": False, "operation": "context_fetch", "query": query, "error": str(exc)})
        raise typer.Exit(code=1)


@plugin_context_app.command("expand")
def plugin_context_expand(
    pack_id: str = typer.Option(..., "--pack-id", help="Root ContextService pack id."),
    handle: list[str] = typer.Option(..., "--handle", help="Expansion handle to request. Repeatable."),
    expected_snapshot_id: str = typer.Option(..., "--expected-snapshot-id", help="Snapshot id from the root pack."),
    workspace_path: str = typer.Option("", "--workspace-path", help="Workspace/vault path."),
    limit_tokens: int = typer.Option(8000, "--limit-tokens", min=1, help="Maximum expansion tokens."),
) -> None:
    """Expand a ContextService pack handle for the local plugin."""
    from .. import plugin_api

    try:
        _print_json(
            plugin_api.expand_context(
                _plugin_paths(workspace_path),
                pack_id=pack_id,
                handles=list(handle),
                expected_snapshot_id=expected_snapshot_id,
                limit_tokens=limit_tokens,
            )
        )
    except Exception as exc:
        _print_json({"ok": False, "operation": "context_expand", "pack_id": pack_id, "error": str(exc)})
        raise typer.Exit(code=1)


@plugin_context_app.command("verify")
def plugin_context_verify(
    pack_id: str = typer.Option(..., "--pack-id", help="Root ContextService pack id."),
    verification_handle: str = typer.Option(..., "--verification-handle", help="Verification handle from a pack item."),
    expected_snapshot_id: str = typer.Option(..., "--expected-snapshot-id", help="Snapshot id from the root pack."),
    workspace_path: str = typer.Option("", "--workspace-path", help="Workspace/vault path."),
) -> None:
    """Verify a ContextService pack item for the local plugin."""
    from .. import plugin_api

    try:
        _print_json(
            plugin_api.verify_context(
                _plugin_paths(workspace_path),
                pack_id=pack_id,
                verification_handle=verification_handle,
                expected_snapshot_id=expected_snapshot_id,
            )
        )
    except Exception as exc:
        _print_json({"ok": False, "operation": "context_verify", "pack_id": pack_id, "error": str(exc)})
        raise typer.Exit(code=1)


@plugin_context_app.command("feedback")
def plugin_context_feedback(
    trace_id: str = typer.Option(..., "--trace-id", help="Root ContextService trace id."),
    pack_id: str = typer.Option(..., "--pack-id", help="Root ContextService pack id."),
    feedback_type: str = typer.Option(..., "--feedback-type", help="One of relevant|irrelevant|incorrect|stale|insufficient|duplicate|new_insight|correction|promotion_request."),
    statement: str = typer.Option(..., "--statement", help="User statement describing the feedback."),
    client: str = typer.Option("", "--client", help="Originating client (e.g. obsidian, mcp)."),
    purpose: str = typer.Option("", "--purpose", help="Request purpose (ground|verify|synthesize|discover)."),
    target_item_id: str = typer.Option("", "--target-item-id", help="Targeted evidence item record id."),
    target_record_id: str = typer.Option("", "--target-record-id", help="Targeted source/record id."),
    reviewed_span_id: list[str] = typer.Option([], "--reviewed-span-id", help="Reviewed source span id. Repeatable."),
    workspace_path: str = typer.Option("", "--workspace-path", help="Workspace/vault path."),
) -> None:
    """Append an append-only ContextService feedback event for the local plugin."""
    from .. import plugin_api

    target = {
        "item_id": target_item_id or None,
        "record_id": target_record_id or None,
        "claim_id": None,
    }
    try:
        _print_json(
            plugin_api.feedback_context(
                _plugin_paths(workspace_path),
                trace_id=trace_id,
                pack_id=pack_id,
                feedback_type=feedback_type,
                statement=statement,
                client=client,
                purpose=purpose,
                target=target,
                reviewed_source_span_ids=list(reviewed_span_id),
            )
        )
    except Exception as exc:
        _print_json({"ok": False, "operation": "context_feedback", "trace_id": trace_id, "pack_id": pack_id, "error": str(exc)})
        raise typer.Exit(code=1)


@plugin_app.command("promote")
def plugin_promote(
    question: str = typer.Option(..., "--question", help="The question that produced the answer."),
    answer: str = typer.Option(..., "--answer", help="The answer text to promote to 02_Wiki."),
    workspace_path: str = typer.Option("", "--workspace-path", help="Workspace/vault path."),
    source_span_ids: str = typer.Option(
        "", "--source-span-ids",
        help="JSON array of source_span_ids from the answer's query trace. When "
        "given, a ## Sources section linking the original source documents is appended.",
    ),
) -> None:
    """Promote a sessionless Q&A answer into 02_Wiki after explicit plugin user approval."""
    import json as _json

    from .. import plugin_api

    span_ids: list[str] = []
    if source_span_ids.strip():
        try:
            parsed = _json.loads(source_span_ids)
            if isinstance(parsed, list):
                span_ids = [str(s) for s in parsed]
        except (ValueError, TypeError):
            span_ids = []

    try:
        _print_json(plugin_api.promote_answer(
            _plugin_paths(workspace_path), question=question, answer=answer,
            workspace_path=workspace_path, source_span_ids=span_ids,
        ))
    except Exception as exc:
        _print_json({"ok": False, "error": str(exc)})
        raise typer.Exit(code=1)


@plugin_curate_app.command("plan")
def plugin_curate_plan(
    workspace_path: str = typer.Option(..., "--workspace-path", help="Workspace path with curate.yml."),
) -> None:
    """Compile + record the workspace curation plan; return JSON for the plugin."""
    from .. import curate_yml
    try:
        policy, spec_hash = curate_yml.resolve_curate_policy(
            workspace_path, require_spec=True
        )
        paths = _plugin_paths(workspace_path)
        plan_id = db.record_curation_plan(
            paths.state_db, workspace_id=policy.workspace_id, workspace_path=workspace_path,
            project=policy.project, curate_spec_hash=spec_hash,
            route=policy.default_route,
            source_policy={"include": list(policy.source_include), "exclude": list(policy.source_exclude)},
            retrieval_policy={"allowed_routes": sorted(policy.allowed_routes)},
            prompt_profile=policy.prompt_profile,
        )
        _print_json({
            "ok": True, "planId": plan_id, "workspaceId": policy.workspace_id,
            "curateSpecHash": spec_hash,
            "route": policy.default_route, "promptProfile": policy.prompt_profile,
            "selectedSources": list(policy.source_include),
            "excludedSources": [{"path": p, "reason": "curate.yml exclude"} for p in policy.source_exclude],
            "allowedModes": sorted(policy.allowed_routes), "knownGaps": [],
            "validationErrors": [],
        })
    except typer.Exit:
        raise
    except Exception as exc:
        _print_json({"ok": False, "error": str(exc), "validationErrors": [str(exc)]})
        raise typer.Exit(code=1)


@plugin_prompt_app.command("trace")
def plugin_prompt_trace(
    trace_id: str = typer.Option(..., "--trace-id", help="PTR- prompt trace id."),
    workspace_path: str = typer.Option("", "--workspace-path", help="Vault root override."),
) -> None:
    """Return a recorded prompt run as JSON for the plugin trace panel."""
    try:
        run = db.get_prompt_run(_plugin_paths(workspace_path).state_db, trace_id)
        if run is None:
            _print_json({"ok": False, "error": f"unknown prompt trace: {trace_id}"})
            raise typer.Exit(code=1)
        _print_json({
            "ok": True, "traceId": run["trace_id"], "promptId": run["prompt_id"],
            "promptVersion": run["prompt_version"], "family": run["family"],
            "validatorStatus": run["validator_status"], "validatorErrors": run["validator_errors"],
            "modelProvider": run["model_provider"], "modelName": run["model_name"],
        })
    except typer.Exit:
        raise
    except Exception as exc:
        _print_json({"ok": False, "error": str(exc)})
        raise typer.Exit(code=1)


@plugin_insight_app.command("list")
def plugin_insight_list(
    workspace_path: str = typer.Option("", "--workspace-path", help="Workspace path."),
    status: str = typer.Option("pending", "--status", help="Candidate status filter."),
) -> None:
    """List insight candidates as JSON for the plugin."""
    try:
        ws_id = Path(workspace_path).name if workspace_path else None
        rows = db.list_insight_candidates(_plugin_paths(workspace_path).state_db, workspace_id=ws_id, status=status)
        _print_json({"ok": True, "candidates": [
            {"id": r["id"], "classification": r["classification"], "statement": r["statement"],
             "status": r["status"], "affectedNodeIds": r["affected_node_ids"], "confidence": r["confidence"]}
            for r in rows
        ]})
    except Exception as exc:
        _print_json({"ok": False, "error": str(exc)})
        raise typer.Exit(code=1)


@plugin_insight_app.command("promote")
def plugin_insight_promote(
    insight_id: str = typer.Option(..., "--insight-id", help="INS- candidate id."),
    workspace_path: str = typer.Option("", "--workspace-path", help="Workspace path."),
) -> None:
    """Promote an insight candidate to 02_Wiki/ after explicit plugin user approval."""
    from .. import insight_lifecycle
    try:
        rel = insight_lifecycle.promote_insight(_plugin_paths(workspace_path), insight_id)
        _print_json({"ok": True, "insightId": insight_id, "promotedTo": rel})
    except Exception as exc:
        _print_json({"ok": False, "insightId": insight_id, "error": str(exc)})
        raise typer.Exit(code=1)


@plugin_insight_app.command("show")
def plugin_insight_show(
    insight_id: str = typer.Option(..., "--insight-id", help="INS- candidate id."),
    workspace_path: str = typer.Option("", "--workspace-path", help="Workspace path."),
) -> None:
    """Return one insight candidate as JSON for the plugin click-to-use panel."""
    try:
        row = db.get_insight_candidate(_plugin_paths(workspace_path).state_db, insight_id)
        if row is None:
            _print_json({"ok": False, "error": f"unknown insight: {insight_id}"})
            raise typer.Exit(code=1)
        _print_json({"ok": True, "candidate": {
            "id": row["id"], "classification": row["classification"], "statement": row["statement"],
            "status": row["status"], "affectedNodeIds": row["affected_node_ids"],
            "confidence": row["confidence"], "reason": row.get("reason", ""),
        }})
    except typer.Exit:
        raise
    except Exception as exc:
        _print_json({"ok": False, "insightId": insight_id, "error": str(exc)})
        raise typer.Exit(code=1)


@plugin_insight_app.command("reject")
def plugin_insight_reject(
    insight_id: str = typer.Option(..., "--insight-id", help="INS- candidate id."),
    reason: str = typer.Option("", "--reason", help="Optional rejection reason."),
    workspace_path: str = typer.Option("", "--workspace-path", help="Workspace path."),
) -> None:
    """Reject an insight candidate (status → rejected) after explicit plugin user action."""
    try:
        db_path = _plugin_paths(workspace_path).state_db
        if db.get_insight_candidate(db_path, insight_id) is None:
            _print_json({"ok": False, "error": f"unknown insight: {insight_id}"})
            raise typer.Exit(code=1)
        db.update_insight_candidate_status(db_path, insight_id, status="rejected")
        _print_json({"ok": True, "insightId": insight_id, "status": "rejected", "reason": reason})
    except typer.Exit:
        raise
    except Exception as exc:
        _print_json({"ok": False, "insightId": insight_id, "error": str(exc)})
        raise typer.Exit(code=1)


@plugin_trace_app.command("list")
def plugin_trace_list(
    workspace_path: str = typer.Option("", "--workspace-path", help="Workspace path."),
    limit: int = typer.Option(50, "--limit", help="Max traces (most recent first)."),
) -> None:
    """List durable QTR- query traces as JSON for the plugin Trace tab."""
    try:
        ws_id = Path(workspace_path).name if workspace_path else None
        rows = db.list_query_traces(_plugin_paths(workspace_path).state_db, workspace_id=ws_id, limit=limit)
        _print_json({"ok": True, "traces": [
            {"traceId": r["trace_id"], "route": r["route"], "createdAt": r["created_at"],
             "latencyMs": r["latency_ms"], "warnings": r["warnings"],
             "fallbackMode": (r.get("retrieval_trace") or {}).get("fallback_mode", "")}
            for r in rows
        ]})
    except Exception as exc:
        _print_json({"ok": False, "error": str(exc)})
        raise typer.Exit(code=1)


@plugin_trace_app.command("show")
def plugin_trace_show(
    trace_id: str = typer.Option(..., "--trace-id", help="QTR- query trace id."),
    workspace_path: str = typer.Option("", "--workspace-path", help="Workspace path."),
) -> None:
    """Return one QTR- query trace (route, evidence, RRF/rerank trace) as JSON."""
    try:
        row = db.get_query_trace(_plugin_paths(workspace_path).state_db, trace_id)
        if row is None:
            _print_json({"ok": False, "error": f"unknown trace: {trace_id}"})
            raise typer.Exit(code=1)
        _print_json({"ok": True, "trace": {
            "traceId": row["trace_id"], "route": row["route"], "routeReason": row["route_reason"],
            "evidence": row["evidence"], "sourceSpanIds": row["source_span_ids"],
            "synthesisNodeIds": row["synthesis_node_ids"], "communityReportIds": row["community_report_ids"],
            "retrievalTrace": row["retrieval_trace"], "warnings": row["warnings"],
            "latencyMs": row["latency_ms"], "createdAt": row["created_at"],
        }})
    except typer.Exit:
        raise
    except Exception as exc:
        _print_json({"ok": False, "traceId": trace_id, "error": str(exc)})
        raise typer.Exit(code=1)


@plugin_synthesis_app.command("list")
def plugin_synthesis_list(
    workspace_path: str = typer.Option("", "--workspace-path", help="Workspace path."),
    limit: int = typer.Option(50, "--limit", help="Max synthesis nodes."),
) -> None:
    """List L4 synthesis summaries as JSON for the plugin Synthesis tab."""
    from ..inspection import synthesis_audit

    try:
        rows = synthesis_audit.list_synthesis_summaries(
            _plugin_paths(workspace_path).state_db,
            limit=limit,
        )
        _print_json({"ok": True, "synthesis": rows})
    except Exception as exc:
        _print_json({"ok": False, "error": str(exc)})
        raise typer.Exit(code=1)


@plugin_synthesis_app.command("show")
def plugin_synthesis_show(
    synthesis_id: str = typer.Option(..., "--synthesis-id", help="SYN- synthesis id."),
    workspace_path: str = typer.Option("", "--workspace-path", help="Workspace path."),
) -> None:
    """Return one L4-to-L1 synthesis audit report for the plugin."""
    from ..inspection import synthesis_audit

    try:
        audit = synthesis_audit.build_synthesis_audit(
            _plugin_paths(workspace_path).state_db,
            synthesis_id,
        )
        if not audit.get("ok"):
            _print_json({"ok": False, "synthesisId": synthesis_id, "error": audit.get("error")})
            raise typer.Exit(code=1)
        _print_json({"ok": True, "audit": audit})
    except typer.Exit:
        raise
    except Exception as exc:
        _print_json({"ok": False, "synthesisId": synthesis_id, "error": str(exc)})
        raise typer.Exit(code=1)


@plugin_correction_app.command("propose")
def plugin_correction_propose(
    node_id: str = typer.Option(..., "--node-id", help="Generated node id the correction targets."),
    correction: str = typer.Option(..., "--correction", help="Corrected text proposed by the user."),
    previous: str = typer.Option("", "--previous", help="Optional previous text of the node."),
    workspace_path: str = typer.Option("", "--workspace-path", help="Workspace path."),
) -> None:
    """Classify a user correction proposal and return the recommended action as JSON.

    Never overwrites generated nodes. Runs the backprop classifier; the plugin
    shows the classification + any recorded insight candidate for explicit follow-up.
    """
    from .. import backprop_classifier, llm

    try:
        paths = _plugin_paths(workspace_path)
        config = cfg.load_config(paths)
        ws_id = Path(workspace_path).name if workspace_path else "default"
        event = backprop_classifier.BackpropEvent(
            previous_artifact=previous,
            updated_artifact=correction,
            human_request=correction,
            workspace_id=ws_id,
            affected_node_ids=[node_id],
        )
        with llm.build_client(config) as client:
            result = backprop_classifier.classify_feedback(paths.state_db, event, client)
        _print_json({
            "ok": result.ok,
            "nodeId": node_id,
            "classification": result.classification,
            "confidence": result.confidence,
            "recommendedAction": result.recommended_action,
            "sourceTruthImpact": result.source_truth_impact,
            "affectedNodes": result.affected_nodes,
            "reason": result.reason,
            "traceId": result.trace_id,
        })
    except Exception as exc:
        _print_json({"ok": False, "nodeId": node_id, "error": str(exc)})
        raise typer.Exit(code=1)


@plugin_models_app.command("status")
def plugin_models_status(
    workspace_path: str = typer.Option("", "--workspace-path", help="Workspace/vault path."),
) -> None:
    """Return search-model identity + health as JSON for the plugin dashboard."""
    from .. import model_setup, runtime_state

    try:
        paths = _plugin_paths(workspace_path)
        config = cfg.load_config(paths)
        search_cfg = config.get("search", {})
        host = (config.get("llm", {}).get("ollama", {}) or {}).get("host") or consts.DEFAULT_OLLAMA_HOST
        models = runtime_state._search_models_status(search_cfg)
        models["ollamaReachable"] = model_setup._ollama_reachable(host)
        models["ok"] = True
        _print_json(models)
    except Exception as exc:
        _print_json({"ok": False, "error": str(exc)})
        raise typer.Exit(code=1)


@plugin_models_app.command("refresh")
def plugin_models_refresh(
    workspace_path: str = typer.Option("", "--workspace-path", help="Workspace/vault path."),
    force: bool = typer.Option(False, "--force", help="Re-download GGUFs even if present."),
) -> None:
    """(Re)provision the search stack from the plugin and return a per-step report.

    Lets the Obsidian agent repair search when a model is missing/unhealthy:
    starts Ollama, pulls/installs, downloads GGUFs, and pins model paths.
    """
    from .. import model_setup

    try:
        paths = _plugin_paths(workspace_path)
        report = model_setup.ensure_search_models(paths, force=force)
        _print_json({
            "ok": report.ok,
            "steps": [{"name": s.name, "ok": s.ok, "detail": s.detail} for s in report.steps],
        })
    except Exception as exc:
        _print_json({"ok": False, "error": str(exc)})
        raise typer.Exit(code=1)


@plugin_models_app.command("ollama")
def plugin_models_ollama(
    workspace_path: str = typer.Option("", "--workspace-path", help="Workspace/vault path."),
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Recommended Ollama models (models.json) with local install + RAM-fit status.

    Lets the dashboard recommend Ollama models, mark which are already pulled,
    and flag the ones that fit this machine's RAM.
    """
    from .. import llm as _llm
    from ..models import load_models_catalogue

    try:
        paths = _plugin_paths(workspace_path)
        config = cfg.load_config(paths)
        host = (config.get("llm", {}).get("ollama", {}) or {}).get("host") or consts.DEFAULT_OLLAMA_HOST
        ram_gb = round(float(_llm.detect_ram_gb()), 1)
        installed = set(list_models_on_host(host, timeout=3.0) or [])

        models: list[dict] = []
        for m in load_models_catalogue().get("providers", {}).get(consts.BACKEND_OLLAMA, {}).get("models", []):
            mid = m.get("id", "")
            if not mid:
                continue
            vram = m.get("vram_gb")
            # Exact tag match when the catalogue id carries a tag (qwen2.5:7b);
            # only fall back to base-name match for untagged ids (qwen2.5).
            is_installed = mid in installed or (
                ":" not in mid and any(x.split(":")[0] == mid for x in installed)
            )
            fits = vram is None or float(vram) <= ram_gb
            models.append({
                "id": mid,
                "label": m.get("label", mid),
                "vram_gb": vram,
                "supports_vision": bool(m.get("supports_vision")),
                "installed": bool(is_installed),
                "fits_ram": bool(fits),
            })
        payload = {"ok": True, "host": host, "ram_gb": ram_gb, "models": models}
        if json_output:
            _print_json(payload)
        else:
            console.print(f"[dim]Ollama @ {host} · {ram_gb} GB RAM[/dim]")
            for m in models:
                badge = "[green]✓ installed[/green]" if m["installed"] else "[dim]· pull[/dim]"
                fit = "" if m["fits_ram"] else "  [yellow](exceeds RAM)[/yellow]"
                console.print(f"  {badge}  {m['label']} [dim][{m['id']}][/dim]{fit}")
    except Exception as exc:
        _print_json({"ok": False, "error": str(exc)})
        raise typer.Exit(code=1)


@plugin_models_app.command("pull")
def plugin_models_pull(
    model: str = typer.Option(..., "--model", help="Ollama model id to pull, e.g. qwen2.5:7b."),
    workspace_path: str = typer.Option("", "--workspace-path", help="Workspace/vault path."),
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Pull an Ollama model (`ollama pull <model>`) from the plugin dashboard."""
    import subprocess

    try:
        res = subprocess.run([consts.BACKEND_OLLAMA, "pull", model])
        ok = res.returncode == 0
        payload: dict = {"ok": ok, "model": model}
        if not ok:
            payload["error"] = f"ollama pull exited with code {res.returncode}"
        _print_json(payload)
    except Exception as exc:
        _print_json({"ok": False, "model": model, "error": str(exc)})


@plugin_zotero_app.command("status")
def zotero_status(
    custom_paths: str = typer.Option("", "--custom-paths", help="Zotero data directory or zotero.sqlite path."),
    workspace_path: str = typer.Option("", "--workspace-path", help="Vault root override."),
) -> None:
    """Return backend-owned Zotero setup diagnostics."""
    from .. import zotero_tools

    try:
        _print_json(zotero_tools.zotero_status(_plugin_paths(workspace_path), custom_paths))
    except Exception as exc:
        _print_json({"ok": False, "error": str(exc)})
        raise typer.Exit(code=1)


@plugin_zotero_app.command("init")
def zotero_init(
    data_dir: str = typer.Option("", "--data-dir", help="Zotero data directory or zotero.sqlite path."),
    linked_base_dir: str = typer.Option("", "--linked-base-dir", help="Optional linked attachment base directory."),
    custom_paths: str = typer.Option("", "--custom-paths", help="Extra Zotero data directory or sqlite candidates."),
    workspace_path: str = typer.Option("", "--workspace-path", help="Vault root override."),
) -> None:
    """Persist local Zotero roots for backend plugin commands."""
    from .. import zotero_tools

    try:
        _print_json(
            zotero_tools.zotero_init(
                _plugin_paths(workspace_path),
                data_dir=data_dir,
                linked_base_dir=linked_base_dir,
                custom_paths=custom_paths,
            )
        )
    except Exception as exc:
        _print_json({"ok": False, "error": str(exc)})
        raise typer.Exit(code=1)


@plugin_zotero_app.command("search")
def zotero_search(
    query: str = typer.Option("", "--query", "-q", help="Title/author search query."),
    custom_paths: str = typer.Option("", "--custom-paths", help="Zotero data directory or zotero.sqlite path."),
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum results."),
    workspace_path: str = typer.Option("", "--workspace-path", help="Vault root override."),
) -> None:
    """Search local Zotero items and print JSON."""
    from .. import zotero_tools

    try:
        _print_json(zotero_tools.search_items(query, custom_paths, limit=limit, paths=_plugin_paths(workspace_path)))
    except Exception as exc:
        _print_json({"ok": False, "error": str(exc)})
        raise typer.Exit(code=1)


@plugin_zotero_app.command("metadata")
def zotero_metadata(
    item_key: str = typer.Option(..., "--item-key", help="Zotero item key."),
    custom_paths: str = typer.Option("", "--custom-paths", help="Zotero data directory or zotero.sqlite path."),
    citation_style: str = typer.Option("", "--citation-style", help="Optional CSL citation style."),
    workspace_path: str = typer.Option("", "--workspace-path", help="Vault root override."),
) -> None:
    """Fetch Zotero item metadata and print JSON."""
    from .. import zotero_tools

    try:
        _print_json(
            zotero_tools.item_metadata(
                item_key,
                custom_paths,
                citation_style=citation_style,
                paths=_plugin_paths(workspace_path),
            )
        )
    except Exception as exc:
        _print_json({"ok": False, "error": str(exc)})
        raise typer.Exit(code=1)


@plugin_zotero_app.command("annotations")
def zotero_annotations(
    attachment_key: str = typer.Option(..., "--attachment-key", help="Zotero attachment item key."),
    custom_paths: str = typer.Option("", "--custom-paths", help="Zotero data directory or zotero.sqlite path."),
    workspace_path: str = typer.Option("", "--workspace-path", help="Vault root override."),
) -> None:
    """Fetch Zotero PDF annotations and print JSON."""
    from .. import zotero_tools

    paths = _plugin_paths(workspace_path)
    try:
        _print_json(zotero_tools.get_annotations(attachment_key, paths, custom_paths))
    except Exception as exc:
        _print_json({"ok": False, "error": str(exc)})
        raise typer.Exit(code=1)


@plugin_zotero_app.command("resolve-pdf")
def zotero_resolve_pdf(
    attachment_key: str = typer.Option(..., "--attachment-key", help="Zotero attachment item key."),
    custom_paths: str = typer.Option("", "--custom-paths", help="Zotero data directory or zotero.sqlite path."),
    workspace_path: str = typer.Option("", "--workspace-path", help="Vault root override."),
) -> None:
    """Resolve a Zotero PDF attachment path and print JSON."""
    from .. import zotero_tools

    paths = _plugin_paths(workspace_path)
    try:
        payload = zotero_tools.resolve_pdf(attachment_key, paths, custom_paths)
        _print_json(payload)
        if not payload.get("ok"):
            raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as exc:
        _print_json({"ok": False, "error": str(exc)})
        raise typer.Exit(code=1)


@plugin_app.command("access")
def plugin_access(
    workspace_path: str = typer.Option("", "--workspace-path", help="Vault root override."),
) -> None:
    """Report which folders Incurator can read, and which to grant when it cannot.

    The backend has always known this — `file_access.probe` classifies a path and
    `grant_root` names the folder — and nothing asked it on the user's behalf. A
    vault whose PDFs moved into a cloud folder failed with no way to learn why,
    which is the incident this command exists for.
    """
    from .. import plugin_api

    try:
        _print_json(
            {
                "ok": True,
                # The BACKEND's platform, not the plugin's. This process is the
                # one that holds (or lacks) the permission, so it is the one
                # whose OS decides what the fix even is — a macOS grant dialog
                # and a Linux chmod are not the same instruction.
                "platform": sys.platform,
                "roots": plugin_api.access_report(_plugin_paths(workspace_path)),
            }
        )
    except Exception as exc:  # noqa: BLE001 - the plugin renders whatever it gets
        _print_json({"ok": False, "error": str(exc), "platform": sys.platform, "roots": []})
