"""LLM client layer — supports Ollama (local) and Gemini (cloud) backends.

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
import threading
import time
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
DEFAULT_OLLAMA_MODEL = "qwen2.5:7b"
DEFAULT_GEMINI_FLASH_MODEL = "gemini-3.1-flash-lite-preview"
DEFAULT_GEMINI_THINK_MODEL = "gemini-3.1-pro-preview"
DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-6"
DEFAULT_CLAUDE_THINK_MODEL = "claude-opus-4-7"
DEFAULT_OPENAI_MODEL = "gpt-4.1"
DEFAULT_OPENAI_THINK_MODEL = "o3"
DEFAULT_TIMEOUT = 1800.0  # 30 minutes — thinking-mode extraction can be slow
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_VERSION = "2023-06-01"
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"

# ---------------------------------------------------------------------------
# Vision / multimodal support
# ---------------------------------------------------------------------------

# Model name substrings (lowercase, tag stripped) that guarantee vision support.
# Used as a fast path before querying the Ollama API.
VISION_CAPABLE_KEYWORDS: frozenset[str] = frozenset({
    "llava",            # LLaVA base
    "llava-llama3",     # LLaVA Llama 3
    "llava-phi3",       # LLaVA Phi-3
    "bakllava",         # BakLLaVA
    "moondream",        # Moondream 2
    "minicpm-v",        # MiniCPM-V
    "llama3.2-vision",  # Llama 3.2 Vision
    "llama-3.2-vision", # (Keyword variation)
    "pixtral",          # Pixtral 12B
    "mistral-pixtral",  # (Keyword variation)
    
    # (Real-world models that require custom GGUF for llama.cpp, etc.)
    "qwen2-vl",         # Qwen2-VL
    "qwen2.5-vl",       # Qwen2.5-VL
    "cogvlm",           # CogVLM
    "internvl",         # InternVL
    "phi3-vision",      # Phi-3 Vision (usually replaced by llava-phi3)
    "phi-3-vision",
    "deepseek-vl",      # DeepSeek-VL
    "idefics",          # IDEFICS
    "fuyu",             # Fuyu
})


def is_vision_capable_model(model_name: str) -> bool:
    """Return True if the model name indicates vision/image support."""
    name = model_name.lower().split(":")[0]  # strip tag: "llava:13b" → "llava"
    return any(kw in name for kw in VISION_CAPABLE_KEYWORDS)


def get_ollama_model_capabilities(
    host: str, model: str, timeout: float = 5.0
) -> list[str]:
    """Query Ollama /api/show for model capabilities.

    Returns e.g. ['completion', 'vision', 'tools'] or [] on failure.
    Requires Ollama >= 0.5; older versions return an empty list.
    """
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.post(
                f"{host.rstrip('/')}/api/show", json={"model": model}
            )
            if r.status_code == 200:
                return r.json().get("capabilities", [])
    except Exception:
        pass
    return []


def list_ollama_models_with_vision(
    host: str = DEFAULT_OLLAMA_HOST, timeout: float = 5.0
) -> list[tuple[str, bool]]:
    """Return all Ollama models with their vision support status.

    Each entry is (model_name, supports_vision).
    Models matching VISION_CAPABLE_KEYWORDS are marked True immediately;
    others fall back to a /api/show capabilities query.
    """
    models = list_models_on_host(host, timeout=timeout)
    result: list[tuple[str, bool]] = []
    for name in models:
        if is_vision_capable_model(name):
            result.append((name, True))
        else:
            caps = get_ollama_model_capabilities(host, name, timeout=2.0)
            result.append((name, "vision" in caps))
    return result


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


class ClaudeError(LLMError):
    """Anthropic Claude API call failed."""


class OpenAIError(LLMError):
    """OpenAI API call failed."""


class ClaudeCodeError(LLMError):
    """Claude Code CLI call failed."""


class GeminiCliError(LLMError):
    """Gemini CLI call failed."""


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

    def unload(self) -> None:
        """Ask Ollama to immediately evict this model from VRAM (keep_alive=0).

        Called automatically by close() so any finally-block close() also
        frees GPU memory for other consumers (e.g. qmd's llama-cpp model).
        Best-effort: silently ignored if Ollama is unreachable.
        """
        try:
            self._client.post(
                f"{self.host}/api/generate",
                json={"model": self.model, "prompt": "", "keep_alive": 0},
                timeout=10.0,
            )
        except Exception:
            pass

    def close(self) -> None:
        self.unload()
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
    # Context & Chunking Optimization
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Vision support
    # ------------------------------------------------------------------

    @property
    def supports_vision(self) -> bool:
        """True if the configured model supports vision/image inference.

        Checks known model keywords first (fast), then queries /api/show
        (requires Ollama >= 0.5).
        """
        if is_vision_capable_model(self.model):
            return True
        caps = get_ollama_model_capabilities(self.host, self.model)
        return "vision" in caps

    def describe_image(
        self,
        image_data: bytes,
        prompt: str = "Describe this image in detail for a knowledge base.",
        *,
        temperature: float = 0.3,
    ) -> str:
        """Describe an image using the model's vision capability.

        Raises LLMError if the model does not support vision.
        """
        import base64

        if not self.supports_vision:
            raise LLMError(
                f"Model '{self.model}' does not support vision. "
                f"Use a vision-capable model such as gemma4:31b-it, "
                f"gemma3:12b, llava:latest, or qwen2.5-vl:7b."
            )

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [base64.b64encode(image_data).decode()],
                }
            ],
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_ctx": self.optimal_context_window,
            },
        }

        try:
            r = self._client.post(f"{self.host}/api/chat", json=payload)
            r.raise_for_status()
        except httpx.ConnectError as e:
            raise OllamaNotRunning(
                f"Cannot connect to Ollama at {self.host}."
            ) from e
        except httpx.HTTPStatusError as e:
            body = e.response.text
            raise LLMError(
                f"Vision inference error {e.response.status_code}: {body}"
            ) from e
        except httpx.HTTPError as e:
            raise LLMError(f"Vision request failed: {e}") from e

        return r.json().get("message", {}).get("content", "").strip()

    # ------------------------------------------------------------------
    # Context & Chunking Optimization
    # ------------------------------------------------------------------

    @property
    def optimal_context_window(self) -> int:
        """Dynamically set the context window to avoid OOM while maximizing context length."""
        name = self.model.lower()
        if "70b" in name or "72b" in name:
            return 8192
        elif "14b" in name or "27b" in name or "32b" in name:
            return 16384
        else:
            return 32768  # For smaller models like 7b, 8b, 3b

    @property
    def optimal_chunk_chars(self) -> int:
        """Estimate the optimal chunk size in characters based on the context window."""
        # 1 token ≈ 4 characters. We leave ~20% of context window for prompts and generation
        usable_tokens = int(self.optimal_context_window * 0.8)
        return usable_tokens * 4

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
            "options": {
                "temperature": temperature,
                "num_ctx": self.optimal_context_window,
            },
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
        json_mode: bool = False,
        temperature: float = 0.3,
    ) -> Generator[str, None, str]:
        """Streaming chat. Yields content chunks as they arrive.

        Prefer this over chat() for long-running generations — each received
        token resets the httpx read timeout, preventing spurious timeouts.
        """
        payload_messages = self._prepare_messages(messages, thinking=thinking)
        payload = {
            "model": self.model,
            "messages": payload_messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_ctx": self.optimal_context_window,
            },
        }
        if json_mode:
            payload["format"] = "json"

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
    # Context & Chunking Optimization
    # ------------------------------------------------------------------

    @property
    def optimal_chunk_chars(self) -> int:
        """Gemini has a 1M+ token context window. We can safely pass huge chunks."""
        return 1_000_000  # ~250k tokens

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
# Claude client (same interface as OllamaClient / GeminiClient)
# ---------------------------------------------------------------------------


class ClaudeClient:
    """Anthropic Claude API client using httpx directly (no SDK required).

    Set ANTHROPIC_API_KEY env var or pass api_key.
    thinking=True  → uses think_model + extended thinking tokens
    thinking=False → uses model
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_CLAUDE_MODEL,
        think_model: str = DEFAULT_CLAUDE_THINK_MODEL,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = model
        self.think_model = think_model
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)

        if not self.api_key:
            raise ClaudeError(
                "Anthropic API key not set.\n"
                "Set the ANTHROPIC_API_KEY environment variable, or add it to "
                "your wiki config.yml under llm.anthropic_api_key."
            )

    def close(self) -> None:
        self._client.close()

    # ------------------------------------------------------------------
    # Context & Chunking Optimization
    # ------------------------------------------------------------------

    @property
    def optimal_chunk_chars(self) -> int:
        """Claude 3.5 has a 200k token context window."""
        return 400_000  # ~100k tokens

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_API_VERSION,
            "content-type": "application/json",
        }

    def _build_body(
        self,
        messages: list[ChatMessage],
        *,
        thinking: bool,
        json_mode: bool,
        temperature: float,
        stream: bool = False,
    ) -> dict:
        system_content = ""
        anthropic_messages = []
        for m in messages:
            if m.role == "system":
                system_content = m.content
            else:
                anthropic_messages.append({"role": m.role, "content": m.content})

        body: dict = {
            "model": self.think_model if thinking else self.model,
            "max_tokens": 16000 if thinking else 8192,
            "messages": anthropic_messages,
            "temperature": temperature,
        }
        if system_content:
            body["system"] = system_content
        if thinking:
            body["thinking"] = {"type": "enabled", "budget_tokens": 10000}
        if stream:
            body["stream"] = True
        return body

    def _extract_text(self, content: list[dict]) -> str:
        return "".join(
            block["text"]
            for block in content
            if block.get("type") == "text"
        )

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        thinking: bool = False,
        json_mode: bool = False,
        temperature: float = 0.3,
    ) -> str:
        body = self._build_body(
            messages, thinking=thinking, json_mode=json_mode, temperature=temperature
        )
        try:
            resp = self._client.post(
                ANTHROPIC_API_URL, json=body, headers=self._headers()
            )
            resp.raise_for_status()
            return self._extract_text(resp.json().get("content", []))
        except httpx.HTTPStatusError as e:
            raise ClaudeError(
                f"Claude API error {e.response.status_code}: {e.response.text}"
            ) from e
        except ClaudeError:
            raise
        except Exception as e:
            raise ClaudeError(f"Claude API call failed: {e}") from e

    def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        thinking: bool = False,
        temperature: float = 0.3,
    ) -> Generator[str, None, str]:
        body = self._build_body(
            messages, thinking=thinking, json_mode=False, temperature=temperature, stream=True
        )
        full: list[str] = []
        try:
            with self._client.stream(
                "POST", ANTHROPIC_API_URL, json=body, headers=self._headers()
            ) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:]
                    if payload == "[DONE]":
                        break
                    try:
                        event = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    if event.get("type") == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta":
                            text = delta.get("text", "")
                            full.append(text)
                            yield text
        except httpx.HTTPStatusError as e:
            raise ClaudeError(
                f"Claude streaming error {e.response.status_code}: {e.response.text}"
            ) from e
        except ClaudeError:
            raise
        except Exception as e:
            raise ClaudeError(f"Claude streaming failed: {e}") from e
        return "".join(full)

    def ensure_ready(self) -> None:
        try:
            resp = self._client.post(
                ANTHROPIC_API_URL,
                json={
                    "model": self.model,
                    "max_tokens": 1,
                    "messages": [{"role": "user", "content": "hi"}],
                },
                headers=self._headers(),
            )
            if resp.status_code == 401:
                raise ClaudeError("Invalid Anthropic API key.")
            # 400 = bad request (max_tokens too small on some models) but auth OK
            if resp.status_code not in (200, 400):
                raise ClaudeError(
                    f"Claude API returned {resp.status_code}: {resp.text}"
                )
        except ClaudeError:
            raise
        except Exception as e:
            raise ClaudeError(f"Could not reach Anthropic API: {e}") from e

    def ping(self) -> bool:
        try:
            self.ensure_ready()
            return True
        except ClaudeError:
            return False


