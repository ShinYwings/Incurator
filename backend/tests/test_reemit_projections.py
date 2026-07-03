"""Optional follow-up (v0.3.1): re-emit derived L2/L3 corpus from DB records."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3
import tempfile

import pytest

from curator import config as cfg, db
from curator.pipeline import compile as compile_mod


@pytest.fixture()
def vault():
    with tempfile.TemporaryDirectory() as t:
        root = Path(t)
        paths = cfg.WikiPaths(root)
        db.init_db(paths.state_db)
        with db.connect(paths.state_db) as c:
            c.execute("INSERT INTO sources (relpath,content_hash,file_type,bytes,added_at) "
                      "VALUES ('04_Resources/r.md','h','md',1,datetime('now'))")
            c.execute(
                "UPDATE sources SET context_id='CTX-keep0001', l1_status='done', "
                "l2_status='done', l3_status='done', l4_status='done' WHERE id=1"
            )
            c.execute(
                "INSERT INTO sources (relpath,content_hash,file_type,bytes,added_at,"
                "l2_status,l3_status,l4_status) VALUES "
                "('04_Resources/orphan.md','h2','md',1,datetime('now'),"
                "'skipped','pending','pending')"
            )
        span = db.upsert_source_span(paths.state_db, source_id=1, relpath="04_Resources/r.md",
                                     span_type="paragraph", content_hash="c1",
                                     text_preview="Residual connections ease optimization.")
        unit_id = db.upsert_knowledge_unit(paths.state_db, unit_type="claim",
                                           canonical_name="Residual learning",
                                           statement="eases optimization",
                                           source_span_ids=[span], source_id=1,
                                           confidence=0.9, atom_node_id="ATM-keep0001")
        db.set_unit_support_status(paths.state_db, unit_id, "verified")
        # Served units belong to an authoritative compiler generation (§26.3).
        gen = db.create_compiler_generation(paths.state_db, prompt_contract_version="v2", source_id=1)
        db.publish_compiler_generation(paths.state_db, gen)
        with db.connect(paths.state_db) as c:
            c.execute("UPDATE knowledge_units SET generation_id = ? WHERE id = ?", (gen, unit_id))
        db.upsert_community_report(paths.state_db, community_key="comm-1", title="Residual",
                                   summary="s", full_content="f", dependency_hash="d1",
                                   source_span_ids=[span])
        # stale projection files that must be replaced
        paths.atoms.mkdir(parents=True, exist_ok=True)
        paths.concepts.mkdir(parents=True, exist_ok=True)
        paths.contexts.mkdir(parents=True, exist_ok=True)
        (paths.contexts / "CTX-keep0001.md").write_text("current", encoding="utf-8")
        (paths.contexts / "CTX-stale999.md").write_text("stale", encoding="utf-8")
        (paths.atoms / "ATM-stale999.md").write_text("stale", encoding="utf-8")
        (paths.concepts / "CON-stale999.md").write_text("stale", encoding="utf-8")
        yield paths


def test_reemit_replaces_stale_and_reflects_db(vault) -> None:
    paths = vault
    counts = compile_mod.reemit_projections(paths)
    assert counts == {"contexts": 1, "atoms": 1, "concepts": 1, "synthesis": 0}

    # Stale files removed.
    assert not (paths.atoms / "ATM-stale999.md").exists()
    assert not (paths.concepts / "CON-stale999.md").exists()
    assert not (paths.contexts / "CTX-stale999.md").exists()
    assert (paths.contexts / "CTX-keep0001.md").exists()
    with db.connect(paths.state_db) as conn:
        supported = conn.execute(
            "SELECT l2_status, l3_status, l4_status FROM sources WHERE id=1"
        ).fetchone()
        unsupported = conn.execute(
            "SELECT l2_status, l3_status, l4_status FROM sources WHERE id=2"
        ).fetchone()
    assert tuple(supported) == ("done", "done", "skipped")
    assert tuple(unsupported) == ("skipped", "skipped", "skipped")

    # ATM re-emitted at the unit's stored atom_node_id, content from DB.
    atom = paths.atoms / "ATM-keep0001.md"
    assert atom.exists()
    body = atom.read_text(encoding="utf-8")
    assert "Residual learning" in body and "source_span_ids" in body

    con_files = list(paths.concepts.glob("CON-*.md"))
    assert len(con_files) == 1
    assert "community_report_id" in con_files[0].read_text(encoding="utf-8")


def test_reemit_does_not_touch_source(vault) -> None:
    paths = vault
    compile_mod.reemit_projections(paths)
    # Source folders / spans untouched.
    assert not (paths.root / "03_Notes").exists()
    assert db.list_source_spans(paths.state_db, 1)  # spans still present


def test_reemit_chunks_more_than_999_report_span_ids(vault, monkeypatch) -> None:
    paths = vault
    span_ids = [
        db.upsert_source_span(
            paths.state_db,
            source_id=1,
            relpath="04_Resources/r.md",
            span_type="paragraph",
            content_hash=f"bulk-{index}",
            text_preview=f"span {index}",
        )
        for index in range(1001)
    ]
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "UPDATE community_reports SET source_span_ids = ?",
            (compile_mod.json.dumps(span_ids),),
        )

    real_connect = db.connect

    class LimitedConnection:
        def __init__(self, conn):
            self._conn = conn

        def execute(self, sql, parameters=()):
            if len(parameters) > 999:
                raise sqlite3.OperationalError("too many SQL variables")
            return self._conn.execute(sql, parameters)

        def __getattr__(self, name):
            return getattr(self._conn, name)

    @contextmanager
    def limited_connect(path):
        with real_connect(path) as conn:
            yield LimitedConnection(conn)

    monkeypatch.setattr(compile_mod.db, "connect", limited_connect)
    counts = compile_mod.reemit_projections(paths)
    assert counts["concepts"] == 1
