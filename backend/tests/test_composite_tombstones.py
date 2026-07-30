"""Schema-v13 composite tombstone transport and convergence tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from curator import db, db_sync


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "state.sqlite"
    db.init_db(path)
    return path


def _canonical_token(key: dict[str, object]) -> str:
    return json.dumps(
        {"key": key, "v": 1},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _write_rows(
    path: Path,
    rows: list[tuple[str, dict[str, Any]]],
) -> None:
    records = [
        {
            "type": "header",
            "schema_version": db.SCHEMA_VERSION,
            "export_id": f"exp-{path.stem}",
            "exported_at": "2026-07-30T00:00:00Z",
        },
        *[
            {"type": "row", "table": table, "row": row}
            for table, row in rows
        ],
    ]
    path.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records)
        + "\n",
        encoding="utf-8",
    )


def test_schema_v13_is_the_composite_tombstone_boundary() -> None:
    assert db.SCHEMA_VERSION == 13


def _insert_source(conn: Any, *, source_id: int = 9) -> None:
    conn.execute(
        "INSERT INTO sources "
        "(id, relpath, sync_key, content_hash, file_type, bytes, added_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            source_id,
            "04_Resources/portable.pdf",
            "vault:04_Resources/portable.pdf",
            "hash",
            "pdf",
            10,
            "2026-01-01T00:00:00Z",
            "2026-01-01T00:00:00Z",
        ),
    )


_COMPOSITE_CASES = [
    pytest.param(
        "source_pages",
        {
            "source_sync_key": "vault:04_Resources/portable.pdf",
            "wiki_path": '02_Atoms/인용,"A".md',
            "at": "2026-01-01T00:00:00Z",
        },
        (
            "INSERT INTO source_pages (source_id, wiki_path, operation, at) "
            "VALUES (?, ?, ?, ?)"
        ),
        (9, '02_Atoms/인용,"A".md', "created", "2026-01-01T00:00:00Z"),
        (9, '02_Atoms/인용,"A".md', "created", "2026-01-02T00:00:00Z"),
        "at = '2026-01-01T00:00:00Z'",
        id="source-pages-portable-source-key",
    ),
    pytest.param(
        "source_pdf_pages",
        {
            "source_sync_key": "vault:04_Resources/portable.pdf",
            "page_number": 1,
        },
        (
            "INSERT INTO source_pdf_pages "
            "(source_id, relpath, page_number, content_hash, char_count, "
            "word_count, metadata, extracted_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        ),
        (
            9,
            "04_Resources/portable.pdf",
            1,
            "p1",
            10,
            2,
            "{}",
            "2026-01-01T00:00:00Z",
        ),
        (
            9,
            "04_Resources/portable.pdf",
            2,
            "p2",
            10,
            2,
            "{}",
            "2026-01-01T00:00:00Z",
        ),
        "page_number = 1",
        id="source-pdf-pages-portable-source-key",
    ),
    pytest.param(
        "claim_supports",
        {
            "knowledge_unit_id": "KNU-1",
            "source_span_id": "SPAN-1",
            "support_role": "primary",
        },
        (
            "INSERT INTO claim_supports "
            "(knowledge_unit_id, source_span_id, support_role, support_status, "
            "support_reason, evidence_hash, validator_trace_id, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
        ),
        (
            "KNU-1",
            "SPAN-1",
            "primary",
            "verified",
            "",
            "e1",
            None,
            "2026-01-01T00:00:00Z",
            "2026-01-01T00:00:00Z",
        ),
        (
            "KNU-1",
            "SPAN-1",
            "contextual",
            "verified",
            "",
            "e2",
            None,
            "2026-01-01T00:00:00Z",
            "2026-01-01T00:00:00Z",
        ),
        "support_role = 'primary'",
        id="claim-supports",
    ),
    pytest.param(
        "graph_relation_supports",
        {
            "relation_id": "REL-1",
            "knowledge_unit_id": "KNU-1",
            "support_hash": "support-1",
        },
        (
            "INSERT INTO graph_relation_supports "
            "(relation_id, knowledge_unit_id, source_span_ids, assertion_source, "
            "confidence, support_status, support_hash, source_lineage_hash, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        ),
        (
            "REL-1",
            "KNU-1",
            "[]",
            "source_states",
            0.9,
            "verified",
            "support-1",
            "lineage-1",
            "2026-01-01T00:00:00Z",
            "2026-01-01T00:00:00Z",
        ),
        (
            "REL-1",
            "KNU-1",
            "[]",
            "source_states",
            0.9,
            "verified",
            "support-2",
            "lineage-1",
            "2026-01-01T00:00:00Z",
            "2026-01-01T00:00:00Z",
        ),
        "support_hash = 'support-1'",
        id="graph-relation-supports",
    ),
    pytest.param(
        "entity_resolution_lineage",
        {"decision_id": "MERGE-1", "origin_entity_id": "ENT-1"},
        (
            "INSERT INTO entity_resolution_lineage "
            "(decision_id, origin_entity_id, canonical_entity_id, rewrite_json) "
            "VALUES (?, ?, ?, ?)"
        ),
        ("MERGE-1", "ENT-1", "ENT-C", "{}"),
        ("MERGE-1", "ENT-2", "ENT-C", "{}"),
        "origin_entity_id = 'ENT-1'",
        id="entity-resolution-lineage",
    ),
    pytest.param(
        "artifact_dependencies",
        {
            "artifact_id": "KNU-1",
            "depends_on_id": "SPAN-1",
            "depends_on_type": "source_span",
        },
        (
            "INSERT INTO artifact_dependencies "
            "(artifact_id, artifact_type, depends_on_id, depends_on_type, "
            "dependency_hash, created_at) VALUES (?, ?, ?, ?, ?, ?)"
        ),
        (
            "KNU-1",
            "knowledge_unit",
            "SPAN-1",
            "source_span",
            "dep-1",
            "2026-01-01T00:00:00Z",
        ),
        (
            "KNU-1",
            "knowledge_unit",
            "REL-1",
            "relation",
            "dep-2",
            "2026-01-01T00:00:00Z",
        ),
        "depends_on_type = 'source_span'",
        id="artifact-dependencies",
    ),
]


@pytest.mark.parametrize(
    ("table", "transport_key", "insert_sql", "target", "control", "target_where"),
    _COMPOSITE_CASES,
)
def test_composite_tombstone_deletes_only_the_exact_row(
    db_path: Path,
    tmp_path: Path,
    table: str,
    transport_key: dict[str, object],
    insert_sql: str,
    target: tuple[object, ...],
    control: tuple[object, ...],
    target_where: str,
) -> None:
    with db.connect(db_path) as conn:
        if table.startswith("source_"):
            _insert_source(conn)
        conn.execute(insert_sql, target)
        conn.execute(insert_sql, control)

    incoming = tmp_path / f"{table}.jsonl"
    _write_rows(
        incoming,
        [
            (
                "deleted_records",
                {
                    "table_name": table,
                    "record_id": _canonical_token(transport_key),
                    "deleted_at": "2026-02-01T00:00:00Z",
                },
            )
        ],
    )

    stats = db_sync.import_knowledge(db_path, incoming)

    with db.connect(db_path) as conn:
        target_count = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE {target_where}"
        ).fetchone()[0]
        total_count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    assert stats.deleted == 1
    assert target_count == 0
    assert total_count == 1


@pytest.mark.parametrize(
    "token",
    [
        "legacy-partial-key",
        '{"key":{"artifact_id":"A","depends_on_id":"B","depends_on_type":"C"},"v":2}',
        '{"key":{"artifact_id":"A","depends_on_id":"B"},"v":1}',
        (
            '{"key":{"artifact_id":"A","depends_on_id":"B",'
            '"depends_on_type":"C","extra":"x"},"v":1}'
        ),
        (
            '{"key":{"artifact_id":"A","depends_on_id":"B",'
            '"depends_on_type":1},"v":1}'
        ),
        (
            '{"v":1, "key":{"artifact_id":"A","depends_on_id":"B",'
            '"depends_on_type":"C"}}'
        ),
        (
            '{"key":{"artifact_id":"A","artifact_id":"B","depends_on_id":"C",'
            '"depends_on_type":"source_span"},"v":1}'
        ),
    ],
)
def test_invalid_composite_token_rolls_back_the_whole_import(
    db_path: Path,
    tmp_path: Path,
    token: str,
) -> None:
    with db.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO atoms "
            "(id, name, parent_source, claim_type, one_liner, last_updated) "
            "VALUES ('ATM-KEEP', 'Keep', 'CTX-1', 'fact', '.', "
            "'2026-01-01T00:00:00Z')"
        )

    incoming = tmp_path / "invalid-composite.jsonl"
    _write_rows(
        incoming,
        [
            (
                "deleted_records",
                {
                    "table_name": "atoms",
                    "record_id": "ATM-KEEP",
                    "deleted_at": "2026-02-01T00:00:00Z",
                },
            ),
            (
                "deleted_records",
                {
                    "table_name": "artifact_dependencies",
                    "record_id": token,
                    "deleted_at": "2026-02-01T00:00:00Z",
                },
            ),
        ],
    )

    with pytest.raises(ValueError, match="artifact_dependencies"):
        db_sync.import_knowledge(db_path, incoming)

    with db.connect(db_path) as conn:
        assert conn.execute(
            "SELECT 1 FROM atoms WHERE id = 'ATM-KEEP'"
        ).fetchone()
        assert conn.execute(
            "SELECT 1 FROM deleted_records WHERE table_name = 'atoms'"
        ).fetchone() is None


def test_export_rejects_and_preserves_legacy_composite_token(
    db_path: Path,
    tmp_path: Path,
) -> None:
    with db.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO deleted_records (table_name, record_id, deleted_at) "
            "VALUES ('claim_supports', 'legacy-partial-key', "
            "'2026-01-01T00:00:00Z')"
        )

    with pytest.raises(ValueError, match="claim_supports"):
        db_sync.export_knowledge(db_path, tmp_path / "out.jsonl")

    with db.connect(db_path) as conn:
        assert conn.execute(
            "SELECT record_id FROM deleted_records "
            "WHERE table_name = 'claim_supports'"
        ).fetchone()[0] == "legacy-partial-key"


def test_v12_database_is_stamped_v13_without_rewriting_legacy_token(
    db_path: Path,
    tmp_path: Path,
) -> None:
    with db.connect(db_path) as conn:
        conn.execute("UPDATE schema_version SET version = 12")
        conn.execute(
            "INSERT INTO deleted_records (table_name, record_id, deleted_at) "
            "VALUES ('artifact_dependencies', 'legacy-partial-key', "
            "'2026-01-01T00:00:00Z')"
        )

    with db.connect(db_path) as conn:
        assert conn.execute(
            "SELECT version FROM schema_version"
        ).fetchone()[0] == 13
        assert conn.execute(
            "SELECT record_id FROM deleted_records "
            "WHERE table_name = 'artifact_dependencies'"
        ).fetchone()[0] == "legacy-partial-key"

    with pytest.raises(ValueError, match="artifact_dependencies"):
        db_sync.export_knowledge(db_path, tmp_path / "v13.jsonl")


def _claim_support_row(updated_at: str) -> dict[str, object]:
    return {
        "knowledge_unit_id": "KNU-STALE",
        "source_span_id": "SPAN-STALE",
        "support_role": "primary",
        "support_status": "verified",
        "support_reason": "",
        "evidence_hash": "evidence",
        "validator_trace_id": None,
        "created_at": updated_at,
        "updated_at": updated_at,
    }


@pytest.mark.parametrize(
    ("row_revision", "row_survives"),
    [
        ("2026-01-01T00:00:00Z", False),
        ("2026-02-01T00:00:00Z", False),
        ("2026-03-01T00:00:00Z", True),
    ],
)
def test_row_tombstone_timestamp_order_is_symmetric(
    db_path: Path,
    tmp_path: Path,
    row_revision: str,
    row_survives: bool,
) -> None:
    key = {
        "knowledge_unit_id": "KNU-STALE",
        "source_span_id": "SPAN-STALE",
        "support_role": "primary",
    }
    token = _canonical_token(key)
    with db.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO deleted_records (table_name, record_id, deleted_at) "
            "VALUES ('claim_supports', ?, '2026-02-01T00:00:00Z')",
            (token,),
        )

    incoming = tmp_path / f"row-{row_survives}.jsonl"
    _write_rows(incoming, [("claim_supports", _claim_support_row(row_revision))])
    stats = db_sync.import_knowledge(db_path, incoming)

    with db.connect(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM claim_supports "
            "WHERE knowledge_unit_id = 'KNU-STALE'"
        ).fetchone()
        tombstone = conn.execute(
            "SELECT 1 FROM deleted_records "
            "WHERE table_name = 'claim_supports' AND record_id = ?",
            (token,),
        ).fetchone()
    assert (row is not None) is row_survives
    assert (tombstone is None) is row_survives
    assert stats.inserted == int(row_survives)
    assert stats.skipped == int(not row_survives)


def test_source_scoped_tombstone_blocks_stale_row_on_a_clean_replica(
    db_path: Path,
    tmp_path: Path,
) -> None:
    token = _canonical_token(
        {
            "source_sync_key": "vault:04_Resources/new.pdf",
            "page_number": 1,
        }
    )
    incoming = tmp_path / "clean-replica.jsonl"
    _write_rows(
        incoming,
        [
            (
                "deleted_records",
                {
                    "table_name": "source_pdf_pages",
                    "record_id": token,
                    "deleted_at": "2026-02-01T00:00:00Z",
                },
            ),
            (
                "sources",
                {
                    "id": 77,
                    "relpath": "04_Resources/new.pdf",
                    "sync_key": "vault:04_Resources/new.pdf",
                    "content_hash": "source",
                    "file_type": "pdf",
                    "bytes": 10,
                    "added_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-03-01T00:00:00Z",
                },
            ),
            (
                "source_pdf_pages",
                {
                    "source_id": 77,
                    "relpath": "04_Resources/new.pdf",
                    "page_number": 1,
                    "content_hash": "stale-page",
                    "char_count": 10,
                    "word_count": 2,
                    "metadata": "{}",
                    "extracted_at": "2026-01-01T00:00:00Z",
                },
            ),
        ],
    )

    stats = db_sync.import_knowledge(db_path, incoming)

    with db.connect(db_path) as conn:
        assert conn.execute("SELECT 1 FROM sources").fetchone()
        assert conn.execute("SELECT 1 FROM source_pdf_pages").fetchone() is None
        assert conn.execute(
            "SELECT 1 FROM deleted_records "
            "WHERE table_name = 'source_pdf_pages' AND record_id = ?",
            (token,),
        ).fetchone()
    assert stats.inserted == 1
    assert stats.skipped == 1


def test_immutable_row_never_supersedes_an_existing_tombstone(
    db_path: Path,
    tmp_path: Path,
) -> None:
    token = _canonical_token(
        {"decision_id": "MERGE-1", "origin_entity_id": "ENT-1"}
    )
    with db.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO deleted_records (table_name, record_id, deleted_at) "
            "VALUES ('entity_resolution_lineage', ?, "
            "'2026-02-01T00:00:00Z')",
            (token,),
        )
    incoming = tmp_path / "immutable.jsonl"
    _write_rows(
        incoming,
        [
            (
                "entity_resolution_lineage",
                {
                    "decision_id": "MERGE-1",
                    "origin_entity_id": "ENT-1",
                    "canonical_entity_id": "ENT-C",
                    "rewrite_json": "{}",
                },
            )
        ],
    )

    stats = db_sync.import_knowledge(db_path, incoming)

    with db.connect(db_path) as conn:
        assert conn.execute(
            "SELECT 1 FROM entity_resolution_lineage"
        ).fetchone() is None
        assert conn.execute(
            "SELECT 1 FROM deleted_records "
            "WHERE table_name = 'entity_resolution_lineage' "
            "AND record_id = ?",
            (token,),
        ).fetchone()
    assert stats.skipped == 1


def test_stale_third_peer_cannot_resurrect_a_composite_row(
    tmp_path: Path,
) -> None:
    stale_db = tmp_path / "stale.sqlite"
    deleting_db = tmp_path / "deleting.sqlite"
    target_db = tmp_path / "target.sqlite"
    for path in (stale_db, deleting_db, target_db):
        db.init_db(path)
    insert_sql = (
        "INSERT INTO artifact_dependencies "
        "(artifact_id, artifact_type, depends_on_id, depends_on_type, "
        "dependency_hash, created_at) VALUES "
        "('KNU-1', 'knowledge_unit', 'SPAN-1', 'source_span', 'dep', "
        "'2026-01-01T00:00:00Z')"
    )
    with db.connect(stale_db) as conn:
        conn.execute(insert_sql)
    stale_export = tmp_path / "stale.jsonl"
    db_sync.export_knowledge(stale_db, stale_export)

    with db.connect(deleting_db) as conn:
        conn.execute(insert_sql)
        db_sync.delete_rows_with_tombstones_on_connection(
            conn,
            "artifact_dependencies",
            "artifact_id = ? AND depends_on_id = ? AND depends_on_type = ?",
            ("KNU-1", "SPAN-1", "source_span"),
        )
    deleting_export = tmp_path / "deleting.jsonl"
    db_sync.export_knowledge(deleting_db, deleting_export)

    assert db_sync.import_knowledge(target_db, stale_export).inserted == 1
    assert db_sync.import_knowledge(target_db, deleting_export).deleted == 1
    stale_retry = db_sync.import_knowledge(target_db, stale_export)

    with db.connect(target_db) as conn:
        assert conn.execute(
            "SELECT 1 FROM artifact_dependencies"
        ).fetchone() is None
        assert conn.execute(
            "SELECT 1 FROM deleted_records "
            "WHERE table_name = 'artifact_dependencies'"
        ).fetchone()
    assert stale_retry.skipped == 1


def test_composite_tombstone_dry_run_is_read_only(
    db_path: Path,
    tmp_path: Path,
) -> None:
    with db.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO artifact_dependencies "
            "(artifact_id, artifact_type, depends_on_id, depends_on_type, "
            "dependency_hash, created_at) "
            "VALUES ('KNU-1', 'knowledge_unit', 'SPAN-1', 'source_span', "
            "'dep', '2026-01-01T00:00:00Z')"
        )
    token = _canonical_token(
        {
            "artifact_id": "KNU-1",
            "depends_on_id": "SPAN-1",
            "depends_on_type": "source_span",
        }
    )
    incoming = tmp_path / "dry-run.jsonl"
    _write_rows(
        incoming,
        [
            (
                "deleted_records",
                {
                    "table_name": "artifact_dependencies",
                    "record_id": token,
                    "deleted_at": "2026-02-01T00:00:00Z",
                },
            )
        ],
    )

    stats = db_sync.import_knowledge(db_path, incoming, dry_run=True)

    with db.connect(db_path) as conn:
        assert conn.execute(
            "SELECT 1 FROM artifact_dependencies"
        ).fetchone()
        assert conn.execute(
            "SELECT 1 FROM deleted_records "
            "WHERE table_name = 'artifact_dependencies'"
        ).fetchone() is None
    assert stats.deleted == 1


def test_source_tombstone_removes_non_cascading_dependents(
    db_path: Path,
    tmp_path: Path,
) -> None:
    with db.connect(db_path) as conn:
        _insert_source(conn)
        conn.execute(
            "INSERT INTO source_pages (source_id, wiki_path, operation, at) "
            "VALUES (9, '02_Atoms/ATM-1.md', 'created', "
            "'2026-01-01T00:00:00Z')"
        )
        conn.execute(
            "INSERT INTO ingest_runs "
            "(started_at, source_id, mode) "
            "VALUES ('2026-01-01T00:00:00Z', 9, 'batch')"
        )
        conn.execute(
            "INSERT INTO ingest_jobs "
            "(source_id, job_type, trigger, state, created_at) "
            "VALUES (9, 'l2_atoms', 'wiki_add', 'queued', "
            "'2026-01-01T00:00:00Z')"
        )
        job_id = conn.execute(
            "SELECT id FROM ingest_jobs WHERE source_id = 9"
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO job_events (job_id, seq, kind, data, at) "
            "VALUES (?, 1, 'status', '{}', '2026-01-01T00:00:00Z')",
            (job_id,),
        )
        conn.execute(
            "INSERT INTO dag_edges "
            "(id, from_id, to_id, edge_type, source_id, created_at) "
            "VALUES ('CTX-1:ATM-1', 'CTX-1', 'ATM-1', 'extracted_from', 9, "
            "'2026-01-01T00:00:00Z')"
        )

    incoming = tmp_path / "source-delete.jsonl"
    _write_rows(
        incoming,
        [
            (
                "deleted_records",
                {
                    "table_name": "sources",
                    "record_id": "vault:04_Resources/portable.pdf",
                    "deleted_at": "2026-02-01T00:00:00Z",
                },
            )
        ],
    )

    stats = db_sync.import_knowledge(db_path, incoming)

    with db.connect(db_path) as conn:
        for table in (
            "sources",
            "source_pages",
            "ingest_runs",
            "ingest_jobs",
            "job_events",
            "dag_edges",
        ):
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    assert stats.deleted == 1


def test_local_support_and_dependency_deletes_emit_and_reinsert_clears(
    db_path: Path,
) -> None:
    with db.connect(db_path) as conn:
        _insert_source(conn)
        conn.execute(
            "INSERT INTO source_spans "
            "(id, source_id, relpath, span_type, content_hash, text_preview, "
            "created_at) VALUES ('SPAN-1', 9, '04_Resources/portable.pdf', "
            "'page', 'span-hash', 'text', '2026-01-01T00:00:00Z')"
        )
        conn.execute(
            "INSERT INTO claim_supports "
            "(knowledge_unit_id, source_span_id, support_role, support_status, "
            "support_reason, evidence_hash, validator_trace_id, created_at, "
            "updated_at) VALUES ('KNU-1', 'SPAN-1', 'primary', 'verified', '', "
            "'evidence', NULL, '2026-01-01T00:00:00Z', "
            "'2026-01-01T00:00:00Z')"
        )
        conn.execute(
            "INSERT INTO artifact_dependencies "
            "(artifact_id, artifact_type, depends_on_id, depends_on_type, "
            "dependency_hash, created_at) VALUES "
            "('KNU-1', 'knowledge_unit', 'SPAN-1', 'source_span', 'dep', "
            "'2026-01-01T00:00:00Z')"
        )

    db.delete_source_spans(db_path, ["SPAN-1"])

    support_token = _canonical_token(
        {
            "knowledge_unit_id": "KNU-1",
            "source_span_id": "SPAN-1",
            "support_role": "primary",
        }
    )
    dependency_token = _canonical_token(
        {
            "artifact_id": "KNU-1",
            "depends_on_id": "SPAN-1",
            "depends_on_type": "source_span",
        }
    )
    with db.connect(db_path) as conn:
        tombstones = {
            (row["table_name"], row["record_id"])
            for row in conn.execute(
                "SELECT table_name, record_id FROM deleted_records"
            ).fetchall()
        }
    assert ("claim_supports", support_token) in tombstones
    assert ("artifact_dependencies", dependency_token) in tombstones

    db.upsert_claim_support(
        db_path,
        knowledge_unit_id="KNU-1",
        source_span_id="SPAN-1",
        support_role="primary",
        support_status="verified",
        evidence_hash="new-evidence",
    )
    db.record_artifact_dependency(
        db_path,
        artifact_id="KNU-1",
        artifact_type="knowledge_unit",
        depends_on_id="SPAN-1",
        depends_on_type="source_span",
        dependency_hash="new-dep",
    )

    with db.connect(db_path) as conn:
        assert conn.execute(
            "SELECT 1 FROM deleted_records "
            "WHERE (table_name = 'claim_supports' AND record_id = ?) "
            "OR (table_name = 'artifact_dependencies' AND record_id = ?)",
            (support_token, dependency_token),
        ).fetchone() is None


def test_pdf_page_replacement_emits_only_removed_key_tombstones(
    db_path: Path,
) -> None:
    with db.connect(db_path) as conn:
        _insert_source(conn)
    initial_pages = [
        {"page": 1, "content_hash": "old-1"},
        {"page": 2, "content_hash": "old-2"},
    ]
    db.replace_source_pdf_pages(
        db_path, 9, "04_Resources/portable.pdf", initial_pages
    )

    db.replace_source_pdf_pages(
        db_path,
        9,
        "04_Resources/portable.pdf",
        [{"page": 1, "content_hash": "new-1"}],
    )

    page_1 = _canonical_token(
        {
            "source_sync_key": "vault:04_Resources/portable.pdf",
            "page_number": 1,
        }
    )
    page_2 = _canonical_token(
        {
            "source_sync_key": "vault:04_Resources/portable.pdf",
            "page_number": 2,
        }
    )
    with db.connect(db_path) as conn:
        tombstones = {
            row["record_id"]
            for row in conn.execute(
                "SELECT record_id FROM deleted_records "
                "WHERE table_name = 'source_pdf_pages'"
            ).fetchall()
        }
    assert page_1 not in tombstones
    assert page_2 in tombstones
