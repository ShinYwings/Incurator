"""v0.3.2 Phase 6: vector cosine KNN, typed expansion, and RRF fusion.

All deterministic — embeddings are written directly and the Tier-2 expander is a
local stub, so no live model is required.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from curator import db
from curator.retrieval import expansion, fusion, vector
from curator.retrieval.embedding import pack_vector


@pytest.fixture()
def db_path():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "state.sqlite"
        db.init_db(path)
        yield path


def _embed_doc(db_path, doc_id, record_id, vec, record_type="knowledge_unit"):
    db.upsert_search_document(
        db_path, doc_id=doc_id, record_type=record_type, record_id=record_id,
        title="t", body="b", content_hash=doc_id, dependency_hash=doc_id,
    )
    chunk_id = f"CHK-{doc_id}"
    db.upsert_search_chunk(
        db_path, chunk_id=chunk_id, doc_id=doc_id, record_type=record_type,
        record_id=record_id, chunk_index=0, char_start=0, char_end=1, text="b",
        input_hash="h",
    )
    blob, dim = pack_vector(vec)
    db.upsert_search_embedding(
        db_path, chunk_id=chunk_id, provider="ollama", model="bge-m3", dim=dim,
        vector=blob, input_hash="h", dependency_hash="d",
    )
    return doc_id


# --- vector KNN -------------------------------------------------------------


def test_vector_search_orders_by_cosine(db_path: Path):
    near = _embed_doc(db_path, "DOC-1", "ATM-1", [1.0, 0.0, 0.0])
    mid = _embed_doc(db_path, "DOC-2", "ATM-2", [0.7, 0.7, 0.0])
    far = _embed_doc(db_path, "DOC-3", "ATM-3", [0.0, 0.0, 1.0])
    hits = vector.vector_search(db_path, [1.0, 0.0, 0.0], provider="ollama", model="bge-m3")
    assert [h.doc_id for h in hits] == [near, mid, far]
    assert hits[0].rank == 1 and hits[0].score > hits[-1].score


def test_vector_search_family_filter_and_empty(db_path: Path):
    _embed_doc(db_path, "DOC-1", "ATM-1", [1.0, 0.0], record_type="knowledge_unit")
    _embed_doc(db_path, "DOC-2", "SYN-1", [1.0, 0.0], record_type="synthesis_node")
    hits = vector.vector_search(
        db_path, [1.0, 0.0], provider="ollama", model="bge-m3", families={"synthesis_node"}
    )
    assert {h.record_type for h in hits} == {"synthesis_node"}
    # unknown model → no rows → empty (engine degrades to FTS5-only)
    assert vector.vector_search(db_path, [1.0, 0.0], provider="ollama", model="other") == []


def test_vector_search_dim_mismatch_returns_empty(db_path: Path):
    _embed_doc(db_path, "DOC-1", "ATM-1", [1.0, 0.0, 0.0])
    with pytest.raises(vector.VectorCompatibilityError):
        vector.vector_search(db_path, [1.0, 0.0], provider="ollama", model="bge-m3")


def test_vector_search_mixed_index_dimensions_raise(db_path: Path):
    _embed_doc(db_path, "DOC-1", "ATM-1", [1.0, 0.0])
    _embed_doc(db_path, "DOC-2", "ATM-2", [1.0, 0.0, 0.0])

    with pytest.raises(vector.VectorCompatibilityError):
        vector.vector_search(db_path, [1.0, 0.0], provider="ollama", model="bge-m3")


# --- typed expansion --------------------------------------------------------


def test_expand_tier1_intent_and_synonyms():
    exp = expansion.expand("what is RRF")
    assert exp.intent == "definition"
    assert "reciprocal rank fusion" in exp.lex_terms_expanded  # synonym map
    assert exp.vec_texts == ["what is RRF"]
    assert exp.hyde_text == ""


def test_expand_tier2_adds_paraphrases_and_hyde():
    def _stub(_raw):
        return {"lex_terms": ["fusion ranking"], "vec_texts": ["combine rankings"],
                "hyde_text": "RRF combines ranked lists by reciprocal rank."}

    exp = expansion.expand("rank fusion", expander=_stub, want_hyde=True)
    assert "fusion ranking" in exp.lex_terms_expanded
    assert "combine rankings" in exp.vec_texts
    assert exp.hyde_text.startswith("RRF combines")


def test_expand_tier2_failure_is_non_fatal():
    def _broken(_raw):
        raise RuntimeError("expander down")

    exp = expansion.expand("rank fusion", expander=_broken, want_hyde=True)
    assert exp.vec_texts == ["rank fusion"]  # falls back to Tier-1


# --- RRF fusion -------------------------------------------------------------


def test_rrf_fuse_weights_and_trace():
    lists = {
        "lex_raw": (1.0, ["A", "B", "C"]),
        "vec_raw": (0.9, ["B", "A", "D"]),
    }
    fused = fusion.rrf_fuse(lists)
    ids = [h.doc_id for h in fused]
    # A and B appear in both lists → outrank single-list C/D
    assert set(ids[:2]) == {"A", "B"}
    top = fused[0]
    assert top.rank == 1
    assert {c["list"] for c in top.contributions} == {"lex_raw", "vec_raw"}


def test_rrf_original_query_outweighs_expansion():
    # A leads only the expansion list; B leads the high-weight raw list.
    lists = {
        "lex_raw": (1.0, ["B"]),
        "lex_exp": (0.6, ["A", "B"]),
    }
    fused = fusion.rrf_fuse(lists)
    assert fused[0].doc_id == "B"  # original-query weighting wins


def test_rrf_caps_and_determinism():
    lists = {"lex_raw": (1.0, [f"D{i}" for i in range(200)])}
    a = fusion.rrf_fuse(lists, fuse_cap=10)
    b = fusion.rrf_fuse(lists, fuse_cap=10)
    assert len(a) == 10
    assert [h.doc_id for h in a] == [h.doc_id for h in b]