# ---------------------------------------------------------------------------
# OpenAI client
# ---------------------------------------------------------------------------


class OpenAIClient:
    """OpenAI API client using httpx directly (no SDK required).

    Set OPENAI_API_KEY env var or pass api_key.
    thinking=True uses think_model (o3, non-streaming, no temperature param).
    thinking=False uses model (gpt-4.1, supports streaming and temperature).
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_OPENAI_MODEL,
        think_model: str = DEFAULT_OPENAI_THINK_MODEL,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.model = model
        self.think_model = think_model
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)
        if not self.api_key:
            raise OpenAIError(
                "OpenAI API key not set.\n"
                "Set the OPENAI_API_KEY environment variable, or add it to "
                "your wiki config.yml under llm.openai_api_key."
            )

    def close(self) -> None:
        self._client.close()

    # ------------------------------------------------------------------
    # Context & Chunking Optimization
    # ------------------------------------------------------------------

    @property
    def optimal_chunk_chars(self) -> int:
        """OpenAI (gpt-4) has a 128k token context window."""
        return 250_000  # ~62k tokens

    def __enter__(self) -> "OpenAIClient":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _build_messages(self, messages: list[ChatMessage]) -> list[dict]:
        return [{"role": m.role, "content": m.content} for m in messages]

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        thinking: bool = False,
        json_mode: bool = False,
        temperature: float = 0.3,
    ) -> str:
        model = self.think_model if thinking else self.model
        body: dict = {
            "model": model,
            "messages": self._build_messages(messages),
        }
        # o3 does not accept temperature or response_format
        if not thinking:
            body["temperature"] = temperature
            if json_mode:
                body["response_format"] = {"type": "json_object"}
        try:
            resp = self._client.post(OPENAI_API_URL, json=body, headers=self._headers())
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"] or ""
        except httpx.HTTPStatusError as e:
            raise OpenAIError(
                f"OpenAI API error {e.response.status_code}: {e.response.text}"
            ) from e
        except OpenAIError:
            raise
        except Exception as e:
            raise OpenAIError(f"OpenAI API call failed: {e}") from e

    def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        thinking: bool = False,
        temperature: float = 0.3,
    ) -> Generator[str, None, str]:
        # o3 does not support streaming — fall back to non-streaming and yield once
        if thinking:
            result = self.chat(messages, thinking=True)
            yield result
            return result

        body: dict = {
            "model": self.model,
            "messages": self._build_messages(messages),
            "temperature": temperature,
            "stream": True,
        }
        full: list[str] = []
        try:
            with self._client.stream(
                "POST", OPENAI_API_URL, json=body, headers=self._headers()
            ) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:]
                    if payload == "[DONE]":
                        break
                    try:
                        event = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    delta = event.get("choices", [{}])[0].get("delta", {})
                    text = delta.get("content") or ""
                    if text:
                        full.append(text)
                        yield text
        except httpx.HTTPStatusError as e:
            raise OpenAIError(
                f"OpenAI streaming error {e.response.status_code}: {e.response.text}"
            ) from e
        except OpenAIError:
            raise
        except Exception as e:
            raise OpenAIError(f"OpenAI streaming failed: {e}") from e
        return "".join(full)

    def ensure_ready(self) -> None:
        try:
            resp = self._client.post(
                OPENAI_API_URL,
                json={
                    "model": self.model,
                    "max_tokens": 1,
                    "messages": [{"role": "user", "content": "hi"}],
                },
                headers=self._headers(),
            )
            if resp.status_code == 401:
                raise OpenAIError("Invalid OpenAI API key.")
            if resp.status_code not in (200, 400):
                raise OpenAIError(f"OpenAI API returned {resp.status_code}: {resp.text}")
        except OpenAIError:
            raise
        except Exception as e:
            raise OpenAIError(f"Could not reach OpenAI API: {e}") from e

    def ping(self) -> bool:
        try:
            self.ensure_ready()
            return True
        except OpenAIError:
            return False


# ---------------------------------------------------------------------------
# CLI-subprocess clients (Claude Code / Gemini CLI)
# ---------------------------------------------------------------------------


def _cli_installed(cmd: str) -> bool:
    """Return True if *cmd* is found in PATH."""
    import shutil
    return shutil.which(cmd) is not None


def _messages_to_prompt(messages: list[ChatMessage]) -> str:
    """Flatten ChatMessage list to a single text prompt for CLI backends."""
    system_parts: list[str] = []
    body_parts: list[str] = []
    for m in messages:
        if m.role == "system":
            system_parts.append(m.content)
        elif m.role == "user":
            body_parts.append(m.content)
        elif m.role == "assistant":
            body_parts.append(f"[Previous assistant response: {m.content}]")
    parts: list[str] = []
    if system_parts:
        parts.append("[Instructions: " + "\n".join(system_parts) + "]")
    parts.extend(body_parts)
    return "\n\n".join(parts)


class ClaudeCodeClient:
    """LLM backend using the *claude* CLI (Claude Pro/Max subscription).

    Requires: npm install -g @anthropic-ai/claude-code
    """

    CLI = "claude"
    INSTALL_CMD = "npm install -g @anthropic-ai/claude-code"

    def __init__(self, model: str = DEFAULT_CLAUDE_MODEL, api_key: str = "") -> None:
        self.model = model
        self.api_key = api_key

    def close(self) -> None:
        pass

    def __enter__(self) -> "ClaudeCodeClient":
        return self

    def __exit__(self, *args) -> None:
        pass

    def _run(self, prompt: str) -> str:
        # Pass the prompt via stdin to avoid "Argument list too long" errors
        cmd = [self.CLI, "-p", "Follow the instructions in the provided input."]
        if self.model:
            cmd += ["--model", self.model]
        env = dict(os.environ)
        env["CLAUDE_BYPASS_PERMISSIONS"] = "true"
        if self.api_key:
            env["ANTHROPIC_API_KEY"] = self.api_key
        try:
            result = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=300, env=env)
        except FileNotFoundError:
            raise ClaudeCodeError(
                f"'{self.CLI}' CLI not found.\n"
                f"Install: {self.INSTALL_CMD}\n"
                "Authenticate: claude"
            )
        except subprocess.TimeoutExpired:
            raise ClaudeCodeError("claude CLI timed out after 300 s")
        if result.returncode != 0:
            raise ClaudeCodeError(
                f"claude CLI exited {result.returncode}: {result.stderr.strip()}"
            )
        return result.stdout.strip()

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        thinking: bool = False,
        json_mode: bool = False,
        temperature: float = 0.3,
    ) -> str:
        return self._run(_messages_to_prompt(messages))

    def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        thinking: bool = False,
        temperature: float = 0.3,
    ) -> Generator[str, None, str]:
        result = self._run(_messages_to_prompt(messages))
        yield result
        return result

    def ensure_ready(self) -> None:
        if not _cli_installed(self.CLI):
            raise ClaudeCodeError(
                f"'{self.CLI}' CLI not installed.\n"
                f"Install: {self.INSTALL_CMD}\n"
                "Authenticate: claude"
            )
        try:
            env = dict(os.environ)
            env["CLAUDE_BYPASS_PERMISSIONS"] = "true"
            r = subprocess.run(
                [self.CLI, "--version"], capture_output=True, text=True, timeout=5, env=env
            )
            if r.returncode != 0:
                raise ClaudeCodeError(
                    f"'{self.CLI}' not functional: {r.stderr.strip()}"
                )
        except FileNotFoundError:
            raise ClaudeCodeError(f"'{self.CLI}' not found in PATH.")
        except subprocess.TimeoutExpired:
            raise ClaudeCodeError(f"'{self.CLI}' --version timed out.")

    def ping(self) -> bool:
        try:
            self.ensure_ready()
            return True
        except ClaudeCodeError:
            return False


def _get_gemini_fallback_chain(model_name: str) -> list[str]:
    """Given a Gemini model name, return a list of models to try in order of fallback.
    
    If it's a lite model, fallback to flash, then pro.
    If it's a flash model (not lite), fallback to pro.
    If it's already a pro model, just return [pro].
    """
    name = model_name.lower()
    chain = [model_name]
    
    if "3.1" in name or "3-" in name:
        if "lite" in name:
            chain.extend(["gemini-3-flash-preview", "gemini-3.1-pro-preview"])
        elif "flash" in name and "lite" not in name:
            chain.extend(["gemini-3.1-pro-preview"])
    else:
        if "lite" in name:
            chain.extend(["gemini-2.5-flash", "gemini-2.5-pro"])
        elif "flash" in name and "lite" not in name:
            chain.extend(["gemini-2.5-pro"])
            
    result = []
    for m in chain:
        if m not in result:
            result.append(m)
    return result

class GeminiCliClient:
    """LLM backend using the *gemini* CLI (Gemini Advanced subscription).

    Requires: npm install -g @google/gemini-cli  then  gemini (login flow)
    """

    CLI = "gemini"
    INSTALL_CMD = "npm install -g @google/gemini-cli"

    def __init__(self, model: str = DEFAULT_GEMINI_FLASH_MODEL, api_key: str = "") -> None:
        self.model = model
        self.api_key = api_key

    def close(self) -> None:
        pass

    def __enter__(self) -> "GeminiCliClient":
        return self

    def __exit__(self, *args) -> None:
        pass

    def _run(self, prompt: str) -> str:
        models_to_try = _get_gemini_fallback_chain(self.model)
        
        for i, current_model in enumerate(models_to_try):
            # Pass the prompt via stdin to avoid "Argument list too long" errors
            cmd = [self.CLI]
            if current_model:
                cmd += ["--model", current_model]
            env = dict(os.environ)
            env["GEMINI_CLI_TRUST_WORKSPACE"] = "true"
            if self.api_key:
                env["GEMINI_API_KEY"] = self.api_key
            try:
                result = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=900, env=env)
            except FileNotFoundError:
                raise GeminiCliError(
                    f"'{self.CLI}' CLI not found.\n"
                    f"Install: {self.INSTALL_CMD}\n"
                    "Authenticate: gemini"
                )
            except subprocess.TimeoutExpired:
                raise GeminiCliError("gemini CLI timed out after 900 s")
                
            if result.returncode != 0:
                stderr = result.stderr.strip()
                is_capacity_error = (
                    "No capacity available" in stderr
                    or "MODEL_CAPACITY_EXHAUSTED" in stderr
                    or "QUOTA_EXHAUSTED" in stderr
                    or "TerminalQuotaError" in stderr
                    or "exhausted your capacity" in stderr
                    or "429" in stderr
                )
                
                if is_capacity_error and i < len(models_to_try) - 1:
                    next_model = models_to_try[i+1]
                    print(f"llm-wiki: Gemini CLI capacity exhausted for '{current_model}', falling back to '{next_model}'...", file=sys.stderr)
                    continue
                    
                if is_capacity_error:
                    raise GeminiCliError(
                        f"Gemini API Capacity Exhausted (429) for all fallback models.\n"
                        f"Last model tried: '{current_model}'.\n"
                        f"Try switching to the Cloud API backend:\n"
                        f"  wiki config provider --primary cloud --cloud-provider gemini"
                    )
                raise GeminiCliError(
                    f"gemini CLI exited {result.returncode}: {stderr}"
                )
            return result.stdout.strip()
        
        raise GeminiCliError("No output returned from gemini CLI.")

    @property
    def optimal_chunk_chars(self) -> int:
        """Keep CLI prompts modest; subprocess CLIs time out on very large chunks."""
        return 18000

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        thinking: bool = False,
        json_mode: bool = False,
        temperature: float = 0.3,
    ) -> str:
        return self._run(_messages_to_prompt(messages))

    def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        thinking: bool = False,
        temperature: float = 0.3,
    ) -> Generator[str, None, str]:
        result = self._run(_messages_to_prompt(messages))
        yield result
        return result

    def ensure_ready(self) -> None:
        if not _cli_installed(self.CLI):
            raise GeminiCliError(
                f"'{self.CLI}' CLI not installed.\n"
                f"Install: {self.INSTALL_CMD}\n"
                "Authenticate: gemini"
            )
        try:
            env = dict(os.environ)
            env["GEMINI_CLI_TRUST_WORKSPACE"] = "true"
            r = subprocess.run(
                [self.CLI, "--version"], capture_output=True, text=True, timeout=5, env=env
            )
            if r.returncode != 0:
                raise GeminiCliError(
                    f"'{self.CLI}' not functional: {r.stderr.strip()}"
                )
        except FileNotFoundError:
            raise GeminiCliError(f"'{self.CLI}' not found in PATH.")
        except subprocess.TimeoutExpired:
            raise GeminiCliError(f"'{self.CLI}' --version timed out.")

    def ping(self) -> bool:
        try:
            self.ensure_ready()
            return True
        except GeminiCliError:
            return False


# ---------------------------------------------------------------------------
# FailoverClient — ordered provider chain with background probe
# ---------------------------------------------------------------------------


_FAILOVER_ERRORS = (OllamaNotRunning, ModelNotFound, OSError)
_CLOUD_PRIMARY_FAILOVER_ERRORS = _FAILOVER_ERRORS + (ClaudeError, GeminiError, OpenAIError)
_CLI_PRIMARY_FAILOVER_ERRORS = _FAILOVER_ERRORS + (ClaudeCodeError, GeminiCliError)


class FailoverClient:
    """Wraps an ordered provider list with automatic failover and background probe.

    providers[0] is primary (preferred). On failover_errors, the client advances
    to the next provider and retries, updating active_idx.

    A daemon thread probes providers[0] every probe_interval seconds. If it comes
    back while active_idx > 0, promotes back to primary automatically.

    Interface identical to OllamaClient / GeminiClient / ClaudeClient.
    """

    def __init__(
        self,
        providers: list,
        probe_interval: int = 60,
        failover_errors: tuple = _FAILOVER_ERRORS,
    ) -> None:
        if not providers:
            raise ValueError("FailoverClient requires at least one provider")
        self.providers = providers
        self.probe_interval = probe_interval
        self._failover_errors = failover_errors
        self._active_idx: int = 0
        self._lock = threading.Lock()
        from rich.console import Console
        self._console = Console(stderr=True)
        self._probe_thread: threading.Thread | None = None
        if len(providers) > 1 and probe_interval > 0:
            self._probe_thread = threading.Thread(
                target=self._probe_loop, daemon=True, name="llm-probe"
            )
            self._probe_thread.start()

    @property
    def active_idx(self) -> int:
        with self._lock:
            return self._active_idx

    @property
    def active_provider(self):
        with self._lock:
            return self.providers[self._active_idx]

    @property
    def model(self) -> str:
        return self.active_provider.model

    def _probe_loop(self) -> None:
        while True:
            time.sleep(self.probe_interval)
            with self._lock:
                if self._active_idx == 0:
                    continue
                primary = self.providers[0]
            try:
                alive = primary.ping()
            except Exception:
                alive = False
            if alive:
                with self._lock:
                    if self._active_idx > 0:
                        self._active_idx = 0
                self._console.print(
                    "[dim cyan]llm-wiki:[/dim cyan] primary provider back online — "
                    f"switched to {type(self.providers[0]).__name__}"
                )

    def ensure_ready(self) -> None:
        last_error: Exception | None = None
        for idx, provider in enumerate(self.providers):
            try:
                provider.ensure_ready()
                with self._lock:
                    self._active_idx = idx
                if idx > 0:
                    self._console.print(
                        f"[dim yellow]llm-wiki:[/dim yellow] primary unavailable — "
                        f"using {type(provider).__name__} (provider {idx})"
                    )
                return
            except Exception as e:
                last_error = e
        raise LLMError(
            f"All LLM providers failed. Last error: {last_error}"
        ) from last_error

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        thinking: bool = False,
        json_mode: bool = False,
        temperature: float = 0.3,
    ) -> str:
        start = self.active_idx
        for offset in range(len(self.providers)):
            idx = (start + offset) % len(self.providers)
            try:
                result = self.providers[idx].chat(
                    messages,
                    thinking=thinking,
                    json_mode=json_mode,
                    temperature=temperature,
                )
                if idx != self.active_idx:
                    with self._lock:
                        self._active_idx = idx
                    self._console.print(
                        f"[dim yellow]llm-wiki:[/dim yellow] failed over to "
                        f"{type(self.providers[idx]).__name__}"
                    )
                return result
            except self._failover_errors as e:
                if offset == len(self.providers) - 1:
                    raise LLMError(f"All providers failed: {e}") from e
        raise LLMError("Unreachable")

    def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        thinking: bool = False,
        temperature: float = 0.3,
    ) -> Generator[str, None, str]:
        start = self.active_idx
        for offset in range(len(self.providers)):
            idx = (start + offset) % len(self.providers)
            provider = self.providers[idx]
            try:
                gen = provider.chat_stream(
                    messages, thinking=thinking, temperature=temperature
                )
                # Peek at first chunk to catch connection failures before yielding
                try:
                    first = next(gen)
                except StopIteration as s:
                    return s.value or ""
                # Committed to this provider
                if idx != self.active_idx:
                    with self._lock:
                        self._active_idx = idx
                    self._console.print(
                        f"[dim yellow]llm-wiki:[/dim yellow] failed over to "
                        f"{type(provider).__name__}"
                    )
                yield first
                parts = [first]
                try:
                    while True:
                        chunk = next(gen)
                        parts.append(chunk)
                        yield chunk
                except StopIteration as s:
                    return s.value if s.value else "".join(parts)
                return
            except self._failover_errors as e:
                if offset == len(self.providers) - 1:
                    raise LLMError(f"All providers failed during stream: {e}") from e
                # mid-stream errors (after first chunk) propagate — partial output delivered

    def ping(self) -> bool:
        return any(p.ping() for p in self.providers)

    def unload(self) -> None:
        """Forward unload to any OllamaClient providers to free VRAM."""
        for p in self.providers:
            if hasattr(p, "unload"):
                try:
                    p.unload()
                except Exception:
                    pass

    def close(self) -> None:
        for p in self.providers:
            try:
                p.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Ollama model discovery helper (no client instance required)
# ---------------------------------------------------------------------------


def list_models_on_host(host: str, timeout: float = 5.0) -> list[str]:
    """Return model names available on an Ollama host.

    Returns an empty list if the host is unreachable or returns an error.
    Does NOT raise — callers can distinguish empty-list from error by checking
    reachability separately if needed.
    """
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.get(f"{host.rstrip('/')}/api/tags")
            r.raise_for_status()
            return [m.get("name", "") for m in r.json().get("models", [])]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Factory — auto-select backend based on RAM
# ---------------------------------------------------------------------------


def _make_gemini(llm_cfg: dict) -> GeminiClient:
    return GeminiClient(
        api_key=llm_cfg.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY", ""),
        flash_model=llm_cfg.get("gemini_flash_model", DEFAULT_GEMINI_FLASH_MODEL),
        think_model=llm_cfg.get("gemini_think_model", DEFAULT_GEMINI_THINK_MODEL),
    )


def _make_claude(llm_cfg: dict) -> ClaudeClient:
    return ClaudeClient(
        api_key=llm_cfg.get("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY", ""),
        model=llm_cfg.get("claude_model", DEFAULT_CLAUDE_MODEL),
        think_model=llm_cfg.get("claude_think_model", DEFAULT_CLAUDE_THINK_MODEL),
    )


def _make_openai(llm_cfg: dict) -> OpenAIClient:
    return OpenAIClient(
        api_key=llm_cfg.get("openai_api_key") or os.environ.get("OPENAI_API_KEY", ""),
        model=llm_cfg.get("openai_model", DEFAULT_OPENAI_MODEL),
        think_model=llm_cfg.get("openai_think_model", DEFAULT_OPENAI_THINK_MODEL),
    )


def _make_claude_code(llm_cfg: dict) -> ClaudeCodeClient:
    return ClaudeCodeClient(
        model=llm_cfg.get("claude_model", DEFAULT_CLAUDE_MODEL),
        api_key=llm_cfg.get("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY", ""),
    )


def _make_gemini_cli(llm_cfg: dict) -> GeminiCliClient:
    return GeminiCliClient(
        model=llm_cfg.get("gemini_flash_model", DEFAULT_GEMINI_FLASH_MODEL),
        api_key=llm_cfg.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY", ""),
    )


def _make_cloud(llm_cfg: dict) -> "GeminiClient | ClaudeClient | OpenAIClient":
    """Build the configured cloud client (gemini/claude/openai)."""
    cp = llm_cfg.get("cloud_provider", "gemini")
    if cp == "claude":
        return _make_claude(llm_cfg)
    if cp == "openai":
        return _make_openai(llm_cfg)
    return _make_gemini(llm_cfg)


def _make_ollama(llm_cfg: dict) -> OllamaClient:
    return OllamaClient(
        host=llm_cfg.get("host", DEFAULT_OLLAMA_HOST),
        model=llm_cfg.get("model", DEFAULT_OLLAMA_MODEL),
    )


def _make_by_key(key: str, llm_cfg: dict):
    """Build any client by its backend key string."""
    if key == "ollama":
        return _make_ollama(llm_cfg)
    if key == "cloud":
        return _make_cloud(llm_cfg)
    if key == "claude-code":
        return _make_claude_code(llm_cfg)
    if key == "gemini-cli":
        return _make_gemini_cli(llm_cfg)
    return None


def make_client_by_key(key: str, config: dict):
    """Public: build a single backend client by key ('ollama'|'cloud'|'claude-code'|'gemini-cli')."""
    return _make_by_key(key, config.get("llm", {}))


def build_client(
    config: dict,
) -> "OllamaClient | GeminiClient | ClaudeClient | OpenAIClient | FailoverClient":
    """Return the appropriate LLM client based on config.

    Decision logic (in priority order):
      primary='ollama'      → OllamaClient first; fallback from config or cloud_provider
      primary='cloud'       → cloud client first; fallback from config or Ollama
      primary='claude-code' → Claude CLI first; fallback from config or Ollama
      primary='gemini-cli'  → Gemini CLI first; fallback from config or Ollama
      provider override 'ollama'|'gemini'|'claude'|'openai' → single explicit client
      auto + RAM ≥ 16 GB → OllamaClient (local)
      auto + RAM < 16 GB → cloud client (gemini/claude/openai per cloud_provider)
        + remote_ollama_host set → FailoverClient([OllamaClient(remote), cloud_client])
    """
    llm_cfg = config.get("llm", {})
    primary = llm_cfg.get("primary", "")
    fallback = llm_cfg.get("fallback", "")
    probe_interval = int(llm_cfg.get("probe_interval", 60))

    _PRIMARY_ERRORS = {
        "ollama":      _FAILOVER_ERRORS,
        "cloud":       _CLOUD_PRIMARY_FAILOVER_ERRORS,
        "claude-code": _CLI_PRIMARY_FAILOVER_ERRORS,
        "gemini-cli":  _CLI_PRIMARY_FAILOVER_ERRORS,
    }

    if primary in _PRIMARY_ERRORS:
        p_client = _make_by_key(primary, llm_cfg)

        # Explicit fallback takes precedence over legacy heuristics
        if fallback and fallback != primary:
            f_client = _make_by_key(fallback, llm_cfg)
            if f_client:
                return FailoverClient(
                    [p_client, f_client],
                    probe_interval=probe_interval,
                    failover_errors=_PRIMARY_ERRORS[primary],
                )
            return p_client

        # Explicitly disabled fallback via empty string in config
        if "fallback" in llm_cfg and not llm_cfg["fallback"]:
            return p_client

        # Legacy heuristics when no explicit fallback is set
        if primary == "ollama":
            cp = llm_cfg.get("cloud_provider", "")
            if cp:
                cloud = _make_cloud(llm_cfg)
                return FailoverClient(
                    [p_client, cloud],
                    probe_interval=probe_interval,
                    failover_errors=_FAILOVER_ERRORS,
                )
            return p_client

        if primary == "cloud":
            ollama = _make_ollama(llm_cfg)
            return FailoverClient(
                [p_client, ollama],
                probe_interval=probe_interval,
                failover_errors=_CLOUD_PRIMARY_FAILOVER_ERRORS,
            )

        # claude-code / gemini-cli → default fallback to ollama
        ollama = _make_ollama(llm_cfg)
        return FailoverClient(
            [p_client, ollama],
            probe_interval=probe_interval,
            failover_errors=_CLI_PRIMARY_FAILOVER_ERRORS,
        )

    # Legacy: explicit provider or auto/RAM-based selection
    provider = llm_cfg.get("provider", "auto")

    if provider == "ollama":
        return _make_ollama(llm_cfg)
    if provider == "gemini":
        return _make_gemini(llm_cfg)
    if provider == "claude":
        return _make_claude(llm_cfg)
    if provider == "openai":
        return _make_openai(llm_cfg)

    # Auto mode: select based on RAM
    ram_gb = detect_ram_gb()
    if ram_gb >= RAM_THRESHOLD_GB:
        return _make_ollama(llm_cfg)

    # Low-RAM machine: cloud with optional remote Ollama failover
    cloud_client = _make_cloud(llm_cfg)
    remote_host = (llm_cfg.get("remote_ollama_host") or "").strip()
    if not remote_host:
        return cloud_client

    remote_client = OllamaClient(
        host=remote_host,
        model=llm_cfg.get("model", DEFAULT_OLLAMA_MODEL),
    )
    return FailoverClient([remote_client, cloud_client], probe_interval=probe_interval)


def describe_backend(config: dict, client: object = None) -> str:
    """Return a human-readable description of the backend.

    If a live FailoverClient is passed, shows active provider and chain.
    Otherwise reconstructs from config (pre-build display).
    """
    if client is not None and isinstance(client, FailoverClient):
        active = client.active_provider
        chain = " → ".join(type(p).__name__ for p in client.providers)
        return (
            f"Failover [active: {type(active).__name__}]  "
            f"chain: {chain}  probe={client.probe_interval}s"
        )

    ram_gb = detect_ram_gb()
    llm_cfg = config.get("llm", {})
    primary = llm_cfg.get("primary", "")
    host = llm_cfg.get("host", DEFAULT_OLLAMA_HOST)
    model = llm_cfg.get("model", DEFAULT_OLLAMA_MODEL)
    cp = llm_cfg.get("cloud_provider", "gemini")
    probe = llm_cfg.get("probe_interval", 60)

    if primary == "ollama":
        base = f"Ollama  model={model}  host={host}"
        if "fallback" in llm_cfg and not llm_cfg["fallback"]:
            return base
        fallback = llm_cfg.get("fallback", "")
        if fallback:
            return f"Failover  primary=Ollama → fallback={fallback}  probe={probe}s"
        if "fallback" not in llm_cfg and cp:
            return f"Failover  primary=Ollama → fallback={cp}  probe={probe}s"
        return base

    if primary == "cloud":
        return f"{cp} API [DISABLED]"

    if primary == "claude-code":
        claude_m = llm_cfg.get("claude_model", DEFAULT_CLAUDE_MODEL)
        fallback = llm_cfg.get("fallback", "")
        if not fallback:
            return f"claude CLI [{claude_m}]"
        return f"Failover  primary=claude CLI [{claude_m}] → fallback={fallback}  model={model}  host={host}"

    if primary == "gemini-cli":
        gemini_m = llm_cfg.get("gemini_flash_model", DEFAULT_GEMINI_FLASH_MODEL)
        fallback = llm_cfg.get("fallback", "")
        if not fallback:
            return f"gemini CLI [{gemini_m}]"
        return f"Failover  primary=gemini CLI [{gemini_m}] → fallback={fallback}  model={model}  host={host}"

    # Legacy auto/explicit-provider path
    provider = llm_cfg.get("provider", "auto")
    if provider == "auto":
        provider = "ollama" if ram_gb >= RAM_THRESHOLD_GB else cp

    if provider == "gemini":
        flash = llm_cfg.get("gemini_flash_model", DEFAULT_GEMINI_FLASH_MODEL)
        think = llm_cfg.get("gemini_think_model", DEFAULT_GEMINI_THINK_MODEL)
        return f"Gemini API  [{ram_gb:.1f} GB RAM]  flash={flash}  think={think}"
    if provider == "claude":
        m = llm_cfg.get("claude_model", DEFAULT_CLAUDE_MODEL)
        return f"Claude API  [{ram_gb:.1f} GB RAM]  model={m}"
    if provider == "openai":
        m = llm_cfg.get("openai_model", DEFAULT_OPENAI_MODEL)
        think = llm_cfg.get("openai_think_model", DEFAULT_OPENAI_THINK_MODEL)
        return f"OpenAI API  [{ram_gb:.1f} GB RAM]  model={m}  think={think}"

    remote = llm_cfg.get("remote_ollama_host", "").strip()
    if remote and ram_gb < RAM_THRESHOLD_GB:
        return f"Failover (config)  remote={remote}  fallback={cp}  probe={probe}s"
    return f"Ollama  [{ram_gb:.1f} GB RAM]  model={model}  host={host}"
