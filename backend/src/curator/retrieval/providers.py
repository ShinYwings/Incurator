"""P5: Embedder / Reranker provider family for v0.3.2 DB-native search.

Mirrors ``llm.build_client``: duck-typed provider interfaces plus
``build_embedder()`` / ``build_reranker()`` factories driven by ``settings.yml``
``search.embedding`` / ``search.reranker`` (``provider::model``). Providers are
optional — a missing/unreachable provider returns ``None`` so the engine degrades
to FTS5-only (no embeddings) or RRF order (no rerank) rather than hard-failing.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Protocol, runtime_checkable

import httpx

from .. import constants as consts

__all__ = [
    "Embedder",
    "Reranker",
    "OllamaEmbedder",
    "LlamaCppEmbedder",
    "LlamaCppReranker",
    "build_embedder",
    "build_reranker",
    "embedding_identity",
    "embedding_identity_available",
]


@runtime_checkable
class Embedder(Protocol):
    """Turns texts into row vectors. ``fingerprint`` pins the vector space."""

    provider: str
    model: str
    dim: int

    @property
    def fingerprint(self) -> str:  # 'provider::model::dim'
        ...

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text. May raise on transport failure."""
        ...

    def embed_query(self, texts: list[str]) -> list[list[float]]:
        """Return query vectors when the provider has asymmetric instructions."""
        ...


@runtime_checkable
class Reranker(Protocol):
    """Scores (query, passage) pairs; higher = more relevant."""

    provider: str
    model: str

    @property
    def fingerprint(self) -> str:
        ...

    def score(self, query: str, passages: list[str]) -> list[float]:
        ...


def embedding_identity(search_config: dict) -> tuple[str, str] | None:
    """Return the configured embedding provider/model without loading the model."""
    spec = str((search_config or {}).get("embedding") or "").strip()
    if not spec:
        return None
    provider, _, model = spec.partition("::")
    provider = provider.strip()
    model = model.strip()
    if not provider:
        return None
    if provider == consts.BACKEND_OLLAMA:
        model = model or consts.DEFAULT_EMBED_MODEL
    elif provider == "llama-cpp":
        model = model or consts.DEFAULT_EMBED_MODEL
    elif not model:
        return None
    return provider, model


def _llama_cpp_embedding_model_path(search_config: dict) -> Path | None:
    model_path = str((search_config or {}).get("embedding_model_path") or "").strip()
    if model_path:
        path = Path(model_path)
        return path if path.exists() else None

    from ..model_setup import models_cache_dir

    cached = models_cache_dir() / str(
        (search_config or {}).get("embedding_gguf_file") or consts.DEFAULT_EMBED_GGUF_FILE
    )
    if cached.exists() and cached.stat().st_size > 0:
        return cached
    return None


def embedding_identity_available(
    search_config: dict,
    *,
    ollama_host: str | None = None,
) -> bool:
    """Return whether the configured embedding identity is constructible now.

    This is intentionally lighter than ``build_embedder`` for llama-cpp: it
    checks package + model-file availability without loading the GGUF into memory.
    """
    identity = embedding_identity(search_config)
    if identity is None:
        return False
    provider, _model = identity
    if provider == consts.BACKEND_OLLAMA:
        return build_embedder(search_config, ollama_host=ollama_host) is not None
    if provider == "llama-cpp":
        return (
            importlib.util.find_spec("llama_cpp") is not None
            and _llama_cpp_embedding_model_path(search_config) is not None
        )
    return build_embedder(search_config, ollama_host=ollama_host) is not None


class OllamaEmbedder:
    """Ollama ``/api/embed`` backed embedder (e.g. ``bge-m3``, 1024-dim)."""

    def __init__(
        self,
        model: str = consts.DEFAULT_EMBED_MODEL,
        *,
        host: str = consts.DEFAULT_OLLAMA_HOST,
        dim: int = consts.DEFAULT_EMBED_DIM,
        timeout: float = consts.DEFAULT_TIMEOUT,
    ) -> None:
        self.provider = consts.BACKEND_OLLAMA
        self.model = model
        self.host = host.rstrip("/")
        self.dim = dim
        self.timeout = timeout

    @property
    def fingerprint(self) -> str:
        return f"{self.provider}::{self.model}::{self.dim}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(
                f"{self.host}/api/embed",
                json={"model": self.model, "input": texts},
            )
            resp.raise_for_status()
            data = resp.json()
        embeddings = data.get("embeddings") or []
        if len(embeddings) != len(texts):
            raise ValueError(
                f"embed count mismatch: got {len(embeddings)} for {len(texts)} inputs"
            )
        # pin dim from the live model if the configured default was wrong
        if embeddings and len(embeddings[0]) != self.dim:
            self.dim = len(embeddings[0])
        return [[float(x) for x in vec] for vec in embeddings]

    def embed_query(self, texts: list[str]) -> list[list[float]]:
        return self.embed(texts)


