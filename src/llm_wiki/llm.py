"""LLM client layer — supports Ollama (local) and Gemini (cloud) backends.

RAM-based auto-selection at startup:
  < 16 GB  →  Gemini API  (gemini-2.0-flash  /  gemini-2.0-flash-thinking-exp)
  ≥ 16 GB  →  Ollama      (deepseek-r1:14b)

Both clients expose the same interface:
  .chat()         — non-streaming, returns str
  .chat_stream()  — streaming generator, yields chunks
  .ensure_ready() — raises LLMError subclass if not operational
  .close()        — release resources
  .ping()         — bool liveness check

Use build_client(config) to get the right backend automatically.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Generator

import httpx

# ---------------------------------------------------------------------------
# RAM detection
# ---------------------------------------------------------------------------

RAM_THRESHOLD_GB = 16


def detect_ram_gb() -> float:
    """Return total system RAM in gigabytes (best-effort, never raises)."""
    try:
        if sys.platform == "darwin":
            # macOS: sysctl -n hw.memsize  → bytes
            out = subprocess.check_output(
                ["sysctl", "-n", "hw.memsize"], timeout=3
            ).decode().strip()
            return int(out) / (1024 ** 3)
        elif sys.platform.startswith("linux"):
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        return kb / (1024 ** 2)
        elif sys.platform == "win32":
            import ctypes
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(stat)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            return stat.ullTotalPhys / (1024 ** 3)
    except Exception:
        pass
    # Fallback: assume high-RAM machine (use local Ollama)
    return 32.0


def has_enough_ram_for_local() -> bool:
    return detect_ram_gb() >= RAM_THRESHOLD_GB


# ---------------------------------------------------------------------------
# Constants & defaults
# ---------------------------------------------------------------------------

DEFAULT_OLLAMA_HOST = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "deepseek-r1:14b"
DEFAULT_GEMINI_FLASH_MODEL = "gemini-3-flash-preview"
DEFAULT_GEMINI_THINK_MODEL = "gemini-3.1-pro-preview"
DEFAULT_TIMEOUT = 300.0  # 5 minutes — thinking-mode extraction can be slow


# ---------------------------------------------------------------------------
# Shared error types
# ---------------------------------------------------------------------------


class LLMError(Exception):
    """Raised when an LLM call fails in a user-recoverable way."""


class OllamaNotRunning(LLMError):
    """Ollama HTTP API is not reachable."""


class ModelNotFound(LLMError):
    """Requested model isn't pulled."""


class GeminiError(LLMError):
    """Gemini API call failed."""


# ---------------------------------------------------------------------------
# Message type (provider-agnostic)
# ---------------------------------------------------------------------------


@dataclass
class ChatMessage:
    role: str  # 'system' | 'user' | 'assistant'
    content: str


# ---------------------------------------------------------------------------
# Ollama client
# ---------------------------------------------------------------------------


