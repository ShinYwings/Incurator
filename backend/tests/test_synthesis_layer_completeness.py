"""A truncated L4 layer must never be accepted as complete (B3 P5 / CP-2a).

`generate_synthesis` regenerates wholesale: clear the layer, then write N nodes each
stamped with the current dependency hash. A crash between the clear and the last
write leaves a truncated but self-consistent-looking layer — and the idempotency
guard then sees every surviving node carrying the current hash and returns them
as complete. Every later `wiki build` does the same, so the vault serves a
partial synthesis until the corpus changes enough to move the hash. Nothing
reports it.

The stored hash therefore has to carry the layer's cardinality, not just its
inputs: a hash that matches the corpus but not the node count means the write
was interrupted. Legacy rows carry a bare hash with no cardinality, which reads
as "unknown" and forces exactly one regeneration — that is how an
already-frozen vault repairs itself.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from curator import db
from curator.pipeline import synthesis as syn

DEP = "dep-abc123"


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "state.sqlite"
    db.init_db(p)
    return p


def _write(db_path: Path, count: int, stored_hash: str) -> None:
    for i in range(count):
        db.upsert_synthesis_node(
            db_path,
            title=f"T{i}",
            statement=f"S{i}",
            dependency_hash=stored_hash,
            community_report_ids=["CR-1"],
            concept_ids=["CON-1"],
            source_span_ids=["SPAN-1"],
            confidence=0.9,
        )


def test_a_complete_layer_is_reused(db_path: Path) -> None:
    _write(db_path, 6, syn.layer_dependency_hash(DEP, 6))
    nodes = db.list_synthesis_nodes(db_path)
    assert syn.layer_is_current(nodes, DEP) is True


def test_a_truncated_layer_is_not_reused(db_path: Path) -> None:
    """The reported defect: 3 of an intended 6 survived a crash."""
    _write(db_path, 3, syn.layer_dependency_hash(DEP, 6))
    nodes = db.list_synthesis_nodes(db_path)
    assert syn.layer_is_current(nodes, DEP) is False, (
        "a truncated layer was accepted as complete; every later build would "
        "return it and never regenerate the missing nodes"
    )


def test_a_legacy_layer_regenerates_once(db_path: Path) -> None:
    """An already-frozen vault must repair itself.

    Rows written before this change carry a bare corpus hash with no
    cardinality. That reads as unknown, not as current.
    """
    _write(db_path, 3, DEP)
    nodes = db.list_synthesis_nodes(db_path)
    assert syn.layer_is_current(nodes, DEP) is False


def test_a_stale_corpus_hash_still_regenerates(db_path: Path) -> None:
    _write(db_path, 6, syn.layer_dependency_hash("dep-old", 6))
    nodes = db.list_synthesis_nodes(db_path)
    assert syn.layer_is_current(nodes, DEP) is False


def test_an_empty_layer_is_not_current(db_path: Path) -> None:
    assert syn.layer_is_current([], DEP) is False


def test_a_mixed_layer_is_not_current(db_path: Path) -> None:
    """Nodes disagreeing among themselves cannot be a complete layer."""
    _write(db_path, 2, syn.layer_dependency_hash(DEP, 3))
    _write(db_path, 1, syn.layer_dependency_hash("dep-other", 3))
    nodes = db.list_synthesis_nodes(db_path)
    assert syn.layer_is_current(nodes, DEP) is False


def test_the_audit_compares_only_the_corpus_hash_for_a_synthesis_node(
    db_path: Path,
) -> None:
    """An edge records the corpus hash; the node records hash + cardinality.

    Comparing them whole would report every such dependency stale forever,
    drowning the real ones. Nothing writes a `synthesis_node` edge today, but
    the comparison must not be a trap for whoever does.
    """
    from curator.inspection import synthesis_audit

    _write(db_path, 6, syn.layer_dependency_hash(DEP, 6))
    node_id = db.list_synthesis_nodes(db_path)[0]["id"]

    current = synthesis_audit._current_dependency_hash(
        db_path, "synthesis_node", node_id
    )
    assert current == DEP, (
        f"the audit sees {current!r}; an edge stores {DEP!r}, so every such "
        f"dependency would read as stale forever"
    )
