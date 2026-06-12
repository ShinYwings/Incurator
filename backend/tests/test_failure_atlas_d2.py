"""Plan D2 fine-grained observatory and one-shot holdout contracts."""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from curator.retrieval.evaluation import evaluate_rankings

REPO_ROOT = Path(__file__).resolve().parents[2]
ATLAS_DIR = REPO_ROOT / "docs" / "specs" / "failure_atlas"


def test_fine_grained_evaluation_reports_every_required_metric_per_family() -> None:
    documents = [
        {
            "record_id": "ATM-expected",
            "title": "Expected",
            "body": "authoritative expected evidence",
            "source_span_ids": ["SPAN-expected"],
        },
        {
            "record_id": "ATM-negative",
            "title": "Negative",
            "body": "hard negative evidence",
            "source_span_ids": ["SPAN-negative"],
        },
    ]
    queries = [
        {
            "id": "Q-test",
            "family": "direct-factual",
            "partition": "regression",
            "expected": ["ATM-expected"],
            "hard_negatives": ["ATM-negative"],
        }
    ]
    ranked = {
        "Q-test": [
            {"record_id": "ATM-negative", "source_span_ids": ["SPAN-negative"]},
            {"record_id": "ATM-expected", "source_span_ids": ["SPAN-expected"]},
        ]
    }

    report = evaluate_rankings(
        documents,
        queries,
        ranked,
        expected_spans_by_query={"Q-test": ["SPAN-expected"]},
        authoritative_spans_by_record={
            "ATM-expected": {"SPAN-expected"},
            "ATM-negative": {"SPAN-negative"},
        },
        latency_ms={"Q-test": 7},
    )

    assert set(report) == {"queries", "families"}
    assert set(report["families"]) == {"direct-factual"}
    row = report["queries"][0]
    assert row["recall_at"] == {1: 0.0, 3: 1.0, 5: 1.0}
    assert row["mrr"] == 0.5
    assert row["top1_citation_correctness"] == 0.0
    assert row["citation_completeness"] == 1.0
    assert row["provenance_resolution_rate"] == 1.0
    assert row["hard_negative_outranks"] == 1
    assert row["indexed_characters"] > 0
    assert row["latency_ms"] == 7


def test_provenance_resolution_rejects_unknown_and_mismatched_spans() -> None:
    report = evaluate_rankings(
        [{"record_id": "ATM-a", "title": "A", "body": "A"}],
        [{
            "id": "Q", "family": "direct-factual", "partition": "adversarial",
            "expected": ["ATM-missing"], "hard_negatives": ["ATM-negative"],
        }],
        {"Q": [
            {"record_id": "ATM-a", "source_span_ids": ["SPAN-other"]},
            {"record_id": "ATM-unknown", "source_span_ids": ["SPAN-a"]},
            {"record_id": "ATM-negative", "source_span_ids": ["SPAN-negative"]},
        ]},
        expected_spans_by_query={"Q": ["SPAN-missing"]},
        authoritative_spans_by_record={
            "ATM-a": {"SPAN-a"},
            "ATM-missing": {"SPAN-missing"},
            "ATM-negative": {"SPAN-negative"},
        },
    )
    row = report["queries"][0]
    assert row["provenance_resolution_rate"] == 1 / 3
    assert row["hard_negative_outranks"] == 1


def test_d2_holdout_result_is_single_run_frozen_and_fine_grained() -> None:
    result = yaml.safe_load(
        (ATLAS_DIR / "D2_HOLDOUT_RESULT.yml").read_text(encoding="utf-8")
    )
    assert result["procedure"]["run_count"] == 3
    assert result["procedure"]["valid_run_count"] == 1
    assert result["procedure"]["invalidated_runs"][0]["run"] == 1
    assert result["procedure"]["invalidated_runs"][0]["ranking_configuration_changed"] is False
    assert result["procedure"]["invalidated_runs"][1]["run"] == 2
    assert result["procedure"]["invalidated_runs"][1]["ranking_configuration_changed"] is False
    assert result["procedure"]["tuning_after_run"] is False
    assert result["procedure"]["provider_calls"] == 0
    assert result["holdout_ids"] == ["Q06"]
    assert result["families"]["direct-factual"]["query_count"] == 1
    required = {
        "recall_at", "mrr", "top1_citation_correctness",
        "citation_completeness", "provenance_resolution_rate",
        "hard_negative_outranks", "indexed_characters", "latency_ms",
    }
    assert required <= set(result["queries"][0])
    assert result["queries"][0]["top1_citation_correctness"] == 1.0
    assert result["queries"][0]["citation_completeness"] == 1.0
    assert result["queries"][0]["provenance_resolution_rate"] == 1.0
    assert result["queries"][0]["hard_negative_outranks"] == 0
    for name, recorded in (
        ("fixture_corpus.yml", result["frozen_inputs"]["fixture_corpus_sha256"]),
        ("qrels.yml", result["frozen_inputs"]["qrels_sha256"]),
        ("support_labels.yml", result["frozen_inputs"]["support_labels_sha256"]),
    ):
        assert hashlib.sha256((ATLAS_DIR / name).read_bytes()).hexdigest() == recorded
    for relpath, recorded in result["evaluated_code"]["file_sha256"].items():
        assert hashlib.sha256((REPO_ROOT / relpath).read_bytes()).hexdigest() == recorded
    assert result["environment"] == {
        "package_version": "0.7.0",
        "db_schema_version": 7,
        "scenario": "failure_atlas_fixture",
        "providers": "none",
        "model_judges": "none",
    }


def test_query_level_support_labels_cover_qrels_and_resolve() -> None:
    corpus = yaml.safe_load((ATLAS_DIR / "fixture_corpus.yml").read_text(encoding="utf-8"))
    qrels = yaml.safe_load((ATLAS_DIR / "qrels.yml").read_text(encoding="utf-8"))
    labels = yaml.safe_load((ATLAS_DIR / "support_labels.yml").read_text(encoding="utf-8"))
    spans_by_record = {
        document["record_id"]: set(document["source_span_ids"])
        for document in corpus["documents"]
    }
    qrels_by_id = {query["id"]: query for query in qrels["queries"]}
    assert set(labels["queries"]) == {query["id"] for query in qrels["queries"]}
    for query_id, expected_spans in labels["queries"].items():
        allowed = {
            span
            for record_id in qrels_by_id[query_id]["expected"]
            for span in spans_by_record[record_id]
        }
        assert set(expected_spans) <= allowed
