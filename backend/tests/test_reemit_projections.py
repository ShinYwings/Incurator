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
                "l2_status='done', l3_status='error', l4_status='pending' WHERE id=1"
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
        source_ent = db.upsert_graph_entity(
            paths.state_db,
            canonical_name="Residual learning",
            entity_type="concept",
            source_span_ids=[span],
            knowledge_unit_ids=[unit_id],
        )
        target_ent = db.upsert_graph_entity(
            paths.state_db,
            canonical_name="Optimization",
            entity_type="concept",
            source_span_ids=[span],
            knowledge_unit_ids=[unit_id],
        )
        rel_id = db.upsert_graph_relation(
            paths.state_db,
            source_entity_id=source_ent,
            target_entity_id=target_ent,
            relation_type="eases",
            source_span_ids=[span],
            confidence=0.9,
        )
        db.upsert_graph_relation_support(
            paths.state_db,
            relation_id=rel_id,
            knowledge_unit_id=unit_id,
            source_span_ids=[span],
            source_lineage_hash="h",
        )
        db.upsert_community_report(paths.state_db, community_key="comm-1", title="Residual",
                                   summary="s", full_content="f", dependency_hash="d1",
                                   relation_ids=[rel_id], source_span_ids=[span])
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
    db.update_page_hash(
        paths.state_db,
        f"{paths.contexts.name}/CTX-keep0001.md",
        "prior-context-hash",
    )
    for relpath in (
        f"{paths.contexts.name}/CTX-stale999.md",
        f"{paths.atoms.name}/ATM-stale999.md",
        f"{paths.concepts.name}/CON-stale999.md",
    ):
        db.update_page_hash(paths.state_db, relpath, "stale-hash")

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
    assert "source_path: 04_Resources/r.md" in body

    con_files = list(paths.concepts.glob("CON-*.md"))
    assert len(con_files) == 1
    first_con_name = con_files[0].name
    con_text = con_files[0].read_text(encoding="utf-8")
    assert "community_report_id" in con_text
    assert "## Relations" in con_text
    assert "[[02_Atoms/ATM-keep0001]]" in con_text
    page_hashes = db.get_page_hashes(paths.state_db)
    assert f"{paths.contexts.name}/CTX-keep0001.md" in page_hashes
    assert (
        page_hashes[f"{paths.contexts.name}/CTX-keep0001.md"]
        == "prior-context-hash"
    )
    assert f"{paths.atoms.name}/ATM-keep0001.md" in page_hashes
    assert f"{paths.concepts.name}/{first_con_name}" in page_hashes
    assert f"{paths.contexts.name}/CTX-stale999.md" not in page_hashes
    assert f"{paths.atoms.name}/ATM-stale999.md" not in page_hashes
    assert f"{paths.concepts.name}/CON-stale999.md" not in page_hashes

    compile_mod.reemit_projections(paths)
    assert [p.name for p in paths.concepts.glob("CON-*.md")] == [first_con_name]


def test_reemit_does_not_touch_source(vault) -> None:
    paths = vault
    compile_mod.reemit_projections(paths)
    # Source folders / spans untouched.
    assert not (paths.root / "03_Notes").exists()
    assert db.list_source_spans(paths.state_db, 1)  # spans still present


def test_reemit_persists_missing_atom_identity_before_writing(vault) -> None:
    paths = vault
    with db.connect(paths.state_db) as conn:
        unit_id = str(
            conn.execute(
                "SELECT id FROM knowledge_units WHERE source_id = 1"
            ).fetchone()[0]
        )
        conn.execute(
            "UPDATE knowledge_units SET atom_node_id = NULL WHERE id = ?",
            (unit_id,),
        )

    compile_mod.reemit_projections(paths)
    with db.connect(paths.state_db) as conn:
        first_atom_id = str(
            conn.execute(
                "SELECT atom_node_id FROM knowledge_units WHERE id = ?",
                (unit_id,),
            ).fetchone()[0]
        )

    compile_mod.reemit_projections(paths)
    with db.connect(paths.state_db) as conn:
        second_atom_id = str(
            conn.execute(
                "SELECT atom_node_id FROM knowledge_units WHERE id = ?",
                (unit_id,),
            ).fetchone()[0]
        )

    assert first_atom_id.startswith("ATM-")
    assert second_atom_id == first_atom_id
    assert (paths.atoms / f"{first_atom_id}.md").exists()


def test_reemit_does_not_churn_synthesis_updated_at_when_concepts_unchanged(vault) -> None:
    paths = vault
    with db.connect(paths.state_db) as conn:
        report_id = conn.execute("SELECT id FROM community_reports").fetchone()[0]
    syn_id = db.upsert_synthesis_node(
        paths.state_db,
        title="Synthesis",
        statement="Stable statement.",
        full_content="Stable content.",
        dependency_hash="syn-deps",
        community_report_ids=[report_id],
        source_span_ids=[],
        confidence=0.9,
    )

    compile_mod.reemit_projections(paths)
    with db.connect(paths.state_db) as conn:
        concept_ids = conn.execute(
            "SELECT concept_ids FROM synthesis_nodes WHERE id = ?",
            (syn_id,),
        ).fetchone()[0]
        assert compile_mod.json.loads(concept_ids)
        conn.execute(
            "UPDATE synthesis_nodes SET updated_at = 'SENTINEL' WHERE id = ?",
            (syn_id,),
        )

    compile_mod.reemit_projections(paths)

    with db.connect(paths.state_db) as conn:
        row = conn.execute(
            "SELECT concept_ids, updated_at FROM synthesis_nodes WHERE id = ?",
            (syn_id,),
        ).fetchone()
    assert row["concept_ids"] == concept_ids
    assert row["updated_at"] == "SENTINEL"


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
