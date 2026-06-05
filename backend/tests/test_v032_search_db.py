"""v0.3.2 Phase 2: DB-native search accessors (SCHEMA_v0.3.2 §11.12–§11.16)."""

from __future__ import annotations

import struct
import tempfile
from pathlib import Path

import pytest

from curator import db


@pytest.fixture()
def db_path():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "state.sqlite"
        db.init_db(path)
        yield path


def test_search_document_roundtrip_and_fts(db_path: Path) -> None:
    doc_id = db.upsert_search_document(
        db_path,
        record_type="knowledge_unit",
        record_id="ATM-1",
        title="Residual learning",
        body="Residual connections ease optimization in nn.Conv2d networks.",
        content_hash="c1",
        dependency_hash="d1",
    )
    got = db.get_search_document(db_path, doc_id)
    assert got is not None and got["record_id"] == "ATM-1"
    assert got["provenance"] == {}

    hits = db.fts_search(db_path, "residual")
    assert any(h["doc_id"] == doc_id for h in hits)
    # dotted identifier preserved by the unicode61 tokenchars config
    assert any(h["doc_id"] == doc_id for h in db.fts_search(db_path, '"nn.Conv2d"'))


def test_fts_reindex_on_upsert_and_delete(db_path: Path) -> None:
    doc_id = db.upsert_search_document(
        db_path, record_type="synthesis_node", record_id="SYN-1",
        title="t", body="alpha beta", content_hash="c", dependency_hash="d",
    )
    assert db.fts_search(db_path, "alpha")
    # re-upsert replaces FTS rows (no duplicate / stale term)
    db.upsert_search_document(
        db_path, record_type="synthesis_node", record_id="SYN-1",
        title="t", body="gamma delta", content_hash="c2", dependency_hash="d2",
    )
    assert not db.fts_search(db_path, "alpha")
    assert db.fts_search(db_path, "gamma")
    db.delete_search_document(db_path, doc_id)
    assert not db.fts_search(db_path, "gamma")
    assert db.get_search_document(db_path, doc_id) is None


def test_trigram_search_for_cjk(db_path: Path) -> None:
    db.upsert_search_document(
        db_path, record_type="source_span", record_id="SPAN-1",
        title="", body="잔차 학습은 최적화를 돕는다", content_hash="c", dependency_hash="d",
    )
    # trigram table supports CJK substring matching (>=3 chars) where unicode61
    # struggles; sub-3-char CJK queries fall back to LIKE at the engine layer (P4).
    assert db.fts_search(db_path, "최적화", trigram=True)


def test_chunk_and_embedding_roundtrip_with_cascade(db_path: Path) -> None:
    doc_id = db.upsert_search_document(
        db_path, record_type="knowledge_unit", record_id="ATM-9",
        title="t", body="b", content_hash="c", dependency_hash="d",
    )
    db.upsert_search_chunk(
        db_path, chunk_id="CHK-1", doc_id=doc_id, record_type="knowledge_unit",
        record_id="ATM-9", chunk_index=0, char_start=0, char_end=3, text="abc",
        input_hash="h1", source_span_ids=["SPAN-1"],
    )
    vec = struct.pack("<3f", 0.1, 0.2, 0.3)
    db.upsert_search_embedding(
        db_path, chunk_id="CHK-1", provider="ollama", model="bge-m3", dim=3,
        vector=vec, input_hash="h1", dependency_hash="d",
    )
    chunks = db.list_search_chunks_for_doc(db_path, doc_id)
    assert len(chunks) == 1 and chunks[0]["source_span_ids"] == ["SPAN-1"]
    embs = db.get_search_embeddings(db_path, "ollama", "bge-m3")
    assert len(embs) == 1 and embs[0]["vector"] == vec
    # deleting the document cascades to chunks and embeddings
    db.delete_search_document(db_path, doc_id)
    assert db.list_search_chunks_for_doc(db_path, doc_id) == []
    assert db.get_search_embeddings(db_path, "ollama", "bge-m3") == []


def test_index_meta(db_path: Path) -> None:
    assert db.get_index_meta(db_path, "embed_fingerprint") is None
    db.set_index_meta(db_path, "embed_fingerprint", "ollama:bge-m3:1024:v1")
    assert db.get_index_meta(db_path, "embed_fingerprint") == "ollama:bge-m3:1024:v1"
    db.set_index_meta(db_path, "embed_fingerprint", "changed")
    assert db.get_index_meta(db_path, "embed_fingerprint") == "changed"


def test_query_trace_persistence(db_path: Path) -> None:
    tid = db.insert_query_trace(
        db_path, route="global", question_hash="qh", workspace_id="Lab",
        route_reason="broad", synthesis_node_ids=["SYN-1"],
        community_report_ids=["REP-1"], retrieval_trace={"rrf": {"k": 60}},
        warnings=["vector_unavailable"], latency_ms=42,
    )
    assert tid.startswith("QTR-")
    got = db.get_query_trace(db_path, tid)
    assert got["route"] == "global"
    assert got["synthesis_node_ids"] == ["SYN-1"]
    assert got["retrieval_trace"] == {"rrf": {"k": 60}}
    assert got["warnings"] == ["vector_unavailable"]
    assert got["latency_ms"] == 42
    listed = db.list_query_traces(db_path, workspace_id="Lab")
    assert [t["trace_id"] for t in listed] == [tid]
