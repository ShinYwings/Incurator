"""Cutover (v0.3.1): end-to-end L2/L3 compile orchestration.

Exercises pipeline.compile against a real source file with a dynamic fake LLM
that cites the runtime-generated span ids it sees in the prompt.
"""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

import pytest

from curator import config as cfg
from curator import db
from curator.llm import ChatMessage
from curator.pipeline import compile as compile_mod

SOURCE_MD = """\
# Residual Learning

Residual connections make very deep networks easier to optimize.

They address the degradation problem in deep networks.

# Euler Discretization

A residual block resembles one Euler step of an ODE.
"""


class DynamicFakeClient:
    """Returns contract-appropriate JSON, citing real span ids from the prompt."""

    model = "fake"

    def chat(self, messages: list[ChatMessage], *, json_mode=False, temperature=0.3) -> str:
        text = "\n".join(m.content for m in messages)
        span_ids = re.findall(r"SPAN-[0-9a-f]{8}", text)
        first = span_ids[0] if span_ids else "SPAN-00000000"
        if "Extract the knowledge units" in text:
            return json.dumps(
                {
                    "units": [
                        {
                            "canonical_name": "Residual learning eases optimization",
                            "unit_type": "claim",
                            "statement": "Residual connections make deep nets easier to optimize.",
                            "source_span_ids": [first],
                            "confidence": 0.9,
                            "truth_status": "source_supported",
                        }
                    ]
                }
            )
        if "Extract entities and relations" in text:
            return json.dumps(
                {
                    "entities": [
                        {"canonical_name": "ResNet", "entity_type": "method",
                         "source_span_ids": [first]},
                        {"canonical_name": "degradation problem", "entity_type": "concept",
                         "source_span_ids": [first]},
                    ],
                    "relations": [
                        {"source": "ResNet", "target": "degradation problem",
                         "relation_type": "addresses", "assertion_source": "source_states",
                         "source_span_ids": [first], "confidence": 0.9},
                    ],
                }
            )
        if "Write the community report" in text:
            return json.dumps(
                {
                    "title": "Residual learning community",
                    "summary": "ResNet addresses the degradation problem.",
                    "full_content": "Report body.",
                    "findings": [{"summary": "ResNet addresses degradation",
                                  "source_span_ids": [first], "rank": 0.8}],
                    "contradictions": [],
                    "source_span_ids": [first],
                    "rank": 0.7,
                }
            )
        return "{}"


def _layer_status(paths, source_id: int, layer: str) -> str:
    with db.connect(paths.state_db) as conn:
        row = conn.execute(
            f"SELECT {layer}_status AS s FROM sources WHERE id = ?", (source_id,)
        ).fetchone()
    return row["s"]


@pytest.fixture()
def vault():
    with tempfile.TemporaryDirectory() as t:
        root = Path(t)
        paths = cfg.WikiPaths(root)
        db.init_db(paths.state_db)
        src = root / "04_Resources" / "resnet.md"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text(SOURCE_MD, encoding="utf-8")
        with db.connect(paths.state_db) as conn:
            conn.execute(
                "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at, "
                "context_id, l1_status) VALUES (?, ?, ?, ?, datetime('now'), ?, 'done')",
                ("04_Resources/resnet.md", "h", "md", len(SOURCE_MD), "CTX-test1234"),
            )
        yield paths


def test_compile_source_l2_writes_units_atoms_graph(vault) -> None:
    paths = vault
    result = compile_mod.compile_source_l2(paths, DynamicFakeClient(), 1)
    assert result.ok, result.error

    # Knowledge units persisted, with spans.
    units = db.list_knowledge_units_for_source(paths.state_db, 1)
    assert units and units[0]["source_span_ids"]

    # ATM projection pages emitted.
    atom_files = list(paths.atoms.glob("ATM-*.md"))
    assert len(atom_files) == len(result.atom_ids) == len(units)
    assert "source_span_ids" in atom_files[0].read_text(encoding="utf-8")

    # Graph entities persisted.
    with db.connect(paths.state_db) as conn:
        n_ent = conn.execute("SELECT COUNT(*) FROM graph_entities").fetchone()[0]
        n_rel = conn.execute("SELECT COUNT(*) FROM graph_relations").fetchone()[0]
    assert n_ent == 2 and n_rel == 1

    # CTX -> ATM dag edges.
    edges = db.get_dag_edges_for_source(paths.state_db, "1")
    assert any(e["edge_type"] == "extracted_from" for e in edges)

    # l2 done.
    assert _layer_status(paths, 1, "l2") == "done"
    assert any(doc["record_type"] == "knowledge_unit" for doc in db.list_search_documents(paths.state_db))


def test_compile_global_l3_writes_concepts(vault) -> None:
    paths = vault
    client = DynamicFakeClient()
    compile_mod.compile_source_l2(paths, client, 1)
    concept_ids = compile_mod.compile_global_l3(paths, client)
    assert concept_ids

    con_files = list(paths.concepts.glob("CON-*.md"))
    assert len(con_files) == len(concept_ids)
    assert "community_report_id" in con_files[0].read_text(encoding="utf-8")

    with db.connect(paths.state_db) as conn:
        n_rep = conn.execute("SELECT COUNT(*) FROM community_reports").fetchone()[0]
    assert n_rep >= 1

    assert _layer_status(paths, 1, "l3") == "done"


def test_compile_source_l2_failed_extraction_sets_error(vault) -> None:
    paths = vault

    class BadClient:
        model = "fake"

        def chat(self, messages, *, json_mode=False, temperature=0.3) -> str:
            return "not json"

    result = compile_mod.compile_source_l2(paths, BadClient(), 1)
    assert not result.ok
    assert _layer_status(paths, 1, "l2") == "error"
    assert db.list_knowledge_units_for_source(paths.state_db, 1) == []
    docs = db.list_search_documents(paths.state_db)
    assert {doc["record_type"] for doc in docs} == {"source_span"}
    assert len(docs) == len(db.list_source_spans(paths.state_db, 1))
