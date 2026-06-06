"""LLM client layer — supports Ollama (local) and Antigravity (cloud) backends.

Both clients expose the same interface:
  .chat()         — non-streaming, returns str
  .chat_stream()  — streaming generator, yields chunks
  .ensure_ready() — raises LLMError subclass if not operational
  .close()        — release resources
  .ping()         — bool liveness check

Use build_client(config) to get the right backend automatically.
"""

from __future__ import annotations
from . import constants as consts

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from typing import Generator

import httpx

# ---------------------------------------------------------------------------
# Global PATH Augmentation for GUI Environments
# Obsidian plugins inherit a restricted PATH. We must add common local bin paths
# so that shutil.which() and subprocess.run() can find 'agy', 'claude', etc.
# ---------------------------------------------------------------------------
_common_bins = [
    os.path.expanduser("~/.local/bin"),
    os.path.expanduser("~/bin"),
    "/opt/homebrew/bin",
    "/usr/local/bin"
]
_current_path = os.environ.get("PATH", "")
for _p in _common_bins:
    if _p not in _current_path and os.path.isdir(_p):
        _current_path = f"{_p}:{_current_path}"
os.environ["PATH"] = _current_path
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# RAM detection
# ---------------------------------------------------------------------------

RAM_THRESHOLD_GB = 16


def detect_ram_gb() -> float:
    """Return total system RAM in gigabytes (best-effort, never raises)."""
    platform = sys.platform
    try:
        if platform == "darwin":
            out = subprocess.check_output(
                ["sysctl", "-n", "hw.memsize"], timeout=3
            ).decode().strip()
            return int(out) / (1024 ** 3)
        if platform.startswith("linux"):
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        return int(line.split()[1]) / (1024 ** 2)
    except Exception:
        pass
    return 32.0


def has_enough_ram_for_local() -> bool:
    return detect_ram_gb() >= RAM_THRESHOLD_GB


# ---------------------------------------------------------------------------
# Constants & defaults
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Vision / multimodal support
# ---------------------------------------------------------------------------




