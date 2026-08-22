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
    # Plan C (§27.2): the claim-grounded L3 path grounds a community report only on
    # `active` relations. Since v0.43.0 one independent source lineage is enough, so
    # a second source is no longer REQUIRED to reach the floor — this fixture keeps
    # two (distinct content_hash => distinct lineage, asserting the SAME
    # proposition) to exercise support AGGREGATION onto one relation, which is what
    # this test is about.
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
    con_text = con_files[0].read_text(encoding="utf-8")
    assert "community_report_id" in con_text
    assert "## Relations" in con_text
    assert "[[02_Atoms/" in con_text
    syn_files = list(paths.synthesis.glob("SYN-*.md"))
    assert syn_files
    syn_text = syn_files[0].read_text(encoding="utf-8")
    assert "concept_ids:" in syn_text
    assert any(concept_id in syn_text for concept_id in concept_ids)

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
        conn.execute(
            "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at, "
            "context_id, l1_status, l2_status) VALUES (?, ?, ?, ?, datetime('now'), ?, 'done', 'done')",
            ("04_Resources/unrelated.md", "h3", "md", 1, "CTX-unrelated"),
        )

    compile_mod.compile_source_l2(paths, client, 1)
    compile_mod.compile_source_l2(paths, client, 2)
    compile_mod.compile_global_l3(paths, client)

    assert db.list_synthesis_nodes(paths.state_db)
    assert _layer_status(paths, 1, "l4") == "done"
    assert _layer_status(paths, 2, "l4") == "done"
    assert _layer_status(paths, 3, "l4") == "skipped"


def test_compile_global_l3_builds_l3_from_a_single_source(vault) -> None:
    """v0.43.0: ONE ingested source is enough to produce L3/L4.

    This test previously asserted the opposite — that a single source yields no
    concepts, no reports, no synthesis, and `skipped` layers — because the ≥2
    corroboration threshold quarantined every single-lineage relation. That is
    the defect, not the contract: a personal vault is mostly single-source
    papers, so it produced an empty graph (measured: 717 of 722 relations
    quarantined on a real 37-source vault). The threshold is now ≥1.
    """
    paths = vault
    client = DynamicFakeClient()

    compile_mod.compile_source_l2(paths, client, 1)
    concept_ids = compile_mod.compile_global_l3(paths, client)

    assert concept_ids, "a single source's verified relations must form a community"
    assert db.list_community_reports(paths.state_db), "the community must produce a report"
    assert _layer_status(paths, 1, "l3") == "done", (
        "a source grounding a live community report reaches l3=done"
    )


def test_l3_regeneration_from_existing_atoms_reaches_terminal_done(vault) -> None:
    """Re-running L3 over already-extracted atoms must reach terminal `done`.

    Like its sibling above, this previously pinned the empty-graph outcome that
    the ≥2 corroboration threshold produced. With the threshold at ≥1 the single
    source's relations are active, so the rerun path yields synthesis and both
    layers reach a terminal `done` rather than `skipped`. The point of the test —
    that the rerun path assigns TERMINAL statuses rather than leaving layers
    `pending` — is unchanged.
    """
    paths = vault
    client = DynamicFakeClient()

    compile_mod.compile_source_l2(paths, client, 1)
    ingest_llm.run_l3_from_existing_atoms(paths, client, lambda: ingest_llm.IngestCallbacks)

    assert db.list_synthesis_nodes(paths.state_db), "L4 synthesis must be produced"
    assert _layer_status(paths, 1, "l3") == "done"
    assert _layer_status(paths, 1, "l4") == "done"


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


