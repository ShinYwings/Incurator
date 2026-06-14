"""Plan C (v0.9.0) P2 — failing gold tests for HIERARCHY baseline & GRAPH AUDIT.

TDD red tests written BEFORE the P5 hierarchy and P7 graph-audit implementation.
They pin the frozen v9 contracts (SCHEMA §21.7/§21.8, SYSTEM_BEHAVIOR §27.4/§27.6/
§27.8) and MUST fail for the intended reason — the connected-components baseline,
graph audit, and lifecycle columns are not built yet — never via ``ImportError``.
Every forward reference is guarded with an intention-revealing message.

Fixtures covered (plan P2 list):
  * connected-components baseline excludes a quarantined noisy bridge (the
    degraded fallback the hierarchy benchmark improves on, §27.4);
  * a retired (edit/delete reconciliation tombstone) relation never feeds active
    topology (§27.8);
  * graph audit flags: an active relation with no independent support, an
    authoritative reference to a redirected entity, a quarantined relation
    missing its reason, and a served report finding without active claim support
    (§21.8 / §27.6 endpoint/support/lineage/report-freshness invariants).

P5/P7 API hooks these tests pin (documented in RELAY for the implementer):
  ``db.connected_components(db_path, *, only_active=True) -> list[set[str]]``,
  ``db.graph_audit(db_path) -> list[dict]`` where each violation mapping carries
  a ``code`` and the offending artifact's ``subject_id`` (empty list == clean).
"""

from __future__ import annotations

import json
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


def _relate(state_db: Path, src: str, tgt: str) -> str:
    return db.upsert_graph_relation(
        state_db,
        source_entity_id=src,
        target_entity_id=tgt,
        relation_type="rel",
        confidence=0.9,
    )


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(r[1]) for r in conn.execute(f"PRAGMA table_info({table})")}


def _subjects(report: list[dict]) -> set[str]:
    return {str(v["subject_id"]) for v in report}


# --------------------------------------------------------------------------- #
# Connected-components baseline (§27.4) — the degraded hierarchy fallback
# --------------------------------------------------------------------------- #


def test_connected_components_baseline_excludes_quarantined_bridge(
    vault: Path,
) -> None:
    cc = getattr(db, "connected_components", None)
    assert cc is not None, (
        "P5 must define db.connected_components baseline (SYSTEM_BEHAVIOR §27.4)"
    )
    cluster_a = [_seed_entity(vault, n) for n in ("A1", "A2", "A3")]
    cluster_b = [_seed_entity(vault, n) for n in ("B1", "B2", "B3")]
    for ring in (cluster_a, cluster_b):
        _relate(vault, ring[0], ring[1])
        _relate(vault, ring[1], ring[2])
        _relate(vault, ring[2], ring[0])
    bridge = _relate(vault, cluster_a[0], cluster_b[0])
    with db.connect(vault) as conn:
        assert "lifecycle_status" in _columns(conn, "graph_relations"), (
            "v9 graph_relations.lifecycle_status must exist"
        )
        conn.execute("UPDATE graph_relations SET lifecycle_status = 'active'")
        conn.execute(
            "UPDATE graph_relations "
            "SET lifecycle_status = 'quarantined', quarantine_reason = 'bridge_risk' "
            "WHERE id = ?",
            (bridge,),
        )
    sizes = sorted(len(component) for component in cc(vault, only_active=True))
    assert sizes == [3, 3], (
        "with the noisy bridge quarantined, the active baseline must yield two "
        f"3-node components, not one giant component; got {sizes}"
    )


def test_retired_relation_is_excluded_from_active_topology(vault: Path) -> None:
    """A source edit/delete retires a relation as a tombstone; it is never an
    authoritative topology input, so its endpoint drops out (§27.8)."""
    cc = getattr(db, "connected_components", None)
    assert cc is not None, (
        "P5 must define db.connected_components baseline (SYSTEM_BEHAVIOR §27.4)"
    )
    a = _seed_entity(vault, "A")
    b = _seed_entity(vault, "B")
    c = _seed_entity(vault, "C")
    _relate(vault, a, b)
    retired = _relate(vault, b, c)
    with db.connect(vault) as conn:
        assert "lifecycle_status" in _columns(conn, "graph_relations"), (
            "v9 graph_relations.lifecycle_status must exist"
        )
        conn.execute("UPDATE graph_relations SET lifecycle_status = 'active'")
        conn.execute(
            "UPDATE graph_relations SET lifecycle_status = 'retired' WHERE id = ?",
            (retired,),
        )
    sizes = sorted(len(component) for component in cc(vault, only_active=True))
    assert sizes == [1, 2], (
        "a retired reconciliation tombstone never feeds active topology: A-B stay "
        f"connected and C drops to a singleton; got {sizes}"
    )


