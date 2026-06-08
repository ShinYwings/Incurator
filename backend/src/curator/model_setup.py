"""v0.3.2 search-stack model & dependency provisioning.

Reusable by `setup.sh` (first install) and updates (`git pull && ./setup.sh`) via
the `wiki models ensure` CLI command, and by search providers to free Ollama VRAM
before llama-cpp GGUF models are loaded.

Responsibilities:
- Ensure Ollama is serving when needed for chat/fallback profiles.
- Optionally pull an Ollama embedding model when the active embedding provider is
  Ollama.
- Ensure `llama-cpp-python` is installed (Metal on Apple Silicon).
- Download the embedding + reranker GGUFs and pin model paths in config.
- Best-effort unload configured Ollama LLM models before llama-cpp search loads.

Every step is fail-safe: a missing/unreachable component is reported, never fatal.
Search degrades to FTS5-only (no embeddings) or `no_rerank` (no reranker) per the
engine's documented degradation matrix.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from . import config as cfg
from . import constants as consts
from .llm import list_models_on_host

__all__ = [
    "ModelStep",
    "models_cache_dir",
    "ensure_ollama_serving",
    "ensure_ollama_model",
    "unload_ollama_model",
    "unload_configured_ollama_models",
    "llama_cpp_installed",
    "install_llama_cpp",
    "download_gguf",
    "smoke_test_search_models",
    "ensure_search_models",
]


@dataclass
class ModelStep:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class ModelReport:
    steps: list[ModelStep] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(s.ok for s in self.steps)

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.steps.append(ModelStep(name=name, ok=ok, detail=detail))


def models_cache_dir() -> Path:
    """Project-local model cache (`.cache/models/`)."""
    base = os.environ.get("INCURATOR_MODELS_DIR")
    if base:
        return Path(base).expanduser()
    return Path(__file__).resolve().parents[3] / ".cache" / "models"


# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------


def _ollama_reachable(host: str, *, timeout: float = 2.0) -> bool:
    try:
        with httpx.Client(timeout=timeout) as client:
            return client.get(f"{host.rstrip('/')}/api/tags").status_code == 200
    except Exception:
        return False


def ensure_ollama_serving(host: str, *, wait_seconds: int = 10) -> ModelStep:
    """Start `ollama serve` in the background if it is not already reachable.

    Non-interactive (for the MCP daemon / setup). No-op when already running.
    """
    if _ollama_reachable(host):
        return ModelStep("ollama-serving", True, "already running")
    if not shutil.which(consts.BACKEND_OLLAMA):
        return ModelStep("ollama-serving", False, "ollama not installed (see https://ollama.com)")
    try:
        subprocess.Popen(
            [consts.BACKEND_OLLAMA, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as exc:
        return ModelStep("ollama-serving", False, f"failed to start: {exc}")
    for _ in range(max(1, wait_seconds)):
        time.sleep(1)
        if _ollama_reachable(host, timeout=1.0):
            return ModelStep("ollama-serving", True, "started")
    return ModelStep("ollama-serving", False, "did not become ready in time")


def ensure_ollama_model(host: str, model: str) -> ModelStep:
    """Pull an Ollama model if it is not already present."""
    if not model:
        return ModelStep("ollama-model", True, "no model configured")
    if not _ollama_reachable(host):
        return ModelStep(f"ollama:{model}", False, "ollama not reachable")
    tag = model.split(":")[0]
    present = list_models_on_host(host, timeout=5.0)
    if any(m == model or m.startswith(tag) for m in present):
        return ModelStep(f"ollama:{model}", True, "already pulled")
    if not shutil.which(consts.BACKEND_OLLAMA):
        return ModelStep(f"ollama:{model}", False, "ollama CLI not found; pull manually")
    try:
        res = subprocess.run([consts.BACKEND_OLLAMA, "pull", model])
    except Exception as exc:
        return ModelStep(f"ollama:{model}", False, f"pull error: {exc}")
    if res.returncode == 0:
        return ModelStep(f"ollama:{model}", True, "pulled")
    return ModelStep(f"ollama:{model}", False, f"pull failed (exit {res.returncode})")


def unload_ollama_model(host: str, model: str, *, timeout: float = 5.0) -> ModelStep:
    """Ask Ollama to evict one model from memory with ``keep_alive=0``.

    Best-effort and non-fatal. This frees VRAM before llama-cpp search models are
    loaded, but must not break search when Ollama is absent.
    """
    if not model:
        return ModelStep("ollama-unload", True, "no model configured")
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(
                f"{host.rstrip('/')}/api/generate",
                json={"model": model, "prompt": "", "keep_alive": 0},
            )
        if resp.status_code == 200:
            return ModelStep(f"ollama-unload:{model}", True, "unloaded")
        if resp.status_code == 404:
            return ModelStep(f"ollama-unload:{model}", True, "model not loaded/present")
        return ModelStep(f"ollama-unload:{model}", False, f"HTTP {resp.status_code}")
    except Exception as exc:
        return ModelStep(f"ollama-unload:{model}", False, f"unload skipped: {exc}")


def _configured_ollama_models(config: dict) -> list[str]:
    llm_cfg = config.get("llm", {}) or {}
    ollama_cfg = llm_cfg.get(consts.BACKEND_OLLAMA, {}) or {}
    models: list[str] = []
    for key in ("primary", "fallback"):
        provider, _, model = str(llm_cfg.get(key) or "").partition("::")
        if provider.strip() == consts.BACKEND_OLLAMA and model.strip():
            models.append(model.strip())
    legacy_model = str(ollama_cfg.get("model") or "").strip()
    if legacy_model:
        models.append(legacy_model)
    deduped: list[str] = []
    for model in models:
        if model not in deduped:
            deduped.append(model)
    return deduped


def unload_configured_ollama_models(config: dict | None = None) -> ModelReport:
    """Unload only Incurator-configured Ollama LLM models, never arbitrary apps."""
    config = config or dict(cfg.DEFAULT_CONFIG)
    ollama_host = (config.get("llm", {}).get("ollama", {}) or {}).get("host") or consts.DEFAULT_OLLAMA_HOST
    report = ModelReport()
    for model in _configured_ollama_models(config):
        report.steps.append(unload_ollama_model(ollama_host, model))
    if not report.steps:
        report.add("ollama-unload", True, "no configured Ollama LLM model")
    return report


# ---------------------------------------------------------------------------
# llama-cpp-python (reranker runtime)
# ---------------------------------------------------------------------------


def llama_cpp_installed() -> bool:
    try:
        import llama_cpp  # noqa: F401
        return True
    except Exception:
        return False


def install_llama_cpp(*, metal: bool = True) -> ModelStep:
    """Install `llama-cpp-python`, enabling Metal on Apple Silicon."""
    if llama_cpp_installed():
        return ModelStep("llama-cpp-python", True, "already installed")
    env = dict(os.environ)
    if metal and sys.platform == "darwin":
        # Apple Silicon GPU offload. (CMAKE_ARGS="-DGGML_METAL=on")
        env["CMAKE_ARGS"] = "-DGGML_METAL=on"
    if shutil.which("uv"):
        # Explicitly target *this* interpreter: when `wiki` is installed via
        # `uv tool`, it lives in an isolated env under
        # `~/.local/share/uv/tools/incurator/`. Without `--python`, `uv pip`
        # may install into a different venv and the import will still fail.
        cmd = ["uv", "pip", "install", "--python", sys.executable,
               "llama-cpp-python"]
    else:
        cmd = [sys.executable, "-m", "pip", "install", "llama-cpp-python"]
    try:
        res = subprocess.run(cmd, env=env)
    except Exception as exc:
        return ModelStep("llama-cpp-python", False, f"install error: {exc}")
    if res.returncode == 0:
        # Python caches failed imports in sys.modules. After the subprocess
        # installs the package into the venv, the in-process import finder
        # still holds a stale "not found" result. Clear both caches so the
        # verification import below can discover the freshly-installed package.
        import importlib
        sys.modules.pop("llama_cpp", None)
        importlib.invalidate_caches()
        if llama_cpp_installed():
            return ModelStep("llama-cpp-python", True, "installed")
    return ModelStep(
        "llama-cpp-python",
        False,
        "install failed; run `./setup.sh` from the repository root, or "
        "`uv pip install -e './backend[rerank]'` for a backend-only repair",
    )


# ---------------------------------------------------------------------------
# Reranker GGUF download
# ---------------------------------------------------------------------------


def download_gguf(repo: str, filename: str, dest_dir: Path, *, force: bool = False) -> tuple[Path | None, str]:
    """Download a GGUF from the HuggingFace `resolve/main` endpoint (no hub dep)."""
    dest = dest_dir / filename
    if dest.exists() and dest.stat().st_size > 0 and not force:
        return dest, "already present"
    url = f"https://huggingface.co/{repo}/resolve/main/{filename}"
    dest_dir.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=None) as r:
            if r.status_code != 200:
                return None, f"HTTP {r.status_code} for {url} (check repo/filename)"
            with open(tmp, "wb") as fh:
                for chunk in r.iter_bytes(chunk_size=1 << 20):
                    fh.write(chunk)
        tmp.replace(dest)
        return dest, "downloaded"
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        return None, f"download error: {exc}"


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5 or 1.0
    nb = sum(y * y for y in b) ** 0.5 or 1.0
    return dot / (na * nb)


def smoke_test_search_models(config: dict | None = None) -> ModelReport:
    """Live semantic sanity checks for embedding/reranker providers.

    This intentionally stays tiny: it catches broken GGUF conversions that return
    garbage rerank scores without trying to benchmark quality.
    """
    from .retrieval import providers

    config = config or dict(cfg.DEFAULT_CONFIG)
    search_cfg = config.get("search", {})
    ollama_host = (config.get("llm", {}).get("ollama", {}) or {}).get("host") or consts.DEFAULT_OLLAMA_HOST
    report = ModelReport()

    embedder = providers.build_embedder(search_cfg, ollama_host=ollama_host)
    if embedder is None:
        report.add("embedding-smoke", False, "embedder unavailable")
    else:
        try:
            embed_query = getattr(embedder, "embed_query", None)
            qv = (embed_query(["capital of China"]) if callable(embed_query) else embedder.embed(["capital of China"]))[0]
            docs = embedder.embed([
                "The capital of China is Beijing.",
                "Gravity is a force that attracts masses.",
            ])
            ok = _cosine(qv, docs[0]) > _cosine(qv, docs[1])
            report.add("embedding-smoke", ok, "relevant document ranked above unrelated" if ok else "relevant document did not rank higher")
        except Exception as exc:
            report.add("embedding-smoke", False, f"error: {exc}")

    reranker = providers.build_reranker(search_cfg)
    if reranker is None:
        report.add("reranker-smoke", False, "reranker unavailable")
    else:
        try:
            scores = reranker.score(
                "What is the capital of China?",
                [
                    "The capital of China is Beijing.",
                    "Gravity is a force that attracts masses.",
                ],
            )
            ok = len(scores) == 2 and scores[0] > scores[1]
            report.add("reranker-smoke", ok, "relevant document scored higher" if ok else f"bad ordering: {scores}")
        except Exception as exc:
            report.add("reranker-smoke", False, f"error: {exc}")
    return report


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def ensure_search_models(
    paths: cfg.WikiPaths | None = None,
    config: dict | None = None,
    *,
    serve_ollama: bool = True,
    pull_embed: bool = True,
    install_llama: bool = True,
    download_embedder: bool = True,
    download_reranker: bool = True,
    force: bool = False,
) -> ModelReport:
    """Ensure the v0.3.2 search stack is provisioned. Returns a per-step report.

    `paths` may be None (e.g. during `setup.sh`, before any vault exists): global
    steps (serve/pull/install/download to the host cache) still run; per-vault
    model paths are only persisted when a vault is given. Providers also fall
    back to the cached GGUFs when paths are unset.
    """
    if config is None:
        config = cfg.load_config(paths) if paths is not None else dict(cfg.DEFAULT_CONFIG)
    search_cfg = config.get("search", {})
    ollama_host = (config.get("llm", {}).get("ollama", {}) or {}).get("host") or consts.DEFAULT_OLLAMA_HOST
    report = ModelReport()

    if serve_ollama:
        report.steps.append(ensure_ollama_serving(ollama_host))

    if pull_embed:
        embed_spec = str(search_cfg.get("embedding") or "")
        provider, _, model = embed_spec.partition("::")
        if provider.strip() == consts.BACKEND_OLLAMA and model.strip():
            report.steps.append(ensure_ollama_model(ollama_host, model.strip()))

    uses_llama_embed = str(search_cfg.get("embedding") or "").split("::", 1)[0].strip() == "llama-cpp"
    uses_llama_rerank = search_cfg.get("rerank", True) and str(search_cfg.get("reranker") or "").split("::", 1)[0].strip() == "llama-cpp"

    if install_llama and (uses_llama_embed or uses_llama_rerank):
        report.steps.append(install_llama_cpp())

    if download_embedder and uses_llama_embed:
        repo = str(search_cfg.get("embedding_gguf_repo") or consts.DEFAULT_EMBED_GGUF_REPO)
        filename = str(search_cfg.get("embedding_gguf_file") or consts.DEFAULT_EMBED_GGUF_FILE)
        path, detail = download_gguf(repo, filename, models_cache_dir(), force=force)
        report.add(f"embedding-gguf:{filename}", path is not None, detail)
        if path is not None and str(search_cfg.get("embedding_model_path") or "") != str(path):
            try:
                cfg.save_global_config({"search": {"embedding_model_path": str(path)}})
                report.add("embedding-config", True, f"set embedding_model_path={path}")
            except Exception as exc:
                report.add("embedding-config", False, f"could not persist path: {exc}")

    if download_reranker and search_cfg.get("rerank", True):
        repo = str(search_cfg.get("reranker_gguf_repo") or consts.DEFAULT_RERANK_GGUF_REPO)
        filename = str(search_cfg.get("reranker_gguf_file") or consts.DEFAULT_RERANK_GGUF_FILE)
        path, detail = download_gguf(repo, filename, models_cache_dir(), force=force)
        report.add(f"reranker-gguf:{filename}", path is not None, detail)
        # Persist the resolved path only when a vault exists; otherwise the engine
        # falls back to the cached GGUF automatically (providers.build_reranker).
        if path is not None and str(search_cfg.get("reranker_model_path") or "") != str(path):
            try:
                cfg.save_global_config({"search": {"reranker_model_path": str(path)}})
                report.add("reranker-config", True, f"set reranker_model_path={path}")
            except Exception as exc:
                report.add("reranker-config", False, f"could not persist path: {exc}")

    return report
