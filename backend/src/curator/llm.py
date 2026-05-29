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

from . import models as model_catalogue

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
DEFAULT_ANTIGRAVITY_FLASH_MODEL = (
    model_catalogue.get_default_model("antigravity", "flash")
    or "gemini-3.1-flash-lite-preview"
)
DEFAULT_ANTIGRAVITY_THINK_MODEL = (
    model_catalogue.get_default_model("antigravity", "think")
    or "gemini-3.1-pro-preview"
)
# Backward-compatible names for older callers/config migrations.
DEFAULT_GEMINI_FLASH_MODEL = DEFAULT_ANTIGRAVITY_FLASH_MODEL
DEFAULT_GEMINI_THINK_MODEL = DEFAULT_ANTIGRAVITY_THINK_MODEL
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





class ClaudeCodeError(LLMError):
    """Claude Code CLI call failed."""


class GeminiCliError(LLMError):
    """Gemini CLI call failed."""


class AntigravityCliError(GeminiCliError):
    """Antigravity CLI call failed."""


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
    """Minimal, synchronous Ollama client tuned for the incurator use case."""

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
        self._job_input_tokens: int = 0
        self._job_output_tokens: int = 0

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

    def clone(self) -> "OllamaClient":
        """Return a new independent OllamaClient with the same config.

        Each clone owns its own httpx.Client, making it safe to run in a
        separate thread without sharing the underlying connection pool.
        """
        return OllamaClient(host=self.host, model=self.model, timeout=self.timeout)

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
        self._job_input_tokens += int(data.get("prompt_eval_count") or 0)
        self._job_output_tokens += int(data.get("eval_count") or 0)
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
                            self._job_input_tokens += int(data.get("prompt_eval_count") or 0)
                            self._job_output_tokens += int(data.get("eval_count") or 0)
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
                        self._job_input_tokens += int(data.get("prompt_eval_count") or 0)
                        self._job_output_tokens += int(data.get("eval_count") or 0)
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

    def get_and_reset_token_usage(self) -> tuple[int, int]:
        """Return (input_tokens, output_tokens) since last reset and reset counters."""
        result = (self._job_input_tokens, self._job_output_tokens)
        self._job_input_tokens = 0
        self._job_output_tokens = 0
        return result




# ---------------------------------------------------------------------------
# Claude client (same interface as OllamaClient / GeminiClient)
# ---------------------------------------------------------------------------





# ---------------------------------------------------------------------------
# OpenAI client
# ---------------------------------------------------------------------------





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
    turns: list[str] = []
    for m in messages:
        if m.role == "system":
            system_parts.append(m.content)
        elif m.role == "user":
            turns.append(f"User: {m.content}")
        elif m.role == "assistant":
            turns.append(f"Assistant: {m.content}")
    parts: list[str] = []
    if system_parts:
        parts.append("[System]\n" + "\n".join(system_parts))
    if turns:
        parts.append("[Conversation]\n" + "\n\n".join(turns))
    parts.append("Assistant:")
    return "\n\n".join(parts)


class ClaudeCodeClient:
    """LLM backend using the *claude* CLI (Claude Pro/Max subscription).

    Requires: npm install -g @anthropic-ai/claude-code
    """

    CLI = "claude"
    INSTALL_CMD = "npm install -g @anthropic-ai/claude-code"

    def __init__(self, model: str = DEFAULT_CLAUDE_MODEL) -> None:
        self.model = model

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

    def get_and_reset_token_usage(self) -> tuple[int, int]:
        return (0, 0)


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

