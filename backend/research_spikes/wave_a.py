"""Plan E Wave A deterministic retrieval-unit and diagnostic comparison."""

from __future__ import annotations

import argparse
import hashlib
import tempfile
from pathlib import Path
from typing import Any

from curator import db  # type: ignore[import-untyped]
from curator.retrieval.embedding import embed_corpus, materialize_chunks  # type: ignore[import-untyped]
from curator.retrieval.engine import HybridEngine  # type: ignore[import-untyped]

from contracts import load_yaml, write_json
from metrics import hard_negative_outranks, mrr_at, recall_at, set_correctness, set_coverage

VARIANTS = ("raw", "heading", "context")
MODES = ("lex", "vec", "hybrid")
MEASURED_PARTITIONS = {"dev", "regression", "adversarial"}


class DeterministicTokenEmbedder:
    provider = "research"
    model = "token-hash-v1"
    dim = 64

    @property
    def fingerprint(self) -> str:
        return f"{self.provider}::{self.model}::{self.dim}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, texts: list[str]) -> list[list[float]]:
        return self.embed(texts)

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        for token in text.lower().replace("-", " ").split():
            index = int(hashlib.sha256(token.strip(".,?!").encode()).hexdigest()[:8], 16) % self.dim
            vector[index] += 1.0
        return vector


def _body(document: dict[str, Any], variant: str) -> str:
    if variant == "raw":
        return document["raw_chunk"]
    if variant == "heading":
        return f"{document['heading']}\n{document['raw_chunk']}"
    return f"[GENERATED CONTEXT] {document['generated_context']}\n{document['raw_chunk']}"


def _evaluate_variant(corpus: dict[str, Any], variant: str, mode: str) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as temp:
        db_path = Path(temp) / "state.sqlite"
        db.init_db(db_path)
        indexed_characters = 0
        for document in corpus["documents"]:
            body = _body(document, variant)
            indexed_characters += len(body)
            db.upsert_search_document(
                db_path,
                record_type="knowledge_unit",
                record_id=document["record_id"],
                title="",
                body=body,
                content_hash=document["record_id"],
                dependency_hash=document["record_id"],
                provenance={"source_span_ids": document["source_span_ids"]},
            )
        materialize_chunks(db_path)
        embedder = DeterministicTokenEmbedder()
        embed_corpus(db_path, embedder)
        engine = HybridEngine(db_path, embedder=embedder)

        cases: list[dict[str, Any]] = []
        for query in corpus["queries"]:
            if query["partition"] not in MEASURED_PARTITIONS:
                continue
            result = engine.search(
                query["text"], mode=mode, limit=5, rerank=False, persist=False
            )
            ranked = [hit.record_id for hit in result.hits]
            selected_spans = set(result.hits[0].source_span_ids) if result.hits else set()
            provenance_resolution_rate = (
                sum(1 for hit in result.hits if hit.source_span_ids) / len(result.hits)
                if result.hits
                else 1.0
            )
            expected = set(query["expected"])
            expected_spans = set(query["expected_spans"])
            cases.append(
                {
                    "id": query["id"],
                    "partition": query["partition"],
                    "family": query["family"],
                    "ranked": ranked,
                    "recall_at_1": recall_at(ranked, expected, 1),
                    "recall_at_5": recall_at(ranked, expected, 5),
                    "mrr_at_5": mrr_at(ranked, expected, 5),
                    "hard_negative_outranks": hard_negative_outranks(
                        ranked, expected, set(query.get("hard_negatives", []))
                    ),
                    "provenance_resolution_rate": provenance_resolution_rate,
                    "citation_correctness": set_correctness(selected_spans, expected_spans),
                    "citation_completeness": set_coverage(selected_spans, expected_spans),
                    "latency_ms": result.retrieval_trace["latency_ms"],
                }
            )
        return {
            "variant": variant,
            "mode": mode,
            "indexed_characters": indexed_characters,
            "holdout_measured": False,
            "cases": cases,
        }


def run_wave_a(corpus_path: Path) -> dict[str, Any]:
    corpus = load_yaml(corpus_path)
    runs = [
        _evaluate_variant(corpus, variant, mode)
        for variant in VARIANTS
        for mode in MODES
    ]
    return {
        "wave": "A",
        "execution_mode": "deterministic-provider-free",
        "corpus_version": corpus["version"],
        "runs": runs,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--corpus",
        type=Path,
        default=Path(__file__).resolve().parent / "corpora" / "retrieval_units.yml",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / "local" / "results" / "wave_a.json",
    )
    args = parser.parse_args()
    result = run_wave_a(args.corpus)
    write_json(args.output, result)
    print(args.output)


if __name__ == "__main__":
    main()
