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
  * single-lineage support -> ``active`` since v0.43.0 (independence is by source
    lineage, not row count, and the lineage hash already collapses copies, so
    exactly 1 distinct lineage means one genuine source);
  * unresolved endpoint (relation pointing at a redirected entity) ->
    quarantined ``endpoint_unresolved``;
  * a canonical-endpoint edge with >=1 independent source lineage -> ``active``
    (the §27.2 corroboration threshold; only 0 lineages is ``unsupported``, so
    the support-side partition is total and disjoint);
  * noisy bridge (single low-confidence edge joining two dense components) ->
    ``bridge_risk``; a low-confidence edge INSIDE a dense cluster is NOT flagged
    (topology, not a raw-confidence filter);
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


def test_single_source_lineage_relation_is_active(vault: Path) -> None:
    """v0.43.0: two verified supports sharing ONE source_lineage_hash give an
    independent-lineage count of exactly 1 — one genuine source asserting the
    proposition — and that is now ACTIVE.

    The lineage hash already collapses copied/forked sources to one lineage, so a
    count of 1 means "one real source", not "a duplicate faking corroboration".
    Requiring 2 excluded every fact stated by a single paper, which in a personal
    research vault is nearly all of them: measured on a real 37-source vault, 717
    of 722 relations were quarantined and only 5 were active, so communities never
    formed and L3/L4 reported `skipped`. That contradicted the product philosophy,
    where a Permanent Note is a SINGLE idea and the value is linking such notes
    across distinct sources.

    Only a count of 0 is now `unsupported`."""
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
        _add_support(conn, rel, "KNU-2", "lineage-X", "h2")  # same source lineage
        # The fixture deliberately has TWO support rows collapsing to ONE
        # lineage — the exact shape the old threshold rejected.
        distinct_lineages = conn.execute(
            "SELECT COUNT(DISTINCT source_lineage_hash) "
            "FROM graph_relation_supports WHERE relation_id = ? "
            "AND support_status = 'verified'",
            (rel,),
        ).fetchone()[0]
    assert distinct_lineages == 1, (
        "fixture must have exactly one independent source lineage (not zero); "
        f"got {distinct_lineages}"
    )
    status = compile_fn(vault, relation_id=rel)
    with db.connect(vault) as conn:
        reason = _reason(conn, rel)
    assert status == "active", (
        "one genuine source lineage is legitimate support: the lineage hash "
        "already collapses copies, so 1 means one real source, not a duplicate "
        f"faking corroboration; got {status!r}/{reason!r}"
    )
    assert reason == "", f"an active relation carries no quarantine reason; got {reason!r}"