class AntigravityCliClient:
    """LLM backend using the *agy* CLI (Google Antigravity subscription).

    Requires Antigravity CLI, then its login flow. The legacy GeminiCliClient
    name remains as an alias below so older imports keep working.
    """

    CLI = "agy"
    INSTALL_CMD = "curl -fsSL https://antigravity.google/cli/install.sh | bash"

    def __init__(self, model: str = DEFAULT_ANTIGRAVITY_FLASH_MODEL) -> None:
        self.model = model

    def close(self) -> None:
        pass

    def __enter__(self) -> "AntigravityCliClient":
        return self

    def __exit__(self, *args) -> None:
        pass

    def _run(self, prompt: str) -> str:
        models_to_try = _get_gemini_fallback_chain(self.model)
        
        for i, current_model in enumerate(models_to_try):
            # Antigravity CLI currently exposes model choice through its own
            # settings, not a stable --model flag. Keep the selected model in
            # the prompt for traceability and pass the large payload via stdin.
            cmd = [self.CLI, "--print", "--print-timeout", "15m"]
            prompt_with_model = (
                f"[Preferred model: {current_model}]\n\n{prompt}"
                if current_model else prompt
            )
            env = dict(os.environ)
            env["GEMINI_CLI_TRUST_WORKSPACE"] = "true"
            env["ANTIGRAVITY_TRUST_WORKSPACE"] = "true"
            env["AGY_TRUST_WORKSPACE"] = "true"
            try:
                result = subprocess.run(
                    cmd,
                    input=prompt_with_model,
                    capture_output=True,
                    text=True,
                    timeout=900,
                    env=env,
                )
            except FileNotFoundError:
                raise AntigravityCliError(
                    f"'{self.CLI}' CLI not found.\n"
                    f"Install: {self.INSTALL_CMD}\n"
                    "Authenticate: agy"
                )
            except subprocess.TimeoutExpired:
                raise AntigravityCliError("Antigravity CLI timed out after 900 s")
                
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
                    print(f"incurator: Antigravity CLI capacity exhausted for '{current_model}', falling back to '{next_model}'...", file=sys.stderr)
                    continue
                    
                if is_capacity_error:
                    raise AntigravityCliError(
                        f"Antigravity/Gemini capacity exhausted (429) for all fallback models.\n"
                        f"Last model tried: '{current_model}'.\n"
                        f"Try a local fallback or a lighter model."
                    )

                raise AntigravityCliError(
                    f"Antigravity CLI exited {result.returncode}: {stderr}"
                )
            return result.stdout.strip()
        
        raise AntigravityCliError("No output returned from Antigravity CLI.")

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
            raise AntigravityCliError(
                f"'{self.CLI}' CLI not installed.\n"
                f"Install: {self.INSTALL_CMD}\n"
                "Authenticate: agy"
            )
        try:
            env = dict(os.environ)
            env["GEMINI_CLI_TRUST_WORKSPACE"] = "true"
            env["ANTIGRAVITY_TRUST_WORKSPACE"] = "true"
            env["AGY_TRUST_WORKSPACE"] = "true"
            r = subprocess.run(
                [self.CLI, "--version"], capture_output=True, text=True, timeout=5, env=env
            )
            if r.returncode != 0:
                raise AntigravityCliError(
                    f"'{self.CLI}' not functional: {r.stderr.strip()}"
                )
        except FileNotFoundError:
            raise AntigravityCliError(f"'{self.CLI}' not found in PATH.")
        except subprocess.TimeoutExpired:
            raise AntigravityCliError(f"'{self.CLI}' --version timed out.")

    def ping(self) -> bool:
        try:
            self.ensure_ready()
            return True
        except GeminiCliError:
            return False

    def get_and_reset_token_usage(self) -> tuple[int, int]:
        return (0, 0)


# Compatibility alias. New code should use AntigravityCliClient.
GeminiCliClient = AntigravityCliClient


# ---------------------------------------------------------------------------
# FailoverClient — ordered provider chain with background probe
# ---------------------------------------------------------------------------


