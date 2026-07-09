from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from curator import config as cfg
from curator import ingest_raw, llm
from curator.commands import model_stack, persona, plugin, workspace
from curator.workspace.provisioner import WorkspacePrepareResult


class CloseTrackingClient:
    model = "fake-model"

    def __init__(self, response: str = "Clean $x^2$ text") -> None:
        self.closed = False
        self.response = response

    def chat(self, *_args, **_kwargs) -> str:
        return self.response

    def describe_image(self, *_args, **_kwargs) -> str:
        return self.response

    def close(self) -> None:
        self.closed = True


def test_models_ensure_treats_missing_vault_as_optional(monkeypatch) -> None:
    from curator import model_setup

    seen: dict[str, object] = {}

    def missing_vault(_hint_path=None):
        raise SystemExit(1)

    def fake_ensure(paths, **_kwargs):
        seen["paths"] = paths
        return SimpleNamespace(ok=True, steps=[])

    monkeypatch.setattr(model_stack, "_resolve_root_or_die", missing_vault)
    monkeypatch.setattr(model_setup, "ensure_search_models", fake_ensure)

    model_stack.models_ensure()

    assert seen["paths"] is None


def test_persona_update_closes_started_client_on_failure(monkeypatch, tmp_path: Path) -> None:
    paths = cfg.WikiPaths(tmp_path / "vault")
    client = CloseTrackingClient()

    monkeypatch.setattr(persona, "_resolve_root_or_die", lambda: paths)
    monkeypatch.setattr(persona.cfg, "load_config", lambda _paths: {"persona": {}})
    monkeypatch.setattr(persona, "_start_client", lambda _config: client)
    monkeypatch.setattr("curator.ingest_llm.read_recent_domains", lambda _paths: [])

    def fail_wizard(*_args, **_kwargs):
        raise RuntimeError("wizard failed")

    monkeypatch.setattr(persona, "_run_curator_persona_wizard", fail_wizard)

    with pytest.raises(RuntimeError, match="wizard failed"):
        persona.persona_update(workspace=None)

    assert client.closed is True


def test_workspace_init_closes_interactive_persona_client(monkeypatch, tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    paths = cfg.WikiPaths(vault)
    workspace_path = vault / "01_Workspaces" / "Lab"
    client = CloseTrackingClient()

    monkeypatch.setattr(workspace, "_resolve_root_or_die", lambda hint_path=None: paths)
    monkeypatch.setattr(workspace, "_interactive", lambda: True)
    monkeypatch.setattr(workspace.cfg, "load_config", lambda _paths: {})
    monkeypatch.setattr(workspace, "_start_client", lambda _config: client)
    monkeypatch.setattr(
        workspace,
        "_run_artist_persona_wizard",
        lambda _client, _project: {
            "goal": "Knowledge workspace",
            "confidence": {"low_threshold": 0.7},
        },
    )
    monkeypatch.setattr(workspace, "_ask_source_dirs", lambda _root: [])
    monkeypatch.setattr(
        workspace,
        "prepare_workspace",
        lambda **kwargs: WorkspacePrepareResult(workspace=kwargs["workspace"], agent=kwargs["agent"]),
    )

    workspace.workspace_init(
        workspace_path,
        agent="none",
        no_rules=False,
        force_curate=False,
        yes=False,
        project=None,
        description=None,
        min_confidence=0.6,
    )

    assert client.closed is True


def test_plugin_pdf_transcribe_closes_base_and_extract_clients(monkeypatch, capsys) -> None:
    base_client = CloseTrackingClient()
    extract_client = CloseTrackingClient("<transcription>Clean $x^2$ text</transcription>")

    monkeypatch.setattr(plugin, "_plugin_paths", lambda _workspace_path="": None)
    monkeypatch.setattr(cfg, "load_config", lambda _paths: {"llm": {}})
    monkeypatch.setattr(llm, "build_client", lambda _config: base_client)
    monkeypatch.setattr(ingest_raw, "_resolve_extract_client", lambda _config, _base: extract_client)

    plugin.plugin_pdf_transcribe(image_file="", text="garbled x2 text", workspace_path="")

    assert '"ok": true' in capsys.readouterr().out
    assert extract_client.closed is True
    assert base_client.closed is True
