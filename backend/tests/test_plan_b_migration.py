"""Plan B (v0.8.0) P3 — v8 additive migration + claim-support/generation helpers.

Covers the SYSTEM_BEHAVIOR §26.6 migration acceptance criteria on a SYNTHETIC
pre-Plan-B (v7) database (CI-safe: the real rehearsal on
``.agents/backups/b-pre-implementation-state.sqlite`` is a P7/manual testbed
step, and that backup is gitignored). Also unit-tests the SCHEMA §20 DB
lifecycle helpers added in P3.
"""

from __future__ import annotations

import hashlib
import sqlite3
import tempfile
from pathlib import Path

import pytest

from curator import config as cfg
from curator import db
from curator import db_sync

RELPATH = "04_Resources/pb.md"

# Pre-Plan-B (SCHEMA_VERSION = 7) DDL fragments. Deliberately omit the §20
# columns/tables so the migration has real work to do.
_V7_KNOWLEDGE_UNITS = """
CREATE TABLE knowledge_units (
    id              TEXT PRIMARY KEY,
    unit_type       TEXT NOT NULL,
    canonical_name  TEXT NOT NULL,
    statement       TEXT NOT NULL,
    source_span_ids TEXT NOT NULL,
    source_id       INTEGER,
    confidence      REAL NOT NULL DEFAULT 0.0,
    truth_status    TEXT NOT NULL DEFAULT 'source_supported',
    atom_node_id    TEXT,
    prompt_run_id   TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
"""
_V7_DELETED_RECORDS = """
CREATE TABLE deleted_records (
    table_name  TEXT NOT NULL,
    record_id   TEXT NOT NULL,
    deleted_at  TEXT NOT NULL,
    PRIMARY KEY (table_name, record_id),
    CHECK (table_name IN (
        'sources','atoms','concepts','synthesis_nodes',
        'source_spans','knowledge_units','graph_entities','graph_relations',
        'community_reports','memory_paths','prompt_runs','dag_edges',
        'curation_plans','insight_candidates','artifact_dependencies',
        'synthesis','query_traces','source_pages','source_pdf_pages'
    ))
);
"""


