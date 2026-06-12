"""Failure Atlas evaluation baseline runner (Plan D phase P4).

Validates the frozen fixture corpus + qrels structure, then measures the
deterministic lexical retrieval baseline (Recall@1/3/5, MRR@5, hard-negative
outranks) per query family and partition. Measured values are recorded in
docs/specs/failure_atlas/EVALUATION_BASELINE.md; the assertions here pin the
CURRENT baseline so any retrieval regression (or silent improvement without an
atlas update) fails CI.

No-tuning discipline: the holdout partition is structurally validated but
NEVER measured here (FAILURE_ATLAS.md / qrels.yml). Provider-dependent modes
(vector, rerank) are out of scope for the deterministic baseline and are
scheduled for Plan E / D2.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml

from curator import db
from curator.retrieval.embedding import materialize_chunks
from curator.retrieval.engine import HybridEngine

REPO_ROOT = Path(__file__).resolve().parents[2]
ATLAS_DIR = REPO_ROOT / "docs" / "specs" / "failure_atlas"

PARTITIONS = {"dev", "regression", "holdout", "adversarial"}
FAMILIES = {
    "direct-factual", "associative", "global", "source-scoped",
    "cross-route", "compiler", "client-parity", "evaluation-infra",
}
MEASURED_PARTITIONS = ("dev", "regression", "adversarial")


def _load_yaml(name: str) -> dict:
    return yaml.safe_load((ATLAS_DIR / name).read_text(encoding="utf-8"))


CORPUS = _load_yaml("fixture_corpus.yml")
QRELS = _load_yaml("qrels.yml")
DOC_IDS = {d["record_id"] for d in CORPUS["documents"]}


# ---------------------------------------------------------------------------
# Structural validation (ground-truth label integrity)
# ---------------------------------------------------------------------------

def test_corpus_documents_are_well_formed() -> None:
    assert CORPUS["version"] >= 1
    assert len(DOC_IDS) == len(CORPUS["documents"]), "duplicate record ids"
    for doc in CORPUS["documents"]:
        assert doc["record_type"] == "knowledge_unit"
        assert doc["title"].strip() and doc["body"].strip()
        assert doc["source_span_ids"], "every document must declare span provenance"


def test_qrels_are_well_formed_and_resolve() -> None:
    seen: set[str] = set()
    for q in QRELS["queries"]:
        assert q["id"] not in seen, f"duplicate query id {q['id']}"
        seen.add(q["id"])
        assert q["family"] in FAMILIES
        assert q["partition"] in PARTITIONS
        assert q["text"].strip()
        assert q["expected"], f"{q['id']}: empty expected set"
        for rid in q["expected"] + q.get("hard_negatives", []):
            assert rid in DOC_IDS, f"{q['id']}: unknown record id {rid}"
        assert not (set(q["expected"]) & set(q.get("hard_negatives", []))), (
            f"{q['id']}: expected and hard negatives overlap"
        )
        if q["partition"] == "holdout":
            assert q.get("frozen") is True, "holdout queries must be marked frozen"


def test_every_measured_partition_has_coverage() -> None:
    by_partition: dict[str, int] = {}
    for q in QRELS["queries"]:
        by_partition[q["partition"]] = by_partition.get(q["partition"], 0) + 1
    for partition in PARTITIONS:
        assert by_partition.get(partition, 0) >= 1, f"no queries in {partition}"


# ---------------------------------------------------------------------------
# Deterministic lexical baseline measurement
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def measured() -> dict[str, dict]:
    """Run every non-holdout query against the frozen corpus; return per-query
    metrics keyed by query id."""
    with tempfile.TemporaryDirectory() as t:
        db_path = Path(t) / "state.sqlite"
        db.init_db(db_path)
        for doc in CORPUS["documents"]:
            db.upsert_search_document(
                db_path, record_type=doc["record_type"],
                record_id=doc["record_id"], title=doc["title"],
                body=doc["body"], content_hash=doc["record_id"],
                dependency_hash=doc["record_id"],
                provenance={"source_span_ids": doc["source_span_ids"]},
            )
        materialize_chunks(db_path)
        engine = HybridEngine(db_path, embedder=None)

        out: dict[str, dict] = {}
        for q in QRELS["queries"]:
            if q["partition"] == "holdout":
                continue  # frozen — never measured during development
            result = engine.search(
                q["text"], mode="hybrid", limit=5, rerank=False, persist=False
            )
            ranked = [h.record_id for h in result.hits]
            expected = set(q["expected"])
            first_hit_rank = next(
                (i + 1 for i, rid in enumerate(ranked) if rid in expected), None
            )
            out[q["id"]] = {
                "family": q["family"],
                "partition": q["partition"],
                "ranked": ranked,
                "recall_at": {
                    k: len(expected & set(ranked[:k])) / len(expected)
                    for k in (1, 3, 5)
                },
                "mrr": (1.0 / first_hit_rank) if first_hit_rank else 0.0,
                "hard_negative_outranks": sum(
                    1
                    for neg in q.get("hard_negatives", [])
                    if neg in ranked
                    and first_hit_rank is not None
                    and ranked.index(neg) + 1 < first_hit_rank
                ),
            }
        return out


def _family_partition(measured: dict, family: str, partition: str) -> list[dict]:
    return [
        m for m in measured.values()
        if m["family"] == family and m["partition"] == partition
    ]


def test_baseline_direct_factual_dev(measured: dict) -> None:
    rows = _family_partition(measured, "direct-factual", "dev")
    assert len(rows) == 3
    # Measured baseline (2026-06-12, lexical-only): perfect on the dev set.
    assert all(m["recall_at"][1] == 1.0 for m in rows)
    assert all(m["mrr"] == 1.0 for m in rows)


def test_baseline_direct_factual_regression(measured: dict) -> None:
    rows = _family_partition(measured, "direct-factual", "regression")
    assert len(rows) == 2
    # Binding regression floor: Recall@1 == 1.0 on the frozen partition.
    assert all(m["recall_at"][1] == 1.0 for m in rows)


def test_baseline_adversarial_hard_negatives(measured: dict) -> None:
    rows = _family_partition(measured, "direct-factual", "adversarial")
    assert len(rows) == 2
    # Measured baseline: the expected document is found in top-5 and no hard
    # negative outranks it on this corpus.
    assert all(m["recall_at"][5] == 1.0 for m in rows)
    assert sum(m["hard_negative_outranks"] for m in rows) == 0


def test_baseline_associative_dev(measured: dict) -> None:
    rows = _family_partition(measured, "associative", "dev")
    assert len(rows) == 1
    # Measured baseline: both endpoints of the associative pair retrievable
    # lexically when the query names both concepts.
    assert rows[0]["recall_at"][5] == 1.0


def test_holdout_never_measured(measured: dict) -> None:
    holdout_ids = {q["id"] for q in QRELS["queries"] if q["partition"] == "holdout"}
    assert holdout_ids, "holdout partition must exist"
    assert not (holdout_ids & set(measured)), "holdout was measured — no-tuning violation"
