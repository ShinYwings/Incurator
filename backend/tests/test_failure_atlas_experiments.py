"""Failure Atlas mutation/degradation/cross-client experiments (Plan D phase P3).

Each test is an evidence bundle per FAILURE_ATLAS.md §4: it declares the atlas
case(s) it serves in its docstring, runs a deterministic experiment against the
synthetic corpus, and asserts the OBSERVED current behavior (good or bad).
Observed results feed EVALUATION_BASELINE.md and the per-case
``observed_result``/``notes`` fields. No production behavior is repaired here.
"""

from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from curator import config as cfg
from curator import db, search
from curator.pipeline import graph_index
from curator.pipeline import source_spans as l1
from curator.retrieval import providers
from curator.retrieval import query_expander as qe_mod
from curator.retrieval.embedding import materialize_chunks

RELPATH = "04_Resources/fa.md"


@pytest.fixture()
def vault():
    with tempfile.TemporaryDirectory() as t:
        root = Path(t)
        paths = cfg.WikiPaths(root)
        paths.internal.mkdir(parents=True, exist_ok=True)
        db.init_db(paths.state_db)
        with db.connect(paths.state_db) as conn:
            conn.execute(
                "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at) "
                "VALUES (?, 'h', 'md', 1, datetime('now'))",
                (RELPATH,),
            )
        yield paths


@pytest.fixture()
def degraded_search():
    with (
        patch.object(cfg, "load_config", return_value=copy.deepcopy(cfg.DEFAULT_CONFIG)),
        patch.object(providers, "build_embedder", return_value=None),
        patch.object(providers, "build_reranker", return_value=None),
        patch.object(qe_mod, "build_query_expander", return_value=None),
    ):
        yield


def _spans_for(paths: cfg.WikiPaths, source_id: int, text: str) -> list[str]:
    sections = [{"id": "s1", "title": "Note", "page": None, "text": text}]
    return l1.store_source_spans(
        paths.state_db, source_id, RELPATH, l1.spans_from_sections(sections)
    )


def _count(paths: cfg.WikiPaths, table: str) -> int:
    with db.connect(paths.state_db) as conn:
        allowed_tables = {"sources", "source_spans", "search_documents", "search_chunks", "graph_entities"}
        assert table in allowed_tables, f"Invalid table: {table}"
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


# ---------------------------------------------------------------------------
# Unchanged-rebuild experiments (F7 evidence — the parts that DO hold today)
# ---------------------------------------------------------------------------

def test_unchanged_rebuild_is_id_stable_at_l1_and_search(vault) -> None:
    """F7 partial pass: unchanged re-store is idempotent at L1 and search layers.

    Observed: span ids are stable per (source_id, content_hash); repeating
    upsert_search_document with identical content keeps exactly one row per
    record; materialize_chunks twice does not duplicate chunks. The F7 defect
    is therefore concentrated in EDIT reconciliation and dependency-closure
    invalidation, not in unchanged re-runs.
    """
    paths = vault
    spans1 = _spans_for(paths, 1, "Original derivation of the bound.")
    assert _spans_for(paths, 1, "Original derivation of the bound.") == spans1
    assert _count(paths, "source_spans") == len(spans1)

    for _ in range(2):
        db.upsert_search_document(
            paths.state_db, record_type="knowledge_unit", record_id="ATM-x1",
            title="Residual learning", body="Residual connections ease optimization.",
            content_hash="c1", dependency_hash="d1",
            provenance={"source_span_ids": spans1},
        )
    assert _count(paths, "search_documents") == 1
    materialize_chunks(paths.state_db)
    chunks_once = _count(paths, "search_chunks")
    materialize_chunks(paths.state_db)
    assert _count(paths, "search_chunks") == chunks_once


