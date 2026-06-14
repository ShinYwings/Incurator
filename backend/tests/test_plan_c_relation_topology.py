"""Plan C (v0.9.0) P2 — failing gold tests for RELATION lifecycle & topology.

TDD red tests written BEFORE the P4 relation-support/quarantine implementation.
They pin the frozen v9 relation contract (SCHEMA §21.5/§21.6, SYSTEM_BEHAVIOR
§27.2/§27.3) and MUST fail for the intended reason — the v9 lifecycle compiler is
not built yet — never via ``ImportError``. Every forward reference to a
not-yet-existing column or ``db`` API is guarded with an intention-revealing
message.

Adversarial fixtures covered (plan P2 list):
  * self-loop -> quarantined ``self_loop``;
  * unsupported edge -> quarantined ``unsupported``;
  * copied-source-only support -> quarantined ``copied_source_only`` (independence
    is by source lineage, not row count);
  * unresolved endpoint (relation pointing at a redirected entity) ->
    quarantined ``endpoint_unresolved``;
  * a fully supported, canonical-endpoint edge -> ``active``;
  * noisy bridge (single low-confidence edge joining two dense components) ->
    ``bridge_risk``;
  * authored vs extracted edge classes stay distinct (§27.3 Arena decision 9).

P4 API hooks these tests pin (documented in RELAY for the implementer):
  ``db.compile_relation_lifecycle(db_path, *, relation_id) -> str`` (sets
  ``lifecycle_status``/``quarantine_reason`` and returns the resulting status),
  ``db.detect_bridge_risk_relations(db_path) -> list[str]``.
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from curator import config as cfg
from curator import db


@pytest.fixture()
def vault() -> Path:
    with tempfile.TemporaryDirectory() as t:
        paths = cfg.WikiPaths(Path(t))
        paths.internal.mkdir(parents=True, exist_ok=True)
        db.init_db(paths.state_db)
        yield paths.state_db


def _seed_entity(state_db: Path, name: str, etype: str = "concept") -> str:
    return db.upsert_graph_entity(state_db, canonical_name=name, entity_type=etype)


def _relate(state_db: Path, src: str, tgt: str, rtype: str = "rel") -> str:
    return db.upsert_graph_relation(
        state_db,
        source_entity_id=src,
        target_entity_id=tgt,
        relation_type=rtype,
        confidence=0.9,
    )


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(r[1]) for r in conn.execute(f"PRAGMA table_info({table})")}


def _add_support(
    conn: sqlite3.Connection,
    relation_id: str,
    knu: str,
    lineage: str,
    support_hash: str,
    status: str = "verified",
) -> None:
    conn.execute(
        "INSERT INTO graph_relation_supports "
        "(relation_id, knowledge_unit_id, source_span_ids, assertion_source, "
        " confidence, support_status, support_hash, source_lineage_hash, "
        " created_at, updated_at) "
        "VALUES (?, ?, '[]', 'source_states', 0.9, ?, ?, ?, 't', 't')",
        (relation_id, knu, status, support_hash, lineage),
    )


def _reason(conn: sqlite3.Connection, relation_id: str) -> str:
    return str(
        conn.execute(
            "SELECT quarantine_reason FROM graph_relations WHERE id = ?",
            (relation_id,),
        ).fetchone()[0]
    )


# --------------------------------------------------------------------------- #
# Per-relation lifecycle compilation (§27.3)
# --------------------------------------------------------------------------- #


def test_self_loop_relation_is_quarantined(vault: Path) -> None:
    compile_fn = getattr(db, "compile_relation_lifecycle", None)
    assert compile_fn is not None, (
        "P4 must define db.compile_relation_lifecycle (SYSTEM_BEHAVIOR §27.3)"
    )
    ent = _seed_entity(vault, "Recursion")
    rel = _relate(vault, ent, ent, rtype="depends_on")
    status = compile_fn(vault, relation_id=rel)
    with db.connect(vault) as conn:
        reason = _reason(conn, rel)
    assert status == "quarantined"
    assert reason == "self_loop", (
        f"a source==target edge must quarantine as self_loop; got {reason!r}"
    )


def test_unsupported_relation_is_quarantined(vault: Path) -> None:
    compile_fn = getattr(db, "compile_relation_lifecycle", None)
    assert compile_fn is not None, (
        "P4 must define db.compile_relation_lifecycle (SYSTEM_BEHAVIOR §27.3)"
    )
    src = _seed_entity(vault, "Method A")
    tgt = _seed_entity(vault, "Method B")
    rel = _relate(vault, src, tgt)
    # No graph_relation_supports rows at all.
    status = compile_fn(vault, relation_id=rel)
    with db.connect(vault) as conn:
        reason = _reason(conn, rel)
    assert status == "quarantined"
    assert reason == "unsupported", (
        f"an edge with no eligible support must quarantine as unsupported; "
        f"got {reason!r}"
    )


def test_copied_source_only_relation_is_quarantined(vault: Path) -> None:
    """Two verified supports that share ONE source_lineage_hash give independent
    count 1 — the edge has support but no INDEPENDENT lineage, so it quarantines
    as copied_source_only, not active (§27.2 independence by lineage)."""
    compile_fn = getattr(db, "compile_relation_lifecycle", None)
    assert compile_fn is not None, (
        "P4 must define db.compile_relation_lifecycle (SYSTEM_BEHAVIOR §27.3)"
    )
    src = _seed_entity(vault, "Method A")
    tgt = _seed_entity(vault, "Method B")
    rel = _relate(vault, src, tgt)
    with db.connect(vault) as conn:
        assert "graph_relation_supports" in {
            str(r[0])
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }, "v9 graph_relation_supports table must exist"
        _add_support(conn, rel, "KNU-1", "lineage-X", "h1")
        _add_support(conn, rel, "KNU-2", "lineage-X", "h2")  # copied source
    status = compile_fn(vault, relation_id=rel)
    with db.connect(vault) as conn:
        reason = _reason(conn, rel)
    assert status == "quarantined"
    assert reason == "copied_source_only", (
        "supports sharing one source lineage carry no independent support; the "
        f"edge must quarantine as copied_source_only; got {reason!r}"
    )


def test_endpoint_unresolved_relation_is_quarantined(vault: Path) -> None:
    compile_fn = getattr(db, "compile_relation_lifecycle", None)
    assert compile_fn is not None, (
        "P4 must define db.compile_relation_lifecycle (SYSTEM_BEHAVIOR §27.3)"
    )
    origin = _seed_entity(vault, "Old Name")
    survivor = _seed_entity(vault, "Canonical Name")
    other = _seed_entity(vault, "Other")
    rel = _relate(vault, origin, other)
    with db.connect(vault) as conn:
        assert "resolution_state" in _columns(conn, "graph_entities"), (
            "v9 graph_entities.resolution_state must exist"
        )
        conn.execute(
            "UPDATE graph_entities "
            "SET resolution_state = 'redirected', redirect_to_entity_id = ? "
            "WHERE id = ?",
            (survivor, origin),
        )
    status = compile_fn(vault, relation_id=rel)
    with db.connect(vault) as conn:
        reason = _reason(conn, rel)
    assert status == "quarantined"
    assert reason == "endpoint_unresolved", (
        "a relation pointing at a redirected (non-canonical) entity that was not "
        f"resolved must quarantine as endpoint_unresolved; got {reason!r}"
    )


def test_fully_supported_canonical_edge_is_active(vault: Path) -> None:
    compile_fn = getattr(db, "compile_relation_lifecycle", None)
    assert compile_fn is not None, (
        "P4 must define db.compile_relation_lifecycle (SYSTEM_BEHAVIOR §27.3)"
    )
    src = _seed_entity(vault, "Method A")
    tgt = _seed_entity(vault, "Method B")
    rel = _relate(vault, src, tgt)
    with db.connect(vault) as conn:
        assert "graph_relation_supports" in {
            str(r[0])
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }, "v9 graph_relation_supports table must exist"
        _add_support(conn, rel, "KNU-1", "lineage-A", "h1")
        _add_support(conn, rel, "KNU-2", "lineage-B", "h2")  # independent lineage
    status = compile_fn(vault, relation_id=rel)
    assert status == "active", (
        "an edge with >=1 verified independent support and canonical endpoints "
        f"must become active; got {status!r}"
    )


# --------------------------------------------------------------------------- #
# Topology-level detection (§27.3)
# --------------------------------------------------------------------------- #


def test_noisy_bridge_single_edge_is_flagged_bridge_risk(vault: Path) -> None:
    """Two dense triangles joined by a single low-confidence edge: only that one
    bridge edge is flagged bridge_risk; the intra-cluster edges are not."""
    detect = getattr(db, "detect_bridge_risk_relations", None)
    assert detect is not None, (
        "P4 must define db.detect_bridge_risk_relations (SYSTEM_BEHAVIOR §27.3)"
    )
    a1 = _seed_entity(vault, "A1")
    a2 = _seed_entity(vault, "A2")
    a3 = _seed_entity(vault, "A3")
    b1 = _seed_entity(vault, "B1")
    b2 = _seed_entity(vault, "B2")
    b3 = _seed_entity(vault, "B3")
    dense = [
        _relate(vault, a1, a2),
        _relate(vault, a2, a3),
        _relate(vault, a3, a1),
        _relate(vault, b1, b2),
        _relate(vault, b2, b3),
        _relate(vault, b3, b1),
    ]
    bridge = db.upsert_graph_relation(
        vault,
        source_entity_id=a1,
        target_entity_id=b1,
        relation_type="rel",
        confidence=0.25,
    )
    flagged = set(detect(vault))
    assert flagged == {bridge}, (
        "only the single low-confidence bridge edge joining two dense components "
        f"is a bridge_risk; intra-cluster edges {dense} are not; got {flagged}"
    )


def test_edge_class_separates_authored_from_extracted(vault: Path) -> None:
    a = _seed_entity(vault, "A")
    b = _seed_entity(vault, "B")
    c = _seed_entity(vault, "C")
    authored = _relate(vault, a, b, rtype="links_to")
    _relate(vault, b, c, rtype="improves")
    with db.connect(vault) as conn:
        assert "edge_class" in _columns(conn, "graph_relations"), (
            "v9 graph_relations.edge_class must exist (SCHEMA §21.6)"
        )
        conn.execute(
            "UPDATE graph_relations SET edge_class = 'authored' WHERE id = ?",
            (authored,),
        )
        n_authored = conn.execute(
            "SELECT COUNT(*) FROM graph_relations WHERE edge_class = 'authored'"
        ).fetchone()[0]
        n_extracted = conn.execute(
            "SELECT COUNT(*) FROM graph_relations WHERE edge_class = 'extracted'"
        ).fetchone()[0]
    assert (n_authored, n_extracted) == (1, 1), (
        "authored and extracted edge classes stay distinct; an authored link is "
        "never silently counted as extracted factual evidence (§27.3)"
    )
