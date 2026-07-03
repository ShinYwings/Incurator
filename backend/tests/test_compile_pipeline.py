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
from curator import ingest_llm
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
        if "Write the cross-cutting syntheses" in text:
            return json.dumps(
                {
                    "syntheses": [
                        {
                            "title": "Residual learning as dynamics",
                            "statement": "Residual blocks behave like discretized dynamics.",
                            "full_content": "Cross-cutting synthesis.",
                            "source_span_ids": [first],
                            "confidence": 0.7,
                        }
                    ]
                }
            )
        return "{}"


def _layer_status(paths, source_id: int, layer: str) -> str | None:
    with db.connect(paths.state_db) as conn:
        allowed_layers = {"l1", "l2", "l3", "l4"}
        assert layer in allowed_layers, f"Invalid layer: {layer}"
        row = conn.execute(
            f"SELECT {layer}_status FROM sources WHERE id = ?", (source_id,)
        ).fetchone()
    return row[0] if row else None


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
    assert units[0]["support_status"] == "verified"
    assert units[0]["semantic_hash"]
    assert any(
        row["support_status"] == "verified"
        for row in db.list_claim_supports(paths.state_db, units[0]["id"])
    )

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

    # §26.3: the compile published exactly one authoritative generation for the
    # source, and its units are attributed to it.
    gen = db.get_authoritative_generation(paths.state_db, 1)
    assert gen is not None and gen["status"] == "authoritative"
    assert all(u["generation_id"] == gen["id"] for u in units)
    # Unchanged rebuild is idempotent: reuses the generation, no count amplification.
    before = compile_mod.recompile_source(paths.state_db, 1)
    after = compile_mod.recompile_source(paths.state_db, 1)
    assert before == after
    assert db.get_authoritative_generation(paths.state_db, 1)["id"] == gen["id"]
    assert len(db.list_knowledge_units_for_source(paths.state_db, 1)) == len(units)


def test_compile_source_l2_excludes_failed_claim_from_downstream(vault) -> None:
    paths = vault

    class WrongSpanClient(DynamicFakeClient):
        def chat(self, messages, *, json_mode=False, temperature=0.3) -> str:
            text = "\n".join(m.content for m in messages)
            span_ids = re.findall(r"SPAN-[0-9a-f]{8}", text)
            first = span_ids[0] if span_ids else "SPAN-00000000"
            if "Extract the knowledge units" in text:
                return json.dumps(
                    {
                        "units": [
                            {
                                "canonical_name": "Unrelated coral claim",
                                "unit_type": "claim",
                                "statement": "Coral bleaching expels symbiotic algae.",
                                "source_span_ids": [first],
                                "confidence": 0.9,
                                "truth_status": "source_supported",
                            }
                        ]
                    }
                )
            if "Extract entities and relations" in text:
                raise AssertionError("failed claims must not feed graph extraction")
            return super().chat(messages, json_mode=json_mode, temperature=temperature)

    result = compile_mod.compile_source_l2(paths, WrongSpanClient(), 1)
    assert result.ok, result.error
    units = db.list_knowledge_units_for_source(paths.state_db, 1)
    assert len(units) == 1
    assert units[0]["support_status"] == "failed"
    assert not result.atom_ids
    assert not result.entity_ids
    assert not list(paths.atoms.glob("ATM-*.md"))
    assert not any(
        doc["record_type"] == "knowledge_unit"
        for doc in db.list_search_documents(paths.state_db)
    )


