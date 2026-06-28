"""XC-1 slice 1: error-handling narrowing for llm.py leaf helpers.

The Ollama discovery/probe helpers degrade to empty results on *expected*
transport errors (now logged), but *unexpected* errors must propagate instead of
being swallowed by the old broad ``except Exception``.
"""

import logging

import httpx
import pytest

from curator import llm


class _FakeClient:
    def __init__(self, exc: Exception):
        self._exc = exc

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, *args, **kwargs):
        raise self._exc

    def post(self, *args, **kwargs):
        raise self._exc


def _patch_client(monkeypatch, exc: Exception):
    monkeypatch.setattr(llm.httpx, "Client", lambda *a, **k: _FakeClient(exc))


def test_list_models_on_host_returns_empty_and_logs(monkeypatch, caplog):
    _patch_client(monkeypatch, httpx.ConnectError("down"))
    with caplog.at_level(logging.DEBUG, logger="curator.llm"):
        assert llm.list_models_on_host("http://x") == []
    assert any("Listing models on host" in r.message for r in caplog.records)


def test_list_models_on_host_propagates_unexpected(monkeypatch):
    _patch_client(monkeypatch, RuntimeError("boom"))
    with pytest.raises(RuntimeError):
        llm.list_models_on_host("http://x")


def test_get_ollama_capabilities_returns_empty_and_logs(monkeypatch, caplog):
    _patch_client(monkeypatch, httpx.ConnectError("down"))
    with caplog.at_level(logging.DEBUG, logger="curator.llm"):
        assert llm.get_ollama_model_capabilities("http://x", "m") == []
    assert any("capability probe failed" in r.message for r in caplog.records)


def test_get_ollama_capabilities_propagates_unexpected(monkeypatch):
    _patch_client(monkeypatch, RuntimeError("boom"))
    with pytest.raises(RuntimeError):
        llm.get_ollama_model_capabilities("http://x", "m")
