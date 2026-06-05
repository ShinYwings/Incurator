"""P5: Embedder / Reranker provider family for v0.3.2 DB-native search.

Mirrors ``llm.build_client``: duck-typed provider interfaces plus
``build_embedder()`` / ``build_reranker()`` factories driven by ``config.yml``
``search.embedding`` / ``search.reranker`` (``provider::model``). Providers are
optional — a missing/unreachable provider returns ``None`` so the engine degrades
to FTS5-only (no embeddings) or RRF order (no rerank) rather than hard-failing.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import httpx

from .. import constants as consts

__all__ = [
    "Embedder",
    "Reranker",
    "OllamaEmbedder",
    "LlamaCppReranker",
    "build_embedder",
    "build_reranker",
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
    # Other providers (e.g. openai-api text-embedding-3-small) plug in here later.
    return None


class LlamaCppReranker:
    """bge-reranker-v2-gemma (or any cross-encoder GGUF) via llama-cpp-python.

    Loaded with rank pooling; ``score`` returns one relevance logit per passage
    (higher = more relevant). All llama-cpp specifics are guarded — a wrong API
    shape or model error raises, and the engine catches it to fall back to
    ``no_rerank`` rather than failing the query. Live validation requires
    ``pip install 'incurator[rerank]'`` plus the GGUF model file.
    """

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

    def score(self, query: str, passages: list[str]) -> list[float]:
        scores: list[float] = []
        for passage in passages:
            emb = self._llm.embed(f"{query}\t{passage}")
            value = emb[0] if isinstance(emb, (list, tuple)) else emb
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
            return None
        try:
            return LlamaCppReranker(model or "reranker", model_path)
        except Exception:
            return None  # llama-cpp missing / model load failure → degrade
    # Other reranker providers plug in here later.
    return None
