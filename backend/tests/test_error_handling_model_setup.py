"""XC-1 (slice 2): error-handling narrowing for model_setup.py.

Setup steps degrade to a failed ModelStep / False on the *expected* failure
types (now logged), while *unexpected* errors propagate instead of being hidden.
"""

import logging

import httpx
import pytest

from curator import model_setup as ms


class _RaisingClient:
    def __init__(self, exc: Exception):
        self._exc = exc

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, *args, **kwargs):
        raise self._exc


def test_ollama_reachable_false_and_logs_on_http_error(monkeypatch, caplog):
    monkeypatch.setattr(ms.httpx, "Client", lambda *a, **k: _RaisingClient(httpx.ConnectError("down")))
    with caplog.at_level(logging.DEBUG, logger="curator.model_setup"):
        assert ms._ollama_reachable("http://x") is False
    assert any("reachability probe failed" in r.message for r in caplog.records)


def test_ollama_reachable_propagates_unexpected(monkeypatch):
    monkeypatch.setattr(ms.httpx, "Client", lambda *a, **k: _RaisingClient(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        ms._ollama_reachable("http://x")


def test_ensure_ollama_serving_reports_os_error(monkeypatch):
    monkeypatch.setattr(ms, "_ollama_reachable", lambda *a, **k: False)
    monkeypatch.setattr(ms.shutil, "which", lambda name: "/usr/bin/ollama")

    def boom(*args, **kwargs):
        raise OSError("exec format error")

    monkeypatch.setattr(ms.subprocess, "Popen", boom)
    step = ms.ensure_ollama_serving("http://x", wait_seconds=1)
    assert step.ok is False
    assert "failed to start" in step.detail


def test_ollama_reachable_false_on_malformed_url():
    # A malformed configured host raises httpx.InvalidURL (a bare Exception, not
    # an HTTPError); the probe must still degrade to False, not crash.
    assert ms._ollama_reachable("http://host:notaport/") is False


def test_download_gguf_removes_tmp_on_unexpected_error(monkeypatch, tmp_path):
    part = tmp_path / "model.gguf.part"
    part.write_bytes(b"partial")  # simulate a leftover partial temp file

    def boom(*args, **kwargs):
        raise KeyboardInterrupt()

    monkeypatch.setattr(ms.httpx, "stream", boom)
    with pytest.raises(KeyboardInterrupt):
        ms.download_gguf("repo/x", "model.gguf", tmp_path)
    # BaseException cleanup must remove the .part file before propagating.
    assert not part.exists()


def test_download_gguf_reports_http_error(monkeypatch, tmp_path):
    def boom(*args, **kwargs):
        raise httpx.ConnectError("no network")

    monkeypatch.setattr(ms.httpx, "stream", boom)
    path, detail = ms.download_gguf("repo/x", "model.gguf", tmp_path)
    assert path is None
    assert "download error" in detail