def test_compile_source_l2_repairs_non_english_generated_units(vault) -> None:
    paths = vault

    class KoreanThenEnglishClient(DynamicFakeClient):
        def __init__(self) -> None:
            self.knowledge_unit_calls = 0

        def chat(self, messages, *, json_mode=False, temperature=0.3) -> str:
            text = "\n".join(m.content for m in messages)
            span_ids = re.findall(r"SPAN-[0-9a-f]{8}", text)
            first = span_ids[0] if span_ids else "SPAN-00000000"
            if "Extract the knowledge units" in text:
                self.knowledge_unit_calls += 1
                if self.knowledge_unit_calls == 1:
                    return json.dumps(
                        {
                            "units": [
                                {
                                    "canonical_name": "잔차 학습",
                                    "unit_type": "claim",
                                    "statement": "잔차 연결은 깊은 네트워크 최적화를 쉽게 한다.",
                                    "source_span_ids": [first],
                                    "confidence": 0.9,
                                    "truth_status": "source_supported",
                                }
                            ]
                        }
                    )
            return super().chat(messages, json_mode=json_mode, temperature=temperature)

    client = KoreanThenEnglishClient()
    result = compile_mod.compile_source_l2(paths, client, 1)

    assert result.ok, result.error
    assert client.knowledge_unit_calls == 2
    units = db.list_knowledge_units_for_source(paths.state_db, 1)
    assert units[0]["canonical_name"] == "Residual learning eases optimization"
    assert "잔차" not in units[0]["statement"]


def test_compile_source_l2_rejects_persistently_non_english_generated_units(vault) -> None:
    paths = vault

    class AlwaysKoreanClient(DynamicFakeClient):
        def chat(self, messages, *, json_mode=False, temperature=0.3) -> str:
            text = "\n".join(m.content for m in messages)
            span_ids = re.findall(r"SPAN-[0-9a-f]{8}", text)
            first = span_ids[0] if span_ids else "SPAN-00000000"
            if "Extract the knowledge units" in text:
                return json.dumps(
                    {
                        "units": [
                            {
                                "canonical_name": "잔차 학습",
                                "unit_type": "claim",
                                "statement": "잔차 연결은 깊은 네트워크 최적화를 쉽게 한다.",
                                "source_span_ids": [first],
                                "confidence": 0.9,
                                "truth_status": "source_supported",
                            }
                        ]
                    }
                )
            return super().chat(messages, json_mode=json_mode, temperature=temperature)

    result = compile_mod.compile_source_l2(paths, AlwaysKoreanClient(), 1)

    assert not result.ok
    assert _layer_status(paths, 1, "l2") == "error"
    assert db.list_knowledge_units_for_source(paths.state_db, 1) == []
    assert not list(paths.atoms.glob("ATM-*.md"))


def test_compile_global_l3_writes_concepts(vault) -> None:
    paths = vault
    client = DynamicFakeClient()
    # Plan C (v0.9.0, §27.2): the claim-grounded L3 path grounds a community report
    # only on `active` relations corroborated by >=2 INDEPENDENT source lineages. A
    # single source can never reach the floor, so seed a SECOND independent source
    # (distinct content_hash => distinct lineage) asserting the SAME proposition.
    src2 = paths.root / "04_Resources" / "resnet2.md"
    src2.write_text(SOURCE_MD, encoding="utf-8")
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at, "
            "context_id, l1_status) VALUES (?, ?, ?, ?, datetime('now'), ?, 'done')",
            ("04_Resources/resnet2.md", "h2", "md", len(SOURCE_MD), "CTX-test5678"),
        )
    compile_mod.compile_source_l2(paths, client, 1)
    compile_mod.compile_source_l2(paths, client, 2)
    concept_ids = compile_mod.compile_global_l3(paths, client)
    assert concept_ids

    con_files = list(paths.concepts.glob("CON-*.md"))
    assert len(con_files) == len(concept_ids)
    assert "community_report_id" in con_files[0].read_text(encoding="utf-8")

    with db.connect(paths.state_db) as conn:
        n_rep = conn.execute(
            "SELECT COUNT(*) FROM community_reports WHERE retired_at IS NULL"
        ).fetchone()[0]
    assert n_rep >= 1

    assert _layer_status(paths, 1, "l3") == "done"


