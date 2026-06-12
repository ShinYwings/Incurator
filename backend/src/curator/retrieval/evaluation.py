"""Provider-free fine-grained retrieval evaluation primitives."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

__all__ = ["evaluate_rankings"]


def _mean(rows: list[dict], key: str) -> float:
    return sum(float(row[key]) for row in rows) / len(rows) if rows else 0.0


def evaluate_rankings(
    documents: list[dict],
    queries: list[dict],
    ranked_by_query: dict[str, list[dict]],
    *,
    expected_spans_by_query: dict[str, list[str]],
    authoritative_spans_by_record: dict[str, set[str]],
    latency_ms: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Evaluate frozen ranked results without invoking providers or model judges."""
    indexed_characters = sum(
        len(str(doc.get("title", ""))) + len(str(doc.get("body", "")))
        for doc in documents
    )
    query_rows: list[dict] = []

    for query in queries:
        ranked = ranked_by_query.get(query["id"], [])
        ranked_ids = [hit["record_id"] for hit in ranked]
        expected = set(query["expected"])
        expected_spans = set(expected_spans_by_query[query["id"]])
        resolved_spans = {
            span
            for hit in ranked
            if hit.get("record_id") in authoritative_spans_by_record
            for span in hit.get("source_span_ids", [])
            if span in authoritative_spans_by_record[hit["record_id"]]
        }
        first_expected_rank = next(
            (index + 1 for index, record_id in enumerate(ranked_ids) if record_id in expected),
            None,
        )
        top = ranked[0] if ranked else {}
        top_spans = set(top.get("source_span_ids", []))
        top_authoritative = authoritative_spans_by_record.get(
            str(top.get("record_id", "")), set()
        )
        top_is_correct = top.get("record_id") in expected and bool(
            top_spans & expected_spans
        ) and top_spans <= top_authoritative
        resolved_hits = sum(
            1
            for hit in ranked
            if hit.get("source_span_ids")
            and hit.get("record_id") in authoritative_spans_by_record
            and set(hit["source_span_ids"])
            <= authoritative_spans_by_record[hit["record_id"]]
        )
        query_rows.append(
            {
                "id": query["id"],
                "family": query["family"],
                "partition": query["partition"],
                "ranked": ranked_ids,
                "recall_at": {
                    k: len(expected & set(ranked_ids[:k])) / len(expected)
                    for k in (1, 3, 5)
                },
                "mrr": (1.0 / first_expected_rank) if first_expected_rank else 0.0,
                "top1_citation_correctness": 1.0 if top_is_correct else 0.0,
                "citation_completeness": (
                    len(expected_spans & resolved_spans) / len(expected_spans)
                    if expected_spans else 0.0
                ),
                "provenance_resolution_rate": (
                    resolved_hits / len(ranked) if ranked else 0.0
                ),
                "hard_negative_outranks": sum(
                    1
                    for negative in query.get("hard_negatives", [])
                    if negative in ranked_ids
                    and (
                        first_expected_rank is None
                        or ranked_ids.index(negative) + 1 < first_expected_rank
                    )
                ),
                "indexed_characters": indexed_characters,
                "latency_ms": (latency_ms or {}).get(query["id"], 0),
            }
        )

    rows_by_family: dict[str, list[dict]] = defaultdict(list)
    for row in query_rows:
        rows_by_family[row["family"]].append(row)
    families = {
        family: {
            "query_count": len(rows),
            "recall_at": {
                k: sum(row["recall_at"][k] for row in rows) / len(rows)
                for k in (1, 3, 5)
            },
            "mrr": _mean(rows, "mrr"),
            "top1_citation_correctness": _mean(rows, "top1_citation_correctness"),
            "citation_completeness": _mean(rows, "citation_completeness"),
            "provenance_resolution_rate": _mean(rows, "provenance_resolution_rate"),
            "hard_negative_outranks": sum(
                int(row["hard_negative_outranks"]) for row in rows
            ),
            "indexed_characters": max(int(row["indexed_characters"]) for row in rows),
            "mean_latency_ms": sum(int(row["latency_ms"]) for row in rows) / len(rows),
        }
        for family, rows in rows_by_family.items()
    }
    return {"queries": query_rows, "families": families}
