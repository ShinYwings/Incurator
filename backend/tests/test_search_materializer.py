"""v0.3.2 Phase 3: DB record materialization into native search FTS."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from curator import config as cfg
from curator import db
from curator.cli import app
from curator.retrieval import materializer


def _insert_source(db_path: Path, relpath: str = "04_Resources/resnet.md") -> int:
    with db.connect(db_path) as conn:
        return int(
            conn.execute(
                """
                INSERT INTO sources
                    (relpath, content_hash, file_type, bytes, added_at, context_id,
                     l1_status, l2_status, l3_status)
                VALUES (?, ?, 'md', 128, '2026-06-04T00:00:00Z', 'CTX-resnet',
                        'done', 'done', 'done')
                """,
                (relpath, f"h-{relpath}"),
            ).lastrowid
        )


def _seed_authoritative_records(db_path: Path) -> dict[str, str]:
    source_id = _insert_source(db_path)
    span_id = db.upsert_source_span(
        db_path,
        source_id=source_id,
        relpath="04_Resources/resnet.md",
        span_type="paragraph",
        section_title="Residual blocks",
        start_char=10,
        end_char=70,
        content_hash="span-hash",
        text_preview="Residual learning uses skip connections for optimization.",
    )
    unit_id = db.upsert_knowledge_unit(
        db_path,
        unit_type="claim",
        canonical_name="Residual optimization",
        statement="Skip connections ease optimization in deep networks.",
        source_span_ids=[span_id],
        source_id=source_id,
        confidence=0.91,
        atom_node_id="ATM-resnet",
    )
    db.set_unit_support_status(db_path, unit_id, "verified")
    # Served units belong to an authoritative compiler generation (§26.3).
    _gen = db.create_compiler_generation(
        db_path, prompt_contract_version="v2", source_id=source_id)
    db.publish_compiler_generation(db_path, _gen)
    with db.connect(db_path) as conn:
        conn.execute(
            "UPDATE knowledge_units SET generation_id = ? WHERE id = ?", (_gen, unit_id))
    ent_a = db.upsert_graph_entity(
        db_path,
        canonical_name="ResNet",
        entity_type="method",
        description="Residual neural network architecture.",
        source_span_ids=[span_id],
        knowledge_unit_ids=[unit_id],
    )
    ent_b = db.upsert_graph_entity(
        db_path,
        canonical_name="Optimization",
        entity_type="concept",
        description="Training objective improvement.",
        source_span_ids=[span_id],
        knowledge_unit_ids=[unit_id],
    )
    rel_id = db.upsert_graph_relation(
        db_path,
        source_entity_id=ent_a,
        target_entity_id=ent_b,
        relation_type="improves",
        description="ResNet improves optimization via residual connections.",
        source_span_ids=[span_id],
        confidence=0.82,
    )
    report_id = db.upsert_community_report(
        db_path,
        community_key="resnet-community",
        title="Residual learning community",
        summary="Residual learning links architecture and optimization.",
        full_content="Community report with skip connection evidence.",
        dependency_hash="report-deps",
        entity_ids=[ent_a, ent_b],
        relation_ids=[rel_id],
        source_span_ids=[span_id],
        rank=0.8,
    )
    syn_id = db.upsert_synthesis_node(
        db_path,
        title="Residual synthesis",
        statement="Residual connections are a recurring optimization pattern.",
        full_content="Synthesis across reports.",
        dependency_hash="syn-deps",
        community_report_ids=[report_id],
        source_span_ids=[span_id],
        confidence=0.87,
    )
    return {
        "span": span_id,
        "unit": unit_id,
        "entity_a": ent_a,
        "entity_b": ent_b,
        "relation": rel_id,
        "report": report_id,
        "synthesis": syn_id,
    }


def test_materializer_projects_all_authoritative_record_types(tmp_path: Path) -> None:
    db_path = tmp_path / "state.sqlite"
    db.init_db(db_path)
    ids = _seed_authoritative_records(db_path)

    result = materializer.materialize_search_documents(db_path)

    assert result.documents == 7
    docs = db.list_search_documents(db_path)
    assert {doc["record_type"] for doc in docs} == {
        "source_span",
        "knowledge_unit",
        "graph_entity",
        "graph_relation",
        "community_report",
        "synthesis_node",
    }
    by_record = {(doc["record_type"], doc["record_id"]): doc for doc in docs}
    assert by_record[("source_span", ids["span"])]["projection_path"] == "01_Contexts/CTX-resnet.md"
    assert by_record[("knowledge_unit", ids["unit"])]["projection_path"] == "02_Atoms/ATM-resnet.md"
    assert by_record[("synthesis_node", ids["synthesis"])]["projection_path"].startswith("04_Synthesis/")
    assert by_record[("graph_relation", ids["relation"])]["title"] == "ResNet improves Optimization"
    assert db.get_index_meta(db_path, "search_materialized_documents") == "7"

    assert any(hit["record_id"] == ids["unit"] for hit in db.fts_search(db_path, "skip"))
    assert any(hit["record_id"] == ids["report"] for hit in db.fts_search(db_path, "community"))
    assert any(hit["record_id"] == ids["synthesis"] for hit in db.fts_search(db_path, "recurring"))


def test_materializer_rebuild_is_deterministic_and_removes_stale_fts(tmp_path: Path) -> None:
    db_path = tmp_path / "state.sqlite"
    db.init_db(db_path)
    _seed_authoritative_records(db_path)
    db.upsert_search_document(
        db_path,
        record_type="knowledge_unit",
        record_id="STALE",
        title="stale",
        body="obsolete orphan term",
        content_hash="stale",
        dependency_hash="stale",
    )
    assert db.fts_search(db_path, "obsolete")

    first = materializer.materialize_search_documents(db_path)
    assert first.documents == 7
    assert not db.fts_search(db_path, "obsolete")
    snapshot = [
        (
            doc["doc_id"],
            doc["record_type"],
            doc["record_id"],
            doc["title"],
            doc["body"],
            doc["content_hash"],
            doc["dependency_hash"],
            doc["provenance"],
        )
        for doc in db.list_search_documents(db_path)
    ]
    first_hits = db.fts_search(db_path, "residual", limit=20)

    second = materializer.materialize_search_documents(db_path)
    assert second.documents == 7
    assert snapshot == [
        (
            doc["doc_id"],
            doc["record_type"],
            doc["record_id"],
            doc["title"],
            doc["body"],
            doc["content_hash"],
            doc["dependency_hash"],
            doc["provenance"],
        )
        for doc in db.list_search_documents(db_path)
    ]
    assert [hit["doc_id"] for hit in first_hits] == [
        hit["doc_id"] for hit in db.fts_search(db_path, "residual", limit=20)
    ]


def test_cli_reindex_rebuilds_native_search_without_qmd(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    paths = cfg.WikiPaths(vault)
    cfg.save_config(paths, {})
    db.init_db(paths.state_db)
    _seed_authoritative_records(paths.state_db)

    result = CliRunner().invoke(app, ["reindex"], env={"VAULT_ROOT": str(vault)})

    assert result.exit_code == 0, result.output
    assert "Search index rebuilt" in result.output
    assert len(db.list_search_documents(paths.state_db)) == 7


def test_materializer_handles_empty_corpus(tmp_path: Path) -> None:
    db_path = tmp_path / "state.sqlite"
    db.init_db(db_path)

    result = materializer.materialize_search_documents(db_path)

    assert result.documents == 0
    assert db.list_search_documents(db_path) == []
    assert db.get_index_meta(db_path, "search_materialized_documents") == "0"


def test_materializer_indexes_korean_with_trigram_fallback(tmp_path: Path) -> None:
    db_path = tmp_path / "state.sqlite"
    db.init_db(db_path)
    source_id = _insert_source(db_path, relpath="04_Resources/korean.md")
    db.upsert_source_span(
        db_path,
        source_id=source_id,
        relpath="04_Resources/korean.md",
        span_type="paragraph",
        section_title="잔차 학습",
        content_hash="ko-span",
        text_preview="잔차 학습은 최적화를 돕는다.",
    )

    result = materializer.materialize_search_documents(db_path)

    assert result.documents == 1
    docs = db.list_search_documents(db_path)
    assert docs[0]["language"] == "ko"
    assert db.fts_search(db_path, "최적화", trigram=True)


def test_materializer_allows_global_graph_rows_without_source_spans(tmp_path: Path) -> None:
    db_path = tmp_path / "state.sqlite"
    db.init_db(db_path)
    entity_id = db.upsert_graph_entity(
        db_path,
        canonical_name="Workspace Goal",
        entity_type="concept",
        description="A global planning entity without direct citation.",
    )

    result = materializer.materialize_search_documents(db_path)

    assert result.documents == 1
    doc = db.list_search_documents(db_path)[0]
    assert doc["record_type"] == "graph_entity"
    assert doc["record_id"] == entity_id
    assert doc["source_id"] is None
    assert doc["provenance"]["source_span_ids"] == []
