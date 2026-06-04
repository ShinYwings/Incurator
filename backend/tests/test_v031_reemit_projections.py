"""Optional follow-up (v0.3.1): re-emit derived L2/L3 corpus from DB records."""

from __future__ import annotations

import tempfile
from pathlib import Path

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
        span = db.upsert_source_span(paths.state_db, source_id=1, relpath="04_Resources/r.md",
                                     span_type="paragraph", content_hash="c1",
                                     text_preview="Residual connections ease optimization.")
        db.upsert_knowledge_unit(paths.state_db, unit_type="claim",
                                 canonical_name="Residual learning", statement="eases optimization",
                                 source_span_ids=[span], source_id=1, confidence=0.9,
                                 atom_node_id="ATM-keep0001")
        db.upsert_community_report(paths.state_db, community_key="comm-1", title="Residual",
                                   summary="s", full_content="f", dependency_hash="d1",
                                   source_span_ids=[span])
        # stale projection files that must be replaced
        paths.atoms.mkdir(parents=True, exist_ok=True)
        paths.concepts.mkdir(parents=True, exist_ok=True)
        (paths.atoms / "ATM-stale999.md").write_text("stale", encoding="utf-8")
        (paths.concepts / "CON-stale999.md").write_text("stale", encoding="utf-8")
        yield paths


def test_reemit_replaces_stale_and_reflects_db(vault) -> None:
    paths = vault
    counts = compile_mod.reemit_projections(paths)
    assert counts == {"atoms": 1, "concepts": 1, "synthesis": 0}

    # Stale files removed.
    assert not (paths.atoms / "ATM-stale999.md").exists()
    assert not (paths.concepts / "CON-stale999.md").exists()

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