_FAILOVER_ERRORS = (OllamaNotRunning, ModelNotFound, OSError)
_CLI_PRIMARY_FAILOVER_ERRORS = _FAILOVER_ERRORS + (ClaudeCodeError, GeminiCliError, AntigravityCliError)


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

    def __enter__(self) -> "FailoverClient":
        return self

    def __exit__(self, *args) -> None:
        self.close()

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
                    "[dim cyan]incurator:[/dim cyan] primary provider back online — "
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
                        f"[dim yellow]incurator:[/dim yellow] primary unavailable — "
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
        last_err: Exception | None = None
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
                    err_hint = f" — {str(last_err)[:80]}" if last_err else ""
                    self._console.print(
                        f"[dim yellow]incurator:[/dim yellow] failed over to "
                        f"{type(self.providers[idx]).__name__}{err_hint}"
                    )
                return result
            except self._failover_errors as e:
                last_err = e
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
        last_err: Exception | None = None
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
                    err_hint = f" — {str(last_err)[:80]}" if last_err else ""
                    self._console.print(
                        f"[dim yellow]incurator:[/dim yellow] failed over to "
                        f"{type(provider).__name__}{err_hint}"
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
                last_err = e
                if offset == len(self.providers) - 1:
                    raise LLMError(f"All providers failed during stream: {e}") from e
                # mid-stream errors (after first chunk) propagate — partial output delivered

    def ping(self) -> bool:
        return any(p.ping() for p in self.providers)

    def get_and_reset_token_usage(self) -> tuple[int, int]:
        """Sum and reset token usage across all providers."""
        total_in = total_out = 0
        for p in self.providers:
            if hasattr(p, "get_and_reset_token_usage"):
                pin, pout = p.get_and_reset_token_usage()
                total_in += pin
                total_out += pout
        return (total_in, total_out)

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


def _make_claude_code(llm_cfg: dict) -> ClaudeCodeClient:
    return ClaudeCodeClient(
        model=llm_cfg.get("claude_model", DEFAULT_CLAUDE_MODEL),
    )


def _make_antigravity_cli(llm_cfg: dict) -> AntigravityCliClient:
    return AntigravityCliClient(
        model=(
            llm_cfg.get("antigravity_flash_model")
            or llm_cfg.get("gemini_flash_model")
            or DEFAULT_ANTIGRAVITY_FLASH_MODEL
        ),
    )


def _make_gemini_cli(llm_cfg: dict) -> AntigravityCliClient:
    return _make_antigravity_cli(llm_cfg)





def _make_ollama(llm_cfg: dict) -> OllamaClient:
    return OllamaClient(
        host=llm_cfg.get("host", DEFAULT_OLLAMA_HOST),
        model=llm_cfg.get("model", DEFAULT_OLLAMA_MODEL),
    )


def _make_by_key(key: str, llm_cfg: dict):
    """Build any client by its backend key string."""
    if key == "ollama":
        return _make_ollama(llm_cfg)
    if key == "claude-code":
        return _make_claude_code(llm_cfg)
    if key in ("antigravity-cli", "gemini-cli", "cloud"):
        return _make_antigravity_cli(llm_cfg)
    return None


def make_client_by_key(key: str, config: dict):
    """Public: build a single backend client by key ('ollama'|'cloud'|'claude-code'|'gemini-cli')."""
    return _make_by_key(key, config.get("llm", {}))


def build_client(
    config: dict,
) -> "OllamaClient | ClaudeCodeClient | AntigravityCliClient | FailoverClient":
    """Return the appropriate LLM client based on config.

    Decision logic (in priority order):
      primary='ollama'      → OllamaClient first; fallback from config
      primary='claude-code' → Claude CLI first; fallback from config or Ollama
      primary='antigravity-cli' → Antigravity CLI first; fallback from config or Ollama
      provider override 'ollama'|'antigravity-cli'|'claude-code' → single explicit client
      auto + RAM ≥ 16 GB → OllamaClient (local)
      auto + RAM < 16 GB → antigravity-cli client
    """
    llm_cfg = config.get("llm", {})
    primary = llm_cfg.get("primary", "")
    fallback = llm_cfg.get("fallback", "")
    probe_interval = int(llm_cfg.get("probe_interval", 60))

    _PRIMARY_ERRORS = {
        "ollama":      _FAILOVER_ERRORS,
        "claude-code": _CLI_PRIMARY_FAILOVER_ERRORS,
        "antigravity-cli":  _CLI_PRIMARY_FAILOVER_ERRORS,
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
            return p_client

        # claude-code / antigravity-cli → default fallback to ollama
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
    if provider == "claude":
        return _make_claude_code(llm_cfg)

    # Auto mode: select based on RAM
    ram_gb = detect_ram_gb()
    if ram_gb >= RAM_THRESHOLD_GB:
        return _make_ollama(llm_cfg)

    # Low-RAM machine: Antigravity CLI with optional remote Ollama failover
    cli_client = _make_antigravity_cli(llm_cfg)
    remote_host = (llm_cfg.get("remote_ollama_host") or "").strip()
    if not remote_host:
        return cli_client

    remote_client = OllamaClient(
        host=remote_host,
        model=llm_cfg.get("model", DEFAULT_OLLAMA_MODEL),
    )
    return FailoverClient([remote_client, cli_client], probe_interval=probe_interval)


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
    probe = llm_cfg.get("probe_interval", 60)

    if primary == "ollama":
        base = f"Ollama  model={model}  host={host}"
        if "fallback" in llm_cfg and not llm_cfg["fallback"]:
            return base
        fallback = llm_cfg.get("fallback", "")
        if fallback:
            return f"Failover  primary=Ollama → fallback={fallback}  probe={probe}s"
        return base

    if primary == "claude-code":
        claude_m = llm_cfg.get("claude_model", DEFAULT_CLAUDE_MODEL)
        fallback = llm_cfg.get("fallback", "")
        if not fallback:
            return f"claude CLI ({claude_m})"
        if fallback == "ollama":
            return f"Failover  primary=claude CLI ({claude_m}) → fallback=Ollama  model={model}  host={host}"
        return f"Failover  primary=claude CLI ({claude_m}) → fallback={fallback}"

    if primary in ("antigravity-cli", "gemini-cli"):
        gemini_m = (
            llm_cfg.get("antigravity_flash_model")
            or llm_cfg.get("gemini_flash_model")
            or DEFAULT_ANTIGRAVITY_FLASH_MODEL
        )
        fallback = llm_cfg.get("fallback", "")
        if not fallback:
            return f"Antigravity CLI ({gemini_m})"
        if fallback == "ollama":
            return f"Failover  primary=Antigravity CLI ({gemini_m}) → fallback=Ollama  model={model}  host={host}"
        return f"Failover  primary=Antigravity CLI ({gemini_m}) → fallback={fallback}"

    # Legacy auto/explicit-provider path
    provider = llm_cfg.get("provider", "auto")
    if provider == "auto":
        provider = "ollama" if ram_gb >= RAM_THRESHOLD_GB else "antigravity-cli"

    remote = llm_cfg.get("remote_ollama_host", "").strip()
    if remote and ram_gb < RAM_THRESHOLD_GB:
        return f"Failover (config)  remote={remote}  fallback=antigravity-cli  probe={probe}s"
    return f"Ollama  [{ram_gb:.1f} GB RAM]  model={model}  host={host}"
