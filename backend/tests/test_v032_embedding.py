"""v0.3.2 Phase 5: chunking + embedding lifecycle (embedder mocked, no model)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest

from curator import db
from curator.retrieval import chunking, embedding, providers


@pytest.fixture()
def db_path():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "state.sqlite"
        db.init_db(path)
        yield path


class _FakeEmbedder:
    """Deterministic stand-in: vector = char-class histogram, no network."""

    provider = "ollama"
    model = "bge-m3"
    dim = 4

    @property
    def fingerprint(self) -> str:
        return f"{self.provider}::{self.model}::{self.dim}"

    def embed(self, texts):
        out = []
        for t in texts:
            v = [
                sum(c.isalpha() for c in t),
                sum(c.isdigit() for c in t),
                sum(c.isspace() for c in t),
                float(len(t)),
            ]
            out.append([float(x) for x in v])
        return out


def _doc(db_path, record_id, title, body, record_type="knowledge_unit"):
    return db.upsert_search_document(
        db_path, record_type=record_type, record_id=record_id,
        title=title, body=body, content_hash=record_id, dependency_hash=record_id,
        provenance={"source_span_ids": ["SPAN-1"]},
    )


# --- chunking ---------------------------------------------------------------


def test_chunk_text_is_deterministic_and_bounded():
    text = ("Sentence one is short. " * 40).strip()
    a = chunking.chunk_text(text, target_tokens=40, max_tokens=60, overlap_tokens=8, min_tokens=8)
    b = chunking.chunk_text(text, target_tokens=40, max_tokens=60, overlap_tokens=8, min_tokens=8)
    assert [c.text for c in a] == [c.text for c in b]  # deterministic
    assert len(a) > 1  # long text splits
    # offsets are valid slices of the source
    assert all(text[c.char_start:c.char_end].strip() == c.text for c in a)


def test_chunk_text_empty_and_single():
    assert chunking.chunk_text("") == []
    one = chunking.chunk_text("Just one sentence.")
    assert len(one) == 1 and one[0].text == "Just one sentence."


# --- pack / unpack ----------------------------------------------------------


def test_pack_vector_normalizes():
    blob, dim = embedding.pack_vector([3.0, 4.0])
    assert dim == 2
    vec = embedding.unpack_vector(blob, dim)
    assert np.isclose(np.linalg.norm(vec), 1.0)


# --- lifecycle --------------------------------------------------------------


def test_materialize_chunks_and_embed_roundtrip(db_path: Path):
    doc = _doc(db_path, "ATM-1", "Residual learning",
               "Residual connections ease optimization. They stabilize deep network training.")
    result = embedding.materialize_chunks(db_path)
    assert result.documents == 1 and result.chunks >= 1
    chunks = db.list_search_chunks_for_doc(db_path, doc)
    assert chunks and chunks[0]["source_span_ids"] == ["SPAN-1"]

    emb = embedding.embed_corpus(db_path, _FakeEmbedder())
    assert emb.embedded == len(chunks) and emb.degraded is False
    stored = db.get_search_embeddings(db_path, "ollama", "bge-m3")
    assert len(stored) == len(chunks)
    assert db.get_index_meta(db_path, "search_embed_fingerprint") == "ollama::bge-m3::4"


def test_embed_corpus_skips_unchanged(db_path: Path):
    _doc(db_path, "ATM-1", "t", "alpha beta gamma delta.")
    embedding.materialize_chunks(db_path)
    first = embedding.embed_corpus(db_path, _FakeEmbedder())
    assert first.embedded >= 1
    second = embedding.embed_corpus(db_path, _FakeEmbedder())
    assert second.embedded == 0 and second.skipped == first.embedded


def test_embed_corpus_degrades_without_embedder(db_path: Path):
    _doc(db_path, "ATM-1", "t", "some body text here.")
    embedding.materialize_chunks(db_path)
    emb = embedding.embed_corpus(db_path, None)
    assert emb.degraded is True and "FTS5-only" in emb.warning
    assert db.get_search_embeddings(db_path, "ollama", "bge-m3") == []


def test_embed_corpus_records_failures(db_path: Path):
    _doc(db_path, "ATM-1", "t", "body one. body two.")
    embedding.materialize_chunks(db_path)

    class _Broken(_FakeEmbedder):
        def embed(self, texts):
            raise RuntimeError("ollama down")

    emb = embedding.embed_corpus(db_path, _Broken())
    assert emb.embedded == 0 and emb.failures >= 1 and "ollama down" in emb.warning


def test_build_embedder_factory():
    cfg = {"embedding": "ollama::bge-m3", "embedding_dim": 1024}
    em = providers.build_embedder(cfg, ollama_host="http://localhost:11434")
    assert isinstance(em, providers.OllamaEmbedder)
    assert em.fingerprint == "ollama::bge-m3::1024"
    assert providers.build_embedder({"embedding": ""}) is None


def test_build_reranker_degrades_safely():
    # rerank disabled
    assert providers.build_reranker({"rerank": False}) is None
    # llama-cpp reranker configured but no model path → degrade (no_rerank)
    assert providers.build_reranker(
        {"rerank": True, "reranker": "llama-cpp::bge-reranker-v2-gemma", "reranker_model_path": ""}
    ) is None
    # model path set but llama-cpp-python absent / load fails → degrade, never raise
    assert providers.build_reranker(
        {"rerank": True, "reranker": "llama-cpp::bge-reranker-v2-gemma",
         "reranker_model_path": "/nonexistent/model.gguf"}
    ) is None
