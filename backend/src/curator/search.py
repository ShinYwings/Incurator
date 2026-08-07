"""Search backend — DB-native hybrid search.

Search runs entirely inside `state.sqlite`: FTS5 (BM25) lexical retrieval +
chunk-level vector cosine KNN, fused with RRF and optionally reranked. The
heavy lifting lives in `curator.retrieval` (engine/lexical/vector/fusion/
expansion/providers); this module keeps the stable public surface
(`SearchHit`/`SearchResults`/`query`/`update_index`) that callers depend on.

There is no external binary: lexical search always works (FTS5 is bundled in
Python's SQLite); vector and rerank degrade gracefully when their models are
unavailable. `search_source_pages` is a separate lexical helper over raw
tracked files for provenance lookups.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from . import config as cfg


def _uses_llama_cpp_search_model(search_config: dict, *, include_reranker: bool = True) -> bool:
    embed_provider = str((search_config or {}).get("embedding") or "").split("::", 1)[0].strip()
    rerank_provider = str((search_config or {}).get("reranker") or "").split("::", 1)[0].strip()
    return embed_provider == "llama-cpp" or (
        include_reranker and (search_config or {}).get("rerank", True) and rerank_provider == "llama-cpp"
    )


def _free_ollama_vram_before_llama_cpp(config: dict, search_config: dict, *, include_reranker: bool = True) -> None:
    """Best-effort VRAM guard before loading llama-cpp search GGUFs."""
    if not _uses_llama_cpp_search_model(search_config, include_reranker=include_reranker):
        return
    try:
        from . import model_setup

        model_setup.unload_configured_ollama_models(config)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class SearchHit:
    """One ranked search result."""

    full_path: str           # relpath inside `.curator/Collections/`, e.g. '02_Atoms/ATM-abc12345.md'
    title: str = ""
    score: float = 0.0
    snippet: str = ""
    full_content: str = ""   # populated when hydrate=True
    docid: str = ""          # legacy content-hash short id (#abc123)
    source_span_ids: list[str] = field(default_factory=list)
    # The engine knows both of these; dropping them here is what made real L4
    # content arrive with an empty `synthesis_node_id`, invisible to the pack's
    # own counters (knowledge-value audit, 2026-08-07).
    record_type: str = ""
    support_status: str = ""


@dataclass
class SearchResults:
    """Ranked list of hits returned from one query call."""

    hits: list[SearchHit] = field(default_factory=list)
    fallback_mode: str = ""  # set when hybrid degraded (e.g. "lex"/"no_rerank")
    warnings: list[str] = field(default_factory=list)
    trace_id: str = ""
    retrieval_trace: dict = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.hits)

    def __iter__(self) -> Iterable[SearchHit]:
        return iter(self.hits)


@dataclass
class SourcePageHit:
    """One lexical hit inside a tracked source file."""

    source_id: int
    relpath: str
    file_type: str
    page_number: int | None = None
    score: float = 0.0
    title: str = ""
    snippet: str = ""


@dataclass
class IndexUpdateResult:
    """Outcome of a DB-native search index refresh."""

    updated: bool = False
    embedded: bool = False
    embed_requested: bool = False
    degraded: bool = False
    warning: str = ""


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class SearchBackendError(Exception):
    """The DB-native search engine failed (e.g. malformed FTS5 query, DB error)."""


# ---------------------------------------------------------------------------
# Engine capability probes
# ---------------------------------------------------------------------------


def is_available() -> bool:
    """True — the DB-native search engine (FTS5, bundled in SQLite) is always available.

    Kept for caller/status compatibility after the DB-native search migration.
    Vector/rerank availability is a separate, gracefully-degrading concern.
    """
    return True


def get_version() -> str | None:
    """Return the DB-native search engine version string."""
    from . import __version__

    return f"native-{__version__}"


# ---------------------------------------------------------------------------
# Index management
# ---------------------------------------------------------------------------


def update_index(paths: cfg.WikiPaths, *, embed: bool = False) -> IndexUpdateResult:
    """Rebuild the DB-native search index.

    Materializes `search_documents`/FTS/`search_chunks` from the authoritative
    `state.sqlite` rows and, when `embed=True`, generates chunk embeddings via the
    configured embedder. Embedding degrades gracefully (FTS5-only) when no
    embedder is configured or the model is unreachable.
    """
    from .retrieval import embedding, materializer, providers

    config = cfg.load_config(paths)
    search_config = config.get("search", {})
    result = materializer.materialize_search_documents(paths.state_db, search_config)
    outcome = IndexUpdateResult(updated=True, embed_requested=embed)
    if embed:
        ollama_host = (config.get("llm", {}).get("ollama", {}) or {}).get("host")
        identity = providers.embedding_identity(search_config)
        if identity is not None:
            provider, model = identity
            total, ready = embedding.current_embedding_coverage(
                paths.state_db, provider, model
            )
            if total == ready and providers.embedding_identity_available(
                search_config,
                ollama_host=ollama_host,
            ):
                outcome.embedded = ready > 0
                return outcome
        _free_ollama_vram_before_llama_cpp(config, search_config, include_reranker=False)
        embedder = providers.build_embedder(search_config, ollama_host=ollama_host)
        emb = embedding.embed_corpus(paths.state_db, embedder)
        outcome.embedded = (emb.embedded + emb.skipped) > 0
        if emb.degraded or emb.warning:
            outcome.degraded = True
            outcome.warning = emb.warning or "vector embeddings unavailable (FTS5-only)"
    else:
        outcome.warning = f"indexed {result.documents} documents, {result.chunks} chunks"
    return outcome


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def query(
    paths: cfg.WikiPaths,
    question: str,
    *,
    mode: str = "hybrid",
    limit: int = 8,
    min_score: float = 0.0,
    collections: list[str] | None = None,
    hydrate: bool = True,
    rerank: bool = True,
    families: set[str] | None = None,
    workspace_id: str = "default",
    persist: bool = True,
) -> SearchResults:
    """Run a DB-native hybrid search and return ranked, hydrated hits (v0.3.2).

    Searches `state.sqlite` directly (FTS5 + chunked vector + RRF + optional
    rerank). The `SearchHit`/`SearchResults`
    field shapes are preserved so callers (`query.py`, `evidence.py`, MCP, plugin)
    are unchanged.

    Args:
        paths:        Wiki project paths.
        question:     User query string.
        mode:         'hybrid' (lexical+vector+rerank), 'lex' (FTS5 only),
                      'vec' (vector only).
        limit:        Max number of hits returned.
        min_score:    Advisory filter on the blended score. Native scores are not
                      on a fixed 0–1 scale; defaults to 0 (no hard filter) so RRF-only
                      results are not discarded. The engine never returns empty on
                      a borderline single hit.
        collections:  Legacy collection names — ignored (single corpus now).
        hydrate:      Populate `full_content` from the authoritative DB row.
        rerank:       Apply rerank in hybrid mode when a reranker is configured.
        families:     Optional record-type filter (route-scoped retrieval).
        workspace_id: KRS/workspace id recorded on the persisted query trace.
        persist:      Persist a durable `QTR-` query trace.
    """
    from .retrieval import providers
    from .retrieval.engine import HybridEngine

    config = cfg.load_config(paths)
    search_config = config.get("search", {})
    _free_ollama_vram_before_llama_cpp(config, search_config, include_reranker=rerank)
    ollama_host = (config.get("llm", {}).get("ollama", {}) or {}).get("host")
    embedder = providers.build_embedder(search_config, ollama_host=ollama_host)
    reranker = providers.build_reranker(search_config)

    # Tier-2 LLM query expansion (lex/vec/hyde) only on the answer path, where one
    # extra LLM call is acceptable alongside synthesis. Fail-safe → Tier-1 only.
    expander = None
    want_hyde = mode == "hybrid" and rerank
    if want_hyde:
        from .retrieval.query_expander import build_query_expander
        expander = build_query_expander(config, want_hyde=True)

    engine = HybridEngine(
        paths.state_db, search_config, embedder=embedder, reranker=reranker,
        expander=expander,
    )
    result = engine.search(
        question,
        families=families,
        mode=mode,
        limit=limit,
        min_score=min_score,
        rerank=rerank,
        want_hyde=want_hyde,
        workspace_id=workspace_id,
        persist=persist,
    )

    hits = [
        SearchHit(
            full_path=h.full_path,
            title=h.title,
            score=h.score,
            snippet=h.snippet,
            full_content=h.full_content if hydrate else "",
            docid=h.record_id,
            source_span_ids=h.source_span_ids,
            record_type=h.record_type,
            support_status=h.support_status,
        )
        for h in result.hits
    ]
    return SearchResults(
        hits=hits,
        fallback_mode=result.fallback_mode,
        warnings=result.warnings,
        trace_id=result.trace_id,
        retrieval_trace=result.retrieval_trace,
    )


def _snippet(text: str, query: str, *, width: int = 320) -> str:
    lowered = text.lower()
    idx = lowered.find(query.lower())
    if idx < 0:
        for token in _query_tokens(query):
            idx = lowered.find(token)
            if idx >= 0:
                break
    if idx < 0:
        idx = 0
    start = max(0, idx - width // 3)
    end = min(len(text), start + width)
    snippet = text[start:end].strip()
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet += "..."
    return snippet


def _query_tokens(query: str) -> list[str]:
    return [tok for tok in re.findall(r"[\w가-힣]+", query.lower()) if len(tok) > 1]


def lexical_score(text: str, query: str) -> float:
    if not text:
        return 0.0
    lowered = text.lower()
    exact = lowered.count(query.lower()) if query.strip() else 0
    token_hits = sum(lowered.count(tok) for tok in _query_tokens(query))
    return float(exact * 5 + token_hits)


def search_source_pages(
    paths: cfg.WikiPaths,
    query: str,
    *,
    limit: int = 8,
    source_id: int | None = None,
) -> list[SourcePageHit]:
    """Lexically search tracked raw sources, preserving PDF page numbers.

    This is intentionally simple and local. Curator DAG search still goes
    through the DB-native index; this helper is for provenance lookups against
    original files.
    """
    from . import db, parsers

    if not query.strip() or not paths.state_db.exists():
        return []

    sql = "SELECT id, relpath, file_type FROM sources"
    params: tuple = ()
    if source_id is not None:
        sql += " WHERE id = ?"
        params = (source_id,)
    sql += " ORDER BY id ASC"

    with db.connect(paths.state_db) as conn:
        rows = conn.execute(sql, params).fetchall()

    hits: list[SourcePageHit] = []
    for row in rows:
        sid = int(row["id"])
        relpath = str(row["relpath"])
        file_path = paths.root / relpath
        if not file_path.exists() or not parsers.is_supported(file_path):
            continue
        try:
            parsed = parsers.parse(file_path)
        except Exception:
            continue

        if parsed.file_type == "pdf":
            pages = parsed.metadata.get("pdf_pages") or []
            for idx, page_meta in enumerate(pages):
                page_number = int(page_meta.get("page") or idx + 1)
                text = str(page_meta.get("text") or "")
                score = lexical_score(text, query)
                if score <= 0:
                    continue
                hits.append(
                    SourcePageHit(
                        source_id=sid,
                        relpath=relpath,
                        file_type=parsed.file_type,
                        page_number=page_number,
                        score=score,
                        title=parsed.title,
                        snippet=_snippet(text, query),
                    )
                )
        else:
            score = lexical_score(parsed.text, query)
            if score <= 0:
                continue
            hits.append(
                SourcePageHit(
                    source_id=sid,
                    relpath=relpath,
                    file_type=parsed.file_type,
                    score=score,
                    title=parsed.title,
                    snippet=_snippet(parsed.text, query),
                )
            )

    hits.sort(key=lambda hit: hit.score, reverse=True)
    return hits[:limit]