def is_vision_capable_model(model_name: str) -> bool:
    """Return True if the model name indicates vision/image support."""
    name = model_name.lower().split(":")[0]  # strip tag: "llava:13b" → "llava"
    return any(kw in name for kw in consts.VISION_CAPABLE_KEYWORDS)


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
    host: str = consts.DEFAULT_OLLAMA_HOST, timeout: float = 5.0
) -> list[tuple[str, bool]]:
    """Return all Ollama models with their vision support status.

    Each entry is (model_name, supports_vision).
    Models matching consts.VISION_CAPABLE_KEYWORDS are marked True immediately;
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


class AntigravityCliError(LLMError):
    """Antigravity CLI call failed."""


def _is_capacity_error(text: str) -> bool:
    return (
        "No capacity available" in text
        or "MODEL_CAPACITY_EXHAUSTED" in text
        or "QUOTA_EXHAUSTED" in text
        or "RESOURCE_EXHAUSTED" in text
        or "TerminalQuotaError" in text
        or "exhausted your capacity" in text
        or "Individual quota reached" in text
        or "429" in text
    )


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
        host: str = consts.DEFAULT_OLLAMA_HOST,
        model: str = consts.DEFAULT_OLLAMA_MODEL,
        timeout: float = consts.DEFAULT_TIMEOUT,
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
        """Dynamically set the context window to avoid OOM while maximizing context length.

        Considers both model size AND available system RAM.  On Apple Silicon
        Macs the GPU shares unified memory with the CPU, so large KV caches
        can cause a kernel-panic OOM if the context window is too ambitious.
        """
        name = self.model.lower()
        ram_gb = detect_ram_gb()

        if "70b" in name or "72b" in name:
            return 4096 if ram_gb < 48 else 8192
        elif "14b" in name or "27b" in name or "32b" in name:
            if ram_gb < 16:
                return 4096
            elif ram_gb < 32:
                return 8192
            return 16384
        else:
            # 7B / 8B / 3B class models
            if ram_gb < 12:
                return 4096
            elif ram_gb < 24:
                return 8192
            elif ram_gb < 48:
                return 16384
            return 32768

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
        json_mode: bool = False,
        temperature: float = 0.3,
    ) -> str:
        """Non-streaming chat. Returns the full assistant message content."""
        payload_messages = self._prepare_messages(messages)
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
        json_mode: bool = False,
        temperature: float = 0.3,
    ) -> Generator[str, None, str]:
        """Streaming chat. Yields content chunks as they arrive.

        Prefer this over chat() for long-running generations — each received
        token resets the httpx read timeout, preventing spurious timeouts.
        """
        payload_messages = self._prepare_messages(messages)
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
        self, messages: list[ChatMessage]
    ) -> list[dict]:
        """Convert to Ollama wire format."""
        result = [{"role": m.role, "content": m.content} for m in messages]
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
# Claude client (same interface as OllamaClient / AntigravityCliClient)
# ---------------------------------------------------------------------------





# ---------------------------------------------------------------------------
# OpenAI client
# ---------------------------------------------------------------------------





# ---------------------------------------------------------------------------
# CLI-subprocess clients (Claude Code / Antigravity)
# ---------------------------------------------------------------------------


def _cli_installed(cmd: str) -> bool:
    """Return True if *cmd* is found in PATH."""
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

    CLI = consts.CLOUD_CLAUDE
    INSTALL_CMD = "npm install -g @anthropic-ai/claude-code"

    def __init__(self, model: str = consts.DEFAULT_CLAUDE_MODEL, effort: str = "") -> None:
        self.model = model
        self.effort = effort

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
        # claude CLI exposes reasoning depth via --effort (low|medium|high|xhigh|max).
        if self.effort:
            cmd += ["--effort", self.effort]
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
        # noqa: ARG002
        json_mode: bool = False,  # noqa: ARG002
        temperature: float = 0.3,  # noqa: ARG002
    ) -> str:
        return self._run(_messages_to_prompt(messages))

    def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        # noqa: ARG002
        temperature: float = 0.3,  # noqa: ARG002
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

    def ping(self) -> bool:
        try:
            self.ensure_ready()
            return True
        except ClaudeCodeError:
            return False

    def get_and_reset_token_usage(self) -> tuple[int, int]:
        return (0, 0)




class AntigravityCliClient:
    """LLM backend using the *agy* CLI (Google Antigravity subscription).

    Requires Antigravity CLI, then its login flow.
    """

    CLI = "agy"
    INSTALL_CMD = "curl -fsSL https://antigravity.google/cli/install.sh | bash"

    def __init__(self, model: str = consts.DEFAULT_ANTIGRAVITY_MODEL, effort: str = "") -> None:
        self.model = model
        self.effort = effort
        self._capacity_blocked_until = 0.0

    def _raise_capacity_error(self) -> None:
        self._capacity_blocked_until = time.time() + 300
        raise AntigravityCliError(
            f"Antigravity capacity exhausted (429).\n"
            f"Model tried: '{self.model}'.\n"
            f"Try a local fallback or a lighter model."
        )

    def close(self) -> None:
        pass

    def __enter__(self) -> "AntigravityCliClient":
        return self

    def __exit__(self, *args) -> None:
        pass

    def _run(self, prompt: str) -> str:
        # Antigravity CLI currently exposes model choice through its own
        # settings, not a stable --model flag. Keep the selected model in
        # the prompt for traceability and pass the large payload via stdin.
        log_path = ""
        try:
            log_file = tempfile.NamedTemporaryFile(
                prefix="incurator-agy-", suffix=".log", delete=False
            )
            log_path = log_file.name
            log_file.close()
        except OSError:
            log_path = ""

        cmd = [self.CLI]
        if log_path:
            cmd.extend(["--log-file", log_path])
        cmd.extend(["--print", "--print-timeout", "15m"])
        # agy has no --model/--effort flag, so the preference is embedded as a
        # prompt hint for traceability (best-effort; the active model is chosen
        # in the agy UI/session).
        hint = self.model
        if hint and self.effort:
            hint = f"{self.model} | effort: {self.effort}"
        prompt_with_model = (
            f"[Preferred model: {hint}]\n\n{prompt}"
            if hint else prompt
        )
        env = dict(os.environ)
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

        stderr = result.stderr.strip()
        log_text = ""
        if log_path:
            try:
                with open(log_path, encoding="utf-8", errors="replace") as f:
                    log_text = f.read()
            except OSError:
                log_text = ""
            try:
                os.unlink(log_path)
            except OSError:
                pass

        if result.returncode != 0:
            is_capacity_error = _is_capacity_error(stderr) or _is_capacity_error(log_text)

            if is_capacity_error:
                self._raise_capacity_error()

            raise AntigravityCliError(
                f"Antigravity CLI exited {result.returncode}: {stderr}"
            )
        output = result.stdout.strip()
        if not output:
            if _is_capacity_error(stderr) or _is_capacity_error(log_text):
                self._raise_capacity_error()
            raise AntigravityCliError("Antigravity CLI returned no output.")
        return output

    @property
    def optimal_chunk_chars(self) -> int:
        """Keep CLI prompts modest; subprocess CLIs time out on very large chunks."""
        return 18000

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        # noqa: ARG002
        json_mode: bool = False,  # noqa: ARG002
        temperature: float = 0.3,  # noqa: ARG002
    ) -> str:
        return self._run(_messages_to_prompt(messages))

    def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        # noqa: ARG002
        temperature: float = 0.3,  # noqa: ARG002
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

    def ping(self) -> bool:
        if time.time() < self._capacity_blocked_until:
            return False
        try:
            self.ensure_ready()
            return True
        except AntigravityCliError:
            return False

    def get_and_reset_token_usage(self) -> tuple[int, int]:
        return (0, 0)





# ---------------------------------------------------------------------------
# CodexCliClient — OpenAI Codex CLI backend
# ---------------------------------------------------------------------------


class CodexCliError(LLMError):
    pass


class DeepSeekApiError(LLMError):
    pass


class CodexCliClient:
    """LLM client backed by the OpenAI Codex CLI (`codex exec`)."""

    CLI = "codex"
    INSTALL_CMD = "npm install -g @openai/codex"

    def __init__(self, model: str = consts.DEFAULT_CODEX_MODEL, effort: str = "") -> None:
        self.model = model
        self.effort = effort

    def close(self) -> None:
        pass

    def __enter__(self) -> "CodexCliClient":
        return self

    def __exit__(self, *args) -> None:
        pass

    def clone(self) -> "CodexCliClient":
        return CodexCliClient(model=self.model, effort=self.effort)

    def _run(self, prompt: str) -> str:
        import tempfile
        import os as _os
        out_file = tempfile.mktemp(suffix=".txt")
        cmd = [self.CLI, "--profile", "incurator"]
        # codex exposes reasoning depth through the config override
        # `model_reasoning_effort` (low|medium|high|xhigh).
        if self.effort:
            cmd += ["-c", f"model_reasoning_effort={self.effort}"]
        cmd += [
            "exec",
            "-m", self.model,
            "--sandbox", "read-only",
            "--skip-git-repo-check",
            "--output-last-message", out_file,
            "-",
        ]
        try:
            result = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=900,
            )
        except FileNotFoundError:
            raise CodexCliError(
                f"'{self.CLI}' not found.\n"
                f"Install: {self.INSTALL_CMD}\n"
                "Authenticate: codex login"
            )
        except subprocess.TimeoutExpired:
            raise CodexCliError("Codex CLI timed out after 900 s")

        if _os.path.exists(out_file):
            try:
                text = open(out_file).read().strip()
                _os.unlink(out_file)
                if text:
                    return text
            except OSError:
                pass

        if result.returncode != 0:
            raise CodexCliError(
                f"Codex CLI exited {result.returncode}: {result.stderr.strip()[:400]}"
            )
        return result.stdout.strip()

    @property
    def optimal_chunk_chars(self) -> int:
        return 12000

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        # noqa: ARG002
        json_mode: bool = False,  # noqa: ARG002
        temperature: float = 0.3,  # noqa: ARG002
    ) -> str:
        return self._run(_messages_to_prompt(messages))

    def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        # noqa: ARG002
        temperature: float = 0.3,  # noqa: ARG002
    ) -> Generator[str, None, str]:
        result = self._run(_messages_to_prompt(messages))
        yield result
        return result

    def ensure_ready(self) -> None:
        if not _cli_installed(self.CLI):
            raise CodexCliError(
                f"'{self.CLI}' not installed.\n"
                f"Install: {self.INSTALL_CMD}"
            )
        # Check login credentials
        auth_paths = [
            os.path.join(os.path.expanduser("~"), ".codex", "auth.json"),
            os.path.join(os.path.expanduser("~"), ".config", "codex", "auth.json"),
        ]
        for auth_path in auth_paths:
            if os.path.exists(auth_path):
                try:
                    import json as _json
                    with open(auth_path) as f:
                        data = _json.load(f)
                    if data.get("tokens", {}).get("access_token"):
                        return
                except Exception:
                    pass
        raise CodexCliError(
            "Codex CLI is not authenticated. Run: codex login"
        )

    def ping(self) -> bool:
        try:
            self.ensure_ready()
            return True
        except CodexCliError:
            return False

    def get_and_reset_token_usage(self) -> tuple[int, int]:
        return (0, 0)


class DeepSeekApiClient:
    """OpenAI-compatible DeepSeek API client using DEEPSEEK_API_KEY."""

    def __init__(
        self,
        model: str = consts.DEFAULT_DEEPSEEK_MODEL,
        *,
        base_url: str = "https://api.deepseek.com",
        api_key: str = "",
        api_key_env: str = "DEEPSEEK_API_KEY",
        timeout: float = consts.DEFAULT_TIMEOUT,
        effort: str = "",
    ) -> None:
        self.model = model or consts.DEFAULT_DEEPSEEK_MODEL
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.environ.get(api_key_env, "")
        self.api_key_env = api_key_env
        self.timeout = timeout
        self.effort = effort
        self._client = httpx.Client(timeout=timeout)
        self._job_input_tokens = 0
        self._job_output_tokens = 0

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "DeepSeekApiClient":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def clone(self) -> "DeepSeekApiClient":
        return DeepSeekApiClient(
            model=self.model,
            base_url=self.base_url,
            api_key=self.api_key,
            api_key_env=self.api_key_env,
            timeout=self.timeout,
            effort=self.effort,
        )

    @property
    def optimal_chunk_chars(self) -> int:
        return 50000

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise DeepSeekApiError(
                f"DeepSeek API key is not configured. Set {self.api_key_env}, "
                "llm.deepseek-api.api_key_secret, or legacy llm.deepseek-api.api_key."
            )
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _body(
        self,
        messages: list[ChatMessage],
        *,
        json_mode: bool,
        temperature: float,
        stream: bool,
    ) -> dict:
        body: dict[str, object] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "stream": stream,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        if self.effort:
            body["reasoning_effort"] = self.effort
            body["thinking"] = {"type": "enabled"}
        return body

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        json_mode: bool = False,
        temperature: float = 0.3,
    ) -> str:
        try:
            response = self._client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=self._body(messages, json_mode=json_mode, temperature=temperature, stream=False),
            )
        except httpx.HTTPError as exc:
            raise DeepSeekApiError(f"DeepSeek API request failed: {exc}") from exc

        text = response.text
        if response.status_code >= 400:
            if response.status_code == 429 or _is_capacity_error(text):
                raise DeepSeekApiError(
                    f"DeepSeek quota or capacity exhausted ({response.status_code}): {text[:400]}"
                )
            raise DeepSeekApiError(f"DeepSeek API error {response.status_code}: {text[:400]}")

        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise DeepSeekApiError(f"DeepSeek API returned malformed JSON: {text[:400]}") from exc

        usage = data.get("usage") if isinstance(data, dict) else None
        if isinstance(usage, dict):
            self._job_input_tokens += int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
            self._job_output_tokens += int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "") if isinstance(data, dict) else ""
        if not isinstance(content, str) or not content.strip():
            raise DeepSeekApiError("DeepSeek API returned an empty response.")
        return content.strip()

    def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.3,
    ) -> Generator[str, None, str]:
        result = self.chat(messages, temperature=temperature)
        yield result
        return result

    def ensure_ready(self) -> None:
        if not self.api_key:
            raise DeepSeekApiError(
                f"DeepSeek API key is not configured. Set {self.api_key_env}, "
                "llm.deepseek-api.api_key_secret, or legacy llm.deepseek-api.api_key."
            )

    def ping(self) -> bool:
        try:
            self.ensure_ready()
            return True
        except DeepSeekApiError:
            return False

    def get_and_reset_token_usage(self) -> tuple[int, int]:
        usage = (self._job_input_tokens, self._job_output_tokens)
        self._job_input_tokens = 0
        self._job_output_tokens = 0
        return usage


# ---------------------------------------------------------------------------
# FailoverClient — ordered provider chain with background probe
# ---------------------------------------------------------------------------


_FAILOVER_ERRORS = (OllamaNotRunning, ModelNotFound, OSError)
_CLI_PRIMARY_FAILOVER_ERRORS = _FAILOVER_ERRORS + (ClaudeCodeError, AntigravityCliError, DeepSeekApiError)


class FailoverClient:
    """Wraps an ordered provider list with automatic failover and background probe.

    providers[0] is primary (preferred). On failover_errors, the client advances
    to the next provider and retries, updating active_idx.

    A daemon thread probes providers[0] every probe_interval seconds. If it comes
    back while active_idx > 0, promotes back to primary automatically.

    Interface identical to OllamaClient / AntigravityCliClient / ClaudeClient.
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
        if len(providers) > 1:
            if probe_interval == 0:
                self._console.print(
                    "[dim yellow]incurator:[/dim yellow] FailoverClient probe_interval=0 — "
                    "primary provider will not be auto-recovered after failover."
                )
            else:
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
                    raise LLMError(f"All providers failed: {str(e)[:200]}") from e
        raise LLMError("Unreachable")

    def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.3,
    ) -> Generator[str, None, str]:
        start = self.active_idx
        last_err: Exception | None = None
        for offset in range(len(self.providers)):
            idx = (start + offset) % len(self.providers)
            provider = self.providers[idx]
            try:
                gen = provider.chat_stream(
                    messages, temperature=temperature
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
                    raise LLMError(f"All providers failed during stream: {str(e)[:200]}") from e
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


def _make_claude_code(cfg: dict) -> ClaudeCodeClient:
    model = cfg.get("model") or consts.DEFAULT_CLAUDE_MODEL
    return ClaudeCodeClient(model=model, effort=cfg.get("effort", ""))


def _make_antigravity_cli(cfg: dict) -> AntigravityCliClient:
    model = cfg.get("model") or consts.DEFAULT_ANTIGRAVITY_MODEL
    return AntigravityCliClient(model=model, effort=cfg.get("effort", ""))


def _make_codex_cli(cfg: dict) -> CodexCliClient:
    model = cfg.get("model") or consts.DEFAULT_CODEX_MODEL
    return CodexCliClient(model=model, effort=cfg.get("effort", ""))


def _make_deepseek_api(cfg: dict) -> DeepSeekApiClient:
    model = cfg.get("model") or consts.DEFAULT_DEEPSEEK_MODEL
    api_key = (cfg.get("api_key", "") or "").strip()
    api_key_secret = (cfg.get("api_key_secret", "") or "").strip()
    api_key_env = (cfg.get("api_key_env", "DEEPSEEK_API_KEY") or "DEEPSEEK_API_KEY").strip()
    if not api_key and api_key_secret and not os.environ.get(api_key_env):
        from . import secret_store

        api_key = secret_store.get_secret(api_key_secret)
    # Recover from common misconfiguration where the literal API key is saved
    # into `api_key_env` instead of `api_key`.
    if not api_key and api_key_env.startswith("sk-"):
        api_key = api_key_env
        api_key_env = "DEEPSEEK_API_KEY"
    return DeepSeekApiClient(
        model=model,
        base_url=cfg.get("base_url", "https://api.deepseek.com"),
        api_key=api_key,
        api_key_env=api_key_env,
        timeout=float(cfg.get("timeout", consts.DEFAULT_TIMEOUT)),
        effort=cfg.get("effort", ""),
    )


def _make_ollama(cfg: dict) -> OllamaClient:
    return OllamaClient(
        host=cfg.get("host", consts.DEFAULT_OLLAMA_HOST),
        model=cfg.get("model", consts.DEFAULT_OLLAMA_MODEL),
    )


def _make_by_key(key: str, backend_cfg: dict):
    """Build any client by its backend key string."""
    if key == consts.BACKEND_OLLAMA:
        return _make_ollama(backend_cfg)
    if key == consts.BACKEND_CLAUDE_CODE:
        return _make_claude_code(backend_cfg)
    if key == consts.BACKEND_ANTIGRAVITY_CLI:
        return _make_antigravity_cli(backend_cfg)
    if key == consts.BACKEND_CODEX_CLI:
        return _make_codex_cli(backend_cfg)
    if key == consts.BACKEND_DEEPSEEK_API:
        return _make_deepseek_api(backend_cfg)
    return None


def make_client_by_key(key: str, config: dict):
    """Public: build a single backend client by key."""
    from .config import split_provider_model
    llm_cfg = config.get("llm", {})
    # Find model for this key from primary or fallback
    for slot in ("primary", "fallback"):
        p, m = split_provider_model(llm_cfg.get(slot, ""))
        if p == key:
            if key == consts.BACKEND_OLLAMA:
                return _make_by_key(key, {**llm_cfg.get(consts.BACKEND_OLLAMA, {}), "model": m})
            if key == consts.BACKEND_DEEPSEEK_API:
                return _make_by_key(
                    key,
                    {
                        **llm_cfg.get(consts.BACKEND_DEEPSEEK_API, {}),
                        "model": m,
                        "effort": llm_cfg.get(f"{slot}_effort", ""),
                    },
                )
            return _make_by_key(key, {"model": m, "effort": llm_cfg.get(f"{slot}_effort", "")})
    if key == consts.BACKEND_OLLAMA:
        return _make_by_key(key, llm_cfg.get(consts.BACKEND_OLLAMA, {}))
    if key == consts.BACKEND_DEEPSEEK_API:
        return _make_by_key(key, llm_cfg.get(consts.BACKEND_DEEPSEEK_API, {}))
    return _make_by_key(key, {})


def build_client(
    config: dict,
) -> "OllamaClient | ClaudeCodeClient | AntigravityCliClient | CodexCliClient | DeepSeekApiClient | FailoverClient":
    """Return the appropriate LLM client based on config.

    Decision logic (in priority order):
      primary='ollama'          → OllamaClient; fallback from config
      primary='claude-code'     → Claude CLI; fallback from config or Ollama
      primary='antigravity-cli' → Antigravity CLI; fallback from config or Ollama
      primary='codex-cli'       → Codex CLI; fallback from config or Ollama
      primary='deepseek-api'    → DeepSeek API; fallback from config or Ollama

    """
    from .config import split_provider_model
    llm_cfg = config.get("llm", {})
    probe_interval = int(llm_cfg.get("probe_interval", 60))

    primary,  primary_model  = split_provider_model(llm_cfg.get("primary",  ""))
    fallback, fallback_model = split_provider_model(llm_cfg.get("fallback", ""))
    primary_effort  = llm_cfg.get("primary_effort", "")
    fallback_effort = llm_cfg.get("fallback_effort", "")
    ollama_base = llm_cfg.get(consts.BACKEND_OLLAMA, {})

    if primary == consts.BACKEND_OLLAMA:
        primary_cfg = {**ollama_base, "model": primary_model}
    elif primary == consts.BACKEND_DEEPSEEK_API:
        primary_cfg = {
            **llm_cfg.get(consts.BACKEND_DEEPSEEK_API, {}),
            "model": primary_model,
            "effort": primary_effort,
        }
    else:
        primary_cfg = {"model": primary_model, "effort": primary_effort}

    _PRIMARY_ERRORS = {
        consts.BACKEND_OLLAMA:          _FAILOVER_ERRORS,
        consts.BACKEND_CLAUDE_CODE:     _CLI_PRIMARY_FAILOVER_ERRORS,
        consts.BACKEND_ANTIGRAVITY_CLI: _CLI_PRIMARY_FAILOVER_ERRORS,
        consts.BACKEND_CODEX_CLI:       _CLI_PRIMARY_FAILOVER_ERRORS,
        consts.BACKEND_DEEPSEEK_API:    _CLI_PRIMARY_FAILOVER_ERRORS,
    }

    if primary in _PRIMARY_ERRORS:
        p_client = _make_by_key(primary, primary_cfg)

        # Explicit fallback takes precedence over legacy heuristics
        if fallback and fallback != primary:
            if fallback == consts.BACKEND_OLLAMA:
                fallback_cfg = {**ollama_base, "model": fallback_model}
            elif fallback == consts.BACKEND_DEEPSEEK_API:
                fallback_cfg = {
                    **llm_cfg.get(consts.BACKEND_DEEPSEEK_API, {}),
                    "model": fallback_model,
                    "effort": fallback_effort,
                }
            else:
                fallback_cfg = {"model": fallback_model, "effort": fallback_effort}
            f_client = _make_by_key(fallback, fallback_cfg)
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
        if primary == consts.BACKEND_OLLAMA:
            return p_client

        # claude-code / antigravity-cli → default fallback to ollama
        ollama_cfg = llm_cfg.get(consts.BACKEND_OLLAMA)
        if not isinstance(ollama_cfg, dict):
            ollama_cfg = {}
        ollama = _make_ollama(ollama_cfg)
        return FailoverClient(
            [p_client, ollama],
            probe_interval=probe_interval,
            failover_errors=_CLI_PRIMARY_FAILOVER_ERRORS,
        )

    # No recognized primary — fall back to Antigravity CLI default
    return _make_antigravity_cli({"model": primary_model})


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

    from .config import split_provider_model
    ram_gb = detect_ram_gb()
    llm_cfg  = config.get("llm", {})
    ollama_b = llm_cfg.get(consts.BACKEND_OLLAMA, {})
    host     = ollama_b.get("host", consts.DEFAULT_OLLAMA_HOST)
    probe    = llm_cfg.get("probe_interval", 60)

    primary,  primary_model  = split_provider_model(llm_cfg.get("primary",  ""))
    fallback, fallback_model = split_provider_model(llm_cfg.get("fallback", ""))

    _LABELS = {
        consts.BACKEND_ANTIGRAVITY_CLI: "Antigravity CLI",
        consts.BACKEND_CLAUDE_CODE:     "Claude CLI",
        consts.BACKEND_CODEX_CLI:       "Codex CLI",
        consts.BACKEND_OLLAMA:          "Ollama",
    }

    _DEFAULT_MODELS = {
        consts.BACKEND_ANTIGRAVITY_CLI: consts.DEFAULT_ANTIGRAVITY_MODEL,
        consts.BACKEND_CLAUDE_CODE:     consts.DEFAULT_CLAUDE_MODEL,
        consts.BACKEND_CODEX_CLI:       consts.DEFAULT_CODEX_MODEL,
        consts.BACKEND_OLLAMA:          consts.DEFAULT_OLLAMA_MODEL,
    }

    def _fmt(provider: str, model: str) -> str:
        label = _LABELS.get(provider, provider)
        effective = model or _DEFAULT_MODELS.get(provider, "?")
        if provider == consts.BACKEND_OLLAMA:
            return f"{label}  model={effective}  host={host}"
        return f"{label} ({effective})"

    if not primary:
        # Legacy auto-mode
        if ram_gb >= RAM_THRESHOLD_GB:
            return f"Ollama  [{ram_gb:.1f} GB RAM]  host={host}"
        return f"Antigravity CLI  [{ram_gb:.1f} GB RAM]"

    primary_str = _fmt(primary, primary_model)
    if not fallback:
        return primary_str
    return f"Failover  {primary_str} → {_fmt(fallback, fallback_model)}  probe={probe}s"
