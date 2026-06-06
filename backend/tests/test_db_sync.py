"""Tests for Knowledge Sync Bridge: export/import pipeline."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from curator import db
from curator.db_sync import (
    SYNC_TABLES,
    ExportStats,
    ImportStats,
    export_knowledge,
    import_knowledge,
    record_tombstone,
)


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "state.sqlite"
    db.init_db(p)
    return p


@pytest.fixture()
def populated_db(db_path: Path) -> Path:
    """DB with one source and one atom."""
    with db.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at, last_ingested)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            ("03_Notes/paper.md", "abc123", "md", 100, "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO atoms (id, name, parent_source, claim_type, one_liner, last_updated)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            ("ATM-00000001", "Test Atom", "01_Contexts/CTX-00000001.md", "fact", "A test claim.", "2026-01-01T00:00:00Z"),
        )
    return db_path


class TestSchemaVersion:
    def test_schema_version_bumped_to_7(self, db_path: Path) -> None:
        with db.connect(db_path) as conn:
            version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
        assert version == 7

    def test_deleted_records_table_exists(self, db_path: Path) -> None:
        with db.connect(db_path) as conn:
            tables = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        assert "deleted_records" in tables


class TestTombstone:
    def test_record_tombstone_inserts_row(self, db_path: Path) -> None:
        record_tombstone(db_path, "atoms", "ATM-00000001")
        with db.connect(db_path) as conn:
            row = conn.execute(
                "SELECT * FROM deleted_records WHERE table_name=? AND record_id=?",
                ("atoms", "ATM-00000001"),
            ).fetchone()
        assert row is not None

    def test_record_tombstone_idempotent(self, db_path: Path) -> None:
        record_tombstone(db_path, "atoms", "ATM-00000001")
        record_tombstone(db_path, "atoms", "ATM-00000001")  # second call must not raise
        with db.connect(db_path) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM deleted_records WHERE table_name=? AND record_id=?",
                ("atoms", "ATM-00000001"),
            ).fetchone()[0]
        assert count == 1


class TestExport:
    def test_export_creates_file(self, populated_db: Path, tmp_path: Path) -> None:
        out = tmp_path / "export.jsonl"
        stats = export_knowledge(populated_db, out)
        assert out.exists()
        assert isinstance(stats, ExportStats)
        assert stats.total_rows > 0

    def test_export_header_format(self, populated_db: Path, tmp_path: Path) -> None:
        out = tmp_path / "export.jsonl"
        export_knowledge(populated_db, out)
        with out.open() as f:
            header = json.loads(f.readline())
        assert header["type"] == "header"
        assert header["schema_version"] == 7
        assert "exported_at" in header

    def test_export_excludes_device_tables(self, populated_db: Path, tmp_path: Path) -> None:
        out = tmp_path / "export.jsonl"
        export_knowledge(populated_db, out)
        table_names: set[str] = set()
        with out.open() as f:
            for line in f:
                rec = json.loads(line)
                if rec["type"] == "row":
                    table_names.add(rec["table"])
        for excluded in ("search_embeddings", "ingest_jobs", "job_events", "search_index_meta"):
            assert excluded not in table_names, f"{excluded} should be excluded from export"

    def test_export_includes_canonical_tables(self, populated_db: Path, tmp_path: Path) -> None:
        out = tmp_path / "export.jsonl"
        export_knowledge(populated_db, out)
        table_names: set[str] = set()
        with out.open() as f:
            for line in f:
                rec = json.loads(line)
                if rec["type"] == "row":
                    table_names.add(rec["table"])
        assert "sources" in table_names
        assert "atoms" in table_names


class TestImport:
    def test_import_round_trip(self, populated_db: Path, tmp_path: Path) -> None:
        """Export from populated DB, import into fresh DB, verify records match."""
        out = tmp_path / "export.jsonl"
        export_knowledge(populated_db, out)

        fresh = tmp_path / "fresh.sqlite"
        db.init_db(fresh)
        stats = import_knowledge(fresh, out)

        assert isinstance(stats, ImportStats)
        with db.connect(fresh) as conn:
            sources = conn.execute("SELECT relpath FROM sources").fetchall()
            atoms = conn.execute("SELECT id FROM atoms").fetchall()
        assert any(r[0] == "03_Notes/paper.md" for r in sources)
        assert any(r[0] == "ATM-00000001" for r in atoms)

    def test_import_dry_run_no_changes(self, populated_db: Path, tmp_path: Path) -> None:
        out = tmp_path / "export.jsonl"
        export_knowledge(populated_db, out)

        fresh = tmp_path / "fresh.sqlite"
        db.init_db(fresh)
        import_knowledge(fresh, out, dry_run=True)

        with db.connect(fresh) as conn:
            count = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
        assert count == 0  # nothing inserted in dry-run

    def test_import_lw_wins(self, populated_db: Path, tmp_path: Path) -> None:
        """Newer record from export beats older local record."""
        out = tmp_path / "export.jsonl"
        export_knowledge(populated_db, out)

        # Create target DB with older version of same atom
        target = tmp_path / "target.sqlite"
        db.init_db(target)
        with db.connect(target) as conn:
            conn.execute(
                "INSERT INTO atoms (id, name, parent_source, claim_type, one_liner, last_updated)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                ("ATM-00000001", "Old Name", "01_Contexts/CTX-00000001.md", "fact", "Old.", "2025-01-01T00:00:00Z"),
            )

        import_knowledge(target, out)

        with db.connect(target) as conn:
            name = conn.execute("SELECT name FROM atoms WHERE id=?", ("ATM-00000001",)).fetchone()[0]
        assert name == "Test Atom"  # newer version from export won

    def test_import_tombstone_deletes_local(self, tmp_path: Path) -> None:
        """Tombstone in export file deletes matching local record."""
        source = tmp_path / "source.sqlite"
        db.init_db(source)
        record_tombstone(source, "atoms", "ATM-DEAD0001")
        out = tmp_path / "export.jsonl"
        export_knowledge(source, out)

        target = tmp_path / "target.sqlite"
        db.init_db(target)
        with db.connect(target) as conn:
            conn.execute(
                "INSERT INTO atoms (id, name, parent_source, claim_type, one_liner, last_updated)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                ("ATM-DEAD0001", "To Delete", "01_Contexts/CTX-00000001.md", "fact", ".", "2025-01-01T00:00:00Z"),
            )
        import_knowledge(target, out)

        with db.connect(target) as conn:
            row = conn.execute("SELECT id FROM atoms WHERE id=?", ("ATM-DEAD0001",)).fetchone()
        assert row is None  # tombstone deleted it

    def test_import_schema_version_mismatch_raises(self, tmp_path: Path) -> None:
        bad_jsonl = tmp_path / "bad.jsonl"
        bad_jsonl.write_text(
            json.dumps({"type": "header", "schema_version": 999, "exported_at": "2026-01-01T00:00:00Z"}) + "\n"
        )
        target = tmp_path / "target.sqlite"
        db.init_db(target)
        with pytest.raises(ValueError, match="schema_version"):
            import_knowledge(target, bad_jsonl)
