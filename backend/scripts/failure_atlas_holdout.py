"""Consume the frozen Failure Atlas holdout exactly once for Plan D2."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
import time
from pathlib import Path

import yaml

from curator import __version__
from curator import db
from curator.retrieval.embedding import materialize_chunks
from curator.retrieval.engine import HybridEngine
from curator.retrieval.evaluation import evaluate_rankings

REPO_ROOT = Path(__file__).resolve().parents[2]
ATLAS_DIR = REPO_ROOT / "docs" / "specs" / "failure_atlas"
OUTPUT = ATLAS_DIR / "D2_HOLDOUT_RESULT.yml"
APPROVED_HASHES = {
    "fixture_corpus.yml": "35301871bdd1e8e676d63c032e7c566d863a9760f94d1c00e5de8217e364603b",
    "qrels.yml": "e3b254054779595aa4157df82db1c885356e3763f35430be0b23bb187c35c6a0",
    "support_labels.yml": "89f7842824e381931735583cb1dc28b79d471ea425df88cc9d6e7cd63c4478d5",
}


def _load(name: str) -> dict:
    return yaml.safe_load((ATLAS_DIR / name).read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _seed_authoritative_corpus(db_path: Path, documents: list[dict]) -> dict[str, set[str]]:
    authoritative: dict[str, set[str]] = {}
    with db.connect(db_path) as conn:
        for source_id, document in enumerate(documents, start=1):
            relpath = f"04_Resources/{document['record_id']}.md"
            conn.execute(
                """
                INSERT INTO sources
                    (id, relpath, content_hash, file_type, bytes, added_at)
                VALUES (?, ?, ?, 'md', ?, datetime('now'))
                """,
                (source_id, relpath, document["record_id"], len(document["body"])),
            )
            authoritative[document["record_id"]] = set(document["source_span_ids"])
            for span_id in document["source_span_ids"]:
                conn.execute(
                    """
                    INSERT INTO source_spans
                        (id, source_id, relpath, span_type, content_hash,
                         text_preview, created_at)
                    VALUES (?, ?, ?, 'paragraph', ?, ?, datetime('now'))
                    """,
                    (span_id, source_id, relpath, span_id, document["body"]),
                )
    for document in documents:
        db.upsert_search_document(
            db_path,
            record_type=document["record_type"],
            record_id=document["record_id"],
            title=document["title"],
            body=document["body"],
            content_hash=document["record_id"],
            dependency_hash=document["record_id"],
            provenance={"source_span_ids": document["source_span_ids"]},
        )
    return authoritative


def _rank(engine: HybridEngine, queries: list[dict]) -> tuple[dict, dict]:
    ranked_by_query: dict[str, list[dict]] = {}
    latency_ms: dict[str, int] = {}
    for query in queries:
        started = time.monotonic()
        result = engine.search(
            query["text"], mode="hybrid", limit=5, rerank=False, persist=False
        )
        latency_ms[query["id"]] = int((time.monotonic() - started) * 1000)
        ranked_by_query[query["id"]] = [
            {"record_id": hit.record_id, "source_span_ids": hit.source_span_ids}
            for hit in result.hits
        ]
    return ranked_by_query, latency_ms


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-correction", action="store_true")
    args = parser.parse_args()
    prior_result = _load("D2_HOLDOUT_RESULT.yml") if OUTPUT.exists() else None
    if prior_result and not args.audit_correction:
        raise SystemExit(f"refusing to rerun consumed holdout: {OUTPUT}")
    if prior_result and prior_result["procedure"]["run_count"] >= 3:
        raise SystemExit("refusing more than two audit-correction reruns")

    corpus_path = ATLAS_DIR / "fixture_corpus.yml"
    qrels_path = ATLAS_DIR / "qrels.yml"
    support_path = ATLAS_DIR / "support_labels.yml"
    for name, approved_hash in APPROVED_HASHES.items():
        if _sha256(ATLAS_DIR / name) != approved_hash:
            raise SystemExit(f"frozen input hash mismatch: {name}")
    corpus = _load("fixture_corpus.yml")
    qrels = _load("qrels.yml")
    support = _load("support_labels.yml")["queries"]
    holdout = [query for query in qrels["queries"] if query["partition"] == "holdout"]
    if [query["id"] for query in holdout] != ["Q06"]:
        raise SystemExit("D2 procedure is approved only for frozen holdout Q06")
    if not all(query.get("frozen") is True for query in holdout):
        raise SystemExit("holdout must be frozen before consumption")

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "state.sqlite"
        db.init_db(db_path)
        authoritative = _seed_authoritative_corpus(db_path, corpus["documents"])
        materialize_chunks(db_path)
        engine = HybridEngine(db_path, embedder=None)
        measured = [q for q in qrels["queries"] if q["partition"] != "holdout"]
        measured_ranked, measured_latency = _rank(engine, measured)
        preflight = evaluate_rankings(
            corpus["documents"], measured, measured_ranked,
            expected_spans_by_query=support,
            authoritative_spans_by_record=authoritative,
            latency_ms=measured_latency,
        )
        direct = preflight["families"]["direct-factual"]
        if direct["recall_at"][1] != 1.0:
            raise SystemExit("non-holdout direct-factual Recall@1 preflight failed")
        for family, metrics in preflight["families"].items():
            if metrics["provenance_resolution_rate"] != 1.0:
                raise SystemExit(f"{family} provenance preflight failed")
            if metrics["top1_citation_correctness"] < 0.95:
                raise SystemExit(f"{family} citation correctness preflight failed")
            if metrics["citation_completeness"] < 0.90:
                raise SystemExit(f"{family} citation completeness preflight failed")
            if metrics["hard_negative_outranks"] != 0:
                raise SystemExit(f"{family} hard-negative preflight failed")
        ranked_by_query, latency_ms = _rank(engine, holdout)
        with db.connect(db_path) as conn:
            schema_version = int(
                conn.execute("SELECT version FROM schema_version").fetchone()["version"]
            )

    report = evaluate_rankings(
        corpus["documents"], holdout, ranked_by_query,
        expected_spans_by_query=support,
        authoritative_spans_by_record=authoritative,
        latency_ms=latency_ms,
    )
    code_paths = [
        REPO_ROOT / "backend" / "scripts" / "failure_atlas_holdout.py",
        REPO_ROOT / "backend" / "src" / "curator" / "retrieval" / "evaluation.py",
        REPO_ROOT / "backend" / "src" / "curator" / "retrieval" / "engine.py",
        REPO_ROOT / "backend" / "src" / "curator" / "retrieval" / "lexical.py",
        REPO_ROOT / "backend" / "src" / "curator" / "retrieval" / "fusion.py",
        REPO_ROOT / "backend" / "src" / "curator" / "retrieval" / "embedding.py",
        REPO_ROOT / "backend" / "src" / "curator" / "retrieval" / "chunking.py",
        REPO_ROOT / "backend" / "src" / "curator" / "db.py",
    ]
    output = {
        "version": 2,
        "recorded_at": "2026-06-12",
        "git_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip(),
        "holdout_ids": ["Q06"],
        "frozen_inputs": {
            "fixture_corpus_sha256": _sha256(corpus_path),
            "qrels_sha256": _sha256(qrels_path),
            "support_labels_sha256": _sha256(support_path),
            "engine": "DB-native lexical FTS5/BM25",
            "limit": 5,
            "rerank": False,
        },
        "procedure": {
            "run_count": (prior_result["procedure"]["run_count"] + 1) if prior_result else 1,
            "valid_run_count": 1,
            "tuning_after_run": False,
            "provider_calls": 0,
            "model_judges": 0,
            "ci_reruns_holdout": False,
            "invalidated_runs": (
                prior_result["procedure"]["invalidated_runs"] + [{
                    "run": prior_result["procedure"]["run_count"],
                    "reason": (
                        "review required complete ranking-stack identity, all-gate "
                        "preflight, and authoritative record/span citation pairing"
                    ),
                    "ranking_configuration_changed": False,
                }] if prior_result else []
            ),
        },
        "evaluated_code": {
            "git_dirty": bool(subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=REPO_ROOT, text=True
            ).strip()),
            "file_sha256": {
                str(path.relative_to(REPO_ROOT)): _sha256(path) for path in code_paths
            },
            "preflight_family_metrics": json.loads(json.dumps(preflight["families"])),
        },
        "environment": {
            "package_version": __version__,
            "db_schema_version": schema_version,
            "scenario": "failure_atlas_fixture",
            "providers": "none",
            "model_judges": "none",
        },
        **report,
    }
    OUTPUT.write_text(
        yaml.safe_dump(output, sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
