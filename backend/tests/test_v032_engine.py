"""v0.3.2 Phase 7: hybrid engine answer path, rerank blend, trace persistence.

Embedder and reranker are mocks — no live model. Verifies fusion wiring,
rerank reordering, graceful degradation, and durable QTR- trace rows.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from curator import db
from curator.retrieval import embedding
from curator.retrieval.engine import HybridEngine


@pytest.fixture()
def db_path():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "state.sqlite"
        db.init_db(path)
        yield path


class _FakeEmbedder:
    provider = "ollama"
    model = "bge-m3"
    dim = 3

    @property
    def fingerprint(self):
        return "ollama::bge-m3::3"

    def embed(self, texts):
        # crude bag-of-keyword vector so "residual" queries lean toward the
        # residual doc; deterministic, no network.
        out = []
        for t in texts:
            low = t.lower()
            out.append([
                float("residual" in low or "잔차" in low),
                float("attention" in low),
                float(len(low) % 3),
            ])
        return out


def _seed(db_path):
    for rid, title, body, vec in [
        ("ATM-1", "Residual learning", "Residual connections ease optimization in deep nets.", None),
        ("ATM-2", "Attention", "Attention weights tokens by relevance across the sequence.", None),
    ]:
        db.upsert_search_document(
            db_path, record_type="knowledge_unit", record_id=rid, title=title,
            body=body, content_hash=rid, dependency_hash=rid,
            provenance={"source_span_ids": [f"SPAN-{rid}"]},
        )
    embedding.materialize_chunks(db_path)
    embedding.embed_corpus(db_path, _FakeEmbedder())


def test_engine_hybrid_returns_hits_and_persists_trace(db_path: Path):
    _seed(db_path)
    engine = HybridEngine(db_path, embedder=_FakeEmbedder())
    result = engine.search("residual optimization", limit=5)
    assert result.hits
    assert result.hits[0].record_id == "ATM-1"
    assert result.fallback_mode == "no_rerank"  # no reranker configured
    # durable trace
    assert result.trace_id.startswith("QTR-")
    trace = db.get_query_trace(db_path, result.trace_id)
    assert trace is not None
    assert trace["retrieval_trace"]["intent"] in {"default", "definition", "procedure", "comparison"}
    assert "lex_raw" in trace["retrieval_trace"]["lists"]


def test_engine_degrades_to_fts_only_without_embedder(db_path: Path):
    _seed(db_path)
    engine = HybridEngine(db_path, embedder=None)
    result = engine.search("residual", limit=5)
    assert result.fallback_mode == "lex"
    assert any("vector_unavailable" in w for w in result.warnings)
    assert result.hits and result.hits[0].record_id == "ATM-1"


def test_engine_reranker_reorders_and_clears_fallback(db_path: Path):
    _seed(db_path)

    class _Reranker:
        provider = "ollama"
        model = "bge-reranker"

        @property
        def fingerprint(self):
            return "ollama::bge-reranker"

        def score(self, query, passages):
            # force the attention passage to the top regardless of RRF
            return [1.0 if "attention" in p.lower() else 0.0 for p in passages]

    engine = HybridEngine(db_path, embedder=_FakeEmbedder(), reranker=_Reranker())
    result = engine.search("deep learning", limit=5)
    assert result.fallback_mode == ""  # reranker engaged
    assert result.hits[0].record_id == "ATM-2"
    assert result.hits[0].rerank_score >= result.hits[-1].rerank_score


def test_engine_reranker_failure_degrades(db_path: Path):
    _seed(db_path)

    class _BrokenReranker:
        provider = "x"
        model = "y"
        fingerprint = "x::y"

        def score(self, query, passages):
            raise RuntimeError("rerank model crashed")

    engine = HybridEngine(db_path, embedder=_FakeEmbedder(), reranker=_BrokenReranker())
    result = engine.search("residual", limit=5)
    assert result.fallback_mode == "no_rerank"
    assert any("reranker_failed" in w for w in result.warnings)
    assert result.hits


def test_engine_no_persist(db_path: Path):
    _seed(db_path)
    engine = HybridEngine(db_path, embedder=_FakeEmbedder())
    result = engine.search("residual", persist=False)
    assert result.trace_id == ""
    assert db.list_query_traces(db_path) == []


def test_engine_skips_expander_when_recovery_only_confidence_is_high(db_path: Path):
    _seed(db_path)
    calls = []

    def _expander(raw):
        calls.append(raw)
        return {"lex_terms": ["attention"], "vec_texts": ["attention"], "hyde_text": "attention"}

    engine = HybridEngine(
        db_path,
        {
            "query_expansion": True,
            "expansion_recovery_only": True,
            "expansion_min_lex_hits": 1,
            "expansion_vector_confidence_floor": 0.0,
        },
        embedder=_FakeEmbedder(),
        expander=_expander,
    )
    result = engine.search("residual optimization", rerank=False, want_hyde=True, persist=False)
    assert calls == []
    assert result.retrieval_trace["expansion"]["used"] is False
    assert "vec_hyde" not in result.retrieval_trace["lists"]


def test_engine_uses_expander_when_recovery_is_needed(db_path: Path):
    _seed(db_path)
    calls = []

    def _expander(raw):
        calls.append(raw)
        return {"lex_terms": ["attention"], "vec_texts": ["attention"], "hyde_text": "attention"}

    engine = HybridEngine(
        db_path,
        {
            "query_expansion": True,
            "expansion_recovery_only": True,
            "expansion_min_lex_hits": 5,
            "expansion_vector_confidence_floor": 0.0,
        },
        embedder=_FakeEmbedder(),
        expander=_expander,
    )
    result = engine.search("residual optimization", rerank=False, want_hyde=True, persist=False)
    assert calls == ["residual optimization"]
    assert result.retrieval_trace["expansion"]["used"] is True
    assert result.retrieval_trace["expansion"]["hyde_used"] is True
    assert "lex_exp" in result.retrieval_trace["lists"]
    assert "vec_hyde" in result.retrieval_trace["lists"]