class OllamaClient:
    """Minimal, synchronous Ollama client tuned for the LLM-Wiki use case."""

    def __init__(
        self,
        host: str = DEFAULT_OLLAMA_HOST,
        model: str = DEFAULT_OLLAMA_MODEL,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.host = host.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "OllamaClient":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Health / liveness
    # ------------------------------------------------------------------

    def ping(self) -> bool:
        """True if Ollama is reachable. Does not check model availability."""
        try:
            r = self._client.get(f"{self.host}/api/tags", timeout=5.0)
            return r.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError):
            return False

    def list_models(self) -> list[str]:
        """List models available in this Ollama instance."""
        try:
            r = self._client.get(f"{self.host}/api/tags", timeout=5.0)
            r.raise_for_status()
            data = r.json()
            return [m.get("name", "") for m in data.get("models", [])]
        except httpx.ConnectError as e:
            raise OllamaNotRunning(
                f"Cannot connect to Ollama at {self.host}. "
                f"Is the Ollama app running?"
            ) from e
        except httpx.HTTPError as e:
            raise LLMError(f"Ollama error: {e}") from e

    def ensure_ready(self) -> None:
        """Verify Ollama is running and the configured model is available."""
        if not self.ping():
            raise OllamaNotRunning(
                f"Ollama isn't reachable at {self.host}.\n"
                f"Start it by opening the Ollama app, or run `ollama serve`."
            )
        models = self.list_models()
        if not any(m == self.model or m.startswith(self.model) for m in models):
            raise ModelNotFound(
                f"Model '{self.model}' not found in Ollama.\n"
                f"Available: {', '.join(models) if models else '(none)'}\n"
                f"Pull it with: ollama pull {self.model}"
            )

    # ------------------------------------------------------------------
    # Chat (non-streaming)
    # ------------------------------------------------------------------

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        thinking: bool = False,
        json_mode: bool = False,
        temperature: float = 0.3,
    ) -> str:
        """Non-streaming chat. Returns the full assistant message content."""
        payload_messages = self._prepare_messages(messages, thinking=thinking)
        payload = {
            "model": self.model,
            "messages": payload_messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if json_mode:
            payload["format"] = "json"

        try:
            r = self._client.post(f"{self.host}/api/chat", json=payload)
            r.raise_for_status()
        except httpx.ConnectError as e:
            raise OllamaNotRunning(
                f"Cannot connect to Ollama at {self.host}."
            ) from e
        except httpx.HTTPStatusError as e:
            body = e.response.text
            if "not found" in body.lower() or e.response.status_code == 404:
                raise ModelNotFound(
                    f"Model '{self.model}' not found. "
                    f"Pull it with: ollama pull {self.model}"
                ) from e
            raise LLMError(f"Ollama error {e.response.status_code}: {body}") from e
        except httpx.HTTPError as e:
            raise LLMError(f"Ollama request failed: {e}") from e

        data = r.json()
        content = data.get("message", {}).get("content", "")
        return self._strip_thinking(content)

    # ------------------------------------------------------------------
    # Chat (streaming)
    # ------------------------------------------------------------------

    def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        thinking: bool = False,
        temperature: float = 0.3,
    ) -> Generator[str, None, str]:
        """Streaming chat. Yields content chunks as they arrive."""
        payload_messages = self._prepare_messages(messages, thinking=thinking)
        payload = {
            "model": self.model,
            "messages": payload_messages,
            "stream": True,
            "options": {"temperature": temperature},
        }

        full_content: list[str] = []
        in_thinking_block = False

        try:
            with self._client.stream(
                "POST", f"{self.host}/api/chat", json=payload
            ) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    msg = data.get("message", {})
                    chunk = msg.get("content", "")
                    if not chunk:
                        if data.get("done"):
                            break
                        continue

                    # Strip thinking blocks on the fly
                    visible = ""
                    i = 0
                    while i < len(chunk):
                        if not in_thinking_block:
                            start = chunk.find("<think>", i)
                            if start == -1:
                                visible += chunk[i:]
                                break
                            visible += chunk[i:start]
                            in_thinking_block = True
                            i = start + len("<think>")
                        else:
                            end = chunk.find("</think>", i)
                            if end == -1:
                                break
                            in_thinking_block = False
                            i = end + len("</think>")

                    if visible:
                        full_content.append(visible)
                        yield visible

                    if data.get("done"):
                        break
        except httpx.ConnectError as e:
            raise OllamaNotRunning(
                f"Cannot connect to Ollama at {self.host}."
            ) from e
        except httpx.HTTPStatusError as e:
            body = e.response.read().decode(errors="replace") if e.response else ""
            raise LLMError(f"Ollama error {e.response.status_code}: {body}") from e
        except httpx.HTTPError as e:
            raise LLMError(f"Ollama streaming failed: {e}") from e

        return "".join(full_content)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _prepare_messages(
        self, messages: list[ChatMessage], *, thinking: bool
    ) -> list[dict]:
        """Convert to Ollama wire format and append the DeepSeek thinking tag."""
        result = [{"role": m.role, "content": m.content} for m in messages]
        if result:
            tag = "\n\n/think" if thinking else "\n\n/no_think"
            for i in range(len(result) - 1, -1, -1):
                if result[i]["role"] == "user":
                    result[i]["content"] += tag
                    break
        return result

    @staticmethod
    def _strip_thinking(text: str) -> str:
        """Remove <think>...</think> blocks from a completed response."""
        if "<think>" not in text:
            return text
        return re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL).strip()