# --------------------------------------------------------------------------- #
# Graph audit (§21.8 / §27.6) — endpoint/support/lineage/report freshness
# --------------------------------------------------------------------------- #


def test_graph_audit_flags_active_relation_without_independent_support(
    vault: Path,
) -> None:
    audit = getattr(db, "graph_audit", None)
    assert audit is not None, (
        "P7 must define db.graph_audit (SYSTEM_BEHAVIOR §27.6 / SCHEMA §21.8)"
    )
    src = _seed_entity(vault, "S")
    tgt = _seed_entity(vault, "T")
    rel = _relate(vault, src, tgt)
    with db.connect(vault) as conn:
        assert "lifecycle_status" in _columns(conn, "graph_relations"), (
            "v9 graph_relations.lifecycle_status must exist"
        )
        conn.execute(
            "UPDATE graph_relations SET lifecycle_status = 'active' WHERE id = ?",
            (rel,),
        )
    # No graph_relation_supports rows: an active edge with zero verified
    # independent support violates the §21.8 invariant.
    assert rel in _subjects(audit(vault)), (
        "graph audit must flag an active relation lacking >=1 verified "
        "independent support (§21.8)"
    )


def test_graph_audit_flags_reference_to_redirected_entity(vault: Path) -> None:
    audit = getattr(db, "graph_audit", None)
    assert audit is not None, (
        "P7 must define db.graph_audit (SYSTEM_BEHAVIOR §27.6 / SCHEMA §21.8)"
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
            "UPDATE graph_relations SET lifecycle_status = 'active' WHERE id = ?",
            (rel,),
        )
        conn.execute(
            "UPDATE graph_entities "
            "SET resolution_state = 'redirected', redirect_to_entity_id = ? "
            "WHERE id = ?",
            (survivor, origin),
        )
    assert rel in _subjects(audit(vault)), (
        "graph audit must flag an authoritative relation still referencing a "
        "redirected (non-canonical) entity (§21.8: 0 such references)"
    )


def test_graph_audit_flags_quarantined_relation_missing_reason(
    vault: Path,
) -> None:
    audit = getattr(db, "graph_audit", None)
    assert audit is not None, (
        "P7 must define db.graph_audit (SYSTEM_BEHAVIOR §27.6 / SCHEMA §21.8)"
    )
    src = _seed_entity(vault, "S")
    tgt = _seed_entity(vault, "T")
    rel = _relate(vault, src, tgt)
    with db.connect(vault) as conn:
        assert "quarantine_reason" in _columns(conn, "graph_relations"), (
            "v9 graph_relations.quarantine_reason must exist"
        )
        # Quarantined but with an empty reason code — an opaque discard, which the
        # §27.3 'never an opaque discard pile' invariant forbids.
        conn.execute(
            "UPDATE graph_relations "
            "SET lifecycle_status = 'quarantined', quarantine_reason = '' "
            "WHERE id = ?",
            (rel,),
        )
    assert rel in _subjects(audit(vault)), (
        "graph audit must flag a quarantined relation missing its reason code / "
        "re-eval trigger (§27.3 inspectable quarantine)"
    )


def test_graph_audit_flags_report_finding_without_active_support(
    vault: Path,
) -> None:
    audit = getattr(db, "graph_audit", None)
    assert audit is not None, (
        "P7 must define db.graph_audit (SYSTEM_BEHAVIOR §27.6 / SCHEMA §21.8)"
    )
    src = _seed_entity(vault, "S")
    tgt = _seed_entity(vault, "T")
    dead_rel = _relate(vault, src, tgt)
    with db.connect(vault) as conn:
        assert "lifecycle_status" in _columns(conn, "graph_relations"), (
            "v9 graph_relations.lifecycle_status must exist"
        )
        # The only cited relation is quarantined, so the report finding has no
        # eligible active claim support — a report-freshness violation (§27.6).
        conn.execute(
            "UPDATE graph_relations "
            "SET lifecycle_status = 'quarantined', quarantine_reason = 'unsupported' "
            "WHERE id = ?",
            (dead_rel,),
        )
        conn.execute(
            "INSERT INTO community_reports "
            "(id, community_key, level, title, summary, full_content, finding_json, "
            " entity_ids, relation_ids, dependency_hash, created_at, updated_at) "
            "VALUES ('REP-stale', 'C1', 0, 't', 's', 'f', ?, ?, ?, 'h', 't', 't')",
            (
                json.dumps([{"text": "claim", "relation_ids": [dead_rel]}]),
                json.dumps([src, tgt]),
                json.dumps([dead_rel]),
            ),
        )
    assert "REP-stale" in _subjects(audit(vault)), (
        "graph audit must flag a served report finding whose only cited relation "
        "is not active eligible claim support (§27.6 report freshness)"
    )
