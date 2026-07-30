from __future__ import annotations

from pathlib import Path

import pytest

from curator import llm


_MESSAGES = [llm.ChatMessage(role="user", content="answer")]


class _JsonResponse:
    status_code = 200
    text = ""

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _HttpClient:
    def __init__(self, payload: dict) -> None:
        self._response = _JsonResponse(payload)

    def post(self, *args, **kwargs) -> _JsonResponse:
        return self._response

    def close(self) -> None:
        return None


def test_ollama_rejects_blank_non_streaming_output() -> None:
    client = llm.OllamaClient(model="test")
    client._client.close()
    client._client = _HttpClient({"message": {"content": "  "}})  # type: ignore[assignment]

    with pytest.raises(llm.LLMError, match="empty response"):
        client.chat(_MESSAGES)


def test_claude_rejects_blank_non_streaming_output(monkeypatch) -> None:
    class _Result:
        returncode = 0
        stdout = " \n"
        stderr = ""

    monkeypatch.setattr(llm.subprocess, "run", lambda *args, **kwargs: _Result())

    with pytest.raises(llm.ClaudeCodeError, match="no output"):
        llm.ClaudeCodeClient().chat(_MESSAGES)


def test_antigravity_rejects_blank_non_streaming_output(monkeypatch) -> None:
    class _Result:
        returncode = 0
        stdout = " \n"
        stderr = ""

    monkeypatch.setattr(llm.subprocess, "run", lambda *args, **kwargs: _Result())

    with pytest.raises(llm.AntigravityCliError, match="no output"):
        llm.AntigravityCliClient().chat(_MESSAGES)


def test_codex_rejects_blank_non_streaming_output(monkeypatch) -> None:
    class _Result:
        returncode = 0
        stdout = " \n"
        stderr = ""

    monkeypatch.setattr(llm.subprocess, "run", lambda *args, **kwargs: _Result())

    with pytest.raises(llm.CodexCliError, match="no output"):
        llm.CodexCliClient().chat(_MESSAGES)


def test_deepseek_rejects_blank_non_streaming_output() -> None:
    client = llm.DeepSeekApiClient(api_key="test")
    client._client.close()
    client._client = _HttpClient(  # type: ignore[assignment]
        {"choices": [{"message": {"content": " \n"}}]}
    )

    with pytest.raises(llm.DeepSeekApiError, match="empty response"):
        client.chat(_MESSAGES)


def test_codex_nonzero_exit_rejects_valid_looking_output(
    monkeypatch,
) -> None:
    def fake_run(cmd, **kwargs):
        output_path = Path(cmd[cmd.index("--output-last-message") + 1])
        output_path.write_text("partial but valid-looking answer", encoding="utf-8")

        class _Result:
            returncode = 7
            stdout = ""
            stderr = "provider failed"

        return _Result()

    monkeypatch.setattr(llm.subprocess, "run", fake_run)

    with pytest.raises(llm.CodexCliError, match="exited 7"):
        llm.CodexCliClient().chat(_MESSAGES)


class _SuccessfulProvider:
    model = "fallback"

    def __init__(self) -> None:
        self.calls = 0

    def chat(self, *args, **kwargs) -> str:
        self.calls += 1
        return "fallback answer"

    def close(self) -> None:
        return None


@pytest.mark.parametrize(
    "error",
    [
        llm.LLMError("base"),
        llm.OllamaNotRunning("ollama down"),
        llm.ModelNotFound("model missing"),
        llm.ClaudeCodeError("claude down"),
        llm.AntigravityCliError("antigravity down"),
        llm.CodexCliError("codex down"),
        llm.DeepSeekApiError("deepseek down"),
    ],
    ids=[
        "llm",
        "ollama",
        "model",
        "claude",
        "antigravity",
        "codex",
        "deepseek",
    ],
)
def test_failover_handles_every_llm_error_subtype(error: llm.LLMError) -> None:
    class _FailingProvider:
        model = "primary"

        def chat(self, *args, **kwargs) -> str:
            raise error

        def close(self) -> None:
            return None

    fallback = _SuccessfulProvider()
    client = llm.FailoverClient(
        [_FailingProvider(), fallback],
        probe_interval=0,
    )

    assert client.chat(_MESSAGES) == "fallback answer"
    assert fallback.calls == 1
    assert client.active_idx == 1


def test_all_provider_failure_preserves_labelled_attempt_order() -> None:
    class _PrimaryProvider:
        model = "primary"

        def chat(self, *args, **kwargs) -> str:
            raise llm.CodexCliError("primary quota")

        def close(self) -> None:
            return None

    class _FallbackProvider:
        model = "fallback"

        def chat(self, *args, **kwargs) -> str:
            raise llm.AntigravityCliError("fallback capacity")

        def close(self) -> None:
            return None

    client = llm.FailoverClient(
        [_PrimaryProvider(), _FallbackProvider()],
        probe_interval=0,
    )

    with pytest.raises(llm.LLMError) as exc_info:
        client.chat(_MESSAGES)

    message = str(exc_info.value)
    assert message.index("_PrimaryProvider: primary quota") < message.index(
        "_FallbackProvider: fallback capacity"
    )
    assert isinstance(exc_info.value.__cause__, llm.AntigravityCliError)