# ---------------------------------------------------------------------------
# Gemini client (same interface as OllamaClient)
# ---------------------------------------------------------------------------


class GeminiClient:
    """Google Gemini API client with the same interface as OllamaClient.

    Uses google-generativeai SDK. Set GEMINI_API_KEY env var or pass api_key.

    thinking=True → uses the flash-thinking model
    thinking=False → uses the standard flash model
    """

    def __init__(
        self,
        api_key: str | None = None,
        flash_model: str = DEFAULT_GEMINI_FLASH_MODEL,
        think_model: str = DEFAULT_GEMINI_THINK_MODEL,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.flash_model = flash_model
        self.think_model = think_model
        self.timeout = timeout
        # model property for display (matches OllamaClient interface)
        self.model = flash_model

        if not self.api_key:
            raise GeminiError(
                "Gemini API key not set.\n"
                "Set the GEMINI_API_KEY environment variable, or add it to "
                "your wiki config.yml under llm.gemini_api_key."
            )

        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self._genai = genai
        except ImportError as e:
            raise GeminiError(
                "google-generativeai is not installed.\n"
                "Install it with: pip install 'llm-wiki[gemini]'\n"
                "or: pip install google-generativeai"
            ) from e

    def close(self) -> None:
        pass  # SDK is stateless

    def __enter__(self) -> "GeminiClient":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def ping(self) -> bool:
        """Check that the Gemini API key is valid by listing models."""
        try:
            list(self._genai.list_models())
            return True
        except Exception:
            return False

    def ensure_ready(self) -> None:
        """Verify the API key is valid and the SDK is installed."""
        if not self.ping():
            raise GeminiError(
                "Gemini API is not reachable or the API key is invalid.\n"
                "Check your GEMINI_API_KEY environment variable."
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _model_name(self, thinking: bool) -> str:
        return self.think_model if thinking else self.flash_model

    def _to_gemini_messages(
        self, messages: list[ChatMessage]
    ) -> tuple[str | None, list[dict]]:
        """Split system prompt out and convert user/assistant turns."""
        system_prompt: str | None = None
        history: list[dict] = []
        for msg in messages:
            if msg.role == "system":
                system_prompt = msg.content
            elif msg.role == "user":
                history.append({"role": "user", "parts": [msg.content]})
            elif msg.role == "assistant":
                history.append({"role": "model", "parts": [msg.content]})
        return system_prompt, history

    # ------------------------------------------------------------------
    # Chat (non-streaming)
    # ------------------------------------------------------------------

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        thinking: bool = False,
        json_mode: bool = False,
        temperature: float = 0.3,
    ) -> str:
        """Non-streaming Gemini chat. Returns full assistant response."""
        system_prompt, history = self._to_gemini_messages(messages)
        model_name = self._model_name(thinking)

        generation_config: dict = {"temperature": temperature}
        if json_mode:
            generation_config["response_mime_type"] = "application/json"

        try:
            model = self._genai.GenerativeModel(
                model_name=model_name,
                system_instruction=system_prompt,
            )
            if len(history) > 1:
                # Multi-turn: use chat session
                chat_session = model.start_chat(history=history[:-1])
                response = chat_session.send_message(
                    history[-1]["parts"][0],
                    generation_config=generation_config,
                )
            else:
                user_text = history[0]["parts"][0] if history else ""
                response = model.generate_content(
                    user_text,
                    generation_config=generation_config,
                )
            return response.text or ""
        except Exception as e:
            raise GeminiError(f"Gemini API error: {e}") from e

    # ------------------------------------------------------------------
    # Chat (streaming) — fake streaming via full response
    # ------------------------------------------------------------------

    def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        thinking: bool = False,
        temperature: float = 0.3,
    ) -> Generator[str, None, str]:
        """Streaming-compatible Gemini chat.

        Yields the full response as a single chunk (Gemini streaming works
        differently but the caller interface is preserved).
        """
        system_prompt, history = self._to_gemini_messages(messages)
        model_name = self._model_name(thinking)

        try:
            model = self._genai.GenerativeModel(
                model_name=model_name,
                system_instruction=system_prompt,
            )
            generation_config = {"temperature": temperature}
            if len(history) > 1:
                chat_session = model.start_chat(history=history[:-1])
                response = chat_session.send_message(
                    history[-1]["parts"][0],
                    generation_config=generation_config,
                    stream=True,
                )
            else:
                user_text = history[0]["parts"][0] if history else ""
                response = model.generate_content(
                    user_text,
                    generation_config=generation_config,
                    stream=True,
                )

            full: list[str] = []
            for chunk in response:
                text = chunk.text or ""
                if text:
                    full.append(text)
                    yield text

        except Exception as e:
            raise GeminiError(f"Gemini API streaming error: {e}") from e

        return "".join(full)