def test_zero_verified_lineages_is_still_unsupported(vault: Path) -> None:
    """Lowering the threshold to 1 must not admit relations with NO verified
    support — 0 lineages remains `unsupported`."""
    src = _seed_entity(vault, "Method C")
    tgt = _seed_entity(vault, "Method D")
    rel = _relate(vault, src, tgt)
    status = db.compile_relation_lifecycle(vault, relation_id=rel)
    with db.connect(vault) as conn:
        reason = _reason(conn, rel)
    assert status == "quarantined"
    assert reason == "unsupported", (
        f"no verified support must stay quarantined as unsupported; got {reason!r}"
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
        # Two DISTINCT source lineages: comfortably above the >=1 threshold, and
        # the case where corroboration ADDS confidence to an already-active edge.
        distinct_lineages = conn.execute(
            "SELECT COUNT(DISTINCT source_lineage_hash) "
            "FROM graph_relation_supports WHERE relation_id = ? "
            "AND support_status = 'verified'",
            (rel,),
        ).fetchone()[0]
    assert distinct_lineages == 2, (
        f"fixture must supply 2 independent source lineages; got {distinct_lineages}"
    )
    status = compile_fn(vault, relation_id=rel)
    assert status == "active", (
        "an edge with independent source lineages of verified support and "
        f"canonical endpoints must become active; got {status!r}"
    )


# --------------------------------------------------------------------------- #
# Topology-level detection (§27.3)
# --------------------------------------------------------------------------- #


def test_noisy_bridge_single_edge_is_flagged_bridge_risk(vault: Path) -> None:
    """A dense 4-node cluster A (complete K4) and a dense triangle cluster B,
    joined by a SINGLE low-confidence edge. Only that structural bridge — the lone
    cut edge whose removal disconnects the two dense components — is flagged
    bridge_risk.

    Oracle-leakage guard: cluster A also contains a SECOND, equally
    low-confidence edge (a2→a4, confidence 0.25) placed entirely INSIDE the dense
    cluster. That edge is a redundant chord — a2 and a4 stay connected via a1 or
    a3 after its removal — so it is structurally NOT a bridge and MUST NOT be
    flagged. A naive implementation that merely filters ``confidence < 0.5`` would
    wrongly flag this intra-cluster edge too and fail; only genuine topological
    (cut-edge between dense components) detection passes. The bridge and the noisy
    chord share the same low confidence, so confidence cannot be the
    discriminator — only graph structure can."""
    detect = getattr(db, "detect_bridge_risk_relations", None)
    assert detect is not None, (
        "P4 must define db.detect_bridge_risk_relations (SYSTEM_BEHAVIOR §27.3)"
    )
    a1 = _seed_entity(vault, "A1")
    a2 = _seed_entity(vault, "A2")
    a3 = _seed_entity(vault, "A3")
    a4 = _seed_entity(vault, "A4")
    b1 = _seed_entity(vault, "B1")
    b2 = _seed_entity(vault, "B2")
    b3 = _seed_entity(vault, "B3")
    # Cluster A: a dense, 2-edge-connected block on {a1,a2,a3,a4}. Every strong
    # edge below lies on a cycle, so none of them is a cut edge.
    dense = [
        _relate(vault, a1, a2),
        _relate(vault, a2, a3),
        _relate(vault, a3, a1),
        _relate(vault, a3, a4),
        _relate(vault, a4, a1),
        # Cluster B: a dense triangle on {b1,b2,b3}.
        _relate(vault, b1, b2),
        _relate(vault, b2, b3),
        _relate(vault, b3, b1),
    ]
    # A low-confidence edge INSIDE dense cluster A. Removing it leaves a2 and a4
    # connected (a2-a1-a4 and a2-a3-a4 both remain), so it is NOT a cut edge
    # despite its low confidence. It must NOT be flagged — this is the
    # anti-oracle-leakage assertion.
    noisy_intra = db.upsert_graph_relation(
        vault,
        source_entity_id=a2,
        target_entity_id=a4,
        relation_type="rel",
        confidence=0.25,
    )
    # The ONE edge joining cluster A to cluster B: a genuine cut edge whose
    # removal splits the graph into the two dense components — a true bridge_risk.
    bridge = db.upsert_graph_relation(
        vault,
        source_entity_id=a1,
        target_entity_id=b1,
        relation_type="rel",
        confidence=0.25,
    )
    flagged = set(detect(vault))
    assert flagged == {bridge}, (
        "only the single low-confidence edge that is a structural cut edge between "
        "two dense components is bridge_risk; the equally low-confidence "
        f"intra-cluster chord {noisy_intra} is redundant (not a cut edge) and must "
        f"NOT be flagged, and none of the dense edges {dense} may be flagged; "
        f"got {flagged}"
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


# --------------------------------------------------------------------------- #
# Contradiction-rule exemption (review fix)
# --------------------------------------------------------------------------- #


def test_contradicts_relation_is_not_self_quarantined_by_contradiction(
    vault: Path,
) -> None:
    """A `contradicts` relation must NOT be quarantined by the contradiction rule
    it embodies. Two mutual `contradicts` edges (A->B and B->A) would otherwise
    quarantine each other; instead each is evaluated on its own support, so a
    `contradicts` edge with independent verified lineages goes active (§27.3)."""
    a = _seed_entity(vault, "Claim A")
    b = _seed_entity(vault, "Claim B")
    forward = _relate(vault, a, b, rtype="contradicts")
    _relate(vault, b, a, rtype="contradicts")  # mutual reverse contradiction
    with db.connect(vault) as conn:
        _add_support(conn, forward, "KNU-1", "lin-A", "h1")
        _add_support(conn, forward, "KNU-2", "lin-B", "h2")  # 2nd independent lineage
    status = db.compile_relation_lifecycle(vault, relation_id=forward)
    assert status == "active", (
        "a corroborated `contradicts` relation must not be quarantined by the "
        "contradiction rule (which exists to flag NON-contradiction edges)"
    )


def test_non_contradicts_edge_is_quarantined_when_contradiction_joins_endpoints(
    vault: Path,
) -> None:
    """The contradiction rule still fires for a NON-`contradicts` relation: the
    graph asserting both `A extends B` and `A contradicts B` is inconsistent, so
    the `extends` edge quarantines as `contradiction` even with full support, and
    BEFORE support promotion (§27.3 admissibility-before-support)."""
    a = _seed_entity(vault, "Method A")
    b = _seed_entity(vault, "Method B")
    extends = _relate(vault, a, b, rtype="extends")
    _relate(vault, a, b, rtype="contradicts")  # contradicts the same endpoints
    with db.connect(vault) as conn:
        _add_support(conn, extends, "KNU-1", "lin-A", "h1")
        _add_support(conn, extends, "KNU-2", "lin-B", "h2")  # would be active otherwise
    status = db.compile_relation_lifecycle(vault, relation_id=extends)
    with db.connect(vault) as conn:
        reason = _reason(conn, extends)
    assert (status, reason) == ("quarantined", "contradiction"), (
        "a non-contradicts edge whose endpoints also carry a contradicts edge must "
        "quarantine as contradiction, even with >=2 lineages of support"
    )


def test_relation_support_span_ids_are_deduped_in_hash(vault: Path) -> None:
    """upsert_graph_relation_support canonicalizes (dedup + sort) the cited spans,
    so a duplicated span id cannot vary support_hash by multiplicity — keeping the
    ON-CONFLICT idempotency intact (§21.5 aggregation)."""
    a = _seed_entity(vault, "A")
    b = _seed_entity(vault, "B")
    rel = _relate(vault, a, b)
    h_dup = db.upsert_graph_relation_support(
        vault, relation_id=rel, knowledge_unit_id="KNU-1",
        source_span_ids=["SPAN-1", "SPAN-1", "SPAN-2"], source_lineage_hash="lin",
    )
    h_clean = db.upsert_graph_relation_support(
        vault, relation_id=rel, knowledge_unit_id="KNU-1",
        source_span_ids=["SPAN-2", "SPAN-1"], source_lineage_hash="lin",
    )
    assert h_dup == h_clean, "duplicate/unordered spans must hash identically"
    with db.connect(vault) as conn:
        rows = conn.execute(
            "SELECT source_span_ids FROM graph_relation_supports WHERE relation_id = ?",
            (rel,),
        ).fetchall()
    assert len(rows) == 1, "the same canonical span set is one row (ON CONFLICT)"
    import json as _json
    assert _json.loads(rows[0][0]) == ["SPAN-1", "SPAN-2"], "spans stored deduped + sorted"
