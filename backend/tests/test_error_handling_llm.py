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


class _FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class _RespClient:
    def __init__(self, payload, status=200):
        self._resp = _FakeResponse(payload, status)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, *args, **kwargs):
        return self._resp

    def post(self, *args, **kwargs):
        return self._resp


def _patch_resp(monkeypatch, payload, status=200):
    monkeypatch.setattr(llm.httpx, "Client", lambda *a, **k: _RespClient(payload, status))


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


def test_get_ollama_capabilities_handles_non_dict_json(monkeypatch):
    # Valid-but-non-dict JSON body → .get() would AttributeError; must degrade.
    _patch_resp(monkeypatch, ["not", "a", "dict"])
    assert llm.get_ollama_model_capabilities("http://x", "m") == []


def test_list_models_on_host_handles_non_dict_json(monkeypatch):
    _patch_resp(monkeypatch, ["not", "a", "dict"])
    assert llm.list_models_on_host("http://x") == []


def test_list_models_on_host_handles_non_dict_model_entries(monkeypatch):
    # "models" present but elements are not dicts → m.get() would AttributeError.
    _patch_resp(monkeypatch, {"models": ["plain-string"]})
    assert llm.list_models_on_host("http://x") == []


def test_codex_ensure_ready_non_dict_auth_raises_codex_error(monkeypatch):
    import io

    client = llm.CodexCliClient()
    monkeypatch.setattr(llm, "_cli_installed", lambda cmd: True)
    monkeypatch.setattr(llm.os.path, "exists", lambda p: True)
    # Valid JSON but a list (not a dict) → data.get() would AttributeError; the
    # check must degrade and raise the expected CodexCliError, not AttributeError.
    monkeypatch.setattr("builtins.open", lambda *a, **k: io.StringIO("[1, 2, 3]"))

    with pytest.raises(llm.CodexCliError):
        client.ensure_ready()


def test_ollama_unload_on_closed_client_does_not_raise():
    # POSTing on an already-closed httpx client raises RuntimeError (not an
    # httpx error), e.g. on a double close()/close() inside a `with` block.
    # unload() must short-circuit on a closed client instead of crashing teardown.
    client = llm.OllamaClient(host="http://127.0.0.1:1", model="m")
    client._client.close()
    client.unload()  # without the is_closed guard this raises RuntimeError
    assert client._client.is_closed


def test_ollama_close_is_idempotent():
    client = llm.OllamaClient(host="http://127.0.0.1:1", model="m")
    client._client.close()  # simulate the transport already being torn down
    client.close()  # close() -> unload() (guarded) + _client.close() must not raise


def test_detect_ram_gb_returns_default_on_malformed_meminfo(monkeypatch, caplog):
    import io

    monkeypatch.setattr(llm.sys, "platform", "linux")
    monkeypatch.setattr("builtins.open", lambda *a, **k: io.StringIO("MemTotal:\n"))

    with caplog.at_level(logging.DEBUG, logger="curator.llm"):
        assert llm.detect_ram_gb() == 32.0
    assert any("RAM detection failed" in r.message for r in caplog.records)
