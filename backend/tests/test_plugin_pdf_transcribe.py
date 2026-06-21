"""F3/F4: `wiki plugin pdf transcribe` routes interactive PDF extraction through the
dedicated vision model; CLI vision clients run serially (v0.22.0 review fixes)."""

import typer
import pytest

from curator import cli, config as cfg, ingest_raw, llm
from curator.llm import OllamaClient


class _FakeVision:
    supports_vision = True
    model = "ollama::qwen2.5-vl:7b"

    def describe_image(self, _data: bytes, prompt: str = "") -> str:
        return "$$E = mc^2$$"

    def chat(self, _messages, *, json_mode: bool = False, temperature: float = 0.3) -> str:
        return "Clean $x^2$ text"


def _patch_common(monkeypatch) -> None:
    monkeypatch.setattr(cfg, "load_config", lambda paths: {"llm": {}})
    monkeypatch.setattr(llm, "build_client", lambda c: object())
    monkeypatch.setattr(cli, "_plugin_paths", lambda w="": None)


def test_transcribe_routes_to_dedicated_vision_model(tmp_path, monkeypatch, capsys) -> None:
    png = tmp_path / "region.png"
    png.write_bytes(b"\x89PNG\r\n")
    _patch_common(monkeypatch)
    monkeypatch.setattr(ingest_raw, "_resolve_extract_client", lambda c, m: _FakeVision())

    cli.plugin_pdf_transcribe(image_file=str(png), workspace_path="")
    out = capsys.readouterr().out
    assert '"ok"' in out and "true" in out.split('"ok"')[1][:8]
    assert "mc^2" in out  # dedicated-model LaTeX body present


def test_transcribe_text_routes_to_dedicated_extract_model(monkeypatch, capsys) -> None:
    _patch_common(monkeypatch)
    monkeypatch.setattr(ingest_raw, "_resolve_extract_client", lambda c, m: _FakeVision())

    cli.plugin_pdf_transcribe(image_file="", text="garbled x2 text", workspace_path="")
    out = capsys.readouterr().out
    assert '"ok"' in out and "true" in out.split('"ok"')[1][:8]
    assert "x^2" in out


def test_transcribe_errors_when_no_vision_model(tmp_path, monkeypatch, capsys) -> None:
    png = tmp_path / "region.png"
    png.write_bytes(b"\x89PNG\r\n")
    _patch_common(monkeypatch)
    monkeypatch.setattr(ingest_raw, "_resolve_extract_client", lambda c, m: None)

    with pytest.raises(typer.Exit):
        cli.plugin_pdf_transcribe(image_file=str(png), workspace_path="")
    out = capsys.readouterr().out.replace(" ", "").lower()
    assert '"ok":false' in out
    assert "novisionmodel" in out


def test_ollama_client_is_concurrency_safe_cli_clients_are_not() -> None:
    # F4: only the HTTP Ollama client opts into concurrent vision calls; the agentic
    # CLI clients (claude/agy/codex) do not → ingest runs them serially.
    assert OllamaClient.supports_concurrent_calls is True
    assert getattr(llm.ClaudeCodeClient, "supports_concurrent_calls", False) is False
    assert getattr(llm.AntigravityCliClient, "supports_concurrent_calls", False) is False
    assert getattr(llm.CodexCliClient, "supports_concurrent_calls", False) is False