def test_compile_global_l3_marks_l4_done_when_synthesis_is_generated(vault) -> None:
    paths = vault
    client = DynamicFakeClient()
    src2 = paths.root / "04_Resources" / "resnet2.md"
    src2.write_text(SOURCE_MD, encoding="utf-8")
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at, "
            "context_id, l1_status) VALUES (?, ?, ?, ?, datetime('now'), ?, 'done')",
            ("04_Resources/resnet2.md", "h2", "md", len(SOURCE_MD), "CTX-test5678"),
        )

    compile_mod.compile_source_l2(paths, client, 1)
    compile_mod.compile_source_l2(paths, client, 2)
    compile_mod.compile_global_l3(paths, client)

    assert db.list_synthesis_nodes(paths.state_db)
    assert _layer_status(paths, 1, "l4") == "done"
    assert _layer_status(paths, 2, "l4") == "done"


def test_compile_global_l3_marks_l3_and_l4_skipped_when_no_reports_exist(vault) -> None:
    paths = vault
    client = DynamicFakeClient()

    compile_mod.compile_source_l2(paths, client, 1)
    concept_ids = compile_mod.compile_global_l3(paths, client)

    assert concept_ids == []
    assert db.list_community_reports(paths.state_db) == []
    assert db.list_synthesis_nodes(paths.state_db) == []
    assert _layer_status(paths, 1, "l3") == "skipped"
    assert _layer_status(paths, 1, "l4") == "skipped"


def test_l3_regeneration_preserves_l4_terminal_status(vault) -> None:
    paths = vault
    client = DynamicFakeClient()

    compile_mod.compile_source_l2(paths, client, 1)
    ingest_llm.run_l3_from_existing_atoms(paths, client, lambda: ingest_llm.IngestCallbacks)

    assert db.list_synthesis_nodes(paths.state_db) == []
    assert _layer_status(paths, 1, "l3") == "skipped"
    assert _layer_status(paths, 1, "l4") == "skipped"


def test_compile_source_l2_failed_extraction_sets_error(vault) -> None:
    paths = vault

    class BadClient:
        model = "fake"

        def chat(self, messages, *, json_mode=False, temperature=0.3) -> str:
            return "not json"

    result = compile_mod.compile_source_l2(paths, BadClient(), 1)
    assert not result.ok
    assert result.error is not None
    assert "L2 extraction batch 1/1" in result.error
    assert "output did not parse into the declared model" in result.error
    assert _layer_status(paths, 1, "l2") == "error"
    assert db.list_knowledge_units_for_source(paths.state_db, 1) == []
    docs = db.list_search_documents(paths.state_db)
    assert {doc["record_type"] for doc in docs} == {"source_span"}
    assert len(docs) == len(db.list_source_spans(paths.state_db, 1))


def test_compile_global_l3_failure_sets_l4_skipped_not_error(vault) -> None:
    """When synthesis errors, L4 should be 'skipped' with its own message, not 'error'."""
    paths = vault

    class SynthesisFailClient(DynamicFakeClient):
        def chat(self, messages, *, json_mode=False, temperature=0.3) -> str:
            text = "\n".join(m.content for m in messages)
            if "cross-cutting synthes" in text.lower() or "Write the cross-cutting" in text:
                raise RuntimeError("synthetic synthesis failure")
            return super().chat(messages, json_mode=json_mode, temperature=temperature)

    client = SynthesisFailClient()
    # Need 2 sources for community reports to be generated.
    src2 = paths.root / "04_Resources" / "resnet2.md"
    src2.write_text(SOURCE_MD, encoding="utf-8")
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at, "
            "context_id, l1_status) VALUES (?, ?, ?, ?, datetime('now'), ?, 'done')",
            ("04_Resources/resnet2.md", "h2", "md", len(SOURCE_MD), "CTX-test5678"),
        )

    compile_mod.compile_source_l2(paths, client, 1)
    compile_mod.compile_source_l2(paths, client, 2)

    with pytest.raises(RuntimeError, match="L3 global clustering"):
        compile_mod.compile_global_l3(paths, client)

    assert _layer_status(paths, 1, "l3") == "error"
    assert _layer_status(paths, 2, "l3") == "error"
    # L4 must NOT be "error" — synthesis was the failure, and L4 was never completed.
    assert _layer_status(paths, 1, "l4") == "skipped"
    assert _layer_status(paths, 2, "l4") == "skipped"