# ---------------------------------------------------------------------------
# Factory — auto-select backend based on RAM
# ---------------------------------------------------------------------------


def build_client(config: dict) -> "OllamaClient | GeminiClient":
    """Return the appropriate LLM client based on system RAM and config.

    Decision logic:
      RAM < 16 GB  →  GeminiClient  (cloud, no local compute needed)
      RAM ≥ 16 GB  →  OllamaClient  (local deepseek-r1:14b)

    Config can override this via llm.provider = 'ollama' | 'gemini'.
    """
    llm_cfg = config.get("llm", {})
    ram_gb = detect_ram_gb()
    auto_provider = "gemini" if ram_gb < RAM_THRESHOLD_GB else "ollama"
    provider = llm_cfg.get("provider", "auto")
    if provider == "auto":
        provider = auto_provider

    if provider == "gemini":
        api_key = (
            llm_cfg.get("gemini_api_key")
            or os.environ.get("GEMINI_API_KEY", "")
        )
        flash_model = llm_cfg.get("gemini_flash_model", DEFAULT_GEMINI_FLASH_MODEL)
        think_model = llm_cfg.get("gemini_think_model", DEFAULT_GEMINI_THINK_MODEL)
        return GeminiClient(
            api_key=api_key,
            flash_model=flash_model,
            think_model=think_model,
        )
    else:
        host = llm_cfg.get("host", DEFAULT_OLLAMA_HOST)
        model = llm_cfg.get("model", DEFAULT_OLLAMA_MODEL)
        return OllamaClient(host=host, model=model)


def describe_backend(config: dict) -> str:
    """Return a human-readable description of the auto-selected backend."""
    ram_gb = detect_ram_gb()
    llm_cfg = config.get("llm", {})
    auto_provider = "gemini" if ram_gb < RAM_THRESHOLD_GB else "ollama"
    provider = llm_cfg.get("provider", "auto")
    if provider == "auto":
        provider = auto_provider

    if provider == "gemini":
        flash = llm_cfg.get("gemini_flash_model", DEFAULT_GEMINI_FLASH_MODEL)
        think = llm_cfg.get("gemini_think_model", DEFAULT_GEMINI_THINK_MODEL)
        return (
            f"Gemini API  [{ram_gb:.1f} GB RAM < {RAM_THRESHOLD_GB} GB threshold]  "
            f"flash={flash}  think={think}"
        )
    else:
        host = llm_cfg.get("host", DEFAULT_OLLAMA_HOST)
        model = llm_cfg.get("model", DEFAULT_OLLAMA_MODEL)
        return (
            f"Ollama  [{ram_gb:.1f} GB RAM ≥ {RAM_THRESHOLD_GB} GB threshold]  "
            f"model={model}  host={host}"
        )
