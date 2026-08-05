"""P7 — live pipeline integration (claim-grounded cutover).

Pins the live wiring that lands the Plan C graph-quality compiler into the
serving path (SYSTEM_BEHAVIOR §27.2/§27.5/§27.6/§27.8):

1. ``persist_graph_data`` writes ``graph_relation_supports`` rows keyed by the
   source's lineage, so a relation can reach the >=2-independent-lineage
   ``active`` floor.
2. Two INDEPENDENT sources asserting the same proposition corroborate the SAME
   relation to ``active``; a single source leaves it ``copied_source_only``.
3. ``compile_global_l3`` grounds community reports on the claim-grounded
   ``rebuild_graph_generation`` path (no broad-span fallback).
4. ``wiki lint`` gains a Graph Quality section that surfaces ``graph_audit``
   violations.
"""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

import pytest

from curator import config as cfg
from curator import db
from curator import lint as lint_mod
from curator.llm import ChatMessage
from curator.pipeline import compile as compile_mod

# Two textually-identical sources with DISTINCT content hashes: the fake LLM
# extracts the SAME proposition from each, so they corroborate one relation while
# contributing two INDEPENDENT source lineages (the content_hash is the lineage).
SOURCE_A = """\
# Residual Learning

Residual connections make very deep networks easier to optimize.

They address the degradation problem in deep networks.
"""

SOURCE_B = SOURCE_A


class GraphFakeClient:
    """Returns contract JSON citing real span ids, always asserting the SAME
    proposition (ResNet --addresses--> degradation problem) regardless of the
    source text — so two independent sources corroborate one relation."""

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
                            "statement": "Residual connections make deep networks easier to optimize.",
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


def _layer_status(paths, source_id: int, layer: str) -> str | None:
    with db.connect(paths.state_db) as conn:
        row = conn.execute(
            f"SELECT {layer}_status FROM sources WHERE id = ?", (source_id,)
        ).fetchone()
    return row[0] if row else None


def _seed_source(paths, relpath: str, text: str, content_hash: str, context_id: str) -> None:
    src = paths.root / relpath
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(text, encoding="utf-8")
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at, "
            "context_id, l1_status) VALUES (?, ?, ?, ?, datetime('now'), ?, 'done')",
            (relpath, content_hash, "md", len(text), context_id),
        )


@pytest.fixture()
def vault():
    with tempfile.TemporaryDirectory() as t:
        paths = cfg.WikiPaths(Path(t))
        db.init_db(paths.state_db)
        yield paths


def test_persist_writes_relation_support_with_source_lineage(vault) -> None:
    """A single source's compile writes one verified graph_relation_supports row
    keyed by the source's content lineage; one lineage => ACTIVE (v0.43.0).

    This is the end-to-end shape of the ordinary case: one paper is ingested and
    asserts a proposition. Before v0.43.0 that quarantined as
    `copied_source_only`, which meant a vault of distinct papers produced an
    almost entirely quarantined graph and no L3/L4 at all."""
    paths = vault
    _seed_source(paths, "04_Resources/a.md", SOURCE_A, "hash-a", "CTX-aaaa1111")
    compile_mod.compile_source_l2(paths, GraphFakeClient(), 1)

    with db.connect(paths.state_db) as conn:
        rel = conn.execute("SELECT id FROM graph_relations").fetchone()
        assert rel is not None, "the relation must persist"
        supports = conn.execute(
            "SELECT support_status, source_lineage_hash, knowledge_unit_id "
            "FROM graph_relation_supports WHERE relation_id = ?",
            (rel["id"],),
        ).fetchall()
    assert supports, "persist_graph_data must write a graph_relation_supports row"
    assert all(s["support_status"] == "verified" for s in supports)
    lineages = {s["source_lineage_hash"] for s in supports}
    assert len(lineages) == 1, "one source contributes exactly one independent lineage"

    status = db.compile_relation_lifecycle(paths.state_db, relation_id=rel["id"])
    assert status == "active", (
        "one ingested paper asserting a proposition is legitimate support and must "
        f"enter topology; got {status!r}"
    )
    with db.connect(paths.state_db) as conn:
        reason = conn.execute(
            "SELECT quarantine_reason FROM graph_relations WHERE id = ?", (rel["id"],)
        ).fetchone()[0]
    assert reason == "", f"an active relation carries no quarantine reason; got {reason!r}"


def test_two_independent_sources_corroborate_relation_active(vault) -> None:
    """Two INDEPENDENT sources (distinct content lineage) asserting the SAME
    proposition aggregate onto ONE relation (>=2 distinct lineages) -> active,
    and compile_global_l3 grounds a claim-grounded report on it (§27.2/§27.5)."""
    paths = vault
    client = GraphFakeClient()
    _seed_source(paths, "04_Resources/a.md", SOURCE_A, "hash-a", "CTX-aaaa1111")
    _seed_source(paths, "04_Resources/b.md", SOURCE_B, "hash-b", "CTX-bbbb2222")
    compile_mod.compile_source_l2(paths, client, 1)
    compile_mod.compile_source_l2(paths, client, 2)

    with db.connect(paths.state_db) as conn:
        rels = conn.execute("SELECT id FROM graph_relations").fetchall()
        assert len(rels) == 1, "the same proposition aggregates onto one relation"
        rel_id = rels[0]["id"]
        lineages = conn.execute(
            "SELECT COUNT(DISTINCT source_lineage_hash) FROM graph_relation_supports "
            "WHERE relation_id = ? AND support_status = 'verified'",
            (rel_id,),
        ).fetchone()[0]
    assert lineages == 2, "two independent sources => two independent lineages"

    concept_ids = compile_mod.compile_global_l3(paths, client)
    assert concept_ids, "a corroborated active relation must ground a community report"

    with db.connect(paths.state_db) as conn:
        status = conn.execute(
            "SELECT lifecycle_status FROM graph_relations WHERE id = ?", (rel_id,)
        ).fetchone()[0]
    assert status == "active", "≥2 independent lineages promotes the relation to active"

    reports = db.list_community_reports(paths.state_db)
    assert reports, "the claim-grounded path emits a report"
    assert rel_id in reports[0]["relation_ids"], "report cites the exact active relation"


def test_wiki_lint_surfaces_graph_quality_violation(vault) -> None:
    """`wiki lint` gains a Graph Quality section: an active relation lacking the
    >=2 verified independent lineages is surfaced as a graph-audit violation
    (§27.6)."""
    paths = vault
    # Two canonical entities + an active relation with NO supporting lineage:
    # a hand-forced inconsistency the read-only audit must catch.
    with db.connect(paths.state_db) as conn:
        src = db.upsert_graph_entity(paths.state_db, canonical_name="A",
                                     entity_type="method", conn=conn)
        tgt = db.upsert_graph_entity(paths.state_db, canonical_name="B",
                                     entity_type="method", conn=conn)
        rel = db.upsert_graph_relation(paths.state_db, source_entity_id=src,
                                       target_entity_id=tgt, relation_type="x",
                                       confidence=0.9, conn=conn)
        conn.execute(
            "UPDATE graph_relations SET lifecycle_status = 'active' WHERE id = ?",
            (rel,),
        )

    issues = lint_mod.graph_quality(paths)
    codes = {i.context.get("code") for i in issues}
    assert "active_relation_insufficient_support" in codes, (
        "lint Graph Quality must surface the graph_audit violation"
    )
    assert any(i.check == lint_mod.CheckId.GRAPH_QUALITY for i in issues)
