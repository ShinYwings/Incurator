"""Plan C (v0.9.0) P2 — failing gold tests for graph-quality resolution/support.

These are TDD red tests written BEFORE the P3/P4 implementation. They pin the
frozen v9 contract (SCHEMA.md §21, SYSTEM_BEHAVIOR.md §27) and are EXPECTED to
fail until the additive migration, resolution lifecycle, and relation-support
aggregation land. They must fail for the intended reasons (v9 schema not built
yet) — not via import errors — so every forward reference to not-yet-existing
code is guarded and asserted with an intention-revealing message.

This first module covers the migration foundation plus the two schema flaws
corrected at the P1→P2 boundary:

  * Flaw 1 — `entity_aliases` uses a SURROGATE key so one normalized surface
    form can resolve to MANY distinct entities (homonyms). The old composite
    `(alias_normalized, alias_display, resolution_status)` key collapsed
    homonyms onto one row and silently overwrote the first resolution.
  * Flaw 2 — a relation is NEVER a "duplicate": re-asserting the same canonical
    proposition aggregates independent claim-level support onto the one
    relation, so `duplicate_proposition` is not a quarantine reason. An edge is
    either `unsupported` or valid with aggregated support.

Remaining P2 adversarial fixtures (synonyms, abbreviations, multilingual
aliases, type conflicts, avoid_merges/contradiction guards, self-loops, noisy
bridges, merge reversal, edit/delete reconciliation, and the frozen hierarchy
benchmark) are follow-on P2 modules tracked in RELAY.
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from curator import config as cfg
from curator import db

# Frozen v9 contract names (SCHEMA §21.8). The migration must INFER nothing.
V9_NEW_TABLES = (
    "entity_aliases",
    "entity_merge_proposals",
    "entity_resolution_lineage",
    "graph_relation_supports",
)
V9_RELATION_COLUMNS = (
    "lifecycle_status",
    "quarantine_reason",
    "edge_class",
    "topology_weight",
    "reeval_trigger",
    "generation_id",
)
V9_ENTITY_COLUMNS = ("resolution_state", "redirect_to_entity_id", "decision_id")
V9_COMMUNITY_COLUMNS = (
    "parent_community_key",
    "config_hash",
    "member_hash",
    "support_hash",
    "retired_at",
)

# Frozen quarantine reason codes (SCHEMA §21.6) — `duplicate_proposition` is
# DELIBERATELY absent (Flaw 2). The implementation must expose exactly these.
EXPECTED_QUARANTINE_REASONS = frozenset(
    {
        "unsupported",
        "self_loop",
        "contradiction",
        "copied_source_only",
        "bridge_risk",
        "endpoint_unresolved",
    }
)


@pytest.fixture()
def vault() -> Path:
    with tempfile.TemporaryDirectory() as t:
        paths = cfg.WikiPaths(Path(t))
        paths.internal.mkdir(parents=True, exist_ok=True)
        db.init_db(paths.state_db)
        yield paths.state_db


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {
        str(r[0])
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(r[1]) for r in conn.execute(f"PRAGMA table_info({table})")}


def _pk_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    # PRAGMA table_info columns: (cid, name, type, notnull, dflt_value, pk)
    rows = sorted(
        (r for r in conn.execute(f"PRAGMA table_info({table})") if r[5]),
        key=lambda r: r[5],
    )
    return [str(r[1]) for r in rows]


def _seed_entity(state_db: Path, name: str, etype: str = "concept") -> str:
    return db.upsert_graph_entity(
        state_db, canonical_name=name, entity_type=etype
    )


# --------------------------------------------------------------------------- #
# Group A — v9 migration foundation (SCHEMA §21.8 / SYSTEM_BEHAVIOR §27.7)
# --------------------------------------------------------------------------- #


def test_schema_version_includes_v9() -> None:
    assert db.SCHEMA_VERSION >= 9, "Plan C requires SCHEMA_VERSION >= 9"


def test_v9_creates_resolution_and_support_tables(vault: Path) -> None:
    with db.connect(vault) as conn:
        present = _tables(conn)
    missing = [t for t in V9_NEW_TABLES if t not in present]
    assert not missing, f"v9 must create resolution/support tables; missing: {missing}"


def test_v9_adds_lifecycle_resolution_and_community_columns(vault: Path) -> None:
    with db.connect(vault) as conn:
        rel_cols = _columns(conn, "graph_relations")
        ent_cols = _columns(conn, "graph_entities")
        com_cols = _columns(conn, "community_reports")
    assert set(V9_RELATION_COLUMNS) <= rel_cols, (
        f"graph_relations missing v9 columns: "
        f"{set(V9_RELATION_COLUMNS) - rel_cols}"
    )
    assert set(V9_ENTITY_COLUMNS) <= ent_cols, (
        f"graph_entities missing v9 columns: {set(V9_ENTITY_COLUMNS) - ent_cols}"
    )
    assert set(V9_COMMUNITY_COLUMNS) <= com_cols, (
        f"community_reports missing v9 columns: "
        f"{set(V9_COMMUNITY_COLUMNS) - com_cols}"
    )


def test_v9_backfill_infers_nothing(vault: Path) -> None:
    """Legacy entities -> canonical; legacy relations -> provisional/extracted,
    no generation; zero alias/support rows (SYSTEM_BEHAVIOR §27.7 item 2)."""
    src = _seed_entity(vault, "Gaussian Splatting")
    tgt = _seed_entity(vault, "Radiance Field")
    db.upsert_graph_relation(
        vault,
        source_entity_id=src,
        target_entity_id=tgt,
        relation_type="improves",
        confidence=0.9,
    )
    with db.connect(vault) as conn:
        assert "entity_aliases" in _tables(conn), "v9 schema not built yet"
        ent = conn.execute(
            "SELECT resolution_state, redirect_to_entity_id FROM graph_entities "
            "WHERE id = ?",
            (src,),
        ).fetchone()
        assert ent["resolution_state"] == "canonical"
        assert ent["redirect_to_entity_id"] is None
        rel = conn.execute(
            "SELECT lifecycle_status, edge_class, generation_id FROM graph_relations"
        ).fetchone()
        assert rel["lifecycle_status"] == "provisional"
        assert rel["edge_class"] == "extracted"
        assert rel["generation_id"] is None
        assert conn.execute("SELECT COUNT(*) FROM entity_aliases").fetchone()[0] == 0
        assert (
            conn.execute("SELECT COUNT(*) FROM graph_relation_supports").fetchone()[0]
            == 0
        )


# --------------------------------------------------------------------------- #
# Group B — Flaw 1: entity_aliases surrogate key / homonym support (§21.1)
# --------------------------------------------------------------------------- #


def test_entity_aliases_pk_is_surrogate_not_surface_composite(vault: Path) -> None:
    with db.connect(vault) as conn:
        assert "entity_aliases" in _tables(conn), "v9 entity_aliases must exist"
        pk = _pk_columns(conn, "entity_aliases")
    assert pk == ["id"], (
        "entity_aliases must use a single surrogate primary key `id` (ALI-), not "
        f"a surface-form composite; got PK columns {pk}"
    )


def test_homonym_one_surface_resolves_to_many_entities(vault: Path) -> None:
    """The core Flaw-1 regression: 'mercury' -> planet AND element coexist."""
    planet = _seed_entity(vault, "Mercury (planet)")
    element = _seed_entity(vault, "Mercury (element)")
    with db.connect(vault) as conn:
        assert "entity_aliases" in _tables(conn), "v9 entity_aliases must exist"
        for ali_id, ent in (("ALI-h1", planet), ("ALI-h2", element)):
            conn.execute(
                "INSERT INTO entity_aliases "
                "(id, alias_normalized, entity_id, alias_display, "
                " resolution_status, resolution_reason, created_at, updated_at) "
                "VALUES (?, 'mercury', ?, 'Mercury', 'alias', 'gold', 't', 't')",
                (ali_id, ent),
            )
        rows = conn.execute(
            "SELECT entity_id FROM entity_aliases WHERE alias_normalized = 'mercury'"
        ).fetchall()
    resolved = {str(r[0]) for r in rows}
    assert resolved == {planet, element}, (
        "one normalized surface form must resolve to both distinct entities "
        f"(homonym); got {resolved}"
    )


def test_exact_duplicate_resolved_alias_is_rejected(vault: Path) -> None:
    planet = _seed_entity(vault, "Mercury (planet)")
    with db.connect(vault) as conn:
        assert "entity_aliases" in _tables(conn), "v9 entity_aliases must exist"
        conn.execute(
            "INSERT INTO entity_aliases "
            "(id, alias_normalized, entity_id, alias_display, "
            " resolution_status, resolution_reason, created_at, updated_at) "
            "VALUES ('ALI-d1', 'mercury', ?, 'Mercury', 'alias', 'g', 't', 't')",
            (planet,),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO entity_aliases "
                "(id, alias_normalized, entity_id, alias_display, "
                " resolution_status, resolution_reason, created_at, updated_at) "
                "VALUES ('ALI-d2', 'mercury', ?, 'Mercury', 'alias', 'g', 't', 't')",
                (planet,),
            )


# --------------------------------------------------------------------------- #
# Group C — Flaw 2: relation support aggregation, never "duplicate" (§21.5/§21.6)
# --------------------------------------------------------------------------- #


def test_relation_support_independence_is_by_lineage_not_row_count(
    vault: Path,
) -> None:
    """3 verified supports, 2 sharing one source lineage -> independent count 2;
    all 3 rows persist (aggregation, never overwrite). SCHEMA §21.5."""
    src = _seed_entity(vault, "Method A")
    tgt = _seed_entity(vault, "Method B")
    rel = db.upsert_graph_relation(
        vault,
        source_entity_id=src,
        target_entity_id=tgt,
        relation_type="extends",
        confidence=0.9,
    )
    with db.connect(vault) as conn:
        assert "graph_relation_supports" in _tables(conn), "v9 supports table must exist"
        supports = [
            ("KNU-1", "lin-A", "h1"),
            ("KNU-2", "lin-A", "h2"),  # copied source: shares lineage with KNU-1
            ("KNU-3", "lin-B", "h3"),
        ]
        for knu, lineage, shash in supports:
            conn.execute(
                "INSERT INTO graph_relation_supports "
                "(relation_id, knowledge_unit_id, source_span_ids, assertion_source, "
                " confidence, support_status, support_hash, source_lineage_hash, "
                " created_at, updated_at) "
                "VALUES (?, ?, '[]', 'source_states', 0.9, 'verified', ?, ?, 't', 't')",
                (rel, knu, shash, lineage),
            )
        total = conn.execute(
            "SELECT COUNT(*) FROM graph_relation_supports WHERE relation_id = ?",
            (rel,),
        ).fetchone()[0]
        independent = conn.execute(
            "SELECT COUNT(DISTINCT source_lineage_hash) FROM graph_relation_supports "
            "WHERE relation_id = ? AND support_status = 'verified'",
            (rel,),
        ).fetchone()[0]
    assert total == 3, "re-assertion aggregates supports; nothing is overwritten"
    assert independent == 2, "copied-source rows count once (independence by lineage)"


def test_relation_reassertion_preserves_existing_lifecycle_metadata(
    vault: Path,
) -> None:
    src = _seed_entity(vault, "Stable Method A")
    tgt = _seed_entity(vault, "Stable Method B")
    relation_id = db.upsert_graph_relation(
        vault,
        source_entity_id=src,
        target_entity_id=tgt,
        relation_type="extends",
        confidence=0.8,
        lifecycle_status="active",
        topology_weight=0.75,
    )

    assert db.upsert_graph_relation(
        vault,
        source_entity_id=src,
        target_entity_id=tgt,
        relation_type="extends",
        confidence=0.9,
    ) == relation_id

    with db.connect(vault) as conn:
        row = conn.execute(
            "SELECT lifecycle_status, edge_class, topology_weight "
            "FROM graph_relations WHERE id = ?",
            (relation_id,),
        ).fetchone()
    assert tuple(row) == ("active", "extracted", 0.75)


def test_duplicate_proposition_is_not_a_quarantine_reason() -> None:
    """Flaw 2: relations are never 'duplicates'. The implementation must expose
    the frozen reason set and it must NOT contain `duplicate_proposition`.

    P4 defines `db.QUARANTINE_REASON_CODES`; until then this fails cleanly with
    an intention-revealing message rather than an ImportError.
    """
    codes = getattr(db, "QUARANTINE_REASON_CODES", None)
    assert codes is not None, (
        "P4 must define db.QUARANTINE_REASON_CODES (frozen SCHEMA §21.6 set)"
    )
    code_set = set(codes)
    assert "duplicate_proposition" not in code_set, (
        "a relation is never a duplicate; re-assertion aggregates support "
        "(SCHEMA §21.5/§21.6) — `duplicate_proposition` must not be a reason code"
    )
    assert code_set == set(EXPECTED_QUARANTINE_REASONS), (
        f"frozen quarantine reasons mismatch: got {code_set}, "
        f"expected {set(EXPECTED_QUARANTINE_REASONS)}"
    )
