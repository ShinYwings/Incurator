"""v0.3.2: search-stack model provisioning (network/subprocess mocked)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from curator import constants as consts
from curator import model_setup
from curator.retrieval import providers


def test_models_cache_dir_env_override(monkeypatch):
    monkeypatch.setenv("INCURATOR_MODELS_DIR", "/tmp/incur-models")
    assert model_setup.models_cache_dir() == Path("/tmp/incur-models")
    monkeypatch.delenv("INCURATOR_MODELS_DIR")
    assert model_setup.models_cache_dir().name == "models"


def test_ensure_ollama_serving_already_up(monkeypatch):
    monkeypatch.setattr(model_setup, "_ollama_reachable", lambda *a, **k: True)
    step = model_setup.ensure_ollama_serving("http://x")
    assert step.ok and "already" in step.detail


def test_ensure_ollama_serving_not_installed(monkeypatch):
    monkeypatch.setattr(model_setup, "_ollama_reachable", lambda *a, **k: False)
    monkeypatch.setattr(model_setup.shutil, "which", lambda _c: None)
    step = model_setup.ensure_ollama_serving("http://x")
    assert step.ok is False and "not installed" in step.detail


def test_ensure_ollama_model_pulls_when_missing(monkeypatch):
    monkeypatch.setattr(model_setup, "_ollama_reachable", lambda *a, **k: True)
    monkeypatch.setattr(model_setup, "list_models_on_host", lambda *a, **k: ["other:latest"])
    monkeypatch.setattr(model_setup.shutil, "which", lambda _c: "/usr/bin/ollama")

    class _Res:
        returncode = 0

    calls = {}

    def _run(cmd, **kw):
        calls["cmd"] = cmd
        return _Res()

    monkeypatch.setattr(model_setup.subprocess, "run", _run)
    step = model_setup.ensure_ollama_model("http://x", "bge-m3")
    assert step.ok and calls["cmd"] == ["ollama", "pull", "bge-m3"]


def test_ensure_ollama_model_already_present(monkeypatch):
    monkeypatch.setattr(model_setup, "_ollama_reachable", lambda *a, **k: True)
    monkeypatch.setattr(model_setup, "list_models_on_host", lambda *a, **k: ["bge-m3:latest"])
    step = model_setup.ensure_ollama_model("http://x", "bge-m3")
    assert step.ok and "already" in step.detail


def test_install_llama_cpp_failure_hint_uses_repo_root_safe_commands(monkeypatch):
    monkeypatch.setattr(model_setup, "llama_cpp_installed", lambda: False)
    monkeypatch.setattr(model_setup.shutil, "which", lambda _c: "/usr/bin/uv")

    class _Res:
        returncode = 1

    monkeypatch.setattr(model_setup.subprocess, "run", lambda *a, **k: _Res())
    step = model_setup.install_llama_cpp()

    assert step.ok is False
    assert "./setup.sh" in step.detail
    # v0.53.0: the fallback command must name its target interpreter. A bare
    # `uv pip install -e './backend[rerank]'` installs into whatever environment
    # happens to be active and can leave artifacts under backend/; this repo
    # keeps every venv at the root (.venv runtime, .venv-dev checks).
    assert "backend[rerank]" in step.detail
    assert "--python" in step.detail
    assert "/.venv/bin/python" in step.detail
    assert "-e './backend" not in step.detail
    assert "run `uv pip install" not in step.detail


def test_download_gguf_skip_when_present():
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp)
        f = dest / "model.gguf"
        f.write_bytes(b"x" * 10)
        path, detail = model_setup.download_gguf("repo", "model.gguf", dest)
        assert path == f and "already" in detail


def test_download_gguf_http_error(monkeypatch):
    class _Resp:
        status_code = 404
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def iter_bytes(self, **k): return iter(())

    monkeypatch.setattr(model_setup.httpx, "stream", lambda *a, **k: _Resp())
    with tempfile.TemporaryDirectory() as tmp:
        path, detail = model_setup.download_gguf("repo", "missing.gguf", Path(tmp))
        assert path is None and "404" in detail


def test_ensure_search_models_no_vault_persists_globally(monkeypatch):
    # all global steps stubbed; paths=None must still persist global config
    monkeypatch.setattr(model_setup, "ensure_ollama_serving", lambda h, **k: model_setup.ModelStep("s", True, "ok"))
    monkeypatch.setattr(model_setup, "ensure_ollama_model", lambda h, m: model_setup.ModelStep("m", True, "ok"))
    monkeypatch.setattr(model_setup, "install_llama_cpp", lambda **k: model_setup.ModelStep("l", True, "ok"))
    monkeypatch.setattr(
        model_setup, "download_gguf",
        lambda repo, fn, d, **k: (Path("/tmp/x.gguf"), "downloaded"),
    )
    monkeypatch.setattr(model_setup.cfg, "save_global_config", lambda c: None)
    report = model_setup.ensure_search_models(None)
    assert report.ok
    assert any(s.name.startswith("embedding-gguf:") for s in report.steps)
    assert any(s.name.startswith("reranker-gguf:") for s in report.steps)
    assert any(s.name == "embedding-config" for s in report.steps)
    assert any(s.name == "reranker-config" for s in report.steps)


def test_unload_configured_ollama_models(monkeypatch):
    calls = []
    monkeypatch.setattr(
        model_setup,
        "unload_ollama_model",
        lambda host, model: calls.append((host, model)) or model_setup.ModelStep(f"u:{model}", True, "ok"),
    )
    report = model_setup.unload_configured_ollama_models({
        "llm": {
            "primary": "ollama::qwen2.5:7b",
            "fallback": "ollama::qwen2.5:7b",
            "ollama": {"host": "http://local"},
        }
    })
    assert report.ok
    assert calls == [("http://local", "qwen2.5:7b")]


def test_build_embedder_uses_cached_gguf(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        cache = Path(tmp)
        (cache / consts.DEFAULT_EMBED_GGUF_FILE).write_bytes(b"gguf")
        monkeypatch.setattr("curator.model_setup.models_cache_dir", lambda: cache)

        seen = {}

        class _FakeEmbedder:
            def __init__(self, model, model_path, **k):
                seen["model"] = model
                seen["path"] = model_path

        monkeypatch.setattr(providers, "LlamaCppEmbedder", _FakeEmbedder)
        em = providers.build_embedder(
            {"embedding": "llama-cpp::qwen3-embedding-0.6b", "embedding_model_path": ""}
        )
        assert isinstance(em, _FakeEmbedder)
        assert seen == {
            "model": "qwen3-embedding-0.6b",
            "path": str(cache / consts.DEFAULT_EMBED_GGUF_FILE),
        }


def test_build_embedder_none_when_no_cache(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setattr("curator.model_setup.models_cache_dir", lambda: Path(tmp))
        em = providers.build_embedder(
            {"embedding": "llama-cpp::qwen3-embedding-0.6b", "embedding_model_path": ""}
        )
        assert em is None


def test_build_reranker_uses_cached_gguf(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        cache = Path(tmp)
        (cache / consts.DEFAULT_RERANK_GGUF_FILE).write_bytes(b"gguf")
        monkeypatch.setattr("curator.model_setup.models_cache_dir", lambda: cache)

        seen = {}

        class _FakeReranker:
            def __init__(self, model, model_path, **k):
                seen["path"] = model_path

        monkeypatch.setattr(providers, "LlamaCppReranker", _FakeReranker)
        rr = providers.build_reranker(
            {"rerank": True, "reranker": "llama-cpp::qwen3-reranker-0.6b", "reranker_model_path": ""}
        )
        assert isinstance(rr, _FakeReranker)
        assert seen["path"] == str(cache / consts.DEFAULT_RERANK_GGUF_FILE)


def test_build_reranker_none_when_no_cache(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setattr("curator.model_setup.models_cache_dir", lambda: Path(tmp))
        rr = providers.build_reranker(
            {"rerank": True, "reranker": "llama-cpp::qwen3-reranker-0.6b", "reranker_model_path": ""}
        )
        assert rr is None


def test_smoke_test_search_models(monkeypatch):
    class _Embedder:
        provider = "llama-cpp"
        model = "qwen3-embedding-0.6b"
        dim = 2

        @property
        def fingerprint(self): return "llama-cpp::qwen3-embedding-0.6b::2"
        def embed(self, texts):
            return [[1.0, 0.0] if "China" in t or "Beijing" in t else [0.0, 1.0] for t in texts]
        def embed_query(self, texts):
            return [[1.0, 0.0] for _ in texts]

    class _Reranker:
        def score(self, query, passages):
            return [0.9, 0.1]

    monkeypatch.setattr(providers, "build_embedder", lambda *a, **k: _Embedder())
    monkeypatch.setattr(providers, "build_reranker", lambda *a, **k: _Reranker())
    report = model_setup.smoke_test_search_models()
    assert report.ok
    assert {s.name for s in report.steps} == {"embedding-smoke", "reranker-smoke"}


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