def test_synthesis_failure_marks_l4_error_and_leaves_l3_done(vault) -> None:
    """A synthesis failure is an L4 failure. It is not an L3 failure and it is not a skip.

    Inverted from `test_compile_global_l3_failure_sets_l4_skipped_not_error`,
    which asserted the two lies this batch removes:

    * `l3 == "error"` — clustering demonstrably succeeded here; only synthesis
      threw. Marking L3 failed made a working layer look broken.
    * `l4 == "skipped"` — §4.1 reserves `skipped` for "this source contributed
      nothing to the layer", a non-failing outcome. Reporting an attempted-and-
      thrown synthesis as `skipped` is what let a broken L4 read as a no-op, and
      it is the state the user found on 10 real sources with no recorded reason.

    The old test's defence was that a per-source `l4='error'` is odd because L4
    is global. But a status the user cannot distinguish from success is worse
    than one that is coarse, and the composed `layer_error` names the layer.
    """
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

    # L3 clustering succeeded; only synthesis threw.
    assert _layer_status(paths, 1, "l3") == "done"
    assert _layer_status(paths, 2, "l3") == "done"
    # L4 was attempted and failed, so it is `error` (Q1), not `skipped`.
    assert _layer_status(paths, 1, "l4") == "error"
    assert _layer_status(paths, 2, "l4") == "error"

    # The surviving message names the failing layer and carries the real cause,
    # instead of the old "L3 prerequisite failed; synthesis not attempted" — a
    # claim that was false precisely when synthesis had been attempted.
    with db.connect(paths.state_db) as conn:
        errors = [
            row["layer_error"]
            for row in conn.execute(
                "SELECT layer_error FROM sources WHERE id IN (1, 2)"
            ).fetchall()
        ]
    assert all(e and e.startswith("l4: ") for e in errors), errors
    assert all("synthetic synthesis failure" in e for e in errors), errors
    assert not any("not attempted" in e for e in errors), errors


def test_l3_failure_message_survives_the_l4_status_write(vault) -> None:
    """CP-3b: the L4 write used to clobber the real L3 error message.

    `layer_error` is one column shared by all four layers, and the loop wrote it
    twice per source — first with the L3 cause, then with a fixed L4 string.
    The second write won, so the actual reason L3 failed was destroyed on the
    same line that recorded it.
    """
    paths = vault

    class ReportFailClient(DynamicFakeClient):
        def chat(self, messages, *, json_mode=False, temperature=0.3) -> str:
            text = "\n".join(m.content for m in messages)
            if "community" in text.lower():
                raise RuntimeError("synthetic community report failure")
            return super().chat(messages, json_mode=json_mode, temperature=temperature)

    client = ReportFailClient()
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

    with db.connect(paths.state_db) as conn:
        error = conn.execute(
            "SELECT layer_error FROM sources WHERE id = 1"
        ).fetchone()["layer_error"]

    assert error, "the L3 cause must not be erased by the L4 status write"
    assert "synthetic community report failure" in error
    assert error.startswith("l3: "), error
    # When L3 is the failure, L4 legitimately was not attempted — and now only
    # then does the message say so.
    assert "l4: L3 prerequisite failed; synthesis not attempted" in error


# --- v0.62.0: a failed staged compile must not throw the extraction away ------


