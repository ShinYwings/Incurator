"""Phase 5 (v0.3.1): memory-path associative walks and scoring."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from curator import db
from curator.pipeline import memory_paths as mp


@pytest.fixture()
def graph_db():
    with tempfile.TemporaryDirectory() as t:
        path = Path(t) / "state.sqlite"
        db.init_db(path)
        a = db.upsert_graph_entity(path, canonical_name="residual learning", entity_type="concept",
                                   source_span_ids=["SPAN-1"])
        b = db.upsert_graph_entity(path, canonical_name="Euler discretization", entity_type="concept",
                                   source_span_ids=["SPAN-2"])
        c = db.upsert_graph_entity(path, canonical_name="Neural ODE", entity_type="method")
        db.upsert_graph_relation(path, source_entity_id=a, target_entity_id=c,
                                 relation_type="reinterpreted_as", confidence=0.8,
                                 source_span_ids=["SPAN-1"], assertion_source="system_infers",
                                 lifecycle_status="active")
        db.upsert_graph_relation(path, source_entity_id=c, target_entity_id=b,
                                 relation_type="discretizes", confidence=0.7,
                                 source_span_ids=["SPAN-2"], assertion_source="system_infers",
                                 lifecycle_status="active")
        yield path, {"a": a, "b": b, "c": c}


def test_build_paths_connects_residual_to_euler(graph_db) -> None:
    path, ids = graph_db
    paths = mp.build_memory_paths(path, seed_entity_ids=[ids["a"]], max_depth=2)
    assert paths
    # There is a 2-hop path residual learning -> Neural ODE -> Euler.
    reached = {hop["to"] for p in paths for hop in p.hops}
    assert ids["c"] in reached
    assert ids["b"] in reached
    # Paths are scored and sorted descending.
    scores = [p.score for p in paths]
    assert scores == sorted(scores, reverse=True)
    assert all(p.score > 0 for p in paths)


def test_span_support_increases_score(graph_db) -> None:
    path, ids = graph_db
    paths = mp.build_memory_paths(path, seed_entity_ids=[ids["a"]], max_depth=1)
    one_hop = paths[0]
    assert one_hop.source_span_ids  # walk collected the relation's spans
    assert one_hop.hops[0]["relation_type"] == "reinterpreted_as"


def test_record_memory_paths_persists(graph_db) -> None:
    path, ids = graph_db
    qh = mp.query_hash("dynamics interpretation of residual learning")
    paths = mp.build_memory_paths(path, seed_entity_ids=[ids["a"]], max_depth=2)
    pids = mp.record_memory_paths(path, paths, q_hash=qh, route="explore")
    assert pids and all(p.startswith("MPATH-") for p in pids)
    stored = db.list_memory_paths(path, qh)
    assert len(stored) == len(paths)
    # Highest score first.
    assert stored[0]["score"] >= stored[-1]["score"]
    assert stored[0]["path"]  # hops decoded


def test_domain_terms_influence_score(graph_db) -> None:
    path, ids = graph_db
    plain = mp.build_memory_paths(path, seed_entity_ids=[ids["a"]], max_depth=1)
    boosted = mp.build_memory_paths(
        path, seed_entity_ids=[ids["a"]], max_depth=1, domain_terms=["Neural ODE"]
    )
    assert boosted[0].score >= plain[0].score