def test_rename_as_new_source_duplicates_every_span(vault) -> None:
    """F7 mutation evidence: a renamed/re-registered source duplicates L1 rows.

    Span dedup is keyed on (source_id, content_hash)
    (db.py idx_source_spans_source_hash), so registering the same content under
    a new source id — the effect of a rename that re-registers — mints all-new
    span ids while the old rows linger under the dead relpath.
    """
    paths = vault
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at) "
            "VALUES ('04_Resources/renamed.md', 'h2', 'md', 1, datetime('now'))"
        )
    spans_old = _spans_for(paths, 1, "Identical content before and after rename.")
    spans_new = _spans_for(paths, 2, "Identical content before and after rename.")
    assert set(spans_new).isdisjoint(spans_old)  # duplicated, not reused
    assert _count(paths, "source_spans") == len(spans_old) + len(spans_new)


# ---------------------------------------------------------------------------
# Failed-batch atomicity experiment (F7 evidence)
# ---------------------------------------------------------------------------

class _SecondBatchFailsClient:
    """Graph-extraction client: batch 1 valid, batch 2 invalid JSON."""

    model = "fake"

    def __init__(self) -> None:
        self.calls = 0

    def optimal_chunk_chars(self) -> int:
        return 600  # force multiple unit batches

    def chat(self, messages, *, json_mode=False, temperature=0.3) -> str:
        self.calls += 1
        if self.calls > 1:
            return "NOT JSON — simulated mid-compile failure"
        text = "\n".join(m.content for m in messages)
        spans = [w.strip(",]") for w in text.split() if w.startswith("SPAN-")]
        first = spans[0] if spans else "SPAN-00000000"
        return json.dumps({
            "entities": [
                {"canonical_name": "Residual learning", "entity_type": "concept",
                 "description": "batch-1 entity", "source_span_ids": [first]},
            ],
            "relations": [],
        })


def test_failed_batch_leaves_partial_graph_state(vault) -> None:
    """F7 atomicity evidence: a mid-compile batch failure persists partial truth.

    Observed: when unit batch 2 fails validation, batch 1's entities remain in
    graph_entities and the extraction returns ok=False — there is no
    transaction around the multi-batch compile, so a failed compile leaves
    partial authoritative state (Program 2 gate: it must not).
    """
    paths = vault
    span = db.upsert_source_span(
        paths.state_db, source_id=1, relpath=RELPATH, span_type="paragraph",
        content_hash="fb", section_title="Intro",
        text_preview="Residual connections ease optimization.",
    )
    units = [
        {
            "id": f"KU-{i}", "unit_type": "claim",
            "statement": f"Claim {i}: " + ("residual optimization detail. " * 10),
            "source_span_ids": [span],
        }
        for i in range(4)
    ]
    client = _SecondBatchFailsClient()
    result = graph_index.extract_entities_and_relations(
        paths.state_db, client, units=units, valid_span_ids=[span]
    )
    assert client.calls >= 2, "experiment requires multiple batches"
    assert not result.ok  # the compile FAILED...
    assert _count(paths, "graph_entities") >= 1  # ...but partial truth persisted


# ---------------------------------------------------------------------------
# Degraded-mode experiments (missing providers)
# ---------------------------------------------------------------------------

def test_degraded_hybrid_search_falls_back_to_lexical(vault, degraded_search) -> None:
    """Degraded-mode evidence (FAILURE_ATLAS §5): hybrid search without an
    embedder/reranker degrades to lexical with explicit warnings — it neither
    raises nor returns empty for a matching lexical query.
    """
    paths = vault
    db.upsert_search_document(
        paths.state_db, record_type="knowledge_unit", record_id="ATM-x1",
        title="Residual learning", body="Residual connections ease optimization.",
        content_hash="c1", dependency_hash="d1",
        provenance={"source_span_ids": ["SPAN-x1"]},
    )
    materialize_chunks(paths.state_db)
    results = search.query(
        paths, "residual optimization", mode="hybrid", limit=5,
        min_score=0.0, hydrate=True, rerank=True,
    )
    assert results.hits and results.hits[0].docid == "ATM-x1"
    assert results.fallback_mode in {"lex", "no_rerank"}
    assert any("vector" in w or "rerank" in w for w in results.warnings) or results.fallback_mode == "lex"
