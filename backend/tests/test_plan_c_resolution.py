"""Plan C (v0.9.0) P2 — failing gold tests for ENTITY RESOLUTION adversarial fixtures.

TDD red tests written BEFORE the P3 resolution implementation. They pin the frozen
v9 resolution contract (SCHEMA §21.1–§21.4, SYSTEM_BEHAVIOR §27.1) and MUST fail
for the intended reason — the v9 resolution schema/lifecycle is not built yet —
never via ``ImportError``. Every forward reference to a not-yet-existing table or
``db`` API is guarded and asserted with an intention-revealing message.

Adversarial fixtures covered (plan P2 list):
  * synonyms — many surface forms resolve to ONE entity;
  * multilingual aliases — cross-script surface forms resolve to ONE entity;
  * abbreviation homonym-risk — a multi-expansion abbreviation stays
    ``ambiguous_candidate`` and never auto-resolves;
  * type-conflict guard — an entity-type mismatch blocks the merge;
  * ``avoid_merges`` guard — a workspace-forbidden pair is hard-rejected;
  * contradiction guard — a contradicting edge blocks the merge;
  * ambiguous-alias non-resolution — low context overlap stays ambiguous;
  * accepted-merge proposal -> accept -> reversal lineage (§27.1 acceptance test).

P3 API hooks these tests pin (documented in RELAY for the implementer):
  ``db.RESOLUTION_STATUS_CODES``, ``db.MERGE_DECISION_CODES``,
  ``db.evaluate_merge_guards`` (returns the four §27.1 guard booleans
  ``type_match``/``context_overlap``/``no_contradiction``/``not_avoid_listed``
  plus a ``verdict`` in ``{accept, ambiguous_candidate, rejected}``),
  ``db.propose_entity_merge``, ``db.accept_entity_merge``,
  ``db.reverse_entity_merge``.
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from curator import config as cfg
from curator import db

EXPECTED_RESOLUTION_STATUS = frozenset(
    {
        "alias",
        "ambiguous_candidate",
        "merge_proposed",
        "accepted",
        "rejected",
        "reversed",
    }
)
EXPECTED_MERGE_DECISIONS = frozenset(
    {"proposed", "accepted", "rejected", "reversed"}
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


def _seed_entity(state_db: Path, name: str, etype: str = "concept") -> str:
    return db.upsert_graph_entity(state_db, canonical_name=name, entity_type=etype)


def _insert_alias(
    conn: sqlite3.Connection,
    ali_id: str,
    normalized: str,
    entity_id: str,
    display: str,
    status: str,
) -> None:
    conn.execute(
        "INSERT INTO entity_aliases "
        "(id, alias_normalized, entity_id, alias_display, resolution_status, "
        " resolution_reason, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, 'gold', 't', 't')",
        (ali_id, normalized, entity_id, display, status),
    )


# --------------------------------------------------------------------------- #
# Frozen resolution enums (SCHEMA §21.1 / §21.2)
# --------------------------------------------------------------------------- #


def test_resolution_status_codes_are_frozen_enum() -> None:
    codes = getattr(db, "RESOLUTION_STATUS_CODES", None)
    assert codes is not None, (
        "P3 must define db.RESOLUTION_STATUS_CODES (frozen SCHEMA §21.1 enum)"
    )
    assert set(codes) == set(EXPECTED_RESOLUTION_STATUS), (
        f"frozen §21.1 resolution_status enum mismatch: got {set(codes)}, "
        f"expected {set(EXPECTED_RESOLUTION_STATUS)}"
    )


def test_merge_decision_codes_are_frozen_enum() -> None:
    codes = getattr(db, "MERGE_DECISION_CODES", None)
    assert codes is not None, (
        "P3 must define db.MERGE_DECISION_CODES (frozen SCHEMA §21.2 enum)"
    )
    assert set(codes) == set(EXPECTED_MERGE_DECISIONS), (
        f"frozen §21.2 merge decision enum mismatch: got {set(codes)}, "
        f"expected {set(EXPECTED_MERGE_DECISIONS)}"
    )


# --------------------------------------------------------------------------- #
# Synonyms / multilingual aliases — many surface forms -> ONE entity (§21.1)
# --------------------------------------------------------------------------- #


def test_synonym_many_surface_forms_resolve_to_one_entity(vault: Path) -> None:
    """Inverse of the homonym case: distinct surface forms collapse onto a single
    entity. The surrogate key leaves `entity_id` non-unique, so one entity holds
    many alias rows."""
    ent = _seed_entity(vault, "Automobile")
    with db.connect(vault) as conn:
        assert "entity_aliases" in _tables(conn), "v9 entity_aliases must exist"
        for ali_id, normalized, display in (
            ("ALI-s1", "automobile", "Automobile"),
            ("ALI-s2", "motorcar", "Motorcar"),
            ("ALI-s3", "auto", "Auto"),
        ):
            _insert_alias(conn, ali_id, normalized, ent, display, "alias")
        forms = {
            str(r[0])
            for r in conn.execute(
                "SELECT alias_normalized FROM entity_aliases "
                "WHERE entity_id = ? AND resolution_status = 'alias'",
                (ent,),
            )
        }
    assert forms == {"automobile", "motorcar", "auto"}, (
        f"one entity must hold many distinct synonym surface forms; got {forms}"
    )


def test_multilingual_aliases_resolve_to_one_entity(vault: Path) -> None:
    """Cross-script surface forms ('Gaussian Splatting' / '가우시안 스플래팅' /
    'ガウシアンスプラッティング') are all aliases of the one method entity."""
    ent = _seed_entity(vault, "Gaussian Splatting")
    with db.connect(vault) as conn:
        assert "entity_aliases" in _tables(conn), "v9 entity_aliases must exist"
        for ali_id, normalized, display in (
            ("ALI-m1", "gaussian splatting", "Gaussian Splatting"),
            ("ALI-m2", "가우시안 스플래팅", "가우시안 스플래팅"),
            ("ALI-m3", "ガウシアンスプラッティング", "ガウシアンスプラッティング"),
        ):
            _insert_alias(conn, ali_id, normalized, ent, display, "alias")
        count = conn.execute(
            "SELECT COUNT(*) FROM entity_aliases "
            "WHERE entity_id = ? AND resolution_status = 'alias'",
            (ent,),
        ).fetchone()[0]
    assert count == 3, (
        "all three multilingual surface forms must coexist as aliases of the one "
        f"entity; got {count}"
    )


def test_abbreviation_homonym_risk_stays_ambiguous(vault: Path) -> None:
    """A multi-expansion abbreviation ('GS' -> Gaussian Splatting AND Graph
    Search) is NEVER auto-resolved: both candidates coexist as
    `ambiguous_candidate` and zero rows are `alias`/`accepted` (§27.1)."""
    splatting = _seed_entity(vault, "Gaussian Splatting", etype="method")
    search = _seed_entity(vault, "Graph Search", etype="method")
    with db.connect(vault) as conn:
        assert "entity_aliases" in _tables(conn), "v9 entity_aliases must exist"
        for ali_id, ent in (("ALI-gs1", splatting), ("ALI-gs2", search)):
            _insert_alias(conn, ali_id, "gs", ent, "GS", "ambiguous_candidate")
        resolved = conn.execute(
            "SELECT COUNT(*) FROM entity_aliases WHERE alias_normalized = 'gs' "
            "AND resolution_status IN ('alias', 'accepted')"
        ).fetchone()[0]
        ambiguous = conn.execute(
            "SELECT COUNT(DISTINCT entity_id) FROM entity_aliases "
            "WHERE alias_normalized = 'gs' "
            "AND resolution_status = 'ambiguous_candidate'"
        ).fetchone()[0]
    assert resolved == 0, "a multi-expansion abbreviation must never auto-resolve"
    assert ambiguous == 2, (
        f"both candidate expansions must coexist unresolved; got {ambiguous}"
    )


# --------------------------------------------------------------------------- #
# Merge guards (§27.1) — exact match alone never accepts; every guard must pass
# --------------------------------------------------------------------------- #


def test_type_conflict_guard_blocks_merge(vault: Path) -> None:
    guards = getattr(db, "evaluate_merge_guards", None)
    assert guards is not None, (
        "P3 must define db.evaluate_merge_guards (SYSTEM_BEHAVIOR §27.1 guards)"
    )
    model = _seed_entity(vault, "SAM", etype="method")
    person = _seed_entity(vault, "Sam (researcher)", etype="person")
    verdict = guards(vault, source_entity_id=model, target_entity_id=person)
    assert verdict["type_match"] is False, "method vs person is a type mismatch"
    assert verdict["verdict"] != "accept", (
        "an entity-type mismatch must block the merge (§27.1 type guard)"
    )


def test_avoid_merges_guard_rejects_listed_pair(vault: Path) -> None:
    guards = getattr(db, "evaluate_merge_guards", None)
    assert guards is not None, (
        "P3 must define db.evaluate_merge_guards (SYSTEM_BEHAVIOR §27.1 guards)"
    )
    a = _seed_entity(vault, "Transformer (model)")
    b = _seed_entity(vault, "Transformer (electrical)")
    verdict = guards(
        vault,
        source_entity_id=a,
        target_entity_id=b,
        avoid_merges=[(a, b)],
    )
    assert verdict["not_avoid_listed"] is False, "pair is on the avoid_merges list"
    assert verdict["verdict"] == "rejected", (
        "a workspace avoid_merges pair is durable negative knowledge — it must be "
        "hard-rejected, never accepted or merely deferred (§27.1)"
    )


def test_contradiction_guard_blocks_merge(vault: Path) -> None:
    guards = getattr(db, "evaluate_merge_guards", None)
    assert guards is not None, (
        "P3 must define db.evaluate_merge_guards (SYSTEM_BEHAVIOR §27.1 guards)"
    )
    a = _seed_entity(vault, "Method A")
    b = _seed_entity(vault, "Method B")
    db.upsert_graph_relation(
        vault,
        source_entity_id=a,
        target_entity_id=b,
        relation_type="contradicts",
        confidence=0.9,
    )
    verdict = guards(vault, source_entity_id=a, target_entity_id=b)
    assert verdict["no_contradiction"] is False, (
        "a contradicting edge between the pair is a contradiction signal"
    )
    assert verdict["verdict"] != "accept", (
        "a contradicting claim must block the merge (§27.1 contradiction guard)"
    )


def test_ambiguous_alias_with_low_context_overlap_stays_unresolved(
    vault: Path,
) -> None:
    """Same-type entities with no shared spans/claims/neighbourhood have context
    overlap below threshold, so similarity may only PROPOSE — the verdict is
    `ambiguous_candidate`, never `accept` (§27.1, Arena decision 3)."""
    guards = getattr(db, "evaluate_merge_guards", None)
    assert guards is not None, (
        "P3 must define db.evaluate_merge_guards (SYSTEM_BEHAVIOR §27.1 guards)"
    )
    a = _seed_entity(vault, "Mercury (planet)")
    b = _seed_entity(vault, "Mercury (element)")
    verdict = guards(vault, source_entity_id=a, target_entity_id=b)
    assert verdict["context_overlap"] is False, "no shared context between the two"
    assert verdict["verdict"] == "ambiguous_candidate", (
        "similarity is candidate generation only; with no context overlap the "
        "candidate stays ambiguous and never auto-fuses (§27.1)"
    )


# --------------------------------------------------------------------------- #
# Accepted-merge proposal -> accept -> reversal lineage (§27.1 acceptance test)
# --------------------------------------------------------------------------- #


def test_accepted_merge_redirects_origin_and_writes_lineage(vault: Path) -> None:
    propose = getattr(db, "propose_entity_merge", None)
    accept = getattr(db, "accept_entity_merge", None)
    assert propose is not None and accept is not None, (
        "P3 must define db.propose_entity_merge / db.accept_entity_merge (§27.1)"
    )
    survivor = _seed_entity(vault, "Gaussian Splatting")
    origin = _seed_entity(vault, "3D Gaussian Splatting")
    other = _seed_entity(vault, "Radiance Field")
    db.upsert_graph_relation(
        vault,
        source_entity_id=origin,
        target_entity_id=other,
        relation_type="improves",
        confidence=0.9,
    )
    decision = propose(
        vault,
        source_entity_id=origin,
        target_entity_id=survivor,
        rationale="same method, different surface form",
        evidence={"type_match": True, "context_overlap": True},
    )
    accept(vault, decision_id=decision)
    with db.connect(vault) as conn:
        origin_row = conn.execute(
            "SELECT resolution_state, redirect_to_entity_id, decision_id "
            "FROM graph_entities WHERE id = ?",
            (origin,),
        ).fetchone()
        lineage = conn.execute(
            "SELECT rewrite_json FROM entity_resolution_lineage "
            "WHERE decision_id = ? AND origin_entity_id = ?",
            (decision, origin),
        ).fetchone()
    assert origin_row["resolution_state"] == "redirected", (
        "an accepted merge redirects the origin; it never deletes it (§27.1)"
    )
    assert origin_row["redirect_to_entity_id"] == survivor
    assert origin_row["decision_id"] == decision
    assert lineage is not None and lineage["rewrite_json"], (
        "an accepted merge must persist reversible rewrite lineage (§21.3)"
    )


def test_merge_reversal_restores_origin_and_provenance(vault: Path) -> None:
    propose = getattr(db, "propose_entity_merge", None)
    accept = getattr(db, "accept_entity_merge", None)
    reverse = getattr(db, "reverse_entity_merge", None)
    assert all(fn is not None for fn in (propose, accept, reverse)), (
        "P3 must define propose/accept/reverse_entity_merge (§27.1 reversal)"
    )
    survivor = _seed_entity(vault, "Gaussian Splatting")
    origin = _seed_entity(vault, "3DGS")
    other = _seed_entity(vault, "NeRF")
    rel = db.upsert_graph_relation(
        vault,
        source_entity_id=origin,
        target_entity_id=other,
        relation_type="compared_with",
        confidence=0.8,
    )
    with db.connect(vault) as conn:
        before = conn.execute(
            "SELECT source_entity_id, target_entity_id "
            "FROM graph_relations WHERE id = ?",
            (rel,),
        ).fetchone()
        before_pair = (before["source_entity_id"], before["target_entity_id"])
    decision = propose(
        vault,
        source_entity_id=origin,
        target_entity_id=survivor,
        rationale="abbreviation of the same method",
        evidence={"type_match": True, "context_overlap": True},
    )
    accept(vault, decision_id=decision)
    reverse(vault, decision_id=decision)
    with db.connect(vault) as conn:
        origin_state = conn.execute(
            "SELECT resolution_state FROM graph_entities WHERE id = ?",
            (origin,),
        ).fetchone()[0]
        after = conn.execute(
            "SELECT source_entity_id, target_entity_id "
            "FROM graph_relations WHERE id = ?",
            (rel,),
        ).fetchone()
        decision_state = conn.execute(
            "SELECT decision FROM entity_merge_proposals WHERE id = ?",
            (decision,),
        ).fetchone()[0]
    assert origin_state == "canonical", "reversal restores the origin to canonical"
    assert (after["source_entity_id"], after["target_entity_id"]) == before_pair, (
        "reversal must restore relation endpoints byte-identical to the pre-merge "
        "state (§27.1 acceptance test)"
    )
    assert decision_state == "reversed", (
        "the reversed decision row is retained for audit, never hard-deleted"
    )