def _coerce_vectors(raw) -> list[list[float]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        return [[float(raw)]]
    if not raw:
        return []
    first = raw[0]
    if isinstance(first, (int, float)):
        return [[float(x) for x in raw]]
    return [[float(x) for x in vec] for vec in raw]


class LlamaCppEmbedder:
    """Qwen3 embedding GGUF via llama-cpp-python.

    Document chunks are embedded raw. Query probes receive a short retrieval
    instruction because Qwen3 embeddings are instruction-aware.
    """

    query_instruction = "Retrieve the most relevant knowledge-base chunk for this query."

    def __init__(
        self,
        model: str,
        model_path: str,
        *,
        dim: int = consts.DEFAULT_EMBED_DIM,
        n_ctx: int = 32768,
    ) -> None:
        from llama_cpp import Llama  # lazy: optional dependency

        self.provider = "llama-cpp"
        self.model = model
        self.model_path = model_path
        self.dim = dim
        llama_cpp = __import__("llama_cpp")
        self._llm = Llama(
            model_path=model_path,
            embedding=True,
            pooling_type=getattr(llama_cpp, "LLAMA_POOLING_TYPE_LAST", 2),
            n_ctx=n_ctx,
            verbose=False,
        )

    @property
    def fingerprint(self) -> str:
        return f"{self.provider}::{self.model}::{self.dim}"

    def _embed_inputs(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        raw = self._llm.embed(texts if len(texts) > 1 else texts[0])
        vectors = _coerce_vectors(raw)
        if len(vectors) != len(texts):
            raise ValueError(f"embed count mismatch: got {len(vectors)} for {len(texts)} inputs")
        if vectors and len(vectors[0]) != self.dim:
            self.dim = len(vectors[0])
        return vectors

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._embed_inputs(texts)

    def embed_query(self, texts: list[str]) -> list[list[float]]:
        prefixed = [f"Instruct: {self.query_instruction}\nQuery: {text}" for text in texts]
        return self._embed_inputs(prefixed)


def build_embedder(search_config: dict, *, ollama_host: str | None = None) -> Embedder | None:
    """Construct an embedder from ``search.embedding`` (``provider::model``).

    Returns ``None`` when no embedding is configured (FTS5-only mode).
    """
    spec = str((search_config or {}).get("embedding") or "").strip()
    if not spec:
        return None
    provider, _, model = spec.partition("::")
    provider, model = provider.strip(), model.strip()
    dim = int((search_config or {}).get("embedding_dim") or consts.DEFAULT_EMBED_DIM)
    if provider == consts.BACKEND_OLLAMA:
        return OllamaEmbedder(
            model=model or consts.DEFAULT_EMBED_MODEL,
            host=(ollama_host or consts.DEFAULT_OLLAMA_HOST),
            dim=dim,
        )
    if provider == "llama-cpp":
        model_path = _llama_cpp_embedding_model_path(search_config)
        if model_path is None:
            return None
        try:
            return LlamaCppEmbedder(
                model or consts.DEFAULT_EMBED_MODEL,
                str(model_path),
                dim=dim,
            )
        except Exception:
            return None
    # Other providers (e.g. openai-api text-embedding-3-small) plug in here later.
    return None


class LlamaCppReranker:
    """Qwen3 reranker (or any cross-encoder GGUF) via llama-cpp-python.

    Loaded with rank pooling; ``score`` returns one relevance logit per passage
    (higher = more relevant). All llama-cpp specifics are guarded — a wrong API
    shape or model error raises, and the engine catches it to fall back to
    ``no_rerank`` rather than failing the query. Live validation requires
    ``uv pip install -e './backend[rerank]'`` plus the GGUF model file.
    """

    # Qwen3-Reranker instruction template. The instruction-formatted input gives
    # markedly sharper relevant/irrelevant separation than a bare "query\tpassage"
    # (about 2x the score gap in practice), which keeps ranking stable.
    _INSTRUCTION = "Given a web search query, retrieve relevant passages that answer the query"

    def __init__(self, model: str, model_path: str, *, n_ctx: int = 2048) -> None:
        from llama_cpp import Llama  # lazy: optional dependency

        self.provider = "llama-cpp"
        self.model = model
        self.model_path = model_path
        # pooling_type=RANK (cross-encoder reranker output is a single logit).
        self._llm = Llama(
            model_path=model_path,
            embedding=True,
            pooling_type=getattr(__import__("llama_cpp"), "LLAMA_POOLING_TYPE_RANK", 4),
            n_ctx=n_ctx,
            verbose=False,
        )

    @property
    def fingerprint(self) -> str:
        return f"{self.provider}::{self.model}"

    def _format(self, query: str, passage: str) -> str:
        return f"<Instruct>: {self._INSTRUCTION}\n<Query>: {query}\n<Document>: {passage}"

    def score(self, query: str, passages: list[str]) -> list[float]:
        scores: list[float] = []
        for passage in passages:
            emb = self._llm.embed(self._format(query, passage))
            value = emb
            while isinstance(value, (list, tuple)):
                value = value[0] if value else 0.0
            scores.append(float(value))
        return scores


def build_reranker(search_config: dict) -> Reranker | None:
    """Construct a reranker from ``search.reranker`` + ``search.reranker_model_path``.

    Returns ``None`` (→ ``no_rerank`` degraded mode) when reranking is disabled,
    no model path is configured, llama-cpp-python is not installed, or the model
    fails to load.
    """
    config = search_config or {}
    if not config.get("rerank", True):
        return None
    spec = str(config.get("reranker") or "").strip()
    provider, _, model = spec.partition("::")
    provider, model = provider.strip(), model.strip()
    model_path = str(config.get("reranker_model_path") or "").strip()
    if provider == "llama-cpp":
        if not model_path:
            # Fall back to the host model cache populated by `wiki models ensure`
            # (so a global GGUF download works without per-vault config).
            from ..model_setup import models_cache_dir

            cached = models_cache_dir() / str(
                config.get("reranker_gguf_file") or consts.DEFAULT_RERANK_GGUF_FILE
            )
            if not (cached.exists() and cached.stat().st_size > 0):
                return None
            model_path = str(cached)
        elif not Path(model_path).exists():
            return None
        try:
            return LlamaCppReranker(model or "reranker", model_path)
        except Exception:
            return None  # llama-cpp missing / model load failure → degrade
    # Other reranker providers plug in here later.
    return None
