"""P5 source lifecycle closure and replica replay regressions."""

from __future__ import annotations

import json
from pathlib import Path

from curator import config as cfg
from curator import db
from curator import ingest_raw
from curator.db_sync import export_knowledge, import_knowledge, record_tombstone
from curator.pipeline import compile as compile_pipeline
from curator.retrieval import materializer


def _seed_compiled_source(
    paths: cfg.WikiPaths,
    relpath: str,
    *,
    content_hash: str,
) -> dict[str, object]:
    source_path = paths.root / relpath
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(f"# {relpath}\n\nGrounded source text.\n", encoding="utf-8")
    with db.connect(paths.state_db) as conn:
        source_id = int(
            conn.execute(
                "INSERT INTO sources "
                "(relpath, content_hash, file_type, bytes, added_at, context_id, "
                "l1_status, l2_status) VALUES (?, ?, 'md', 24, ?, ?, 'done', 'done')",
                (
                    relpath,
                    content_hash,
                    "2026-07-01T00:00:00.000000Z",
                    f"CTX-{content_hash[-8:]}",
                ),
            ).lastrowid
        )
    span_id = db.upsert_source_span(
        paths.state_db,
        source_id=source_id,
        relpath=relpath,
        span_type="heading_section",
        content_hash=f"span-{content_hash}",
        text_preview="Grounded source text.",
    )
    generation_id = db.create_compiler_generation(
        paths.state_db,
        prompt_contract_version="curator.compile.v2",
        source_id=source_id,
    )
    unit_id = db.upsert_knowledge_unit(
        paths.state_db,
        unit_type="claim",
        canonical_name=f"Claim {content_hash}",
        statement=f"Claim from {relpath}.",
        source_span_ids=[span_id],
        source_id=source_id,
        confidence=0.9,
        truth_status="source_supported",
    )
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "UPDATE knowledge_units SET generation_id = ?, "
            "support_status = 'verified' WHERE id = ?",
            (generation_id, unit_id),
        )
    db.upsert_claim_support(
        paths.state_db,
        knowledge_unit_id=unit_id,
        source_span_id=span_id,
        support_role="primary",
        support_status="verified",
        evidence_hash=f"span-{content_hash}",
    )
    db.publish_compiler_generation(
        paths.state_db,
        generation_id,
        audit_json=json.dumps(
            {
                "authored_relation_ids": [],
                "content_hash": content_hash,
                "unit_count": 1,
                "unit_ids": [unit_id],
            },
            sort_keys=True,
        ),
    )
    with db.connect(paths.state_db) as conn:
        sync_key = str(
            conn.execute(
                "SELECT sync_key FROM sources WHERE id = ?", (source_id,)
            ).fetchone()[0]
        )
    return {
        "source_id": source_id,
        "sync_key": sync_key,
        "span_id": span_id,
        "generation_id": generation_id,
        "unit_id": unit_id,
    }


