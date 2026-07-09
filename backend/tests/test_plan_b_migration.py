"""Plan B (v0.8.0) P3 — claim-support/generation helper persistence."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from curator import config as cfg
from curator import db
from curator import db_sync

RELPATH = "04_Resources/pb.md"


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