def test_a_failed_staged_compile_keeps_the_extraction_for_a_resume(
    vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The case resumable L2 exists for, and the one its first version missed.

    Measured live before this test existed: a 673-page source completed all 277
    extraction batches — 81.5 minutes, every prompt run `ok` — the staged compile
    hit a 429, and the failure handler deleted every row the extraction had just
    written. Per-batch persistence had moved the work out of memory and into rows
    that the next handler removed. The unit tests all passed, because they call
    `extract_knowledge_units` directly and never reach this handler.
    """
    paths = vault

    def refuse(*_a, **_k):
        raise RuntimeError("Antigravity capacity exhausted (429).")

    real_extract_graph_data = compile_mod.graph_index.extract_graph_data
    monkeypatch.setattr(compile_mod.graph_index, "extract_graph_data", refuse)
    failed = compile_mod.compile_source_l2(paths, DynamicFakeClient(), 1)
    assert not failed.ok
    assert "429" in (failed.error or "")

    with db.connect(paths.state_db) as conn:
        kept, published = conn.execute(
            "SELECT COUNT(*), COUNT(generation_id) FROM knowledge_units WHERE source_id = 1"
        ).fetchone()
        generations = conn.execute(
            "SELECT status FROM compiler_generations WHERE source_id = 1"
        ).fetchall()
    assert kept > 0, "the extraction was deleted; a resume has nothing to adopt"
    assert published == 0, "a failed compile left units attributed to a generation"
    assert [r[0] for r in generations] == ["discarded"]

    # Supports must survive with their units — a support whose unit is gone is
    # `dangling_supports`, which is publish-blocking.
    with db.connect(paths.state_db) as conn:
        orphans = conn.execute(
            "SELECT COUNT(*) FROM claim_supports cs "
            "LEFT JOIN knowledge_units ku ON ku.id = cs.knowledge_unit_id "
            "WHERE ku.id IS NULL"
        ).fetchone()[0]
    assert orphans == 0

    # The retry adopts the kept extraction instead of re-paying for it.
    class CountingClient(DynamicFakeClient):
        def __init__(self) -> None:
            self.extract_calls = 0

        def chat(self, messages, *, json_mode=False, temperature=0.3) -> str:
            text = "\n".join(m.content for m in messages)
            if "Extract the knowledge units" in text:
                self.extract_calls += 1
            return super().chat(messages, json_mode=json_mode, temperature=temperature)

    # Restore just this patch. `monkeypatch.undo()` would also revert conftest's
    # autouse config isolation, which repoints path resolution mid-test.
    monkeypatch.setattr(
        compile_mod.graph_index, "extract_graph_data", real_extract_graph_data
    )
    retry = CountingClient()
    ok = compile_mod.compile_source_l2(paths, retry, 1)
    assert ok.ok, ok.error
    assert retry.extract_calls == 0, (
        f"the resumed compile made {retry.extract_calls} extraction call(s); "
        "the kept batches should have been adopted"
    )
    with db.connect(paths.state_db) as conn:
        served = conn.execute(
            "SELECT COUNT(*) FROM knowledge_units ku "
            "JOIN compiler_generations g ON g.id = ku.generation_id "
            "WHERE ku.source_id = 1 AND g.status = 'authoritative' "
            "AND ku.retired_at IS NULL"
        ).fetchone()[0]
    assert served > 0, "the resumed compile published nothing"


def test_a_generation_left_staged_by_a_killed_run_is_released(vault) -> None:
    """A hard kill never reaches the `except` handler that releases the units.

    Measured after SIGKILLing a live compile mid-graph: GEN-a3863b97 stayed
    `staged` holding all 5,358 extracted units, and `_adoptable_unit_ids` saw
    ZERO — so the next run would have re-paid 85 minutes of extraction that was
    sitting right there. Two compiles for one source never run concurrently, so a
    pre-existing staged generation is by definition abandoned.
    """
    paths = vault
    assert compile_mod.compile_source_l2(paths, DynamicFakeClient(), 1).ok

    # Simulate the kill: a fresh staged generation owning this source's units.
    orphan = db.create_compiler_generation(
        paths.state_db, prompt_contract_version="v3", source_id=1
    )
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "UPDATE knowledge_units SET generation_id = ? WHERE source_id = 1", (orphan,)
        )
        stranded = conn.execute(
            "SELECT COUNT(*) FROM knowledge_units "
            "WHERE source_id = 1 AND generation_id IS NULL AND retired_at IS NULL"
        ).fetchone()[0]
    assert stranded == 0, "the fixture did not actually strand the units"

    released = compile_mod._release_orphaned_staged_generations(paths.state_db, 1)
    assert released > 0
    with db.connect(paths.state_db) as conn:
        adoptable = conn.execute(
            "SELECT COUNT(*) FROM knowledge_units "
            "WHERE source_id = 1 AND generation_id IS NULL AND retired_at IS NULL"
        ).fetchone()[0]
        status = conn.execute(
            "SELECT status FROM compiler_generations WHERE id = ?", (orphan,)
        ).fetchone()[0]
    assert adoptable == released, "released units are not adoptable again"
    assert status == "discarded", "the orphaned generation is still staged"


def test_publish_clears_the_staged_graph_batches(vault) -> None:
    """They exist to survive a failure, not to outlive the publish they fed."""
    paths = vault
    result = compile_mod.compile_source_l2(paths, DynamicFakeClient(), 1)
    assert result.ok, result.error
    with db.connect(paths.state_db) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM graph_batch_results WHERE source_id = 1"
        ).fetchone()[0] == 0


def test_a_failed_publish_keeps_the_staged_graph_batches(vault, monkeypatch) -> None:
    """D2's second half, and the reason v0.62.0 shipped worthless.

    That release moved L2 extraction out of memory and into rows — and the
    compile's failure handler deleted exactly those rows. All 19 unit tests
    passed because none of them reached the handler; only a live run found it.
    Graph staging has the identical exposure, so the test has to drive the real
    compile and fail it AFTER extraction, not assert that a row was written.
    """
    paths = vault

    def explode(*_a, **_k):
        raise RuntimeError("Antigravity capacity exhausted (429).")

    # Fail at the publish gate: graph extraction has already run and staged.
    monkeypatch.setattr(compile_mod, "_run_publish_gate", explode)
    failed = compile_mod.compile_source_l2(paths, DynamicFakeClient(), 1)
    assert not failed.ok

    with db.connect(paths.state_db) as conn:
        staged = conn.execute(
            "SELECT COUNT(*) FROM graph_batch_results WHERE source_id = 1"
        ).fetchone()[0]
    assert staged > 0, "the failure handler destroyed the extraction it should preserve"