def test_local_source_removal_closes_authoritative_serving_state(
    tmp_path: Path,
) -> None:
    paths = cfg.WikiPaths(tmp_path)
    db.init_db(paths.state_db)
    seeded = _seed_compiled_source(
        paths,
        "04_Resources/remove-me.md",
        content_hash="source-a",
    )
    materializer.materialize_search_documents(paths.state_db)
    assert db.get_search_document(
        paths.state_db,
        f"DOC-knowledge_unit-{seeded['unit_id']}",
    )

    removed, message = ingest_raw.remove_source(
        paths,
        int(seeded["source_id"]),
    )

    assert removed, message
    assert (paths.root / "04_Resources/remove-me.md").exists()
    assert db.list_serving_units(paths.state_db) == []
    assert db.get_search_document(
        paths.state_db,
        f"DOC-knowledge_unit-{seeded['unit_id']}",
    ) is None
    with db.connect(paths.state_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM source_spans").fetchone()[0] == 0
        generation = conn.execute(
            "SELECT status FROM compiler_generations WHERE id = ?",
            (seeded["generation_id"],),
        ).fetchone()
        unit = conn.execute(
            "SELECT retired_at FROM knowledge_units WHERE id = ?",
            (seeded["unit_id"],),
        ).fetchone()
        span_tombstone = conn.execute(
            "SELECT 1 FROM deleted_records "
            "WHERE table_name = 'source_spans' AND record_id = ?",
            (seeded["span_id"],),
        ).fetchone()
    assert generation["status"] == "discarded"
    assert unit["retired_at"] is not None
    assert span_tombstone is not None


def test_source_removal_reports_projection_failure_after_canonical_commit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    paths = cfg.WikiPaths(tmp_path)
    db.init_db(paths.state_db)
    seeded = _seed_compiled_source(
        paths,
        "04_Resources/remove-projection-failure.md",
        content_hash="source-projection-failure",
    )

    def _fail_reemit(_paths):
        raise OSError("projection disk unavailable")

    monkeypatch.setattr(compile_pipeline, "reemit_projections", _fail_reemit)
    removed, message = ingest_raw.remove_source(
        paths,
        int(seeded["source_id"]),
    )

    assert removed
    assert "projection refresh failed" in message
    assert "wiki sync --reemit" in message
    assert db.list_serving_units(paths.state_db) == []
    with db.connect(paths.state_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 0


def test_imported_source_tombstone_runs_same_dependency_closure(
    tmp_path: Path,
) -> None:
    target_paths = cfg.WikiPaths(tmp_path / "target")
    db.init_db(target_paths.state_db)
    seeded = _seed_compiled_source(
        target_paths,
        "04_Resources/import-delete.md",
        content_hash="source-import",
    )
    materializer.materialize_search_documents(target_paths.state_db)
    assert db.get_search_document(
        target_paths.state_db,
        f"DOC-knowledge_unit-{seeded['unit_id']}",
    )

    peer_db = tmp_path / "peer.sqlite"
    db.init_db(peer_db)
    record_tombstone(peer_db, "sources", str(seeded["sync_key"]))
    snapshot = tmp_path / "delete.jsonl"
    export_knowledge(peer_db, snapshot)

    stats = import_knowledge(target_paths.state_db, snapshot)

    assert stats.deleted >= 1
    assert db.list_serving_units(target_paths.state_db) == []
    assert db.get_search_document(
        target_paths.state_db,
        f"DOC-knowledge_unit-{seeded['unit_id']}",
    ) is None
    with db.connect(target_paths.state_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 0
        assert conn.execute(
            "SELECT status FROM compiler_generations WHERE id = ?",
            (seeded["generation_id"],),
        ).fetchone()[0] == "discarded"
        assert conn.execute(
            "SELECT retired_at FROM knowledge_units WHERE id = ?",
            (seeded["unit_id"],),
        ).fetchone()[0] is not None


def test_stale_snapshot_cannot_resurrect_deleted_source_closure(
    tmp_path: Path,
) -> None:
    target_paths = cfg.WikiPaths(tmp_path / "target")
    db.init_db(target_paths.state_db)
    seeded = _seed_compiled_source(
        target_paths,
        "04_Resources/stale.md",
        content_hash="source-stale",
    )
    stale_snapshot = tmp_path / "stale.jsonl"
    export_knowledge(target_paths.state_db, stale_snapshot)

    delete_db = tmp_path / "delete.sqlite"
    db.init_db(delete_db)
    record_tombstone(delete_db, "sources", str(seeded["sync_key"]))
    delete_snapshot = tmp_path / "delete.jsonl"
    export_knowledge(delete_db, delete_snapshot)
    import_knowledge(target_paths.state_db, delete_snapshot)

    import_knowledge(target_paths.state_db, stale_snapshot)
    materializer.materialize_search_documents(target_paths.state_db)

    assert db.list_serving_units(target_paths.state_db) == []
    with db.connect(target_paths.state_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 0
        assert conn.execute(
            "SELECT status FROM compiler_generations WHERE id = ?",
            (seeded["generation_id"],),
        ).fetchone()[0] == "discarded"
        assert conn.execute(
            "SELECT retired_at FROM knowledge_units WHERE id = ?",
            (seeded["unit_id"],),
        ).fetchone()[0] is not None


def test_source_removal_preserves_only_live_shared_graph_support(
    tmp_path: Path,
) -> None:
    paths = cfg.WikiPaths(tmp_path)
    db.init_db(paths.state_db)
    sources = [
        _seed_compiled_source(
            paths,
            f"04_Resources/shared-{index}.md",
            content_hash=f"source-{index}",
        )
        for index in range(3)
    ]
    span_ids = [str(item["span_id"]) for item in sources]
    unit_ids = [str(item["unit_id"]) for item in sources]
    source_entity = db.upsert_graph_entity(
        paths.state_db,
        canonical_name="Shared Method",
        entity_type="method",
        source_span_ids=span_ids,
        knowledge_unit_ids=unit_ids,
    )
    target_entity = db.upsert_graph_entity(
        paths.state_db,
        canonical_name="Shared Problem",
        entity_type="concept",
        source_span_ids=span_ids,
        knowledge_unit_ids=unit_ids,
    )
    relation_id = db.upsert_graph_relation(
        paths.state_db,
        source_entity_id=source_entity,
        target_entity_id=target_entity,
        relation_type="addresses",
        description="Shared support",
        source_span_ids=span_ids,
        confidence=0.9,
    )
    for index, item in enumerate(sources):
        db.upsert_graph_relation_support(
            paths.state_db,
            relation_id=relation_id,
            knowledge_unit_id=str(item["unit_id"]),
            source_span_ids=[str(item["span_id"])],
            source_lineage_hash=f"lineage-{index}",
            confidence=0.9,
            support_status="verified",
        )
    assert db.compile_relation_lifecycle(
        paths.state_db,
        relation_id=relation_id,
    ) == "active"
    db.rebuild_graph_generation(paths.state_db)
    old_report_ids = {
        str(report["id"]) for report in db.list_community_reports(paths.state_db)
    }
    synthesis_id = db.upsert_synthesis_node(
        paths.state_db,
        title="Shared synthesis",
        statement="All reports combined.",
        dependency_hash="before-removal",
        community_report_ids=sorted(old_report_ids),
        source_span_ids=span_ids,
    )
    for span_id in span_ids:
        db.record_artifact_dependency(
            paths.state_db,
            artifact_id=synthesis_id,
            artifact_type="synthesis_node",
            depends_on_id=span_id,
            depends_on_type="source_span",
            dependency_hash="before-removal",
        )
    future_revision = "2040-01-01T00:00:00.000000Z"
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "UPDATE sources SET updated_at = ? WHERE id = ?",
            (future_revision, sources[0]["source_id"]),
        )
        conn.execute(
            "UPDATE graph_entities SET updated_at = ? WHERE id IN (?, ?)",
            (future_revision, source_entity, target_entity),
        )
        conn.execute(
            "UPDATE graph_relation_supports SET updated_at = ? "
            "WHERE relation_id = ? AND knowledge_unit_id = ?",
            (future_revision, relation_id, sources[0]["unit_id"]),
        )
        conn.execute(
            "UPDATE synthesis_nodes SET updated_at = ? WHERE id = ?",
            (future_revision, synthesis_id),
        )

    removed, message = ingest_raw.remove_source(
        paths,
        int(sources[0]["source_id"]),
    )

    assert removed, message
    with db.connect(paths.state_db) as conn:
        support_rows = conn.execute(
            "SELECT knowledge_unit_id, support_status, updated_at "
            "FROM graph_relation_supports WHERE relation_id = ? "
            "ORDER BY knowledge_unit_id",
            (relation_id,),
        ).fetchall()
        relation_status = conn.execute(
            "SELECT lifecycle_status FROM graph_relations WHERE id = ?",
            (relation_id,),
        ).fetchone()[0]
        entities = conn.execute(
            "SELECT source_span_ids, knowledge_unit_ids, updated_at "
            "FROM graph_entities "
            "WHERE id IN (?, ?)",
            (source_entity, target_entity),
        ).fetchall()
        synthesis = conn.execute(
            "SELECT 1 FROM synthesis_nodes WHERE id = ?",
            (synthesis_id,),
        ).fetchone()
        synthesis_tombstone = conn.execute(
            "SELECT deleted_at FROM deleted_records "
            "WHERE table_name = 'synthesis_nodes' AND record_id = ?",
            (synthesis_id,),
        ).fetchone()
        source_tombstone = conn.execute(
            "SELECT deleted_at FROM deleted_records "
            "WHERE table_name = 'sources' AND record_id = ?",
            (sources[0]["sync_key"],),
        ).fetchone()

    status_by_unit = {
        str(row["knowledge_unit_id"]): str(row["support_status"])
        for row in support_rows
    }
    assert status_by_unit[str(sources[0]["unit_id"])] == "stale"
    removed_support = next(
        row
        for row in support_rows
        if str(row["knowledge_unit_id"]) == str(sources[0]["unit_id"])
    )
    assert str(removed_support["updated_at"]) > future_revision
    assert {
        status_by_unit[str(sources[1]["unit_id"])],
        status_by_unit[str(sources[2]["unit_id"])],
    } == {"verified"}
    assert relation_status == "active"
    for entity in entities:
        assert str(sources[0]["span_id"]) not in json.loads(entity["source_span_ids"])
        assert str(sources[0]["unit_id"]) not in json.loads(entity["knowledge_unit_ids"])
        assert str(entity["updated_at"]) > future_revision
    assert synthesis is None
    assert synthesis_tombstone is not None
    assert str(synthesis_tombstone["deleted_at"]) > future_revision
    assert source_tombstone is not None
    assert str(source_tombstone["deleted_at"]) > future_revision


def test_source_removal_retires_under_supported_relation_and_search_endpoints(
    tmp_path: Path,
) -> None:
    paths = cfg.WikiPaths(tmp_path)
    db.init_db(paths.state_db)
    sources = [
        _seed_compiled_source(
            paths,
            f"04_Resources/two-supports-{index}.md",
            content_hash=f"two-supports-{index}",
        )
        for index in range(2)
    ]
    span_ids = [str(item["span_id"]) for item in sources]
    unit_ids = [str(item["unit_id"]) for item in sources]
    source_entity = db.upsert_graph_entity(
        paths.state_db,
        canonical_name="Two-source Method",
        entity_type="method",
        source_span_ids=span_ids,
        knowledge_unit_ids=unit_ids,
    )
    target_entity = db.upsert_graph_entity(
        paths.state_db,
        canonical_name="Two-source Problem",
        entity_type="concept",
        source_span_ids=span_ids,
        knowledge_unit_ids=unit_ids,
    )
    relation_id = db.upsert_graph_relation(
        paths.state_db,
        source_entity_id=source_entity,
        target_entity_id=target_entity,
        relation_type="addresses",
        description="Exactly two independent supports",
        source_span_ids=span_ids,
        confidence=0.9,
    )
    for index, item in enumerate(sources):
        db.upsert_graph_relation_support(
            paths.state_db,
            relation_id=relation_id,
            knowledge_unit_id=str(item["unit_id"]),
            source_span_ids=[str(item["span_id"])],
            source_lineage_hash=f"two-lineage-{index}",
            confidence=0.9,
            support_status="verified",
        )
    assert db.compile_relation_lifecycle(
        paths.state_db,
        relation_id=relation_id,
    ) == "active"
    db.rebuild_graph_generation(paths.state_db)
    report_ids = {
        str(report["id"])
        for report in db.list_community_reports(paths.state_db)
    }
    assert report_ids

    removed, message = ingest_raw.remove_source(
        paths,
        int(sources[0]["source_id"]),
    )

    assert removed, message
    materializer.materialize_search_documents(paths.state_db)
    with db.connect(paths.state_db) as conn:
        relation_status = conn.execute(
            "SELECT lifecycle_status FROM graph_relations WHERE id = ?",
            (relation_id,),
        ).fetchone()[0]
        retired_reports = {
            str(row["id"])
            for row in conn.execute(
                "SELECT id FROM community_reports WHERE retired_at IS NOT NULL"
            ).fetchall()
        }
    assert relation_status != "active"
    assert report_ids.issubset(retired_reports)
    assert db.get_search_document(
        paths.state_db,
        f"DOC-graph_entity-{source_entity}",
    ) is not None
    assert db.get_search_document(
        paths.state_db,
        f"DOC-graph_relation-{relation_id}",
    ) is None

    removed, message = ingest_raw.remove_source(
        paths,
        int(sources[1]["source_id"]),
    )

    assert removed, message
    materializer.materialize_search_documents(paths.state_db)
    assert db.get_search_document(
        paths.state_db,
        f"DOC-graph_entity-{source_entity}",
    ) is None
    assert db.get_search_document(
        paths.state_db,
        f"DOC-graph_entity-{target_entity}",
    ) is None
    assert db.get_search_document(
        paths.state_db,
        f"DOC-graph_relation-{relation_id}",
    ) is None
