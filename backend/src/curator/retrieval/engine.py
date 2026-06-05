"""P7: the v0.3.2 hybrid search engine (DB-native, retires qmd).

Ties the P4–P6 stages into one answer path:

    expand → lexical (FTS5 ×2) + vector (cosine KNN) → RRF fuse → rerank (answer
    path only) → hydrate from the authoritative DB row → persist a ``QTR-`` trace.

Every stage degrades explicitly: no embedder → FTS5-only (``lex``); no reranker →
RRF order (``no_rerank``). The reranker is duck-typed (``Reranker.score``) so the
engine is fully testable with a mock; the concrete GGUF reranker plugs into
``providers.build_reranker`` without touching the engine.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path

from .. import db
from . import expansion as expansion_mod
from . import fusion, lexical, vector
from .providers import Embedder, Reranker

__all__ = ["EngineHit", "EngineResult", "HybridEngine"]

_CANDIDATE_CAP = 100
_RERANK_ALPHA = 0.7  # cross-encoder-led blend; RRF retained as a stabilizer


@dataclass
class EngineHit:
    doc_id: str
    record_type: str
    record_id: str
    title: str = ""
    score: float = 0.0
    snippet: str = ""
    full_content: str = ""
    full_path: str = ""
    family: str = ""
    chunk_id: str = ""
    rrf_score: float = 0.0
    rerank_score: float = 0.0
    source_span_ids: list[str] = field(default_factory=list)
    contributions: list[dict] = field(default_factory=list)


@dataclass
class EngineResult:
    hits: list[EngineHit] = field(default_factory=list)
    fallback_mode: str = ""
    trace_id: str = ""
    warnings: list[str] = field(default_factory=list)
    retrieval_trace: dict = field(default_factory=dict)


def _minmax(values: list[float]) -> list[float]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    return [(v - lo) / span for v in values]


class HybridEngine:
    def __init__(
        self,
        db_path: Path,
        search_config: dict | None = None,
        *,
        embedder: Embedder | None = None,
        reranker: Reranker | None = None,
        expander=None,
    ) -> None:
        self.db_path = db_path
        self.config = search_config or {}
        self.embedder = embedder
        self.reranker = reranker
        self.expander = expander

    @property
    def has_embedder(self) -> bool:
        return self.embedder is not None

    def _vectors_available(self) -> bool:
        """True only if an embedder is configured AND the corpus has vectors.

        Distinguishes "no embedder" from "embedder configured but corpus not yet
        embedded / Ollama unreachable" — both degrade to FTS5-only, but the trace
        warning differs.
        """
        if not self.embedder:
            return False
        return db.has_search_embeddings(self.db_path, self.embedder.provider, self.embedder.model)

    @property
    def has_reranker(self) -> bool:
        return self.reranker is not None

    # ------------------------------------------------------------------
    # candidate lists
    # ------------------------------------------------------------------

    def _vector_list(
        self, text: str, families: set[str] | None
    ) -> tuple[list[str], dict[str, str], float | None]:
        """Return (doc_id rank list, doc_id → best chunk_id, top cosine)."""
        if not self.embedder:
            return [], {}, None
        try:
            embed_query = getattr(self.embedder, "embed_query", None)
            vecs = embed_query([text]) if callable(embed_query) else self.embedder.embed([text])
        except Exception:
            return [], {}, None
        if not vecs:
            return [], {}, None
        hits = vector.vector_search(
            self.db_path, vecs[0], provider=self.embedder.provider,
            model=self.embedder.model, families=families, limit=_CANDIDATE_CAP,
        )
        top_score = hits[0].score if hits else None
        return [h.doc_id for h in hits], {h.doc_id: h.chunk_id for h in hits}, top_score

    # ------------------------------------------------------------------
    # rerank
    # ------------------------------------------------------------------

    def _best_chunk_text(self, doc_id: str, vec_chunk: str | None) -> str:
        if vec_chunk:
            chunk = db.get_search_chunk(self.db_path, vec_chunk)
            if chunk:
                return chunk["text"]
        chunks = db.list_search_chunks_for_doc(self.db_path, doc_id)
        if chunks:
            return chunks[0]["text"]
        doc = db.get_search_document(self.db_path, doc_id)
        return (doc or {}).get("body", "") if doc else ""

    def _rerank(
        self,
        question: str,
        fused: list[fusion.FusedHit],
        chunk_by_doc: dict[str, str],
        limit: int,
    ) -> tuple[list[tuple[fusion.FusedHit, float]], str]:
        """Blend reranker scores with RRF; return [(fused_hit, final_score)]."""
        if not self.reranker:
            ordered = [(h, h.score) for h in fused][:limit]
            return ordered, "no_rerank"
        passages = [self._best_chunk_text(h.doc_id, chunk_by_doc.get(h.doc_id)) for h in fused]
        try:
            raw = self.reranker.score(question, passages)
        except Exception:
            ordered = [(h, h.score) for h in fused][:limit]
            return ordered, "no_rerank"
        rrf_norm = _minmax([h.score for h in fused])
        blended = []
        for hit, ce, rn in zip(fused, raw, rrf_norm):
            final = _RERANK_ALPHA * float(ce) + (1 - _RERANK_ALPHA) * rn
            blended.append((hit, final, float(ce)))
        blended.sort(key=lambda x: x[1], reverse=True)
        return [(h, s) for h, s, _ in blended][:limit], ""

    # ------------------------------------------------------------------
    # hydrate
    # ------------------------------------------------------------------

    def _hydrate(self, doc_id: str) -> dict | None:
        doc = db.get_search_document(self.db_path, doc_id)
        if not doc:
            return None
        body = doc.get("body", "") or ""
        prov = doc.get("provenance") or {}
        locator = doc.get("projection_path") or f"{doc['record_type']}/{doc['record_id']}"
        return {
            "record_type": doc["record_type"],
            "record_id": doc["record_id"],
            "title": doc.get("title", "") or doc["record_id"],
            "body": body,
            "snippet": body[:280],
            "full_path": locator,
            "source_span_ids": prov.get("source_span_ids", []),
        }

    # ------------------------------------------------------------------
    # search
    # ------------------------------------------------------------------

    def search(
        self,
        question: str,
        *,
        families: set[str] | None = None,
        mode: str = "hybrid",
        limit: int = 8,
        min_score: float = 0.0,
        rerank: bool = True,
        want_hyde: bool = False,
        boosts: list[str] | None = None,
        route: str = "local",
        workspace_id: str = "default",
        persist: bool = True,
    ) -> EngineResult:
        started = time.monotonic()
        warnings: list[str] = []
        expanded = expansion_mod.expand(question, boosts=boosts)

        ranked_lists: dict[str, tuple[float, list[str]]] = {}
        chunk_by_doc: dict[str, str] = {}
        lex_hit_count = 0
        top_vector_score: float | None = None

        if mode in ("hybrid", "lex"):
            lex_raw = lexical.lexical_search(self.db_path, question, families=families, limit=_CANDIDATE_CAP)
            lex_hit_count = len(lex_raw)
            ranked_lists["lex_raw"] = (fusion.DEFAULT_WEIGHTS["lex_raw"], [h.doc_id for h in lex_raw])

        vectors_available = self._vectors_available()
        if mode in ("hybrid", "vec") and vectors_available:
            docs, chunks, top_vector_score = self._vector_list(expanded.vec_texts[0], families)
            ranked_lists["vec_raw"] = (fusion.DEFAULT_WEIGHTS["vec_raw"], docs)
            chunk_by_doc.update(chunks)

        expansion_recovery_only = bool(self.config.get("expansion_recovery_only", True))
        vector_floor = float(self.config.get("expansion_vector_confidence_floor", 0.35))
        min_lex_hits = int(self.config.get("expansion_min_lex_hits", 5))
        lex_recovery = mode in ("hybrid", "lex") and lex_hit_count < min_lex_hits
        vector_recovery = (
            mode in ("hybrid", "vec")
            and vectors_available
            and top_vector_score is not None
            and top_vector_score < vector_floor
        )
        recovery_needed = lex_recovery or vector_recovery
        use_expander = self.expander is not None and (
            not expansion_recovery_only or recovery_needed
        )
        if self.config.get("query_expansion", True) and self.expander is None and want_hyde:
            warnings.append("query_expander_unavailable: using deterministic expansion only")

        if use_expander:
            expanded = expansion_mod.expand(
                question,
                boosts=boosts,
                expander=self.expander,
                want_hyde=want_hyde and (recovery_needed or not expansion_recovery_only),
            )

        if mode in ("hybrid", "lex") and expanded.lex_terms_expanded:
            exp_q = " ".join(expanded.lex_terms_expanded)
            lex_exp = lexical.lexical_search(self.db_path, exp_q, families=families, limit=_CANDIDATE_CAP)
            ranked_lists["lex_exp"] = (fusion.DEFAULT_WEIGHTS["lex_exp"], [h.doc_id for h in lex_exp])

        if mode in ("hybrid", "vec") and vectors_available:
            for i, text in enumerate(expanded.vec_texts[1:], 1):
                docs, chunks, _ = self._vector_list(text, families)
                ranked_lists[f"vec_exp{i}"] = (fusion.DEFAULT_WEIGHTS["vec_exp"], docs)
                chunk_by_doc.update(chunks)
            if expanded.hyde_text:
                docs, chunks, _ = self._vector_list(expanded.hyde_text, families)
                ranked_lists["vec_hyde"] = (fusion.DEFAULT_WEIGHTS["vec_hyde"], docs)
                chunk_by_doc.update(chunks)

        fallback_mode = "" if (vectors_available and mode != "lex") else "lex"
        if fallback_mode == "lex" and mode != "lex":
            if self.has_embedder:
                warnings.append("vector_unavailable: no embeddings indexed; run `wiki reindex --embed`")
            else:
                warnings.append("vector_unavailable: no embedder configured (FTS5-only)")

        fuse_cap = int(self.config.get("fuse_cap", 40))
        fused = fusion.rrf_fuse(ranked_lists, candidate_cap=_CANDIDATE_CAP, fuse_cap=fuse_cap)

        do_rerank = rerank and mode == "hybrid"
        if do_rerank:
            ranked, rr_mode = self._rerank(question, fused, chunk_by_doc, limit)
            if rr_mode == "no_rerank":
                fallback_mode = fallback_mode or "no_rerank"
                if self.has_reranker:
                    warnings.append("reranker_failed: returned RRF order")
                else:
                    warnings.append("no reranker configured: returned RRF order")
        else:
            ranked = [(h, h.score) for h in fused][:limit]

        hits: list[EngineHit] = []
        for fused_hit, final in ranked:
            data = self._hydrate(fused_hit.doc_id)
            if not data:
                continue
            hits.append(
                EngineHit(
                    doc_id=fused_hit.doc_id,
                    record_type=data["record_type"],
                    record_id=data["record_id"],
                    title=data["title"],
                    score=final,
                    snippet=data["snippet"],
                    full_content=data["body"],
                    full_path=data["full_path"],
                    family=data["record_type"],
                    chunk_id=chunk_by_doc.get(fused_hit.doc_id, ""),
                    rrf_score=fused_hit.score,
                    rerank_score=final if not fallback_mode.startswith("no_rerank") and do_rerank else 0.0,
                    source_span_ids=data["source_span_ids"],
                    contributions=fused_hit.contributions,
                )
            )

        if min_score > 0:
            kept = [h for h in hits if h.score >= min_score]
            hits = kept or hits[:1]

        latency_ms = int((time.monotonic() - started) * 1000)
        retrieval_trace = {
            "mode": mode,
            "intent": expanded.intent,
            "is_cjk": expanded.is_cjk,
            "expansion": {
                "recovery_only": expansion_recovery_only,
                "recovery_needed": recovery_needed,
                "used": use_expander,
                "lex_hit_count": lex_hit_count,
                "min_lex_hits": min_lex_hits,
                "top_vector_score": top_vector_score,
                "vector_confidence_floor": vector_floor,
                "hyde_used": bool(expanded.hyde_text),
            },
            "lists": {name: {"weight": w, "count": len(docs)} for name, (w, docs) in ranked_lists.items()},
            "fused": [{"doc_id": h.doc_id, "rrf_score": h.score, "contributions": h.contributions} for h in fused[:limit]],
            "fallback_mode": fallback_mode,
            "weights": fusion.DEFAULT_WEIGHTS,
            "fuse_cap": fuse_cap,
            "latency_ms": latency_ms,
        }

        trace_id = ""
        if persist:
            trace_id = db.insert_query_trace(
                self.db_path,
                route=route,
                question_hash=hashlib.sha256(question.encode("utf-8")).hexdigest(),
                workspace_id=workspace_id,
                route_reason="hybrid_engine",
                evidence=[{"doc_id": h.doc_id, "record_id": h.record_id, "score": h.score} for h in hits],
                source_span_ids=sorted({s for h in hits for s in h.source_span_ids}),
                retrieval_trace=retrieval_trace,
                warnings=warnings,
                latency_ms=latency_ms,
            )

        return EngineResult(
            hits=hits,
            fallback_mode=fallback_mode,
            trace_id=trace_id,
            warnings=warnings,
            retrieval_trace=retrieval_trace,
        )