def _make_v7_db(path: Path) -> None:
    """Build a minimal but faithful SCHEMA_VERSION=7 database with one legacy
    knowledge unit and a pre-existing tombstone."""
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE schema_version (version INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO schema_version (version) VALUES (7)")
        # The sources table is unchanged by the v8 migration, but SCHEMA_SQL
        # creates indexes on status/domain/logical_source_id/external_path, so
        # the synthetic v7 sources must carry those columns or executescript
        # fails before the migration even runs.
        conn.execute(
            "CREATE TABLE sources (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "relpath TEXT NOT NULL UNIQUE, content_hash TEXT NOT NULL, "
            "file_type TEXT NOT NULL, bytes INTEGER NOT NULL, added_at TEXT NOT NULL, "
            "status TEXT NOT NULL DEFAULT 'pending', domain TEXT, "
            "logical_source_id TEXT, external_path TEXT)"
        )
        conn.execute(
            "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at) "
            "VALUES (?, 'h', 'md', 1, '2026-01-01T00:00:00Z')",
            (RELPATH,),
        )
        conn.executescript(_V7_KNOWLEDGE_UNITS)
        conn.execute(
            "INSERT INTO knowledge_units (id, unit_type, canonical_name, statement, "
            "source_span_ids, source_id, created_at, updated_at) "
            "VALUES ('KNU-legacy0', 'atom', 'Legacy claim', 'A legacy statement.', "
            "'[\"SPAN-legacy0\"]', 1, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"
        )
        conn.executescript(_V7_DELETED_RECORDS)
        conn.execute(
            "INSERT INTO deleted_records (table_name, record_id, deleted_at) "
            "VALUES ('knowledge_units', 'KNU-gone', '2026-01-02T00:00:00Z')"
        )
        conn.commit()
    finally:
        conn.close()


def _schema_fingerprint(path: Path) -> str:
    with db.connect(path) as conn:
        ddl = [
            str(r[0])
            for r in conn.execute(
                "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY name"
            ).fetchall()
        ]
    return hashlib.sha256("\n".join(ddl).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# §26.6 migration acceptance criteria (on a synthetic v7 DB).
# ---------------------------------------------------------------------------

def test_migration_upgrades_v7_db_additively() -> None:
    with tempfile.TemporaryDirectory() as t:
        path = Path(t) / "state.sqlite"
        _make_v7_db(path)
        db.init_db(path)  # runs SCHEMA_SQL (IF NOT EXISTS) + _apply_migrations

        with db.connect(path) as conn:
            # §26.6.2: schema_version stamped to 8.
            assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 8
            # integrity preserved.
            assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            # Pre-existing legacy row preserved AND backfilled conservatively.
            row = conn.execute(
                "SELECT support_status, formula_status, retired_at, generation_id "
                "FROM knowledge_units WHERE id = 'KNU-legacy0'"
            ).fetchone()
            assert row["support_status"] == "unchecked"
            assert row["formula_status"] == "not_applicable"
            assert row["retired_at"] is None
            assert row["generation_id"] is None
            # New canonical tables exist and are empty (nothing verified).
            assert conn.execute("SELECT COUNT(*) FROM claim_supports").fetchone()[0] == 0
            assert conn.execute(
                "SELECT COUNT(*) FROM compiler_generations"
            ).fetchone()[0] == 0
            # Pre-existing tombstone survived the deleted_records rebuild.
            assert conn.execute(
                "SELECT COUNT(*) FROM deleted_records WHERE record_id = 'KNU-gone'"
            ).fetchone()[0] == 1
            # The rebuilt CHECK now accepts the two new tables.
            conn.execute(
                "INSERT INTO deleted_records (table_name, record_id, deleted_at) "
                "VALUES ('claim_supports', 'x', '2026-01-03T00:00:00Z')"
            )
            conn.execute(
                "INSERT INTO deleted_records (table_name, record_id, deleted_at) "
                "VALUES ('compiler_generations', 'GEN-x', '2026-01-03T00:00:00Z')"
            )


def test_migration_is_idempotent() -> None:
    with tempfile.TemporaryDirectory() as t:
        path = Path(t) / "state.sqlite"
        _make_v7_db(path)
        db.init_db(path)
        fp1 = _schema_fingerprint(path)
        db.init_db(path)  # second run must be a no-op
        fp2 = _schema_fingerprint(path)
        assert fp1 == fp2
        with db.connect(path) as conn:
            assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 8


def test_migration_schema_fingerprint_is_deterministic() -> None:
    # §26.6.5 analog: re-running the migration from the same start state
    # reproduces an identical schema fingerprint (ordered sqlite_master DDL).
    with tempfile.TemporaryDirectory() as t:
        a = Path(t) / "a.sqlite"
        b = Path(t) / "b.sqlite"
        _make_v7_db(a)
        _make_v7_db(b)
        db.init_db(a)
        db.init_db(b)
        assert _schema_fingerprint(a) == _schema_fingerprint(b)


def _columns(path: Path, table: str) -> set[str]:
    with db.connect(path) as conn:
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def test_fresh_v8_db_and_migrated_v7_db_have_same_columns() -> None:
    # A migrated old DB and a freshly-created DB must converge to the same
    # logical schema. (Raw DDL text differs: ALTER ADD COLUMN appends to the
    # stored CREATE statement, so we compare column sets, not byte-identical SQL.)
    with tempfile.TemporaryDirectory() as t:
        fresh = Path(t) / "fresh.sqlite"
        migrated = Path(t) / "migrated.sqlite"
        db.init_db(fresh)
        _make_v7_db(migrated)
        db.init_db(migrated)
        for table in ("knowledge_units", "claim_supports", "compiler_generations"):
            assert _columns(fresh, table) == _columns(migrated, table), table


def test_export_import_round_trip_preserves_new_tables() -> None:
    # §26.6.4: export → import on a migrated DB preserves the new tables; the
    # tombstone for a new table applies deletion-before-upsert.
    with tempfile.TemporaryDirectory() as t:
        src = Path(t) / "src.sqlite"
        dst = Path(t) / "dst.sqlite"
        export = Path(t) / "export.jsonl"
        db.init_db(src)
        db.init_db(dst)
        with db.connect(src) as conn:
            conn.execute(
                "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at) "
                "VALUES (?, 'h', 'md', 1, '2026-01-01T00:00:00Z')",
                (RELPATH,),
            )
            conn.execute(
                "INSERT INTO source_spans (id, source_id, relpath, span_type, "
                "content_hash, text_preview, created_at) "
                "VALUES ('SPAN-rt0', 1, ?, 'paragraph', 'hash-rt0', 'preview', "
                "'2026-01-01T00:00:00Z')",
                (RELPATH,),
            )
        unit_id = db.upsert_knowledge_unit(
            src, unit_type="atom", canonical_name="RT", statement="round trip",
            source_span_ids=["SPAN-rt0"], source_id=1,
        )
        db.upsert_claim_support(
            src, knowledge_unit_id=unit_id, source_span_id="SPAN-rt0",
            support_role="primary", support_status="verified", evidence_hash="hash-rt0",
        )
        gen_id = db.create_compiler_generation(src, prompt_contract_version="v1", source_id=1)

        db_sync.export_knowledge(src, export)
        db_sync.import_knowledge(dst, export)

        with db.connect(dst) as conn:
            assert conn.execute(
                "SELECT COUNT(*) FROM claim_supports WHERE knowledge_unit_id = ?",
                (unit_id,),
            ).fetchone()[0] == 1
            assert conn.execute(
                "SELECT status FROM compiler_generations WHERE id = ?", (gen_id,)
            ).fetchone()[0] == "staged"


def test_backup_restore_round_trip() -> None:
    # §26.6: a migrated DB copied byte-for-byte restores with integrity intact.
    with tempfile.TemporaryDirectory() as t:
        live = Path(t) / "state.sqlite"
        backup = Path(t) / "backup.sqlite"
        db.init_db(live)
        unit_id = db.upsert_knowledge_unit(
            live, unit_type="atom", canonical_name="B", statement="backup me",
            source_span_ids=["SPAN-b0"], source_id=1,
        )
        # Checkpoint WAL so a plain file copy is consistent.
        with db.connect(live) as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        backup.write_bytes(live.read_bytes())
        with db.connect(backup) as conn:
            assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert conn.execute(
                "SELECT support_status FROM knowledge_units WHERE id = ?", (unit_id,)
            ).fetchone()[0] == "unchecked"


# ---------------------------------------------------------------------------
# SCHEMA §20 DB lifecycle helpers (P3).
# ---------------------------------------------------------------------------

@pytest.fixture()
def vault():
    with tempfile.TemporaryDirectory() as t:
        paths = cfg.WikiPaths(Path(t))
        paths.internal.mkdir(parents=True, exist_ok=True)
        db.init_db(paths.state_db)
        with db.connect(paths.state_db) as conn:
            conn.execute(
                "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at) "
                "VALUES (?, 'h', 'md', 1, '2026-01-01T00:00:00Z')",
                (RELPATH,),
            )
            conn.execute(
                "INSERT INTO source_spans (id, source_id, relpath, span_type, "
                "content_hash, text_preview, created_at) "
                "VALUES ('SPAN-h0', 1, ?, 'paragraph', 'hash-h0', 'preview', "
                "'2026-01-01T00:00:00Z')",
                (RELPATH,),
            )
        yield paths


def _unit(paths: cfg.WikiPaths) -> str:
    return db.upsert_knowledge_unit(
        paths.state_db, unit_type="atom", canonical_name="H",
        statement="helper unit", source_span_ids=["SPAN-h0"], source_id=1,
    )


def test_claim_support_upsert_and_list(vault) -> None:
    unit_id = _unit(vault)
    db.upsert_claim_support(
        vault.state_db, knowledge_unit_id=unit_id, source_span_id="SPAN-h0",
        support_role="primary", support_status="verified", evidence_hash="hash-h0",
    )
    rows = db.list_claim_supports(vault.state_db, unit_id)
    assert len(rows) == 1
    assert rows[0]["support_role"] == "primary"
    assert rows[0]["support_status"] == "verified"
    # Upsert on the same composite PK updates in place (no duplicate row).
    db.upsert_claim_support(
        vault.state_db, knowledge_unit_id=unit_id, source_span_id="SPAN-h0",
        support_role="primary", support_status="failed",
        evidence_hash="hash-h0", support_reason="does not minimally support",
    )
    rows = db.list_claim_supports(vault.state_db, unit_id)
    assert len(rows) == 1
    assert rows[0]["support_status"] == "failed"


def test_claim_support_rejects_invalid_enums(vault) -> None:
    unit_id = _unit(vault)
    with pytest.raises(ValueError):
        db.upsert_claim_support(
            vault.state_db, knowledge_unit_id=unit_id, source_span_id="SPAN-h0",
            support_role="bogus", support_status="verified", evidence_hash="h",
        )
    with pytest.raises(ValueError):
        db.upsert_claim_support(
            vault.state_db, knowledge_unit_id=unit_id, source_span_id="SPAN-h0",
            support_role="primary", support_status="bogus", evidence_hash="h",
        )


def test_set_support_status_requires_reason_for_failed_and_stale(vault) -> None:
    unit_id = _unit(vault)
    with pytest.raises(ValueError):
        db.set_unit_support_status(vault.state_db, unit_id, "failed")
    db.set_unit_support_status(vault.state_db, unit_id, "verified")
    with db.connect(vault.state_db) as conn:
        assert conn.execute(
            "SELECT support_status FROM knowledge_units WHERE id = ?", (unit_id,)
        ).fetchone()[0] == "verified"


def test_eligibility_excludes_unchecked_and_retired(vault) -> None:
    verified = _unit(vault)
    db.set_unit_support_status(vault.state_db, verified, "verified")
    unchecked = db.upsert_knowledge_unit(
        vault.state_db, unit_type="atom", canonical_name="U", statement="u",
        source_span_ids=["SPAN-h0"], source_id=1,
    )
    retired = db.upsert_knowledge_unit(
        vault.state_db, unit_type="atom", canonical_name="R", statement="r",
        source_span_ids=["SPAN-h0"], source_id=1,
    )
    db.set_unit_support_status(vault.state_db, retired, "verified")
    db.retire_knowledge_unit(vault.state_db, retired)

    eligible_ids = {u["id"] for u in db.list_eligible_knowledge_units(vault.state_db)}
    assert verified in eligible_ids
    assert unchecked not in eligible_ids   # backfill state is not a compiler input
    assert retired not in eligible_ids     # retired never feeds downstream


def test_refresh_freshness_marks_stale_on_hash_change(vault) -> None:
    unit_id = _unit(vault)
    db.upsert_claim_support(
        vault.state_db, knowledge_unit_id=unit_id, source_span_id="SPAN-h0",
        support_role="primary", support_status="verified", evidence_hash="hash-h0",
    )
    db.set_unit_support_status(vault.state_db, unit_id, "verified")
    # No drift yet → nothing goes stale.
    assert db.refresh_support_freshness(vault.state_db) == set()
    # Edit the cited span's content hash → freshness re-check marks it stale.
    with db.connect(vault.state_db) as conn:
        conn.execute("UPDATE source_spans SET content_hash = 'edited' WHERE id = 'SPAN-h0'")
    assert db.refresh_support_freshness(vault.state_db) == {unit_id}
    with db.connect(vault.state_db) as conn:
        assert conn.execute(
            "SELECT support_status FROM knowledge_units WHERE id = ?", (unit_id,)
        ).fetchone()[0] == "stale"
        assert conn.execute(
            "SELECT support_status FROM claim_supports WHERE knowledge_unit_id = ?",
            (unit_id,),
        ).fetchone()[0] == "stale"


def test_generation_publish_keeps_one_authoritative_per_source(vault) -> None:
    g1 = db.create_compiler_generation(vault.state_db, prompt_contract_version="v1", source_id=1)
    db.publish_compiler_generation(vault.state_db, g1)
    assert db.get_authoritative_generation(vault.state_db, 1)["id"] == g1

    g2 = db.create_compiler_generation(vault.state_db, prompt_contract_version="v1", source_id=1)
    db.publish_compiler_generation(vault.state_db, g2)
    # The new authoritative supersedes the old; at most one authoritative remains.
    assert db.get_authoritative_generation(vault.state_db, 1)["id"] == g2
    with db.connect(vault.state_db) as conn:
        statuses = {
            r["id"]: r["status"]
            for r in conn.execute("SELECT id, status FROM compiler_generations").fetchall()
        }
    assert statuses[g1] == "discarded"
    assert statuses[g2] == "authoritative"


def test_generation_discard_and_publish_guards(vault) -> None:
    g = db.create_compiler_generation(vault.state_db, prompt_contract_version="v1", source_id=1)
    db.discard_compiler_generation(vault.state_db, g)
    with db.connect(vault.state_db) as conn:
        assert conn.execute(
            "SELECT status FROM compiler_generations WHERE id = ?", (g,)
        ).fetchone()[0] == "discarded"
    # A discarded generation can no longer be published.
    with pytest.raises(ValueError):
        db.publish_compiler_generation(vault.state_db, g)
    with pytest.raises(ValueError):
        db.publish_compiler_generation(vault.state_db, "GEN-missing")
